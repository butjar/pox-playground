VENV_DIR=.env

venv-create:
	virtualenv $(VENV_DIR)

venv-acitvate:
	source $(VENV_DIR)/bin/activate

venv-rm:
	rm -rf .env

init:
	pip install --upgrade pip
	pip install -r requirements.txt
