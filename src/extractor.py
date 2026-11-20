import json
import re
import torch
import yaml

from transformers import AutoTokenizer, AutoModelForCausalLM
from pathlib import Path
from pypdf import PdfReader


MODEL_NAME = "google/gemma-3-1b-it"
MAX_NEW_TOKENS = 2048
PAGES_PER_CHUNK = 2
MAX_RETRIES = 2

PROMPT_TYPES = [
	"zero-shot",
	"few-shot",
	"chain-of-thought"
]


def validate_documents(doc1, doc2):
	documents = [doc1, doc2]

	for document in documents:
		path = Path(document)

		if not path.exists():
			raise FileNotFoundError(f"File does not exist: {document}")

		if not path.is_file():
			raise ValueError(f"Not a file: {document}")

		if path.suffix.lower() != ".pdf":
			raise ValueError(f"File is not a PDF: {document}")

		try:
			reader = PdfReader(str(path))

			if len(reader.pages) == 0:
				raise ValueError(f"PDF contains no pages: {document}")

		except ValueError:
			raise

		except Exception as e:
			raise ValueError(f"Invalid PDF: {document}") from e

	return True


def extract_pdf_text(pdf_path):
	reader = PdfReader(str(pdf_path))
	text = []

	for page in reader.pages:
		page_text = page.extract_text()

		if page_text:
			text.append(page_text)

	return "\n".join(text)


def _prompt_rules():
	return """
IMPORTANT RULES:
- Extract only actual key data elements and their associated requirements.
- A key data element should be a specific security control or configuration item.
- Do not treat document headings, table headings, references, or section labels as key data elements.
- Do not extract unrelated CIS Controls information as Docker benchmark elements.
- Do not use "References", "Additional Information", "Controls", or similar labels as element names.
- Exclude URLs, bibliography entries, and repeated reference information from requirements.
- Exclude introductory text and unrelated explanatory material.
- Associate each requirement with the correct element.
- Do not associate an unrelated requirement with an element.
- Do not repeat the same element or requirement.
- Preserve the original wording and numbering of actual requirements.
- Do not invent missing information.
- Every element must have a meaningful name and at least one relevant requirement.
- Escape quotation marks inside JSON text values using \\"
- Do not include Markdown code fences or comments.
- Return syntactically valid JSON that can be parsed by Python's json.loads().
- Return the complete JSON object with all brackets and quotation marks closed.
- Do not add explanations before or after the JSON.
"""


def create_zero_shot_prompt(document_text):
	return f"""
Extract the key data elements and their requirements from the following document.

For each element, provide its name and all requirements associated with it.
One element may have multiple requirements.

{_prompt_rules()}

Return only valid JSON in this format:
{{
	"elements": [
		{{
			"name": "Element name",
			"requirements": [
				"Requirement 1",
				"Requirement 2"
			]
		}}
	]
}}

Document:
{document_text}
"""


def create_few_shot_prompt(document_text):
	return f"""
Extract the key data elements and their requirements from the following document.

Example:
1.1.1 Ensure a separate partition for containers exists.
1.1.2 Ensure the Docker daemon data directory is on a separate partition.

Example output:
{{
	"elements": [
		{{
			"name": "Ensure a separate partition for containers exists",
			"requirements": [
				"1.1.1 Ensure a separate partition for containers exists"
			]
		}},
		{{
			"name": "Ensure the Docker daemon data directory is on a separate partition",
			"requirements": [
				"1.1.2 Ensure the Docker daemon data directory is on a separate partition"
			]
		}}
	]
}}

Follow the example structure. An element can have multiple requirements.

{_prompt_rules()}

Return only valid JSON.

Document:
{document_text}
"""


def create_chain_of_thought_prompt(document_text):
	return f"""
Carefully analyze the document to identify its key data elements
and the requirements associated with each element.

Determine which text describes an actual security control or
configuration item and which text describes its requirements.
Group multiple requirements under the same element when appropriate.

Do not include references, unrelated CIS Controls, document headings,
or general explanatory sections as key data elements.

{_prompt_rules()}

Return only the final result as valid JSON in this format:
{{
	"elements": [
		{{
			"name": "Element name",
			"requirements": [
				"Requirement 1",
				"Requirement 2"
			]
		}}
	]
}}

Document:
{document_text}
"""


def _load_model():
	print("Loading Gemma 3 1B. This may take several minutes.")

	tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

	model = AutoModelForCausalLM.from_pretrained(
		MODEL_NAME,
		torch_dtype = torch.float16,
		low_cpu_mem_usage = True,
		device_map = "auto"
	)

	model.eval()

	print("Gemma 3 1B loaded successfully.")
	print(f"Model device: {model.device}")

	return model, tokenizer


