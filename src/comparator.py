from pathlib import Path
import yaml

def load_elements(yaml_file):
	with open(yaml_file, "r", encoding = "utf-8") as file:
		data = yaml.safe_load(file) or {}

	if "elements" in data and isinstance(data["elements"], list):
		return data["elements"]

	return list(data.values())


def compare_element_names(file1, file2, output_file = "outputs/name_differences.txt"):
	elements1 = load_elements(file1)
	elements2 = load_elements(file2)
	names1 = {element["name"].strip().casefold() for element in elements1}
	names2 = {element["name"].strip().casefold() for element in elements2}
	differences = []

	for name in sorted(names1 - names2):
		differences.append(f"Only in first document: {name}")

	for name in sorted(names2 - names1):
		differences.append(f"Only in second document: {name}")

	if differences:
		result = "\n".join(differences)
	else:
		result = "NO DIFFERENCES IN REGARDS TO ELEMENT NAMES"

	output_path = Path(output_file)
	output_path.parent.mkdir(parents = True, exist_ok = True)
	output_path.write_text(result, encoding = "utf-8")

	return result


def compare_element_requirements(file1, file2, output_file = "outputs/requirement_differences.txt"):
	elements1 = load_elements(file1)
	elements2 = load_elements(file2)

	data1 = {
		element["name"].strip().casefold(): {
			requirement.strip() for requirement in element["requirements"]
		}
		for element in elements1
	}

	data2 = {
		element["name"].strip().casefold(): {
			requirement.strip() for requirement in element["requirements"]
		}
		for element in elements2
	}

	differences = []
	all_names = sorted(set(data1) | set(data2))

	for name in all_names:
		requirements1 = data1.get(name, set())
		requirements2 = data2.get(name, set())

		for requirement in sorted(requirements1 - requirements2):
			differences.append(f"({name}, {requirement}) - Only in first document")

		for requirement in sorted(requirements2 - requirements1):
			differences.append(f"({name}, {requirement}) - Only in second document")

	if differences:
		result = "\n".join(differences)
	else:
		result = "NO DIFFERENCES IN REGARDS TO ELEMENT REQUIREMENTS"

	output_path = Path(output_file)
	output_path.parent.mkdir(parents = True, exist_ok = True)
	output_path.write_text(result, encoding = "utf-8")

	return result