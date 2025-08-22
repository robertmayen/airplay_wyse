# AirPlay Wyse

Minimal AirPlay 2 receiver for Wyse 5070 with USB DAC.

## Overview

This repository provides a GitOps-managed AirPlay 2 receiver implementation for Wyse 5070 thin clients with USB DACs. The system uses:

- **Shairport Sync** with AirPlay 2 support (built from source)
- **NQPTP** for time synchronization (built from source)
- **Source-based installation** for latest AirPlay 2 features
- **Single privilege path** via systemd-run wrapper
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
├── bin/            # Core scripts (reconcile, update, converge, health, install-airplay2, test-airplay2, validate-setup)
├── cfg/            # Configuration templates
├── systemd/        # Service definitions (including nqptp.service)
├── scripts/        # Privilege wrapper
├── inventory/      # Host-specific configurations
├── tests/          # Smoke test
└── docs/           # Operations documentation
```

## Validation and Auto-Remediation

The `bin/validate-setup` script provides comprehensive validation and automatic fixing of common deployment issues:

- **User setup validation** - Ensures airplay user exists with correct group memberships
- **Sudoers configuration** - Validates and fixes NOPASSWD rules for privilege escalation
- **Runtime directories** - Creates and fixes permissions for required directories
- **Build dependencies** - Automatically installs missing packages for AirPlay 2 compilation
- **Systemd units** - Verifies service installation and enablement

This addresses "user messed up situations" with repository-based fixes instead of manual shell commands.

## AirPlay 2 Features

- **Full AirPlay 2 support** with multi-room audio capabilities
- **Source-based installation** ensures latest features and compatibility
- **Automatic dependency management** for build requirements
- **NQPTP integration** for precise timing synchronization
- **Comprehensive testing** with validation scripts

## License

MIT
