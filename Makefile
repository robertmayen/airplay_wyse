VENV ?= .venv
PYTHON ?= python3.13
# Prefer the repo venv's tools when it exists (CI installs them globally).
export PATH := $(CURDIR)/$(VENV)/bin:$(PATH)

PLAYBOOKS := site.yml doctor.yml discover.yml migration.yml

.PHONY: venv lint test check converge converge-down

venv:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-dev.txt
	$(VENV)/bin/ansible-galaxy collection install -r collections/requirements.yml

lint:
	yamllint .
	ansible-lint
	ruff check .
	ruff format --check .
	shellcheck ci/*.sh

test:
	pytest

check: lint test
	ansible-playbook --syntax-check $(PLAYBOOKS)

# Full role converge in a Debian 13 systemd container (needs Docker).
# Extra ansible-playbook args via ARGS, e.g.  make converge ARGS='-e foo=bar'
converge:
	ci/converge.sh up
	ci/converge.sh play $(ARGS)
	ci/converge.sh idempotent $(ARGS)

converge-down:
	ci/converge.sh down
