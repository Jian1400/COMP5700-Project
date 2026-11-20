from src.executor import (read_comparison_reports, determine_hadolint_rules, execute_hadolint, save_scan_results)


def test_determine_hadolint_rules_with_mapping(tmp_path):
	output_file = tmp_path / "rules.txt"

	result = determine_hadolint_rules("Different element names", "(Ensure that COPY is used instead of ADD in Dockerfiles)", output_file)

	assert result == "DL3020"
	assert output_file.read_text(encoding = "utf-8") == "DL3020"



def test_determine_hadolint_rules_without_mapping(tmp_path):
	output_file = tmp_path / "rules.txt"

	result = determine_hadolint_rules("Different element names", "(Ensure update instructions are not used alone in Dockerfiles)", output_file)

	assert result == "NO MAPPING FOUND"
	assert output_file.read_text(encoding = "utf-8") == "NO MAPPING FOUND"



def test_determine_hadolint_rules_no_difference(tmp_path):
	output_file = tmp_path / "rules.txt"

	result = determine_hadolint_rules("NO DIFFERENCES IN REGARDS TO ELEMENT NAMES", "NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS", output_file)

	assert result == "NO DIFFERENCES FOUND"
	assert output_file.read_text(encoding = "utf-8") == "NO DIFFERENCES FOUND"