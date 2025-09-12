# AirPlay Wyse

Minimal AirPlay 2 receiver for Wyse 5070 with USB DAC.

## Overview

This repository provides a GitOps-managed AirPlay 2 receiver implementation for Wyse 5070 thin clients with USB DACs. The system uses:

- **Shairport Sync** with AirPlay 2 support (via APT on Debian 13)
- **NQPTP** for time synchronization (via APT)
- **Root-run services with systemd hardening** (no sudo/wrapper needed)
- **Idempotent convergence** with health monitoring

## Quick Start

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for:
- Installation and setup
- GitOps workflow
- Health monitoring
- Troubleshooting

## Requirements

- Debian-based system (tested on Debian 13)
- USB DAC (auto-detected, with optional inventory overrides)
- Network connectivity for GitOps updates
- Build dependencies (automatically installed during setup)

## Repository Structure

```
airplay_wyse/
├── bin/            # Core scripts (reconcile, update, converge, health, test-airplay2, diag, alsa-probe)
├── cfg/            # Configuration templates
├── systemd/        # Service definitions and overrides (vendor nqptp unit used)
├── scripts/        # Privilege wrapper
├── inventory/      # Host-specific configurations
├── tests/          # Smoke test
└── docs/           # Operations documentation
```

## How It Works

- `reconcile.timer` triggers `reconcile.service` as root.
- `bin/reconcile` runs `bin/update` (fetch/select/checkout tag) then `bin/converge` (ensure packages, render configs, restart services, record health).
- Privileged actions are executed directly by the root-run service with strong systemd sandboxing.

## AirPlay 2 Features

- **Full AirPlay 2 support** with multi-room audio capabilities
- **APT-based installation** for shairport-sync (with RAOP2) and nqptp
- **Automatic dependency management** via APT
- **NQPTP integration** for precise timing synchronization
- **Comprehensive testing** with validation scripts

## License

MIT
