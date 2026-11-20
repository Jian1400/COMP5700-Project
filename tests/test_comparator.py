import yaml

from src.comparator import(load_elements, compare_element_names, compare_element_requirements)



def create_yaml_file(path, elements):
	with open(path, "w", encoding = "utf-8") as file:
		yaml.safe_dump(elements, file, sort_keys = False)


def test_load_elements(tmp_path):
	yaml_file = tmp_path / "test.yaml"
	create_yaml_file(
		yaml_file,
		{
			"element1": {
				"name": "Container partition",
				"requirements": ["Requirement 1"]
			}
		}
	)

	elements = load_elements(yaml_file)
	assert elements[0]["name"] == "Container partition"



def test_compare_element_names(tmp_path):
	file1 = tmp_path / "file1.yaml"
	file2 = tmp_path / "file2.yaml"
	create_yaml_file(file1, {
		"element1": {
			"name": "Container partition",
			"requirements": ["Requirement 1"]
		}
	})

	create_yaml_file(file2, {
		"element1": {
			"name": "Docker daemon",
			"requirements": ["Requirement 2"]
		}
	})

	output = tmp_path / "name_differences.txt"
	result = compare_element_names(file1, file2, output)
	assert "container partition" in result
	assert "docker daemon" in result
	assert output.exists()


def test_compare_element_requirements(tmp_path):
	file1 = tmp_path / "file1.yaml"
	file2 = tmp_path / "file2.yaml"
	create_yaml_file(file1, {
		"element1": {
			"name": "Container partition",
			"requirements": ["Requirement 1"]
		}
	})

	create_yaml_file(file2, {
		"element1": {
			"name": "Container partition",
			"requirements": ["Requirement 2"]
		}
	})

	output = tmp_path / "requirement_differences.txt"
	result = compare_element_requirements(file1, file2, output)
	assert "Requirement 1" in result
	assert "Requirement 2" in result
	assert output.exists()