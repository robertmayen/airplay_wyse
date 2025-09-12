# AirPlay Wyse

Minimal AirPlay 2 receiver for Wyse 5070 with USB DAC — now with a simplified, least‑privilege architecture.

## Overview

This repo configures a Wyse 5070 + USB DAC as an AirPlay 2 receiver using:

- Shairport Sync (AirPlay 2) via APT
- NQPTP for precise timing via APT
- A tiny setup/apply workflow (no on-device GitOps, no periodic root jobs)

What changed: previous versions used a root‑run “reconcile/update/converge” model. This has been replaced with a simple one‑time setup and on-demand apply flow. Shairport runs as its vendor user with hardened systemd overrides, and privileged actions happen only during setup/apply.

## Quick Start

1) Install packages and configure once (as root):
- `sudo ./bin/setup`  (auto-detects DAC, sets name "Wyse DAC" by default)

2) Customize name or ALSA device later (as root):
- `sudo ./bin/apply --name "Living Room"`  (auto-detect device)
- or `sudo ./bin/apply --device hw:0,0 --mixer PCM`

3) Verify advertisement:
- `avahi-browse -rt _airplay._tcp`

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for details.

Releases and updates
- Tag releases with SemVer (`vX.Y.Z`) and push tags. See [docs/RELEASES.md](docs/RELEASES.md).
- On devices, switch versions with `./bin/select-tag vX.Y.Z` (or `--latest`) then `sudo ./bin/apply`.

## Requirements

- Debian-based system (tested on Debian 13)
- USB DAC (auto-detected; optional manual overrides)

## Repository Structure

```
airplay_wyse/
├── bin/            # Core scripts (setup, apply, health, alsa-probe, diag, test-airplay2)
├── cfg/            # Templates (minimal shairport-sync.conf)
├── systemd/        # Service overrides (e.g., shairport-sync hardening + nqptp ordering)
├── inventory/      # Optional host-specific hints (kept for alsa-probe)
├── tests/          # Smoke test
└── docs/           # Operations + architecture
```

## How It Works (Simplified)

- `bin/setup` installs APT packages (shairport-sync, nqptp), writes `/etc/shairport-sync.conf`, installs hardened override for `shairport-sync`, and enables nqptp + shairport services.
- `bin/apply` updates `/etc/shairport-sync.conf` when you change name or ALSA settings and restarts shairport-sync.
- No periodic root timers, no on-device GitOps, no custom Avahi config unless you explicitly add one.

## AirPlay 2 Features

- Full AirPlay 2 (via Shairport Sync from APT)
- NQPTP integration and ordering
- Minimal and auditable privileged surface

## License

MIT
