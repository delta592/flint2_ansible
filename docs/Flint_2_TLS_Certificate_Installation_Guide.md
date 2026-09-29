# Flint 2 TLS Certificate Installation Guide

This guide documents how to install a private-CA server certificate on both web interfaces of a GL.iNet Flint 2 (GL-MT6000) running GL.iNet firmware/OpenWrt.

**Ansible automation:** When `.env/` and `.secrets/` contain the certificate files listed below, run `make tls` and `make verify` from the repository root instead of the manual steps in sections 3–8. See the [README](../README.md#secrets-and-certificates) and [`inventory/group_vars/flint2/main.yml`](../inventory/group_vars/flint2/main.yml) for file names and paths. The role builds the full chain on the control node, copies it and the key straight to the nginx and uHTTPd paths (a file is rewritten only when its checksum differs), and first backs up each installed file it is about to replace to `<path>.<backup suffix>`; nginx and uHTTPd restart only when their files change.

## Environment

| Item | Value |
|---|---|
| Hostname | `wapap1003` |
| FQDN | `wapap1003.federation.lcars` |
| Management IP | `192.168.0.247` |
| GL.iNet firmware | `4.9.1-op25` (OpenWrt `25.12.5`) |
| GL.iNet web UI | `https://wapap1003.federation.lcars/` (nginx, port 443) |
| LuCI web UI | `https://wapap1003.federation.lcars:8443/` (uHTTPd, port 8443) |
| LuCI HTTP (redirect) | port `8080` |
| SSH username | `root` |
| Server certificate | `wapap1003.crt` (in `.env/`) |
| Private key | `wapap1003.key` (in `.secrets/`) |
| Intermediate CA | `Federation_LCARS_Intermediate_v002.crt` (in `.env/`) |
| Full-chain file | `wapap1003-fullchain.crt` (built on control node) |
| nginx cert/key on router | `/etc/nginx/nginx.cer`, `/etc/nginx/nginx.key` |
| uHTTPd cert/key on router | `/etc/uhttpd.crt`, `/etc/uhttpd.key` |
| TLS backup suffix (Ansible) | `pre-wapap1003` |

The certificate should contain these Subject Alternative Names:

```text
DNS:wapap1003.federation.lcars
DNS:wapap1003
IP:192.168.0.247
```

---

## 1. Build the full certificate chain

Run this on the Mac from the directory containing the certificate files:

```bash
cat wapap1003.crt Federation_LCARS_Intermediate_v002.crt \
  > wapap1003-fullchain.crt
```

The leaf/server certificate must appear first, followed by the intermediate certificate.

### Verify the certificate and key match

```bash
openssl x509 -in wapap1003.crt -pubkey -noout |
  openssl sha256

openssl pkey -in wapap1003.key -pubout |
  openssl sha256
```

The two SHA-256 values must be identical.

### Inspect the certificate

```bash
openssl x509 \
  -in wapap1003.crt \
  -noout \
  -subject \
  -issuer \
  -dates \
  -ext subjectAltName
```

---

## 2. SSH access (bootstrap vs day-2)

After Ansible (`make ssh` / `make site`), the Flint runs **OpenSSH 10.x** with an ssh-audit-hardened algorithm suite (PQ KEX, ETM MACs, ed25519 host key). Stock **Dropbear** is disabled.

### Day-2 (key-based OpenSSH)

```bash
make known-hosts-reset   # after firmware reset or host-key change; also exits ControlMaster
ssh root@192.168.0.247
# or:
ssh wapap1003
```

Ansible client options in [`inventory/host_vars/router.yml`](../inventory/host_vars/router.yml) already match the server suite. SSH multiplexing stays on for speed; each post-bounce `wait_for_connection` stops the mux, so it cannot hold an old Dropbear session across cutover.

### Bootstrap (factory Dropbear + temporary password)

Only needed before OpenSSH cutover. Copy [`inventory/bootstrap.yml.example`](../inventory/bootstrap.yml.example) to `.secrets/bootstrap.yml` for Ansible, or use a one-shot client config that still allows Dropbear’s older KEX:

```sshconfig
Host wapap1003-bootstrap 192.168.0.247
    HostName 192.168.0.247
    User root
    KexAlgorithms +curve25519-sha256,curve25519-sha256@libssh.org
    PreferredAuthentications password,publickey
    PasswordAuthentication yes
```

See [README → Bootstrap SSH](../README.md#bootstrap-ssh-first-run-after-reset).

Protect the configuration file:

```bash
chmod 600 ~/.ssh/config
```

Test the effective configuration:

```bash
ssh -G wapap1003 | grep -Ei \
  '^(hostname|user|kexalgorithms|hostkeyalgorithms|ciphers|macs|pubkeyauthentication|preferredauthentications|passwordauthentication)'
```

### Equivalent one-time bootstrap SSH command-line overrides

```bash
ssh \
  -o KexAlgorithms=+curve25519-sha256,curve25519-sha256@libssh.org \
  -o PreferredAuthentications=password,publickey \
  -o PasswordAuthentication=yes \
  root@192.168.0.247
```

After `make ssh`, prefer key auth only (password auth is disabled on the OpenSSH server).

---

## 3. Transfer the certificate and key

Modern OpenSSH `scp` uses SFTP by default. **Before** OpenSSH cutover, stock Dropbear may not include `/usr/libexec/sftp-server`, producing:

```text
ash: /usr/libexec/sftp-server: not found
scp: Connection closed
```

Force the legacy SCP protocol with uppercase `-O` for bootstrap/manual transfers. After `make ssh`, OpenSSH’s SFTP server is installed; Ansible still keeps `-O` in inventory so bootstrap and day-2 share one path.

Ansible in this repository already sets `scp -O` via [`ansible.cfg`](../ansible.cfg) and [`inventory/group_vars/openwrt.yml`](../inventory/group_vars/openwrt.yml). Manual `scp` still needs `-O` explicitly when talking to Dropbear.

### Using the SSH-config alias

```bash
scp -O \
  wapap1003.key \
  wapap1003-fullchain.crt \
  wapap1003:/tmp/
```

### Using one-time command-line overrides (bootstrap / Dropbear)

```bash
scp -O \
  -o KexAlgorithms=+curve25519-sha256,curve25519-sha256@libssh.org \
  -o PreferredAuthentications=password,publickey \
  -o PasswordAuthentication=yes \
  wapap1003.key \
  wapap1003-fullchain.crt \
  root@192.168.0.247:/tmp/
```

`-O` is an uppercase letter **O**, not zero.

---

## 4. Verify the transferred files

SSH into the Flint:

```bash
ssh wapap1003
```

Confirm both files exist:

```sh
ls -l /tmp/wapap1003.key /tmp/wapap1003-fullchain.crt
```

Verify the private key:

```sh
openssl pkey -in /tmp/wapap1003.key -noout -check
```

Inspect the certificate:

```sh
openssl x509 \
  -in /tmp/wapap1003-fullchain.crt \
  -noout \
  -subject \
  -issuer \
  -dates \
  -ext subjectAltName
```

Verify the key matches the leaf certificate:

```sh
openssl x509 -in /tmp/wapap1003-fullchain.crt -pubkey -noout |
  openssl sha256

openssl pkey -in /tmp/wapap1003.key -pubout |
  openssl sha256
```

The hashes must match.

---

## 5. Install the certificate for the GL.iNet web UI

The GL.iNet UI is served by nginx on TCP port 443.

### Back up the existing certificate and key

```sh
cp -p /etc/nginx/nginx.cer /etc/nginx/nginx.cer.pre-wapap1003
cp -p /etc/nginx/nginx.key /etc/nginx/nginx.key.pre-wapap1003
```

### Install the new files

```sh
cp /tmp/wapap1003-fullchain.crt /etc/nginx/nginx.cer
cp /tmp/wapap1003.key /etc/nginx/nginx.key

chown root:root /etc/nginx/nginx.cer /etc/nginx/nginx.key
chmod 644 /etc/nginx/nginx.cer
chmod 600 /etc/nginx/nginx.key
```

### Validate and restart nginx

```sh
nginx -t
```

Only continue if the validation succeeds:

```sh
/etc/init.d/nginx restart
```

Test in a browser:

```text
https://wapap1003.federation.lcars/
```

---

## 6. Install the certificate for LuCI

LuCI is served by uHTTPd on TCP port **8443** (HTTP on **8080**).

### OP25 prerequisites

On **4.9.1-op25** after a factory reset:

1. **Install LuCI** — bundled APKs under `/etc/luci_ipks/` via **GL.iNet UI → Applications → LuCI**, or run `make access-control` / `make site` (installs `luci-base`, `uhttpd-mod-ucode`, and related packages).
2. **Enable uHTTPd** — OP25 ships with `uhttpd.main.enabled='0'` until LuCI is initialized. uHTTPd must be enabled or nothing listens on 8443.
3. Without LuCI installed, `https://…:8443/cgi-bin/luci/` returns **404 Not Found** even if uHTTPd is running.

### Confirm the configured certificate paths and listeners

```sh
uci get uhttpd.main.enabled
uci get uhttpd.main.cert
uci get uhttpd.main.key
uci show uhttpd | grep listen
```

Expected listen values (Ansible / Access Control defaults):

```text
uhttpd.main.listen_http='0.0.0.0:8080' '[::]:8080'
uhttpd.main.listen_https='0.0.0.0:8443' '[::]:8443'
```

The standard certificate paths are:

```text
/etc/uhttpd.crt
/etc/uhttpd.key
```

### Back up the existing certificate and key

```sh
cp -p /etc/uhttpd.crt /etc/uhttpd.crt.pre-wapap1003
cp -p /etc/uhttpd.key /etc/uhttpd.key.pre-wapap1003
```

### Install the new files

```sh
cp /tmp/wapap1003-fullchain.crt /etc/uhttpd.crt
cp /tmp/wapap1003.key /etc/uhttpd.key

chown root:root /etc/uhttpd.crt /etc/uhttpd.key
chmod 644 /etc/uhttpd.crt
chmod 600 /etc/uhttpd.key
```

### Enable uHTTPd, commit, and restart

```sh
uci set uhttpd.main.enabled='1'
uci commit uhttpd
/etc/init.d/uhttpd restart
```

Test in a browser:

```text
https://wapap1003.federation.lcars:8443/
```

---

## 7. Verify both TLS endpoints from macOS

### GL.iNet UI on port 443

```bash
openssl s_client \
  -connect wapap1003.federation.lcars:443 \
  -servername wapap1003.federation.lcars \
  -showcerts </dev/null
```

### LuCI on port 8443

```bash
openssl s_client \
  -connect wapap1003.federation.lcars:8443 \
  -servername wapap1003.federation.lcars \
  -showcerts </dev/null
```

A successful result should include:

```text
Verification: OK
Verify return code: 0 (ok)
```

### Concise certificate inspection

Port 443:

```bash
openssl s_client \
  -connect wapap1003.federation.lcars:443 \
  -servername wapap1003.federation.lcars \
  </dev/null 2>/dev/null |
openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

Port 8443:

```bash
openssl s_client \
  -connect wapap1003.federation.lcars:8443 \
  -servername wapap1003.federation.lcars \
  </dev/null 2>/dev/null |
openssl x509 -noout -subject -issuer -dates -ext subjectAltName
```

---

## 8. Remove temporary copies

After both web interfaces have been verified:

```sh
rm -f /tmp/wapap1003.key /tmp/wapap1003-fullchain.crt
```

Retain the original certificate, private key, intermediate certificate, and full-chain file on a secured administrative system.

---

## 9. Reboot verification

Reboot the Flint:

```sh
reboot
```

After it returns, verify:

```text
https://wapap1003.federation.lcars/
https://wapap1003.federation.lcars:8443/
```

You can also rerun both `openssl s_client` tests.

---

## 10. Important maintenance note

A future GL.iNet firmware upgrade may replace the nginx or uHTTPd certificate files, disable uHTTPd, or remove LuCI packages. After each firmware upgrade:

1. Check both HTTPS endpoints.
2. Confirm the expected certificate is still served.
3. Reinstall LuCI if `/cgi-bin/luci/` returns 404 (see [section 6](#6-install-the-certificate-for-luci)).
4. Reinstall the certificate and key if the firmware restored vendor-generated files (`make tls` or manual steps).
5. Confirm `uhttpd.main.enabled='1'` and run `uci commit` before restarting services.
6. Recheck file ownership and permissions.
7. Restart nginx and uHTTPd.

Re-run `make site` or `make verify` to confirm Ansible-managed TLS fingerprints match the installed leaf certificate.
