# Makefile for flint2_ansible
# Ansible automation for GL.iNet GL-MT6000 (Flint 2)

.DEFAULT_GOAL := help

UV ?= uv
EE_IMAGE ?= flint2-ansible-ee:latest
MOLECULE_SCENARIO ?= default
MOLECULE_DIR := roles/flint2
COLIMA_SOCKET := $(HOME)/.colima/default/docker.sock

# Use Colima's Docker socket when present and DOCKER_HOST is not already set.
ifeq ($(origin DOCKER_HOST), undefined)
ifneq (,$(wildcard $(COLIMA_SOCKET)))
export DOCKER_HOST := unix://$(COLIMA_SOCKET)
endif
endif

.PHONY: docker-check
docker-check:
	@docker info >/dev/null 2>&1 || { \
		echo "Docker is required for Molecule tests."; \
		if command -v colima >/dev/null 2>&1; then \
			echo "Start Colima with: make colima-start"; \
		else \
			echo "Start Docker and retry."; \
		fi; \
		exit 1; \
	}

## Start Colima for Molecule Docker tests
.PHONY: colima-start
colima-start:
	@if [ "$$(uname -m)" = "arm64" ]; then \
		colima start --vm-type vz --vz-rosetta; \
	else \
		colima start; \
	fi

## Show this help
.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo ""
	@awk '/^## /{desc=substr($$0,4)} /^[a-zA-Z_-]+:/{if(desc){printf "  %-22s %s\n",$$1,desc; desc=""}}' $(MAKEFILE_LIST) | sed 's/://' | sort
	@echo ""

## Create the uv virtualenv and install Python dev dependencies
.PHONY: setup
setup:
	$(UV) sync --group dev

## Install Ansible collections from requirements.yml
.PHONY: install
install: setup
	$(UV) run ansible-galaxy collection install -r requirements.yml -p collections

## Install pre-commit Git hooks
.PHONY: hooks
hooks: setup
	$(UV) run pre-commit install

## Run all linters (ansible-lint and yamllint)
.PHONY: lint
lint: setup
	$(UV) run ansible-lint
	$(UV) run yamllint .

## Validate Ansible playbook syntax
.PHONY: syntax
syntax: setup install
	$(UV) run ansible-playbook --syntax-check playbooks/site.yml
	$(UV) run ansible-playbook --syntax-check playbooks/ping.yml

## Run pytest with coverage
.PHONY: pytest
pytest: setup
	$(UV) run pytest --cov --cov-report=term-missing

## Scan the repository for accidentally committed secrets
.PHONY: secrets
secrets:
	gitleaks detect --source . --config .gitleaks.toml --no-banner

## Run pre-commit on all files
.PHONY: pre-commit
pre-commit: setup
	$(UV) run pre-commit run --all-files

## Run project sanity checks (lint, syntax, pytest)
.PHONY: sanity
sanity: lint syntax pytest

## Run Molecule integration tests for the flint2 role
.PHONY: molecule
molecule: setup install docker-check
	cd $(MOLECULE_DIR) && $(UV) run molecule test -s $(MOLECULE_SCENARIO)

## Run Molecule converge only (keep containers running)
.PHONY: molecule-converge
molecule-converge: setup install docker-check
	cd $(MOLECULE_DIR) && $(UV) run molecule converge -s $(MOLECULE_SCENARIO)

## Destroy Molecule test resources
.PHONY: molecule-destroy
molecule-destroy: setup
	cd $(MOLECULE_DIR) && $(UV) run molecule destroy -s $(MOLECULE_SCENARIO)

## Run automated tests that do not require Docker
.PHONY: test
test: sanity secrets

## Run all automated tests including Molecule (requires Docker)
.PHONY: test-all
test-all: sanity secrets molecule

## Run tox validation environments
.PHONY: tox
tox: setup
	$(UV) run tox

## Run tox-ansible compatibility matrix (lint across ansible-core versions)
.PHONY: tox-ansible
tox-ansible: setup
	$(UV) run tox --ansible -e lint

## Build the Ansible Execution Environment image
.PHONY: ee-build
ee-build: setup
	$(UV) run ansible-builder build -f execution-environment.yml -t $(EE_IMAGE) --context .

## Lint playbooks using ansible-navigator inside the Execution Environment
.PHONY: navigator-lint
navigator-lint: setup
	$(UV) run ansible-navigator lint --eei $(EE_IMAGE) --rc ansible-navigator.yml

## Run a playbook inside the Execution Environment (PLAYBOOK=playbooks/site.yml)
.PHONY: navigator-run
navigator-run: setup
	@test -n "$(PLAYBOOK)" || (echo "Set PLAYBOOK=playbooks/site.yml" && exit 1)
	$(UV) run ansible-navigator run $(PLAYBOOK) --eei $(EE_IMAGE) --rc ansible-navigator.yml -m stdout

## Test SSH connectivity to the Flint 2
.PHONY: ping
ping: install
	$(UV) run ansible-playbook playbooks/ping.yml

## Apply the full Flint 2 site playbook
.PHONY: site
site: install
	$(UV) run ansible-playbook playbooks/site.yml

## Dry-run the site playbook with diffs
.PHONY: check
check: install
	$(UV) run ansible-playbook playbooks/site.yml --check --diff

## Configure hostname and system settings only
.PHONY: system
system: install
	$(UV) run ansible-playbook playbooks/site.yml --tags system

## Configure wireless networks only
.PHONY: wireless
wireless: install
	$(UV) run ansible-playbook playbooks/site.yml --tags wireless

## Install TLS certificates on nginx and uHTTPd
.PHONY: tls
tls: install
	$(UV) run ansible-playbook playbooks/site.yml --tags tls

## Configure Dropbear and authorized_keys
.PHONY: ssh
ssh: install
	$(UV) run ansible-playbook playbooks/site.yml --tags ssh

## Validate applied configuration and TLS endpoints
.PHONY: verify
verify: install
	$(UV) run ansible-playbook playbooks/site.yml --tags verify