def _extract_pdf_chunks(pdf_path, pages_per_chunk = PAGES_PER_CHUNK):
	reader = PdfReader(str(pdf_path))
	chunks = []

	for start in range(0, len(reader.pages), pages_per_chunk):
		page_text = []

		for page in reader.pages[start:start + pages_per_chunk]:
			text = page.extract_text()

			if text:
				page_text.append(text)

		if page_text:
			chunks.append("\n\n--- PAGE BREAK ---\n\n".join(page_text))

	return chunks


def repair_json_strings(json_text):
	result = []
	inside_string = False
	escaped = False

	for i, char in enumerate(json_text):
		if inside_string:
			if escaped:
				result.append(char)
				escaped = False

			elif char == "\\":
				result.append(char)
				escaped = True

			elif char == '"':
				remaining = json_text[i + 1:].lstrip()

				if remaining.startswith((",", "}", "]", ":")) or not remaining:
					result.append(char)
					inside_string = False
				else:
					result.append('\\"')

			elif char == "\n":
				result.append("\\n")

			elif char == "\r":
				result.append("\\r")

			elif char == "\t":
				result.append("\\t")

			elif ord(char) < 32:
				result.append(" ")

			else:
				result.append(char)

		else:
			result.append(char)

			if char == '"':
				inside_string = True

	return "".join(result)


def save_checkpoint(
	checkpoint_file,
	completed_chunks,
	all_elements,
	prompts_used,
	outputs
):
	checkpoint_file = Path(checkpoint_file)
	checkpoint_file.parent.mkdir(parents = True, exist_ok = True)

	checkpoint_data = {
		"completed_chunks": completed_chunks,
		"elements": list(all_elements.values()),
		"prompts_used": prompts_used,
		"outputs": outputs
	}

	temporary_file = checkpoint_file.with_suffix(".tmp")

	with open(temporary_file, "w", encoding = "utf-8") as file:
		json.dump(
			checkpoint_data,
			file,
			ensure_ascii = False,
			indent = 2
		)

	temporary_file.replace(checkpoint_file)


def _generate_json(prompt, model, tokenizer, chunk_index):
	for attempt in range(MAX_RETRIES + 1):
		current_prompt = prompt

		if attempt > 0:
			print(f"Retrying chunk {chunk_index}, attempt {attempt + 1}")

			current_prompt += """
Your previous response was not valid JSON.

Return a new response from the beginning.
Return ONLY a valid JSON object.
Do not include Markdown, explanations, references, or text outside the JSON.
Make sure every string has a closing quotation mark.
Make sure every object and array has its closing bracket.
Use this exact structure:
{
	"elements": [
		{
			"name": "Element name",
			"requirements": ["Requirement 1"]
		}
	]
}
"""

		messages = [
			{
				"role": "user",
				"content": current_prompt
			}
		]

		inputs = tokenizer.apply_chat_template(
			messages,
			tokenize = True,
			add_generation_prompt = True,
			return_tensors = "pt",
			return_dict = True
		)

		try:
			input_device = model.get_input_embeddings().weight.device
		except (AttributeError, StopIteration):
			try:
				input_device = model.device
			except AttributeError:
				input_device = "cpu"

		inputs = {
			key: value.to(input_device)
			for key, value in inputs.items()
		}

		with torch.inference_mode():
			generated = model.generate(
				**inputs,
				max_new_tokens = MAX_NEW_TOKENS,
				do_sample = False,
				pad_token_id = getattr(tokenizer, "eos_token_id", None)
			)

		input_length = inputs["input_ids"].shape[1]

		output = tokenizer.decode(
			generated[0][input_length:],
			skip_special_tokens = True
		)

		output = re.sub(
			r"```(?:json)?",
			"",
			output
		).replace("```", "").strip()

		start = output.find("{")
		end = output.rfind("}")

		if start == -1 or end == -1:
			print(f"Attempt {attempt + 1}: No complete JSON object found.")
			continue

		json_output = output[start:end + 1]

		json_output = re.sub(
			r'\\(?!["\\/bfnrtu])',
			r'\\\\',
			json_output
		)

		json_output = repair_json_strings(json_output)

		try:
			json_start = json_output.find("{")

			if json_start == -1:
				raise ValueError("No JSON object found in model output.")

			data, _ = json.JSONDecoder().raw_decode(json_output[json_start:])

			if not isinstance(data, dict):
				raise ValueError("JSON output is not an object.")

			if "elements" not in data or not isinstance(data["elements"], list):
				raise ValueError("JSON output does not contain an elements list.")

			valid_elements = []

			for element in data["elements"]:
				if not isinstance(element, dict):
					continue

				if "name" not in element or "requirements" not in element:
					continue

				if not isinstance(element["requirements"], list):
					continue

				name = str(element["name"]).strip()

				if not name:
					continue

				requirements = [
					str(requirement).strip()
					for requirement in element["requirements"]
					if str(requirement).strip()
				]

				if requirements:
					valid_elements.append({
						"name": name,
						"requirements": requirements
					})

			data["elements"] = valid_elements

			return data, output

		except (json.JSONDecodeError, ValueError) as e:
			print(f"Attempt {attempt + 1}: Invalid JSON: {e}")

			if attempt == MAX_RETRIES:
				print("Final invalid model output:")
				print(output)

				raise ValueError(
					f"The model returned invalid JSON for chunk "
					f"{chunk_index} after {MAX_RETRIES + 1} attempts."
				) from e

	raise ValueError(
		f"The model could not generate valid JSON for chunk {chunk_index}."
	)


