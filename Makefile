.PHONY: install lint format test clean help

PYTHON ?= python

help:
	@$(PYTHON) tasks.py --help

install:
	$(PYTHON) tasks.py install

lint:
	$(PYTHON) tasks.py lint

format:
	$(PYTHON) tasks.py format

test:
	$(PYTHON) tasks.py test

clean:
	$(PYTHON) tasks.py clean
