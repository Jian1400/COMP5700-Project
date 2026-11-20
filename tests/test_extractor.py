import json
import torch
import yaml
import src.extractor as extractor

from pypdf import PdfWriter
from src.extractor import (validate_documents, extract_pdf_text, create_zero_shot_prompt, create_few_shot_prompt, create_chain_of_thought_prompt, extract_kdes, save_extraction_outputs)


def test_validate_documents(tmp_path):
	doc1 = tmp_path / "docker-cis-v0.pdf"
	doc2 = tmp_path / "docker-cis-v1.pdf"

	for document in [doc1, doc2]:
		writer = PdfWriter()
		writer.add_blank_page(width = 72, height = 72)

		with open(document, "wb") as file:
			writer.write(file)
	assert validate_documents(doc1, doc2) is True



def test_extract_pdf_text(tmp_path):
	document = tmp_path / "test.pdf"

	writer = PdfWriter()
	writer.add_blank_page(width = 72, height = 72)

	with open(document, "wb") as file:
		writer.write(file)

	assert extract_pdf_text(document) == ""


def test_create_zero_shot_prompt():
	prompt = create_zero_shot_prompt("Example document text")

	assert "Example document text" in prompt
	assert "requirements" in prompt
	assert "JSON" in prompt


def test_create_few_shot_prompt():
	prompt = create_few_shot_prompt("Example document text")

	assert "Example document text" in prompt
	assert "Example:" in prompt
	assert "requirements" in prompt


def test_create_chain_of_thought_prompt():
	prompt = create_chain_of_thought_prompt("Example document text")

	assert "Example document text" in prompt
	assert "Carefully analyze" in prompt
	assert "JSON" in prompt


def test_extract_kdes(monkeypatch, tmp_path):
	document = tmp_path / "test.pdf"
	document.write_bytes(b"fake PDF")

	monkeypatch.setattr(extractor, "_extract_pdf_chunks", lambda pdf_path: ["Example security requirement"])

	class FakeTokenizer:
		def apply_chat_template(self, messages, **kwargs):
			return {"input_ids": torch.tensor([[1, 2]])}

		def decode(self, tokens, skip_special_tokens = True):
			return json.dumps({
				"elements": [
					{
						"name": "Example element",
						"requirements": ["Example requirement"]
					}
				]
			})

	class FakeModel:
		def parameters(self):
			return iter([torch.nn.Parameter(torch.zeros(1))])

		def generate(self, **kwargs):
			return torch.tensor([[1, 2, 3]])

	data, prompt, output = extract_kdes(document, "zero-shot", FakeModel(), FakeTokenizer())

	assert data["elements"][0]["name"] == "Example element"
	assert data["elements"][0]["requirements"] == ["Example requirement"]
	assert "Example security requirement" in prompt
	assert "Example element" in output


def test_save_extraction_outputs(monkeypatch, tmp_path):
	doc1 = tmp_path / "docker-cis-v0.pdf"
	doc2 = tmp_path / "docker-cis-v1.pdf"
	doc1.write_bytes(b"fake PDF")
	doc2.write_bytes(b"fake PDF")

	monkeypatch.setattr(extractor, "validate_documents", lambda doc1, doc2: True)
	monkeypatch.setattr(extractor, "_load_model", lambda: (object(), object()))

	
	def fake_extract_kdes(document, prompt_type, model, tokenizer, checkpoint_file=None):
		data = {
			"elements": [
				{
					"name": "Example element",
					"requirements": ["Example requirement"]
				}
			]
		}

		prompt = f"Example {prompt_type} prompt"
		output = '{"elements": []}'

		if checkpoint_file:
			extractor.save_checkpoint(
				checkpoint_file,
				1,
				{
					"example element": {
						"name": "Example element",
						"requirements": ["Example requirement"]
					}
				},
				[prompt],
				[output]
			)

		return data, prompt, output

	monkeypatch.setattr(extractor, "extract_kdes", fake_extract_kdes)

	output_dir = tmp_path / "outputs"

	result = save_extraction_outputs(doc1, doc2, output_dir)

	assert result is True
	assert (output_dir / "docker-cis-v0_kdes_1.yaml").exists()
	assert (output_dir / "docker-cis-v1_kdes_2.yaml").exists()
	assert (output_dir / "llm_outputs.txt").exists()

	with open(output_dir / "docker-cis-v0_kdes_1.yaml", "r", encoding = "utf-8") as file:
		data = yaml.safe_load(file)

	assert data["element1"]["name"] == "Example element"

	with open(output_dir / "llm_outputs.txt", "r", encoding = "utf-8") as file:
		log = file.read()

	assert "LLM Name:" in log
	assert "Prompt Used:" in log
	assert "Prompt Type:" in log
	assert "LLM Output:" in log
	assert "zero-shot" in log
	assert "few-shot" in log
	assert "chain-of-thought" in log