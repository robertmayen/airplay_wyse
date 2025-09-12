# AirPlay Wyse

Minimal AirPlay 2 receiver for Wyse 5070 with USB DAC — simplified, least‑privilege architecture.

## Overview

This repo configures a Wyse 5070 + USB DAC as an AirPlay 2 receiver using:

- Shairport Sync with AirPlay 2 (APT if available; builds from source when required)
- NQPTP for precise timing (APT if available; builds from source when required)
- A tiny setup/apply workflow (no on-device GitOps, no periodic root jobs)

What changed: previous versions used a root‑run “reconcile/update/converge” model. This has been replaced with a simple one‑time setup and on-demand apply flow. Shairport runs as its vendor user with hardened systemd overrides; privileged actions happen only during setup/apply.

## Quick Start

1) One-time install and configure (run as root):
- `sudo ./bin/setup`  (auto‑detects DAC; default name like "Wyse DAC-ABCD")

2) Customize name, ALSA device, or bind to a NIC later (as root):
- `sudo ./bin/apply --name "Living Room"`  (auto‑detect device)
- or `sudo ./bin/apply --device hw:0,0 --mixer PCM`
- or `sudo ./bin/apply --interface wlp0s12f0`

3) Validate on the device:
- `./bin/test-airplay2`  (sanity checks for nqptp, shairport, mDNS, ALSA)
- `./bin/test-airplay2 --logs --mdns`  (optional detailed view)

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for details.

Updates
- Update by pulling the repo or replacing it with an artifact; run `sudo ./bin/apply` if configs changed. Identity self‑heals automatically on boot via a one‑shot systemd unit.

## Requirements

- Debian-based system (tested on Debian 13)
- USB DAC (auto‑detected; optional manual overrides)

## Repository Structure

```
airplay_wyse/
├── bin/            # Core scripts (setup, apply, health, alsa-probe, diag, test-airplay2)
├── cfg/            # Templates (minimal shairport-sync.conf)
├── systemd/        # Service overrides (e.g., shairport-sync hardening + nqptp ordering)
├── tests/          # Smoke test
├── tools/          # Lints and helpers
└── docs/           # Operations, architecture
```

Optional inventory hints
- `bin/alsa-probe` can use `inventory/hosts/<short-hostname>.yml` if you add it to the device.

## How It Works (Simplified)

- `bin/setup` ensures an AirPlay 2-capable stack: installs APT packages (shairport-sync, nqptp) and, if AirPlay 2 or nqptp are unavailable via APT, builds them from source automatically. It writes `/etc/shairport-sync.conf`, installs a hardened override for `shairport-sync`, and enables nqptp + shairport services.
- `bin/apply` updates `/etc/shairport-sync.conf` when you change name or ALSA settings and restarts shairport-sync.
- `systemd/airplay-wyse-identity.service` runs before shairport-sync to ensure unique identity and sane defaults even if you didn’t run apply.
- No periodic root timers, no on-device GitOps, no custom Avahi config unless you explicitly add one.

## Tips

- Identity is self-managed: on first run or if a cloned image is detected, the AirPlay 2 identity is reset safely so each device has unique pairing keys. The default name includes a MAC suffix for uniqueness.
- Environment flags: you can set `AIRPLAY_NAME`, `ALSA_DEVICE`, `ALSA_MIXER`, `AVAHI_IFACE`, or `HW_ADDR` when running `setup`/`apply`.
- Logs: `journalctl -u shairport-sync -n 200` and `journalctl -u nqptp -n 200`.

## License

MIT
