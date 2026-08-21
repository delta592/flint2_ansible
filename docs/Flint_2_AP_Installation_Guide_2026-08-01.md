# GL.iNet Flint 2 (GL-MT6000) Access Point Installation Guide

This guide documents the successful setup performed on August 1, 2026, beginning with a factory reset and ending with a working Flint 2 access point on the existing pfSense-managed LAN.

It was updated in August 2026 after upgrading to **GL.iNet firmware 4.9.1-op25** (OpenWrt **25.12.5**) and validating the [`flint2_ansible`](../README.md) playbooks against the live device.

## Final working configuration

| Item | Value |
|---|---|
| Device | GL.iNet Flint 2 / GL-MT6000 |
| GL.iNet firmware | `4.9.1-op25` |
| OpenWrt base | `25.12.5` (shown in LuCI status) |
| Package manager | `apk` (not `opkg` on OP25) |
| Operating mode | Access Point |
| Hostname | `wapap1003` |
| FQDN | `wapap1003.federation.lcars` |
| Management IP | `192.168.0.247` |
| IP assignment | pfSense DHCP static mapping |
| pfSense gateway | `192.168.0.250` |
| pfSense DHCP hostname | `gl-mt6000` |
| Uplink port | Dedicated WAN / WAN1 (`eth1`) |
| Uplink speed | 2.5GbE |
| LAN bridge MAC (pfSense mapping) | `94:83:c4:e3:f4:31` |
| Main SSID | `ARGUS` |
| 2.4 GHz radio / iface (UCI) | `radio0` / `default_radio0` |
| 5 GHz radio / iface (UCI) | `radio1` / `default_radio1` |
| 2.4 GHz mode | `11n/ax` (`htmode HE40`, `require_mode n`) |
| 2.4 GHz channel width | 20/40 MHz |
| 5 GHz mode | `11n/ac/ax` (`htmode HE160`, `require_mode n`) |
| 5 GHz channel width | 160 MHz |
| Security | WPA2-PSK/WPA3-SAE mixed mode (`sae-mixed`) |
| NTP upstream | `pool.ntp.org` via `chronyd` |
| Thermal monitoring | LuCI Statistics (`collectd-mod-thermal` / `collectd-mod-sensors`) |
| LuCI time format | 24-Hour Clock (`system.@system[0].clock_hourcycle=h23`) |
| GL.iNet UI | `https://wapap1003.federation.lcars/` (nginx, port 443) |
| LuCI HTTP / HTTPS | ports `8080` / `8443` (uHTTPd) |
| LuCI | `https://wapap1003.federation.lcars:8443/` |
| SSH | `root@wapap1003` port 22, public-key only (after Ansible) |

### Ansible-managed settings

