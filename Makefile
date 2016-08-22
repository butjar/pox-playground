SHELL := /bin/bash
VENV_DIR=.env

.PHONY: venv-create venv-activate venv-rm init run mn

venv-create:
	virtualenv $(VENV_DIR)

venv-rm:
	rm -rf .env

init:
	sudo apt-get install -y python-pip
	sudo pip install --upgrade pip
	sudo pip install virtualenv
	$(MAKE) venv-create

run:
	./pox-wrapper.py log.level --DEBUG controller.loop_discovery

mn:
	sudo mn --custom ring.py --topo ring --controller loop_controller
