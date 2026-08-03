# flint2_ansible

Ansible automation for the [GL.iNet GL-MT6000 (Flint 2)](https://www.gl-inet.com/products/flint-2/) running GL.iNet firmware on OpenWrt. This project configures Access Point mode, wireless networks, TLS certificates, and SSH access using the [`community.openwrt`](https://galaxy.ansible.com/community/openwrt) collection.

Configuration is driven by UCI and shell-based modules — no Python runtime is required on the router.

## Features

- **System** — hostname and AP-mode settings validated against live device state
- **Wireless** — 2.4 GHz and 5 GHz SSIDs via MTK UCI sections (`mt798611`/`wifi2g`, `mt798612`/`wifi5g`)
- **Access Control** — GL.iNet admin panel, LuCI, and SSH ports, Force HTTPS, and auto-logout
- **TLS** — private CA certificates on nginx (GL.iNet UI, port 443) and uHTTPd (LuCI, port 8443)
- **SSH** — Dropbear hardening (password auth off) and `authorized_keys` management
- **Verify** — post-apply checks for hostname, wireless, guest/IoT disabled state, and TLS fingerprints
- **Tagged runs** — apply or validate individual areas via Makefile targets or `--tags`

## Requirements

| Component | Version |
| --- | --- |
| Ansible core | 2.18+ |
| `community.openwrt` collection | >= 1.6.0 |
| `community.docker` collection | >= 3.0.0 (Molecule tests) |
| Python | 3.14.x |
| [uv](https://docs.astral.sh/uv/) | Python environment and dev dependencies |
| Docker | Molecule integration tests ([Colima](https://github.com/abiosoft/colima) supported) |
| SSH access | `root` key-based login to the router |
| Make | optional but recommended |

## Manual prerequisites

These steps are **not** automated and must be completed before running the playbooks:

1. Factory reset and GL.iNet first-run wizard
2. Cable WAN1 uplink and enable **Access Point** mode in the GL.iNet UI
3. Create a pfSense (or upstream) DHCP static mapping for the management IP
4. Upgrade GL.iNet firmware via **System → Upgrade** if needed
5. Back up LuCI configuration before major changes

See the installation guides in [`docs/`](docs/) for full procedures.

## Quick start

```bash
# Install the community.openwrt collection locally
make install

# Confirm SSH connectivity
make ping

# Apply the full configuration
make site

# Validate applied settings and TLS endpoints
make verify
```

Run `make help` for all available targets.

## Development

Install the Python toolchain, Ansible collections, and Git hooks:

```bash
make setup
make install
make hooks
```

Common validation targets:

| Target | Purpose |
| --- | --- |
| `make setup` | Install Python dev dependencies from `uv.lock` |
| `make lock` | Regenerate `uv.lock` from `pyproject.toml` |
| `make deps-update` | Upgrade dependencies, refresh `uv.lock`, and sync `.venv` |
| `make lint` | ansible-lint and yamllint |
| `make syntax` | `ansible-playbook --syntax-check` |
| `make check` | Dry-run site playbook with diffs |
| `make pytest` | Project unit tests with coverage |
| `make molecule` | Molecule role integration tests (Docker/Colima) |
| `make colima-start` | Start Colima for Molecule tests |
| `make secrets` | Gitleaks secret scan |
| `make test` | lint, syntax, pytest, and secrets |
| `make test-all` | `make test` plus Molecule (Docker) |
| `make tox` | Run tox environments from `pyproject.toml` |
| `make ee-build` | Build the Ansible Execution Environment image |

Pre-commit runs the same linters and Gitleaks before each commit once hooks are installed.

### Docker via Colima

Molecule tests provision OpenWrt containers through Docker. OpenWrt publishes `x86_64` rootfs images only, so on Apple Silicon you need Colima with Rosetta emulation:

```bash
make colima-start    # starts Colima with --vm-type vz --vz-rosetta on arm64 Macs
make test-all        # or: make molecule
```

If Colima was previously started without Rosetta, stop it first (`colima stop`) and run `make colima-start` again.

When Colima is running, Make automatically sets `DOCKER_HOST` to `unix://$HOME/.colima/default/docker.sock`. Molecule pulls OpenWrt images with `platform: linux/amd64`. To use a different runtime, set `DOCKER_HOST` yourself before running Molecule.

The Molecule scenario seeds synthetic MTK-style wireless UCI sections, then applies and verifies the `packages`, `system`, `wireless`, and `ssh` task files. TLS and GL.iNet-specific checks are skipped in Docker; use `make check` and `make verify` against the real router for those.

## Secrets and certificates

Sensitive files live outside the repository and are listed in [`.gitignore`](.gitignore).

### Directory layout

```
.env/                          # Public certs and SSH public keys (gitignored)
  wapap1003.crt                # TLS leaf certificate
  Federation_LCARS_Intermediate_v002.crt
  id_ed25519.pub               # SSH authorized keys
  id_ed25519_v002.pub

.secrets/                      # Private keys (gitignored)
  wapap1003.key

inventory/group_vars/flint2/
  main.yml                     # Device and service configuration
  vault.yml                    # Encrypted secrets (gitignored; create from example)
  vault.yml.example
```

### Vault (optional)

If the wireless passphrase should not live in plain text, copy the example and encrypt it:

```bash
cp inventory/group_vars/flint2/vault.yml.example inventory/group_vars/flint2/vault.yml
# Edit vault.yml, then:
ansible-vault encrypt inventory/group_vars/flint2/vault.yml
```

The wireless key is referenced as `vault_flint2_wireless_key` in [`inventory/group_vars/flint2/main.yml`](inventory/group_vars/flint2/main.yml).

## Configuration

### Inventory

| Host | Group | Connection |
| --- | --- | --- |
| `router` | `flint2` → `openwrt` | `ansible_host: wapap1003` in [`inventory/host_vars/router.yml`](inventory/host_vars/router.yml) |

Adjust host name, FQDN, management IP, wireless SSID, and certificate file names in [`inventory/group_vars/flint2/main.yml`](inventory/group_vars/flint2/main.yml).

### Role tags

The [`flint2`](roles/flint2/) role is split into tagged task files:

| Tag | Task file | Purpose |
| --- | --- | --- |
| `packages` | `packages.yml` | Optional package install/remove |
| `system` | `system.yml` | Hostname and system settings |
| `wireless` | `wireless.yml` | 2.4/5 GHz wireless configuration |
| `access_control` | `access_control.yml` | GL.iNet admin panel, LuCI, and SSH access settings |
| `tls` | `tls.yml` | Certificate deployment |
| `ssh` | `ssh.yml` | Dropbear and authorized keys |
| `verify` | `verify.yml` | Post-apply validation |

Run a subset with Make or Ansible directly:

```bash
make tls
make ssh
ansible-playbook playbooks/site.yml --tags wireless,tls
```

Dry-run without applying changes:

```bash
make check
```

## Project layout

```
ansible.cfg                 # Inventory path, collections, SCP settings
requirements.yml            # community.openwrt and community.docker collections
pyproject.toml              # uv-managed Python dev dependencies and tox config
execution-environment.yml   # Ansible Builder EE definition
Makefile                    # install, lint, test, site, tag-specific targets

playbooks/
  site.yml                  # Full Flint 2 configuration
  ping.yml                  # SSH connectivity test

inventory/
  hosts.yml
  group_vars/
    openwrt.yml             # OpenWrt collection defaults, SCP -O for Dropbear
    flint2/main.yml         # Flint 2 device and service variables
  host_vars/router.yml      # ansible_host and Dropbear KEX options

roles/flint2/               # Main configuration role
  meta/argument_specs.yml   # Role variable validation
  molecule/default/         # Docker-based integration tests

tests/
  molecule/                 # Shared Molecule create/destroy playbooks
  test_project.py           # pytest project sanity checks

docs/
  Flint_2_AP_Installation_Guide_2026-08-01.md
  Flint_2_TLS_Certificate_Installation_Guide.md
  ansible_best_practices.md
```

## Dropbear and SCP

GL.iNet firmware ships Dropbear without an SFTP server. The [`community.openwrt.init`](https://docs.ansible.com/ansible/latest/collections/community/openwrt/init_module.html) module uploads files over SCP, so this project forces legacy SCP mode:

- [`ansible.cfg`](ansible.cfg) — `scp_extra_args = -O`
- [`inventory/group_vars/openwrt.yml`](inventory/group_vars/openwrt.yml) — `ansible_scp_extra_args: "-O"`

Without this, module transfer can fail and produce misleading errors (for example, `opkg` not found).

## TLS verification

When `flint2_tls_verify_endpoints` is enabled, the verify playbook checks TLS fingerprints on the router for nginx (443) and uHTTPd (8443) using `127.0.0.1` with the configured FQDN as SNI.

When `flint2_tls_verify_from_client` is enabled, fingerprints are also compared against the leaf certificate in `.env/`.

## Documentation

- [Flint 2 AP Installation Guide](docs/Flint_2_AP_Installation_Guide_2026-08-01.md) — physical setup, AP mode, pfSense DHCP, wireless
- [Flint 2 TLS Certificate Installation Guide](docs/Flint_2_TLS_Certificate_Installation_Guide.md) — private CA cert install on nginx and uHTTPd
- [Ansible best practices](docs/ansible_best_practices.md) — tooling reference for future development

## License

See repository defaults. Certificate and key material in `.env/` and `.secrets/` are local secrets and must not be committed.