After manual prerequisites (sections 1–8), [`make site`](../README.md#quick-start) in this repository applies and verifies the values above. See [section 19](#19-ansible-automation) for bootstrap SSH and tag-specific runs.

---

## 1. Factory-reset the Flint 2

1. Leave the Flint powered on.
2. Press and hold the recessed reset button for about 10 seconds.
3. Release the button.
4. Wait for the Flint to reboot completely.
5. Do not remove power during the reset.

For the initial recovery/setup connection:

```text
MacBook Air Ethernet → Flint LAN2
House LAN switch     → Flint WAN1
```

The MacBook Wi-Fi was left enabled but disconnected.

---

## 2. Reach the factory web interface

The MacBook unexpectedly continued receiving an address from the upstream `192.168.0.0/24` LAN, so a temporary manual address was used.

Configure the MacBook Ethernet interface as:

```text
IP address: 192.168.8.77
Subnet mask: 255.255.255.0
Gateway: 192.168.8.1
```

Then open:

```text
https://192.168.8.1
```

This reached the Flint factory web interface.

---

## 3. Complete the mandatory first-run wizard

The first-run wizard could not be bypassed.

Complete these steps:

1. Create a new GL.iNet administrator password.
2. Accept the default SSID names and Wi-Fi passwords temporarily.
3. Allow the wizard to apply its settings.
4. When the separate **Network Guide** appears, choose **Exit**.

Do not make advanced LuCI changes during this stage.

---

## 4. Diagnose the WAN uplink

When attempting to enable Access Point mode, the Flint reported:

```text
To setup Access Point mode, you need to connect an Ethernet cable to the WAN port first.
```

In the GL.iNet interface, the status initially showed:

```text
Ethernet1 / WAN: No cable detected
```

### Validate the upstream network

The cable was removed from Flint WAN1 and connected directly to the MacBook.

The MacBook was changed back to DHCP and received:

```text
IP address: 192.168.0.76/24
Gateway: 192.168.0.250
```

This confirmed:

- The Buffalo BS-MP2012 switch port worked.
- The Ethernet cable worked.
- pfSense DHCP worked.
- The upstream LAN was healthy.

### Test the second 2.5GbE port

The cable was then connected to:

```text
WAN2 / LAN1
```

The GL.iNet UI showed:

```text
Ethernet2
DHCP address: 192.168.0.77
Link speed: 2.5GbE
```

This confirmed the Flint could negotiate 2.5GbE.

However, the GL.iNet Access Point wizard explicitly required the dedicated WAN port and rejected WAN2/LAN1 as the AP uplink.

### Reconnect WAN1

The cable was moved back from WAN2/LAN1 to the dedicated WAN1 port.

At that point WAN1 successfully renegotiated at:

```text
2.5GbE
```

The earlier failure appears to have been a transient link-negotiation or initialization issue.

---

## 5. Enable Access Point mode

With WAN1 now showing a valid 2.5GbE connection:

1. Open the GL.iNet web interface.
2. Go to:

```text
Network → Network Mode
```

3. Select:

```text
Access Point
```

4. Click **Apply**.
5. Allow the Flint to reboot.

The house LAN cable remained in the dedicated WAN1 port.

After AP mode was applied, pfSense leased an address to the Flint WAN-side/AP MAC.

---

## 6. Find and access the AP management address

pfSense initially assigned:

```text
192.168.0.75
```

The Flint web UI became reachable at:

```text
http://192.168.0.75/
```

The previously created administrator password worked.

LuCI was reachable at:

```text
https://192.168.0.75:8443/
```

The HTTP LuCI endpoint on port 8080 may redirect to HTTPS. HTTPS on port 8443 is the preferred LuCI endpoint.

On **OP25 firmware after a factory reset**, LuCI is not fully installed until you enable it from **GL.iNet UI → Applications → LuCI** or run the Ansible `luci` tasks (see [section 19](#19-ansible-automation)). Until then, uHTTPd may respond on port 8443 with `404` for `/cgi-bin/luci/`.

---

## 7. Create a fixed management address in pfSense

An attempt was made to configure a static address directly in LuCI.

LuCI showed:

```text
Interface: LAN
Device: br-lan
Current address: 192.168.0.75/24
Protocol: Static address
```

Changing the protocol caused a LuCI JavaScript error:

```text
TypeError
can't access property 0, addr is null
```

The pending LuCI changes were dismissed/reverted.

The safer working solution was to leave the Flint as a DHCP client and create a DHCP static mapping in pfSense.

### pfSense static mapping

Create a static mapping for:

```text
IP address: 192.168.0.247
Hostname: gl-mt6000
MAC address: 94:83:c4:e3:f4:31
```

The MAC matched the Flint `br-lan` MAC shown in LuCI.

After rebooting or renewing the lease, the Flint became reachable at:

```text
http://192.168.0.247/
```

This became the permanent management address.

Do not attempt to assign the same static address again in LuCI. The pfSense reservation already provides a fixed address while keeping IP management centralized.

---

## 8. Upgrade the GL.iNet firmware

The firmware upgrade was performed before finalizing the SSIDs.

Use:

```text
GL.iNet UI → System → Upgrade
```

Upgrade the GL.iNet firmware only.

Important:

- GL.iNet firmware is a customized OpenWrt build.
- LuCI is an alternate administration interface into the same firmware.
- Do not separately flash upstream OpenWrt from LuCI unless intentionally replacing GL.iNet firmware entirely.
- On **OP25** builds (OpenWrt **25.12.5**), the package manager is **`apk`**. Do not bulk-upgrade packages with legacy **`opkg`** instructions from older guides.
- The LuCI status page shows the current OpenWrt base (for example **25.12.5** on firmware **4.9.1-op25**). This is informational; continue using **GL.iNet UI → System → Upgrade** for firmware updates.

After the upgrade, verify:

- AP mode remains enabled.
- WAN1 remains at 2.5GbE.
- The AP remains reachable at `192.168.0.247`.
- pfSense remains the DHCP server.
- LuCI is installed and reachable at HTTPS port 8443 (see OP25 note in [section 6](#6-find-and-access-the-ap-management-address)).

---

## 9. Back up the Flint configuration

Use LuCI:

```text
System → Backup / Flash Firmware
```

Then choose:

```text
Generate archive
```

Save the `.tar.gz` backup and include the firmware version in the filename.

Example:

```text
wapap1003-glinet-4.9.1-op25-2026-08-10.tar.gz
```

Restore a backup only to the same or a clearly compatible firmware version.

---

## 10. Set the hostname and LuCI time format

Use LuCI for the system hostname because the GL.iNet interface does not expose it clearly.

Navigate to:

```text
System → System → General Settings
```

Set:

```text
Hostname: wapap1003
Time Format: 24-Hour Clock
```

The time format is stored as UCI option `system.@system[0].clock_hourcycle=h23`.

Then click:

```text
Save & Apply
```

Alternatively, run `make site` or `make system` from this repository (see [section 19](#19-ansible-automation)).

Use the GL.iNet interface for settings it exposes. Use LuCI only for settings absent from the GL.iNet interface.

---

## 11. Configure the wireless networks

All SSIDs were changed to:

```text
ARGUS
```

A strong random passphrase was generated offline and stored in 1Password.

### 2.4 GHz settings

Use:

```text
SSID: ARGUS
Mode: 11n/ax
Channel width: 20/40 MHz
Security: WPA2-PSK/WPA3-SAE mixed mode
```

`11n/ax` was selected to retain compatibility with the ecobee while avoiding obsolete 802.11b / 802.11g rates.

### 5 GHz settings

Use:

```text
SSID: ARGUS
Mode: 11n/ac/ax
Bandwidth: 160 MHz
Security: WPA2-PSK/WPA3-SAE mixed mode
```

`11n/ac/ax` excludes older 802.11a clients while retaining Wi-Fi 5 and Wi-Fi 6 support.

### 160 MHz versus 80 MHz

160 MHz provides higher peak throughput for compatible clients but uses twice as much spectrum and can be more sensitive to DFS/radar events or client quirks.

80 MHz is more conservative and usually more stable.

The final configuration used:

```text
160 MHz
```

If instability appears, reduce the 5 GHz width to 80 MHz.

### Security mode

The final Personal-mode setting was:

```text
WPA2-PSK/WPA3-SAE mixed mode
```

This permits newer clients to use WPA3-SAE while retaining WPA2 compatibility.

### 802.11k / 802.11v BSS Transition

Both main ARGUS interfaces (`default_radio0` / `default_radio1`) enable:

```text
ieee80211k: 1
bss_transition: 1
```

- **802.11k** advertises Radio Resource Measurement (neighbor and beacon reports) so clients can discover better BSS candidates.
- **802.11v BSS Transition** lets the AP request that a client move to another BSS (for example 2.4 GHz ↔ 5 GHz on the same SSID).

Ansible applies these via `flint2_wireless.ieee80211k` and `flint2_wireless.bss_transition` in [`inventory/group_vars/flint2/main.yml`](../inventory/group_vars/flint2/main.yml).

### Active AP-side steering (usteer)

GL.iNet stock firmware does not include band steering. Ansible installs OpenWrt **usteer** (plus optional **luci-app-usteer**) and configures it for single-AP 2.4/5 GHz steering on the ARGUS SSID:

```text
network: lan
local_mode: 1
band_steering_interval: 30000
band_steering_min_snr: -60
ssid_list: ARGUS
```

`local_mode: 1` disables multi-AP coordination (appropriate for one Flint 2). Set `local_mode: 0` if additional OpenWrt APs should exchange steering state over the LAN.

Apply with `make usteer` (or `make wireless`, which includes the usteer tag). Package install requires `usteer` / `luci-app-usteer` to be available in the device feeds (`apk` on OP25). After install, Ansible clears the LuCI index/module cache and restarts `rpcd` / `uhttpd` so **Network → Usteer** appears without a manual LuCI cache flush.

LuCI also exposed:

```text
WPA2-EAP
WPA3-EAP
WPA2-EAP/WPA3-EAP Mixed Mode
```

This confirms the installed build can expose WPA3-Enterprise options, but Enterprise configuration was not completed during this setup.

---

## 12. Validate wireless clients

The following devices were successfully connected:

- MacBook Air
- iPhone
- ecobee

Successful connection of all three confirmed:

- 2.4 GHz operation
- 5 GHz operation
- Shared SSID behavior
- WPA2/WPA3 mixed-mode compatibility
- pfSense DHCP relay through the Flint AP
- Internet and LAN access through the AP

Expected client settings:

```text
IP address: 192.168.0.x
Subnet mask: 255.255.255.0
Gateway: 192.168.0.250
DHCP server: pfSense
```

---

## 13. 1Password router entry

For the 1Password router template:

```text
Base station address:
https://wapap1003.federation.lcars/

Base station password:
GL.iNet administrator password

Wireless network name:
ARGUS

Wireless network password:
The generated Wi-Fi passphrase
```

LuCI details can be stored in Notes:

```text
LuCI:
https://wapap1003.federation.lcars:8443/

Username:
root
```

---

## 14. TLS certificate and SSH configuration

A separate detailed guide was created for:

- Creating the full certificate chain
- Installing the TLS certificate on nginx
- Installing the TLS certificate on uHTTPd/LuCI
- Verifying ports 443 and 8443
- Dropbear/OpenSSH key-exchange overrides
- Password-only bootstrap access
- Legacy SCP mode using `scp -O`
- SSH public-key authentication
- Disabling password fallback client-side
- Clearing SSH ControlMaster sessions

Insert or link that guide here:

[Flint_2_TLS_Certificate_Installation_Guide.md](Flint_2_TLS_Certificate_Installation_Guide.md)

Or apply TLS with Ansible:

```bash
make tls
make verify
```

Final validated HTTPS endpoints:

```text
https://wapap1003.federation.lcars/
https://wapap1003.federation.lcars:8443/
```

Both endpoints were verified with:

```text
Verify return code: 0 (ok)
```

---

## 15. Validate SSH public-key-only login

The SSH test used:

```bash
ssh -O exit wapap1003 2>/dev/null || true
ssh -vvv \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey \
  -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no \
  wapap1003
```

The decisive result was:

```text
Authenticated to 192.168.0.247 ([192.168.0.247]:22) using "publickey".
```

This proved the login succeeded using the Ed25519 key and did not fall back to password authentication.

The Dropbear server still advertised password authentication as available server-side, but the client test explicitly prohibited using it.

---

## 16. Current administration boundaries

Use the GL.iNet interface for:

- Firmware upgrades
- AP/router mode
- SSID names
- Wi-Fi passwords
- Wireless channels and widths
- WPA2/WPA3 Personal security
- LED and vendor-specific settings
- GL.iNet applications

Use LuCI for:

- Hostname
- Time format (24-hour clock)
- Logs and diagnostics
- Configuration backups
- Interface inspection
- Advanced wireless security such as EAP
- Settings not exposed in the GL.iNet interface

Use pfSense for:

- DHCP
- Static DHCP mappings
- DNS
- Routing
- Firewalling
- VLAN policy
- RADIUS, if later configured

Avoid editing the same feature in both GL.iNet and LuCI.

---

## 17. Final validation checklist

Confirm all of the following:

- [x] Flint is in Access Point mode.
- [x] WAN1 negotiates at 2.5GbE.
- [x] pfSense is the only DHCP server.
- [x] Flint management IP is `192.168.0.247`.
- [x] pfSense static mapping is present.
- [x] Hostname is `wapap1003`.
- [x] LuCI time format is 24-Hour Clock.
- [x] FQDN resolves to `192.168.0.247`.
- [x] GL.iNet UI opens securely over HTTPS.
- [x] LuCI opens securely over HTTPS on port 8443.
- [x] LuCI packages installed (OP25 bundled APKs + uhttpd-mod-ucode).
- [x] TLS chain validates successfully.
- [x] SSH public-key authentication works.
- [x] 2.4 GHz clients connect.
- [x] 5 GHz clients connect.
- [x] ecobee connects.
- [x] iPhone connects.
- [x] MacBook Air connects.
- [x] SSID is `ARGUS`.
- [x] Wi-Fi passphrase is stored in 1Password.
- [x] NTP upstream is `pool.ntp.org` (chronyd).
- [x] LuCI Statistics thermal graphs are available (**Statistics → Graphs**).
- [x] Configuration backup has been created.

---

## 18. Firmware caution

The LuCI overview reports the **current** OpenWrt base bundled with GL.iNet firmware (for example **OpenWrt 25.12.5** on **4.9.1-op25**).

Do not flash a different upstream OpenWrt image through LuCI merely because you want a newer upstream release.

Doing so would replace the complete GL.iNet firmware and remove the GL.iNet interface and vendor integrations.

For now:

- Continue using **GL.iNet UI → System → Upgrade**.
- Keep the AP behind pfSense.
- Restrict management access to trusted LAN systems.
- Retain backups and certificate-installation notes.
- Re-evaluate official OpenWrt migration separately if desired later.

---

## 19. Ansible automation

This repository automates post-prerequisite configuration. Inventory values live in [`inventory/group_vars/flint2/main.yml`](../inventory/group_vars/flint2/main.yml).

### First run after factory reset (bootstrap SSH)

Dropbear has a temporary root password and no `authorized_keys` until the `ssh` role runs:

```bash
cp inventory/bootstrap.yml.example .secrets/bootstrap.yml
# Edit ansible_ssh_pass, then:
make ping-bootstrap
make site-bootstrap
make ping          # confirm key-based login
rm .secrets/bootstrap.yml
```

See the [README](../README.md#bootstrap-ssh-first-run-after-reset) for details.

### Routine apply and verify

```bash
make site          # full configuration
make verify        # post-apply checks (includes TLS when enabled)
```

Partial targets automatically run the `always`-tagged UCI commit/apply step (for example `make system`, `make wireless`).

| Make target | Ansible tags | Purpose |
|---|---|---|
| `make system` | `system,always` | Hostname, 24-hour clock |
| `make wireless` | `wireless,always` | ARGUS SSID, radio options, and usteer (usteer tag included) |
| `make usteer` | `usteer,always` | Install/configure usteer active band steering |
| `make ntp` | `ntp,always` | chronyd upstream NTP |
| `make statistics` | `statistics,always` | LuCI Statistics thermal/sensors graphs |
| `make access-control` | `access_control,luci,always` | Admin/LuCI ports, LuCI install |
| `make tls` | `tls,always` | nginx + uHTTPd certificates |
| `make ssh` | `ssh,always` | Dropbear hardening and keys |

Wireless UCI on OP25 uses `radio0`/`default_radio0` and `radio1`/`default_radio1` (not legacy GL.iNet names `mt798611`/`wifi2g`).
