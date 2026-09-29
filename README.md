# flint2_ansible

Ansible automation for the [GL.iNet GL-MT6000 (Flint 2)](https://www.gl-inet.com/products/flint-2/) running GL.iNet firmware on OpenWrt. This project configures Access Point mode, wireless networks, TLS certificates, and SSH access using the [`community.openwrt`](https://galaxy.ansible.com/community/openwrt) collection.

Configuration is driven by UCI and shell-based modules — no Python runtime is required on the router.

## Features

- **System** — hostname, LuCI 24-hour clock (`clock_hourcycle=h23`), and AP-mode settings validated against live device state
- **Firmware** — GL.iNet Automatic Update Check disabled (`upgrade.general.upgrade_enable=0`)
- **Wireless** — 2.4 GHz and 5 GHz SSIDs via UCI sections (`radio0`/`default_radio0`, `radio1`/`default_radio1` on OP25)
- **LuCI** — installs bundled OP25 LuCI APKs, `uhttpd-mod-ucode`, and uHTTPd handler configuration
- **Statistics** — LuCI Statistics (`collectd`) with thermal and sensors graphs under **Statistics → Graphs**
- **Access Control** — GL.iNet admin panel, LuCI, and SSH ports, Force HTTPS, and auto-logout
- **TLS** — private CA certificates on nginx (GL.iNet UI, port 443) and uHTTPd (LuCI, port 8443)
- **SSH** — OpenSSH server with ssh-audit-hardened algorithms (PQ KEX, ETM MACs), password auth off, and `authorized_keys` management (replaces stock Dropbear)
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

Molecule tests provision an **OpenWrt 25.12.5** container aligned with the OP25 base release. The third-party reference image is `albrechtloh/openwrt-docker:openwrt-25.12.5-2bca120`; by default Molecule builds a local rootfs container from the official 25.12.5 tarball because the albrechtloh image runs OpenWrt inside QEMU and requires `/dev/kvm` (not available on Colima/macOS).

On Apple Silicon you need Colima with Rosetta emulation:

```bash
make colima-start    # starts Colima with --vm-type vz --vz-rosetta on arm64 Macs
make test-all        # or: make molecule
```

If Colima was previously started without Rosetta, stop it first (`colima stop`) and run `make colima-start` again.

When Colima is running, Make automatically sets `DOCKER_HOST` to `unix://$HOME/.colima/default/docker.sock`. Molecule builds and runs the 25.12.5 test image with `platform: linux/amd64`. To use a different runtime, set `DOCKER_HOST` yourself before running Molecule.

Optional environment variables:

| Variable | Purpose |
| --- | --- |
| `MOLECULE_OPENWRT_BACKEND=albrechtloh` | Use the albrechtloh QEMU image over SSH (Linux host with KVM) |
| `MOLECULE_OPENWRT_REBUILD=true` | Force rebuild of the local 25.12.5 rootfs image |
| `MOLECULE_OPENWRT_PRUNE_IMAGE=true` | Remove the local 25.12.5 image during `molecule destroy` |

The Molecule scenario seeds synthetic OP25-style wireless UCI sections (`radio0`/`default_radio0`, `radio1`/`default_radio1`), a `br-lan` bridge device section, GL.iNet-style `upgrade.general` and `oui-httpd.main` sections, and a stub `/etc/nginx/conf.d/gl.conf`. It also installs `chrony` so NTP converges through the same chronyd backend as GL.iNet firmware. Prepare also generates throwaway self-signed TLS material in the Molecule ephemeral directory. It then applies and verifies the `packages`, `system`, `ntp`, `network`, `wireless`, `upgrade`, `usteer`, `tls`, `luci`, `access_control`, `statistics`, and `ssh` task files; the `usteer`, `luci`, and `statistics` steps install packages from the OpenWrt 25.12.5 feeds, so the container needs outbound network access. TLS endpoint checks, nginx hardening, and other GL.iNet-specific checks are skipped in Docker; use `make check` and `make verify` against the real router for those.

## Secrets and certificates

Sensitive files live outside the repository and are listed in [`.gitignore`](.gitignore).

### Directory layout

```
.env/                          # Public certs and SSH public keys (gitignored)
  wapap1003.crt                # TLS leaf certificate
  Federation_LCARS_Intermediate_v002.crt
  id_ed25519.pub               # SSH authorized keys
  id_ed25519_v002.pub

.secrets/                      # Private keys and passphrases (gitignored)
  wapap1003.key
  ARGUS_wifi_password.env      # Main Wi-Fi passphrase (single line, no KEY=value)
  guest_passphrases.env        # Shared guest/IoT Wi-Fi passphrase (single line)

inventory/group_vars/flint2/
  main.yml                     # Device and service configuration
  vault.yml                    # Optional encrypted secrets (gitignored)
  vault.yml.example
```

The main wireless passphrase is read from `.secrets/ARGUS_wifi_password.env` via `flint2_wireless_key_file` (a role default, looked up by `flint2_wireless.key` in [`inventory/group_vars/flint2/main.yml`](inventory/group_vars/flint2/main.yml)). Guest and IoT SSIDs (kept disabled) use `.secrets/guest_passphrases.env` via `flint2_wireless_guest_key_file` with `sae-mixed` encryption so the GL.iNet factory `goodlife` / `psk2` defaults are replaced. Both secret files should contain the passphrase alone on one line. The inventory enables `ieee80211k` / `bss_transition`, and the role defaults install **usteer** for active AP-side band steering (`make usteer`).

### Bootstrap SSH (first run after reset)

Normal targets expect key-based SSH. After a factory reset or firmware upgrade, the stock **Dropbear** daemon has a temporary root password and no `authorized_keys` yet. The `ssh` role installs **OpenSSH**, deploys keys to `/root/.ssh/authorized_keys`, applies algorithm hardening, and disables Dropbear.

1. Clear stale host keys and any SSH ControlMaster still attached to the old daemon:

```bash
make known-hosts-reset
```

2. Create bootstrap connection settings:

```bash
cp inventory/bootstrap.yml.example .secrets/bootstrap.yml
# Edit ansible_ssh_pass to the current temporary root password
```

3. Run the playbook with password auth (installs OpenSSH + keys, then disables password login):

```bash
make ping-bootstrap
make check-bootstrap          # optional dry-run
make site-bootstrap           # full apply
# or a subset first:
make site-bootstrap TAGS=ssh
```

4. Confirm key-based access, then remove bootstrap credentials:

```bash
make ping
rm .secrets/bootstrap.yml
```

Bootstrap vars prefer password first, then publickey, so the first connection can use the temporary root password; after keys are installed and OpenSSH is cut over, later tasks reconnect with your Ed25519 key.

## Configuration

### Inventory

| Host | Group | Connection |
| --- | --- | --- |
| `router` | `flint2` → `openwrt` | `ansible_host: wapap1003` in [`inventory/host_vars/router.yml`](inventory/host_vars/router.yml) |

Adjust host name, FQDN, management IP, wireless SSID, and certificate file names in [`inventory/group_vars/flint2/main.yml`](inventory/group_vars/flint2/main.yml). That file holds only host-specific values; everything else comes from [`roles/flint2/defaults/main.yml`](roles/flint2/defaults/main.yml), documented in [`meta/argument_specs.yml`](roles/flint2/meta/argument_specs.yml). Override a variable in inventory only when it must differ from its default: `make pytest` fails if group_vars repeat a role default verbatim, or if a default is missing from, or disagrees with, the argument specs.

### Role tags

The [`flint2`](roles/flint2/) role is split into tagged task files:

| Tag | Task file | Purpose |
| --- | --- | --- |
| `packages` | `packages.yml` | Optional package install/remove |
| `system` | `system.yml` | Hostname, LuCI 24-hour clock |
| `upgrade` | `upgrade.yml` | GL.iNet Automatic Update Check (`upgrade.general.upgrade_enable`) |
| `ntp` | `ntp.yml` | Upstream NTP time synchronization (`pool.ntp.org` via chronyd) |
| `network` | `network.yml` | `br-lan` IGMP snooping + multicast querier (E1/E2) |
| `wireless` | `wireless.yml`, `wireless_iface_options.yml` | 2.4/5 GHz wireless configuration; per-radio wifi-iface overrides (`iface_options`) |
| `usteer` | `usteer.yml` | Active AP-side band steering (usteer + luci-app-usteer) |
| `luci` | `luci.yml` | Bundled LuCI APK install and uHTTPd ucode handler (OP25) |
| `access_control` | `access_control.yml` | GL.iNet admin panel, LuCI, and SSH access settings |
| `statistics` | `statistics.yml` | LuCI Statistics, collectd, and thermal/sensors plugins |
| `tls` | `tls.yml` | Certificate deployment |
| `nginx` | `nginx.yml` | GL.iNet nginx security headers / HSTS (`gl-conf.d`) |
| `ssh` | `ssh.yml` | OpenSSH hardening drop-in, keys; disables Dropbear |
| `always` | `apply.yml` | UCI commit, then reloads only the services whose configuration changed ([handlers](roles/flint2/handlers/main.yml)); runs with every partial Make target |
| `verify` | `verify.yml`, `verify_wireless_iface_options.yml` | Post-apply validation; per-radio wifi-iface override checks |

Partial Make targets (for example `make system`) pass `--tags <area>,always` so UCI changes are committed before verification.

Run a subset with Make or Ansible directly:

```bash
make tls
make nginx            # HSTS + security headers (F-07/F-09)
make ssh              # OpenSSH algorithm hardening + authorized_keys
make ssh-audit        # re-scan the live listener (requires ~/scripts/ssh-audit)
make access-control   # includes luci tag
make statistics       # LuCI Statistics thermal graphs
make usteer           # active AP-side band steering
make network          # br-lan IGMP snooping + multicast querier (E1/E2)
ansible-playbook playbooks/site.yml --tags wireless,tls,nginx,always
```

Dry-run without applying changes:

```bash
make check
```

Services are reloaded through handlers, so a run that changes nothing restarts nothing. In `make check`, the `RUNNING HANDLER` lines show which services a real run would reload; service handlers report `changed` without acting, and command-based ones (Wi-Fi reload, nginx) are skipped.

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
    openwrt.yml             # OpenWrt collection defaults, SCP -O (bootstrap/Dropbear safe)
    flint2/main.yml         # Host-specific overrides of role defaults
  host_vars/router.yml      # ansible_host and OpenSSH client algorithm args

roles/flint2/               # Main configuration role
  defaults/main.yml         # Default value for every role variable
  handlers/main.yml         # Change-driven service reloads
  meta/argument_specs.yml   # Role variable validation and documentation
  molecule/default/         # Docker-based integration tests

tests/
  molecule/                 # Shared Molecule create/destroy playbooks
  test_project.py           # pytest project sanity checks
  test_role_variables.py    # defaults ↔ argument_specs parity; no inventory duplicates or redundant fallbacks

docs/
  Flint_2_AP_Installation_Guide_2026-08-01.md
  Flint_2_TLS_Certificate_Installation_Guide.md
  ansible_best_practices.md
```

## SSH (OpenSSH) and SCP

GL.iNet OP25 ships **Dropbear** by default. This role sets `flint2_ssh_backend: openssh` and:

1. Installs `openssh-server`, `openssh-keygen`, `openssh-sftp-server`, and `dropbearconvert`
2. Deploys `/etc/ssh/sshd_config.d/99-flint2-hardening.conf` (ssh-audit OpenSSH 10.x suite: PQ KEX, AEAD/CTR ciphers, ETM-only MACs, ed25519 host key)
3. Installs root keys in `/root/.ssh/authorized_keys` and disables password auth
4. Disables Dropbear (`dropbear.main.enable=0`) and binds sshd to the management IP
5. Reloads sshd with a post-bounce `wait_for_connection` so Ansible reconnects cleanly

Inventory client args in [`inventory/host_vars/router.yml`](inventory/host_vars/router.yml) match the server suite and set `ControlMaster=no` so a mux cannot hold an old Dropbear session across cutover. After firmware reset, run `make known-hosts-reset` (also exits stale ControlMaster sockets).

Re-audit after changes:

```bash
make ssh
make ssh-audit          # SSH_AUDIT_HOST=192.168.0.247 by default
```

Independent checks (not your local `~/.ssh/config`): `nmap -p 22 --script ssh2-enum-algos <host>` or `uvx --from ssh-audit ssh-audit --skip-rate-test <host>`.

### SCP during bootstrap

Stock Dropbear has no SFTP server. Until OpenSSH is cut over, Ansible and manual `scp` need legacy SCP (`-O`):

- [`ansible.cfg`](ansible.cfg) — `scp_extra_args = -O`
- [`inventory/group_vars/openwrt.yml`](inventory/group_vars/openwrt.yml) — `ansible_ssh_transfer_method: scp` and `ansible_scp_extra_args: "-O"`

Those settings remain after OpenSSH is installed so bootstrap and day-2 runs share one inventory. With OpenSSH’s `sftp-server` present, SFTP would also work; keeping `-O` avoids a Dropbear-only bootstrap path.

`playbooks/ping.yml` includes the `community.openwrt.init` role so connection settings match `site.yml`.

## TLS verification

When `flint2_tls_verify_endpoints` is enabled, the verify playbook checks TLS fingerprints on the router for nginx (443) and uHTTPd (8443) using `127.0.0.1` with the configured FQDN as SNI.

When `flint2_tls_verify_from_client` is enabled, fingerprints are also compared against the leaf certificate in `.env/`.

## Documentation

- [Flint 2 AP Installation Guide](docs/Flint_2_AP_Installation_Guide_2026-08-01.md) — physical setup, AP mode, pfSense DHCP, wireless, OP25 notes, Ansible automation
- [Flint 2 TLS Certificate Installation Guide](docs/Flint_2_TLS_Certificate_Installation_Guide.md) — private CA cert install on nginx and uHTTPd (manual or `make tls`)
- [Ansible best practices](docs/ansible_best_practices.md) — tooling reference for future development

## License

See repository defaults. Certificate and key material in `.env/` and `.secrets/` are local secrets and must not be committed.