def _create_prompt(document_text, prompt_type):
	if prompt_type == "zero-shot":
		return create_zero_shot_prompt(document_text)

	elif prompt_type == "few-shot":
		return create_few_shot_prompt(document_text)

	return create_chain_of_thought_prompt(document_text)


def _split_chunk_text(document_text):
	page_marker = "\n\n--- PAGE BREAK ---\n\n"

	# First, try splitting at the original PDF page boundary.
	pages = document_text.split(page_marker)

	if len(pages) > 1:
		middle = len(pages) // 2

		return (
			"\n\n--- PAGE BREAK ---\n\n".join(pages[:middle]),
			"\n\n--- PAGE BREAK ---\n\n".join(pages[middle:])
		)

	# If there is only one page, try splitting at paragraph boundaries.
	paragraphs = re.split(r"\n\s*\n", document_text)

	if len(paragraphs) > 1:
		middle = len(paragraphs) // 2

		return (
			"\n\n".join(paragraphs[:middle]),
			"\n\n".join(paragraphs[middle:])
		)

	# If there are no paragraph boundaries, split at line boundaries.
	lines = document_text.splitlines()

	if len(lines) > 1:
		middle = len(lines) // 2

		return (
			"\n".join(lines[:middle]),
			"\n".join(lines[middle:])
		)

	# Last resort: split the text approximately in half.
	middle = len(document_text) // 2

	if middle == 0:
		raise ValueError("Cannot split the failed document chunk.")

	return document_text[:middle], document_text[middle:]


def _generate_json_with_fallback(
	document_text,
	prompt_type,
	model,
	tokenizer,
	chunk_index,
	depth = 0
):
	prompt = _create_prompt(document_text, prompt_type)

	try:
		data, output = _generate_json(
			prompt,
			model,
			tokenizer,
			chunk_index
		)

		return data, prompt, output

	except ValueError as e:
		if depth >= 4 or len(document_text) <= 1000:
			raise ValueError(
				f"Extraction failed for chunk {chunk_index} "
				f"even after splitting the document."
			) from e

		print(
			f"Chunk {chunk_index} failed. "
			f"Splitting into smaller pieces (level {depth + 1})."
		)

		first_half, second_half = _split_chunk_text(document_text)

		first_data, first_prompt, first_output = (
			_generate_json_with_fallback(
				first_half,
				prompt_type,
				model,
				tokenizer,
				f"{chunk_index}a",
				depth + 1
			)
		)

		second_data, second_prompt, second_output = (
			_generate_json_with_fallback(
				second_half,
				prompt_type,
				model,
				tokenizer,
				f"{chunk_index}b",
				depth + 1
			)
		)

		combined_elements = (
			first_data["elements"] + second_data["elements"]
		)

		return (
			{"elements": combined_elements},
			first_prompt + "\n\n" + second_prompt,
			first_output + "\n\n" + second_output
		)


