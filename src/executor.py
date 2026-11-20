from pathlib import Path

import re
import zipfile
import subprocess
import json
import pandas as pd



CIS_HADOLINT_MAPPING = [
	{
		"phrases": [
			"non-root user",
			"run as a non-root",
			"user directive"
	],
		"rules": ["DL3002"]
	},
	{
		"phrases": [
			"unnecessary packages",
			"packages strictly necessary",
			"avoid additional packages"
	],
		"rules": ["DL3015"]
	},
	{
		"phrases": [
			"healthcheck"
	],
		"rules": ["DL3057"]
	},
	{
		"phrases": [
			"copy instead of add",
			"copy instruction instead of add",
			"use copy rather than add",
			"use copy instead of add",
			"copy is used instead of add",
			"copy should be used instead of add",
			"copy rather than add"
	],
		"rules": ["DL3020"]
	},
	{
		"phrases": [
			"secrets are not stored in dockerfiles",
			"do not store any secrets in dockerfiles",
			"secrets within dockerfiles"
		],
		"rules": ["DL3064"]
	}
]


def read_comparison_reports(name_file, requirement_file):
	with open(name_file, "r", encoding = "utf-8") as file:
		name_report = file.read().strip()

	with open(requirement_file, "r", encoding = "utf-8") as file:
		requirement_report = file.read().strip()

	return name_report, requirement_report



def determine_hadolint_rules(name_report, requirement_report, output_file = "outputs/hadolint_rules.txt"):
	no_name_differences = (name_report == "NO DIFFERENCES IN REGARDS TO ELEMENT NAMES")
	no_requirement_differences = (requirement_report == "NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS")
	if no_name_differences and no_requirement_differences:
		result = "NO DIFFERENCES FOUND"
	else:
		combined_report = (name_report + "\n" + requirement_report).casefold()

		rules = set()

		for mapping in CIS_HADOLINT_MAPPING:
			for phrase in mapping["phrases"]:
				if phrase in combined_report:
					rules.update(mapping["rules"])
					break

		if rules:
			result = "\n".join(sorted(rules))
		else:
			result = "NO MAPPING FOUND"

	output_path = Path(output_file)
	output_path.parent.mkdir(parents = True, exist_ok = True)
	output_path.write_text(result, encoding = "utf-8")
	return result



def execute_hadolint(rules_file, dockerfiles_zip, hadolint_path = "hadolint.exe", extract_dir = "dockerfiles_extracted"):
	rules_text = Path(rules_file).read_text(encoding = "utf-8").strip()

	all_rules = rules_text in ["NO DIFFERENCES FOUND", "NO MAPPING FOUND"]
	selected_rules = set()

	if not all_rules:
		selected_rules = set(re.findall(r"\bDL\d{4}\b", rules_text))

		if not selected_rules:
			raise ValueError("No valid Hadolint rules were provided.")

	hadolint_path = Path(hadolint_path)

	if not hadolint_path.is_file():
		raise FileNotFoundError(f"Hadolint executable not found: {hadolint_path}")

	dockerfiles_zip = Path(dockerfiles_zip)

	if not dockerfiles_zip.is_file():
		raise FileNotFoundError(f"Dockerfiles ZIP file not found: {dockerfiles_zip}")

	extract_path = Path(extract_dir)
	extract_path.mkdir(parents = True, exist_ok = True)

	with zipfile.ZipFile(dockerfiles_zip, "r") as zip_file:
		for member in zip_file.infolist():
			destination = (extract_path / member.filename).resolve()

			if (extract_path.resolve() not in destination.parents and destination != extract_path.resolve()):
				raise ValueError("Unsafe path found in ZIP file.")

		zip_file.extractall(extract_path)

	dockerfiles = []

	for file in extract_path.rglob("*"):
		if file.is_file() and (file.name.lower() == "dockerfile" or file.name.lower().startswith("dockerfile")):
			dockerfiles.append(file)

	results = []

	for dockerfile in dockerfiles:
		command = [str(hadolint_path), "--format", "json"]

		if not all_rules and "DL3057" in selected_rules:
			command.extend(["--warning", "DL3057"])

		command.append(str(dockerfile))
		completed = subprocess.run(command, capture_output = True, text = True)

		if completed.returncode not in [0, 1]:
			raise RuntimeError(f"Hadolint failed on {dockerfile}: " f"{completed.stderr}")

		if not completed.stdout.strip():
			continue

		findings = json.loads(completed.stdout)

		for finding in findings:
			rule_id = finding.get("code", "")

			if all_rules or rule_id in selected_rules:
				results.append({"FilePath": str(dockerfile), "DefaultSeverity": finding.get("level", ""), "RULEID": rule_id})

	dataframe = pd.DataFrame(results, columns = ["FilePath", "DefaultSeverity", "RULEID"])


	if dataframe.empty:
		return pd.DataFrame(columns = ["FilePath", "DefaultSeverity", "RULEID", "COUNT"])

	dataframe = (dataframe.groupby(["FilePath", "DefaultSeverity", "RULEID"]).size().reset_index(name = "COUNT"))

	return dataframe




def save_scan_results(dataframe, output_file = "outputs/hadolint_results.csv"):
	required_columns = ["FilePath", "DefaultSeverity", "RULEID", "COUNT"]

	dataframe = dataframe[required_columns]

	output_path = Path(output_file)
	output_path.parent.mkdir(parents = True, exist_ok = True)
	dataframe.to_csv(output_path, index = False)

	return True