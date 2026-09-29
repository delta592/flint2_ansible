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

## Refresh uv.lock from pyproject.toml (no version upgrades)
.PHONY: lock
lock:
	$(UV) lock

## Upgrade Python dependencies, refresh uv.lock, and sync the virtualenv
.PHONY: deps-update
deps-update:
	$(UV) lock --upgrade
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

## Run pytest project and role-variable tests
.PHONY: pytest
pytest: setup
	$(UV) run pytest

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

BOOTSTRAP_FILE := .secrets/bootstrap.yml

.PHONY: bootstrap-check
bootstrap-check:
	@test -f $(BOOTSTRAP_FILE) || { \
		echo "Missing $(BOOTSTRAP_FILE)."; \
		echo "Copy inventory/bootstrap.yml.example to $(BOOTSTRAP_FILE) and set ansible_ssh_pass."; \
		exit 1; \
	}

## Remove stale SSH host keys after factory reset or firmware upgrade
.PHONY: known-hosts-reset
known-hosts-reset:
	-ssh -O exit -o ControlPath=$(HOME)/.ssh/control/root@192.168.0.247_22 root@192.168.0.247 2>/dev/null
	-ssh -O exit -o ControlPath=$(HOME)/.ssh/control/root@wapap1003_22 root@wapap1003 2>/dev/null
	-ssh-keygen -R wapap1003 2>/dev/null
	-ssh-keygen -R wapap1003.federation.lcars 2>/dev/null
	-ssh-keygen -R 192.168.0.247 2>/dev/null

## Test SSH connectivity using bootstrap password auth (.secrets/bootstrap.yml)
.PHONY: ping-bootstrap
ping-bootstrap: install bootstrap-check
	$(UV) run ansible-playbook playbooks/ping.yml -e @$(BOOTSTRAP_FILE)

## Apply the site playbook using bootstrap password auth for the initial run
.PHONY: site-bootstrap
site-bootstrap: install bootstrap-check
	$(UV) run ansible-playbook playbooks/site.yml -e @$(BOOTSTRAP_FILE) $(if $(TAGS),--tags $(TAGS),)

## Dry-run the site playbook using bootstrap password auth
.PHONY: check-bootstrap
check-bootstrap: install bootstrap-check
	$(UV) run ansible-playbook playbooks/site.yml --check --diff -e @$(BOOTSTRAP_FILE) $(if $(TAGS),--tags $(TAGS),)

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
	$(UV) run ansible-playbook playbooks/site.yml --tags system,always

## Configure NTP time synchronization only
.PHONY: ntp
ntp: install
	$(UV) run ansible-playbook playbooks/site.yml --tags ntp,always

## Configure br-lan IGMP snooping and multicast querier (E1/E2)
.PHONY: network
network: install
	$(UV) run ansible-playbook playbooks/site.yml --tags network,always

## Install LuCI Statistics and enable collectd thermal/sensors graphs
.PHONY: statistics
statistics: install
	$(UV) run ansible-playbook playbooks/site.yml --tags statistics,always

## Install usteer and enable active AP-side band steering
.PHONY: usteer
usteer: install
	$(UV) run ansible-playbook playbooks/site.yml --tags usteer,always

## Configure wireless networks only
.PHONY: wireless
wireless: install
	$(UV) run ansible-playbook playbooks/site.yml --tags wireless,always

## Configure GL.iNet Access Control settings only
.PHONY: access-control
access-control: install
	$(UV) run ansible-playbook playbooks/site.yml --tags access_control,luci,always

## Install TLS certificates on nginx and uHTTPd
.PHONY: tls
tls: install
	$(UV) run ansible-playbook playbooks/site.yml --tags tls,always

## Harden GL.iNet nginx admin headers (HSTS / security headers)
.PHONY: nginx
nginx: install
	$(UV) run ansible-playbook playbooks/site.yml --tags nginx,always

## Configure SSH hardening (OpenSSH algorithms / authorized_keys)
.PHONY: ssh
ssh: install
	$(UV) run ansible-playbook playbooks/site.yml --tags ssh,always

SSH_AUDIT ?= $(HOME)/scripts/ssh-audit
SSH_AUDIT_HOST ?= 192.168.0.247

## Audit SSH algorithms with ssh-audit (run after make ssh)
.PHONY: ssh-audit
ssh-audit:
	@test -x "$(SSH_AUDIT)" || { echo "Missing executable: $(SSH_AUDIT)"; exit 1; }
	$(SSH_AUDIT) $(SSH_AUDIT_HOST)

## Validate applied configuration and TLS endpoints
.PHONY: verify
verify: install
	$(UV) run ansible-playbook playbooks/site.yml --tags verify,always
