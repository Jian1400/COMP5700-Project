# COMP5700 Project

# IMPORTANT: Link to Executable Binary:
https://tigermailauburn-my.sharepoint.com/:f:/g/personal/ijb0009_auburn_edu/IgDPocrtLl9xR6w7FK0lOdtnAYrYxfap9CrdWi6SK1fbmxM?e=qksQcg

# Important: If the extraction step is skipped because previously generated YAML files are being reused, delete the relevant cached files from outputs/kdes/, outputs/test_v0_v1/, and outputs/comparisons/ before running the program again.

## Team Members

| Isaiah Barlatier | 904232076 | ijb0009@auburn.edu |


## Large Language Model Used

Google Gemma 3 1B (`google/gemma-3-1b-it`)


## Required Input Files

The program requires the following files:

docker-cis-v0.pdf

docker-cis-v1.pdf

docker-cis-v2.pdf

hadolint.exe

dockerfiles.zip


## Running the Executable

1. Download COMP5700-Project.exe using the link above.

2. Place the executable and required input files in the same directory.

3. Open PowerShell in that directory.

4. Run: .\COMP5700-Project.exe

5. Select the desired combination when prompted.


## Running From Source Code

Create and activate a virtual environment:

python -m venv comp5700-venv


Install dependencies:

pip install -r requirements.txt


## Running the Program

Run the main application:

python main.py

Select the desired combination when prompted.


## Running Tests

Run all project tests:

python -m pytest tests/ -v
python -m pytest tests/ -v

