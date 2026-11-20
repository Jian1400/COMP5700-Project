from pathlib import Path
import shutil
import yaml

from src.extractor import (
	validate_documents,
	PROMPT_TYPES,
	_load_model,
	extract_kdes,
	_write_llm_log
)

from src.comparator import (
	compare_element_names,
	compare_element_requirements
)

from src.executor import (
	read_comparison_reports,
	determine_hadolint_rules,
	execute_hadolint,
	save_scan_results
)


PDF_COMBINATIONS = {
	"1": ("docker-cis-v0.pdf", "docker-cis-v1.pdf"),
	"2": ("docker-cis-v0.pdf", "docker-cis-v2.pdf"),
	"3": ("docker-cis-v1.pdf", "docker-cis-v2.pdf"),
	"4": ("docker-cis-v1.pdf", "docker-cis-v1.pdf"),
	"5": ("docker-cis-v2.pdf", "docker-cis-v2.pdf")
}


def display_menu():
	print("\n========================================")
	print("       Docker CIS Security Analyzer")
	print("========================================")
	print("\nSelect the two PDF documents to compare:\n")

	for choice, documents in PDF_COMBINATIONS.items():
		print(f"{choice}. {documents[0]} and {documents[1]}")

	print("\nEnter your choice (1-5): ", end="")


def get_pdf_selection():
	while True:
		display_menu()
		choice = input().strip()

		if choice in PDF_COMBINATIONS:
			return PDF_COMBINATIONS[choice]

		print("\nInvalid selection. Please enter a number from 1 to 5.")


def load_cached_yaml(yaml_file):
	yaml_file = Path(yaml_file)

	if not yaml_file.is_file():
		return False

	try:
		with open(yaml_file, "r", encoding = "utf-8") as file:
			data = yaml.safe_load(file) or {}

		if "elements" in data and isinstance(data["elements"], list):
			elements = data["elements"]
		else:
			elements = list(data.values())

		for element in elements:
			if not isinstance(element, dict):
				return False

			if "name" not in element or "requirements" not in element:
				return False

			if not isinstance(element["requirements"], list):
				return False

		return True

	except (OSError, yaml.YAMLError, AttributeError, TypeError):
		return False


def find_existing_yaml(pdf_path, output_path):
	pdf_path = Path(pdf_path)

	cached_yaml = output_path / f"{pdf_path.stem}_kdes.yaml"

	if load_cached_yaml(cached_yaml):
		print(f"Using existing YAML file: {cached_yaml}")
		return cached_yaml

	legacy_files = {
		"docker-cis-v0": "docker-cis-v0_kdes_1.yaml",
		"docker-cis-v1": "docker-cis-v1_kdes_2.yaml"
	}

	legacy_name = legacy_files.get(pdf_path.stem)

	if legacy_name:
		legacy_yaml = Path("outputs/test_v0_v1") / legacy_name

		if load_cached_yaml(legacy_yaml):
			shutil.copy2(legacy_yaml, cached_yaml)
			print(f"Reusing existing YAML file: {legacy_yaml}")
			return cached_yaml

	return None


def extract_single_pdf(pdf_path, output_path, model, tokenizer):
	pdf_path = Path(pdf_path)

	checkpoint_path = output_path / "checkpoints"
	checkpoint_path.mkdir(parents = True, exist_ok = True)

	all_elements = {}

	for prompt_type in PROMPT_TYPES:
		checkpoint_file = (
			checkpoint_path
			/ f"{pdf_path.stem}_1_{prompt_type}.json"
		)

		print(f"\nExtracting {pdf_path.name} using {prompt_type}.")

		data, prompt, output = extract_kdes(
			pdf_path,
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

		_write_llm_log(output_path, [pdf_path])

	yaml_path = output_path / f"{pdf_path.stem}_kdes.yaml"

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

	return yaml_path


def get_yaml_file(pdf_path, output_path, model, tokenizer):
	existing_yaml = find_existing_yaml(pdf_path, output_path)

	if existing_yaml:
		return existing_yaml

	print(f"\nNo existing YAML file found for {pdf_path}.")
	print("Starting extraction.")

	return extract_single_pdf(
		pdf_path,
		output_path,
		model,
		tokenizer
	)


def run_pipeline(pdf1, pdf2):
	dockerfiles_zip = Path("dockerfiles.zip")
	hadolint_path = Path("hadolint.exe")

	output_path = Path("outputs/kdes")
	output_path.mkdir(parents = True, exist_ok = True)

	comparison_name = f"{Path(pdf1).stem}_{Path(pdf2).stem}"
	output_dir = Path("outputs/comparisons") / comparison_name
	output_dir.mkdir(parents = True, exist_ok = True)

	print("\n===== VALIDATING INPUTS =====")

	validate_documents(pdf1, pdf2)

	if not dockerfiles_zip.is_file():
		raise FileNotFoundError(
			f"Dockerfiles ZIP file not found: {dockerfiles_zip}"
		)

	if not hadolint_path.is_file():
		raise FileNotFoundError(
			f"Hadolint executable not found: {hadolint_path}"
		)

	print("Input files validated successfully.")

	print("\n===== PART 1: EXTRACTOR =====")

	model = None
	tokenizer = None

	pdf1_yaml = find_existing_yaml(pdf1, output_path)
	pdf2_yaml = find_existing_yaml(pdf2, output_path)

	if pdf1_yaml is None or pdf2_yaml is None:
		model, tokenizer = _load_model()

	yaml1 = get_yaml_file(
		pdf1,
		output_path,
		model,
		tokenizer
	)

	yaml2 = get_yaml_file(
		pdf2,
		output_path,
		model,
		tokenizer
	)

	print("Extractor finished.")
	print("YAML files:", yaml1, yaml2)

	del model
	del tokenizer

	print("\n===== PART 2: COMPARATOR =====")

	name_report = output_dir / "name_differences.txt"

	compare_element_names(
		yaml1,
		yaml2,
		output_file = str(name_report)
	)

	requirement_report = output_dir / "requirement_differences.txt"

	compare_element_requirements(
		yaml1,
		yaml2,
		output_file = str(requirement_report)
	)

	print("Comparator finished.")
	print("Name report:", name_report)
	print("Requirement report:", requirement_report)

	print("\n===== PART 3: EXECUTOR =====")

	name_text, requirement_text = read_comparison_reports(
		name_report,
		requirement_report
	)

	rules_file = output_dir / "hadolint_rules.txt"

	determine_hadolint_rules(
		name_text,
		requirement_text,
		output_file = str(rules_file)
	)

	dataframe = execute_hadolint(
		rules_file,
		dockerfiles_zip,
		hadolint_path = hadolint_path,
		extract_dir = str(output_dir / "dockerfiles_extracted")
	)

	csv_file = output_dir / "hadolint_results.csv"

	save_scan_results(
		dataframe,
		output_file = str(csv_file)
	)

	print("Executor finished.")

	print("\nHadolint rules:")
	print(rules_file.read_text(encoding = "utf-8"))

	print("\nCSV results:")
	print(dataframe)

	print("\nCSV saved to:", csv_file)

	print("\n===== PIPELINE FINISHED =====")


def main():
	try:
		pdf1, pdf2 = get_pdf_selection()

		print("\nSelected documents:")
		print("First PDF:", pdf1)
		print("Second PDF:", pdf2)

		run_pipeline(pdf1, pdf2)

	except (FileNotFoundError, ValueError, RuntimeError) as e:
		print(f"\nERROR: {e}")

	except KeyboardInterrupt:
		print("\nProgram cancelled by user.")


if __name__ == "__main__":
	main()
