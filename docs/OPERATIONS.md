# Operations (Simplified, Least‑Privilege)

This document describes a simplified operational workflow for running a Wyse 5070 + USB DAC as an AirPlay 2 receiver. There is no periodic, root‑run GitOps loop. Privileged work is limited to one‑time setup and on‑demand config application.

## Overview
- Install once with `bin/setup` (root): installs packages, writes `/etc/shairport-sync.conf`, installs hardened shairport override, enables nqptp + shairport.
- Apply config changes with `bin/apply` (root) when name or ALSA settings change.
- Shairport runs as its vendor user with a hardened systemd override. NQPTP runs via its vendor unit.

## Prerequisites (Device)
- Debian 13 preferred (APT provides `shairport-sync` with AirPlay 2 and `nqptp`).
- Repository cloned to `/opt/airplay_wyse`.

## Setup
Run once (as root):
```
sudo ./bin/setup
```
Options:
- Default device name is "Wyse DAC".
- ALSA device is auto‑detected via `bin/alsa-probe` (falls back to `hw:0,0`).

## Update Configuration
Apply new name or ALSA settings (as root):
```
sudo ./bin/apply --name "Living Room"
sudo ./bin/apply --device hw:0,0 --mixer PCM
```

## Optional Host Inventory
For environments with multiple similar hosts, `bin/alsa-probe` continues to honor optional hints at `inventory/hosts/<short-hostname>.yml`:
```yaml
alsa:
  mixer: "PCM"        # optional
  device_num: 0       # optional
  vendor_id: "0x08bb" # optional (USB)
  product_id: "0x2902"# optional (USB)
```

## Health & Troubleshooting
- Quick view: `./bin/health` (prints quick probes; read‑only).
- Logs: `journalctl -u shairport-sync -n 200` and `journalctl -u nqptp -n 200`.
- Verify AirPlay 2 capability: `shairport-sync -V | grep -q "AirPlay2"`.
- Verify nqptp active: `systemctl is-active nqptp`.
- Verify advertisement: `avahi-browse -rt _airplay._tcp`.

If your device does not appear
- Ensure `/etc/shairport-sync.conf` has no leftover template markers.
- Remove any custom Avahi restrictions if you previously limited interfaces.
- Re-run: `sudo ./bin/apply`.

## Security Notes
- Shairport runs as its vendor user with hardened limits via `systemd/overrides/shairport-sync.service.d/override.conf`.
- No root‑run timers or on‑device Git operations.

## Acceptance Checklist
- `shairport-sync -V` contains `AirPlay2`.
- `systemctl is-active nqptp` returns `active`.
- `_airplay._tcp` visible via `avahi-browse -rt _airplay._tcp`.
- `bin/alsa-probe` returns an ALSA device string and `aplay -D <device>` can open it (busy tolerated).
