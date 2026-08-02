# Makefile for flint2_ansible
# Ansible automation for GL.iNet GL-MT6000 (Flint 2)

.DEFAULT_GOAL := help

## Show this help
.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo ""
	@awk '/^## /{desc=substr($$0,4)} /^[a-zA-Z_-]+:/{if(desc){printf "  %-22s %s\n",$$1,desc; desc=""}}' $(MAKEFILE_LIST) | sed 's/://' | sort
	@echo ""

## Install Ansible collections from requirements.yml
.PHONY: install
install:
	ansible-galaxy collection install -r requirements.yml -p collections

## Test SSH connectivity to the Flint 2
.PHONY: ping
ping:
	ansible-playbook playbooks/ping.yml

## Apply the full Flint 2 site playbook
.PHONY: site
site:
	ansible-playbook playbooks/site.yml

## Dry-run the site playbook with diffs
.PHONY: check
check:
	ansible-playbook playbooks/site.yml --check --diff

## Configure hostname and system settings only
.PHONY: system
system:
	ansible-playbook playbooks/site.yml --tags system

## Configure wireless networks only
.PHONY: wireless
wireless:
	ansible-playbook playbooks/site.yml --tags wireless

## Install TLS certificates on nginx and uHTTPd
.PHONY: tls
tls:
	ansible-playbook playbooks/site.yml --tags tls

## Configure Dropbear and authorized_keys
.PHONY: ssh
ssh:
	ansible-playbook playbooks/site.yml --tags ssh

## Validate applied configuration and TLS endpoints
.PHONY: verify
verify:
	ansible-playbook playbooks/site.yml --tags verify
