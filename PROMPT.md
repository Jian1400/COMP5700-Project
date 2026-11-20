zero-shot:

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




few-shot:

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





chain-of-thought:

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
