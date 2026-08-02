# Flint 2 TLS Certificate Installation Guide

This guide documents how to install a private-CA server certificate on both web interfaces of a GL.iNet Flint 2 (GL-MT6000) running GL.iNet firmware/OpenWrt.

## Environment

| Item | Value |
|---|---|
| Hostname | `wapap1003` |
| FQDN | `wapap1003.federation.lcars` |
| Management IP | `192.168.0.247` |
| GL.iNet web UI | `https://wapap1003.federation.lcars/` |
| LuCI web UI | `https://wapap1003.federation.lcars:8443/` |
| SSH username | `root` |
| Server certificate | `wapap1003.crt` |
| Private key | `wapap1003.key` |
| Intermediate CA | `Federation_LCARS_Intermediate_v002.crt` |
| Full-chain file | `wapap1003-fullchain.crt` |

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

## 2. Add the SSH host override

The Flint 2 uses Dropbear SSH. If the Mac's OpenSSH client cannot negotiate a key-exchange method, add this host-specific entry to `~/.ssh/config`:

```sshconfig
Host wapap1003 192.168.0.247
    HostName 192.168.0.247
    User root
    KexAlgorithms +curve25519-sha256,curve25519-sha256@libssh.org
    PubkeyAuthentication no
    PreferredAuthentications password
    PasswordAuthentication yes
```

Protect the configuration file:

```bash
chmod 600 ~/.ssh/config
```

Test the effective configuration:

```bash
ssh -G wapap1003 | grep -Ei \
  '^(hostname|user|kexalgorithms|pubkeyauthentication|preferredauthentications|passwordauthentication)'
```

Connect using the alias:

```bash
ssh wapap1003
```

Or connect by IP:

```bash
ssh root@192.168.0.247
```

### Equivalent one-time SSH command-line overrides

Without editing `~/.ssh/config`:

```bash
ssh \
  -o KexAlgorithms=+curve25519-sha256,curve25519-sha256@libssh.org \
  -o PubkeyAuthentication=no \
  -o PreferredAuthentications=password \
  -o PasswordAuthentication=yes \
  root@192.168.0.247
```

---

## 3. Transfer the certificate and key

Modern OpenSSH `scp` uses SFTP by default. The Flint's Dropbear installation may not include `/usr/libexec/sftp-server`, producing this error:

```text
ash: /usr/libexec/sftp-server: not found
scp: Connection closed
```

Force the legacy SCP protocol with uppercase `-O`.

### Using the SSH-config alias

```bash
scp -O \
  wapap1003.key \
  wapap1003-fullchain.crt \
  wapap1003:/tmp/
```

### Using one-time command-line overrides

```bash
scp -O \
  -o KexAlgorithms=+curve25519-sha256,curve25519-sha256@libssh.org \
  -o PubkeyAuthentication=no \
  -o PreferredAuthentications=password \
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

LuCI is served by uHTTPd on TCP port 8443.

### Confirm the configured certificate paths

```sh
uci get uhttpd.main.cert
uci get uhttpd.main.key
uci show uhttpd | grep listen_https
```

The standard paths are:

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

### Restart uHTTPd

```sh
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

A future GL.iNet firmware upgrade may replace the nginx or uHTTPd certificate files. After each firmware upgrade:

1. Check both HTTPS endpoints.
2. Confirm the expected certificate is still served.
3. Reinstall the certificate and key if the firmware restored vendor-generated files.
4. Recheck file ownership and permissions.
5. Restart nginx and uHTTPd.
