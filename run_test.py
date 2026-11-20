from pathlib import Path

from src.extractor import validate_documents, save_extraction_outputs
from src.comparator import compare_element_names, compare_element_requirements
from src.executor import (
	read_comparison_reports,
	determine_hadolint_rules,
	execute_hadolint,
	save_scan_results
)


# Input files
pdf1 = "docker-cis-v0.pdf"
pdf2 = "docker-cis-v1.pdf"
dockerfiles_zip = "dockerfiles.zip"
hadolint_path = "hadolint.exe"


# Output folder for this comparison
output_dir = Path("outputs/test_v0_v1")
output_dir.mkdir(parents = True, exist_ok = True)

print("\n===== PART 1: EXTRACTOR =====")

# Validate the two PDFs
validate_documents(pdf1, pdf2)

# Extract KDEs and save YAML files and LLM output
save_extraction_outputs(pdf1, pdf2, output_dir = str(output_dir))

yaml1 = output_dir / "docker-cis-v0_kdes_1.yaml"
yaml2 = output_dir / "docker-cis-v1_kdes_2.yaml"

print("Extractor finished.")
print("YAML files:", yaml1, yaml2)

print("\n===== PART 2: COMPARATOR =====")

# Compare KDE names
name_report = output_dir / "name_differences.txt"

compare_element_names(
	yaml1,
	yaml2,
	output_file = str(name_report)
)

# Compare KDE requirements
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

# Read the comparison reports
name_text, requirement_text = read_comparison_reports(
	name_report,
	requirement_report
)

# Determine which Hadolint rules apply
rules_file = output_dir / "hadolint_rules.txt"

determine_hadolint_rules(
	name_text,
	requirement_text,
	output_file = str(rules_file)
)

# Run Hadolint against the Dockerfiles
dataframe = execute_hadolint(
	rules_file,
	dockerfiles_zip,
	hadolint_path = hadolint_path,
	extract_dir = str(output_dir / "dockerfiles_extracted")
)

# Save the CSV results
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

print("\n===== PIPELINE FINISHED =====")
