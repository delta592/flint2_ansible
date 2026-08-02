.PHONY: install ping site check

install:
	ansible-galaxy collection install -r requirements.yml -p collections

ping:
	ansible-playbook playbooks/ping.yml

site:
	ansible-playbook playbooks/site.yml

check:
	ansible-playbook playbooks/site.yml --check --diff
