Installed into the dev virtualenv so `ansible-config dump` does not report
the unused `oneline` and `tree` callbacks as if this project enabled them.

Deprecation warnings stay enabled. A playbook that selects either callback
still warns.