def extract_kdes(
	pdf_path,
	prompt_type,
	model = None,
	tokenizer = None,
	checkpoint_file = None
):
	if prompt_type not in PROMPT_TYPES:
		raise ValueError(f"Invalid prompt type: {prompt_type}")

	if model is None or tokenizer is None:
		model, tokenizer = _load_model()

	chunks = _extract_pdf_chunks(pdf_path)

	if not chunks:
		raise ValueError(f"No readable text found in PDF: {pdf_path}")

	all_elements = {}
	prompts_used = []
	outputs = []
	completed_chunks = 0

	if checkpoint_file and Path(checkpoint_file).exists():
		with open(checkpoint_file, "r", encoding = "utf-8") as file:
			checkpoint_data = json.load(file)

		completed_chunks = checkpoint_data["completed_chunks"]

		if completed_chunks > len(chunks):
			raise ValueError(
				"The checkpoint has more completed chunks than the PDF. "
				"Check whether the PDF or chunk size was changed."
			)

		for element in checkpoint_data["elements"]:
			all_elements[element["name"].casefold()] = element

		prompts_used = checkpoint_data["prompts_used"]
		outputs = checkpoint_data["outputs"]

		print(
			f"Resuming {prompt_type} from chunk "
			f"{completed_chunks + 1} of {len(chunks)}"
		)

	for chunk_index in range(completed_chunks, len(chunks)):
		document_text = chunks[chunk_index]

		print(
			f"Processing {prompt_type}: "
			f"chunk {chunk_index + 1} of {len(chunks)}"
		)

		data, prompt, output = _generate_json_with_fallback(
			document_text,
			prompt_type,
			model,
			tokenizer,
			chunk_index + 1
		)

		for element in data["elements"]:
			name = element["name"].strip()
			key = name.casefold()

			if key not in all_elements:
				all_elements[key] = {
					"name": name,
					"requirements": []
				}

			for requirement in element["requirements"]:
				if requirement not in all_elements[key]["requirements"]:
					all_elements[key]["requirements"].append(requirement)

		prompts_used.append(prompt)
		outputs.append(output)

		completed_chunks = chunk_index + 1

		if checkpoint_file:
			save_checkpoint(
				checkpoint_file,
				completed_chunks,
				all_elements,
				prompts_used,
				outputs
			)

		print(
			f"Completed and saved chunk "
			f"{completed_chunks} of {len(chunks)}"
		)

	result = {
		"elements": list(all_elements.values())
	}

	return (
		result,
		"\n\n".join(prompts_used),
		"\n\n".join(outputs)
	)


def _write_llm_log(output_path, documents):
	log_path = output_path / "llm_outputs.txt"

	with open(log_path, "w", encoding = "utf-8") as log_file:
		for document_index, document in enumerate(documents, start = 1):
			document_path = Path(document)

			for prompt_type in PROMPT_TYPES:
				checkpoint_file = (
					output_path
					/ "checkpoints"
					/ f"{document_path.stem}_{document_index}_{prompt_type}.json"
				)

				if checkpoint_file.exists():
					with open(
						checkpoint_file,
						"r",
						encoding = "utf-8"
					) as checkpoint:
						checkpoint_data = json.load(checkpoint)

					prompts = checkpoint_data["prompts_used"]
					outputs = checkpoint_data["outputs"]

				else:
					continue

				if not prompts or not outputs:
					continue

				log_file.write(f"LLM Name: {MODEL_NAME}\n")
				log_file.write(f"Prompt Type: {prompt_type}\n")
				log_file.write("Prompt Used:\n")
				log_file.write("\n\n".join(prompts))
				log_file.write("\n")
				log_file.write("LLM Output:\n")
				log_file.write("\n\n".join(outputs))
				log_file.write("\n")
				log_file.write("\n" + "=" * 60 + "\n\n")


def save_extraction_outputs(doc1, doc2, output_dir = "outputs"):
	validate_documents(doc1, doc2)

	output_path = Path(output_dir)
	output_path.mkdir(parents = True, exist_ok = True)

	checkpoint_path = output_path / "checkpoints"
	checkpoint_path.mkdir(parents = True, exist_ok = True)

	model, tokenizer = _load_model()

	documents = [doc1, doc2]

	for document_index, document in enumerate(documents, start = 1):
		document_path = Path(document)
		all_elements = {}

		for prompt_type in PROMPT_TYPES:
			checkpoint_file = (
				checkpoint_path
				/ f"{document_path.stem}_{document_index}_{prompt_type}.json"
			)

			data, prompt, output = extract_kdes(
				document,
				prompt_type,
				model,
				tokenizer,
				checkpoint_file
			)

			for element in data["elements"]:
				name = element["name"]
				key = name.casefold()

				if key not in all_elements:
					all_elements[key] = {
						"name": name,
						"requirements": []
					}

				for requirement in element["requirements"]:
					if requirement not in all_elements[key]["requirements"]:
						all_elements[key]["requirements"].append(requirement)

			_write_llm_log(output_path, documents)

		yaml_path = (
			output_path
			/ f"{document_path.stem}_kdes_{document_index}.yaml"
		)

		with open(yaml_path, "w", encoding = "utf-8") as yaml_file:
			yaml.safe_dump(
				{
					f"element{i + 1}": element
					for i, element in enumerate(all_elements.values())
				},
				yaml_file,
				sort_keys = False,
				allow_unicode = True
			)

		print(f"Saved YAML file: {yaml_path}")

	_write_llm_log(output_path, documents)

	return True
