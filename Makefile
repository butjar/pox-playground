VENV_DIR=.env

.PHONY: venv-create venv-acitvate venv-rm init run mn

venv-create:
	virtualenv $(VENV_DIR)

venv-acitvate:
	source $(VENV_DIR)/bin/activate

venv-rm:
	rm -rf .env

init:
	pip install --upgrade pip
	pip install -r requirements.txt

run:
	./pox-wrapper.py log.level --DEBUG controller.loop_discovery

mn:
	sudo mn --custom ring.py --topo ring --controller remote
