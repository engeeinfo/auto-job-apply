.PHONY: build lint test

PYTHON ?= python3

build:
	$(PYTHON) -m compileall -q .

lint:
	$(PYTHON) -m compileall -q naukri_bot tests

test:
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
