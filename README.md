# AirPlay Wyse

Minimal AirPlay 2 receiver for Wyse 5070 with USB DAC.

## Overview

This repository provides a GitOps-managed AirPlay 2 receiver implementation for Wyse 5070 thin clients with USB DACs. The system uses:

- **Shairport Sync** with AirPlay 2 support
- **NQPTP** for time synchronization
- **APT-only** package management (no on-device compilation)
- **Single privilege path** via systemd-run wrapper
- **Idempotent convergence** with health monitoring

## Quick Start

See [docs/OPERATIONS.md](docs/OPERATIONS.md) for:
- Installation and setup
- GitOps workflow
- Health monitoring
- Troubleshooting

## Requirements

- Debian 13 (or compatible with AirPlay 2-capable packages)
- USB DAC (auto-detected, with optional inventory overrides)
- Network connectivity for GitOps updates

## Repository Structure

```
airplay_wyse/
├── bin/            # Core scripts (reconcile, update, converge, health)
├── cfg/            # Configuration templates
├── systemd/        # Service definitions
├── scripts/        # Privilege wrapper
├── inventory/      # Host-specific configurations
├── tests/          # Smoke test
└── docs/           # Operations documentation
```

## License

MIT
