# Repository Audit Report

**Date:** 2025-01-22  
**Goal:** Minimal AirPlay 2 receiver on Wyse 5070 with USB DAC via APT-only converge

## Classification Definitions

- **CORE**: Strictly required for AirPlay 2 on Wyse 5070 via APT-only converge
- **AUX**: Single ops doc + smoke test supporting CORE
- **DEAD**: Files to remove (build scripts, patches, multi-path privilege, etc.)

## File Classification Table

| Path | Classification | Rationale |
|------|---------------|-----------|
| `bin/reconcile` | CORE | Timer entrypoint sequencing update → converge |
| `bin/update` | CORE | GitOps tag fetch/select/checkout |
| `bin/converge` | CORE | Idempotent converge: APT packages, ALSA detect, config render |
| `bin/alsa-probe` | CORE | USB DAC detection and device string resolution |
| `bin/health` | CORE | Health JSON reporter for monitoring |
| `bin/diag` | CORE | Basic diagnostics collector |
| `bin/airplay-sd-run` | DEAD | Duplicate of scripts/airplay-sd-run |
| `scripts/airplay-sd-run` | CORE | Single privilege wrapper via systemd-run |
| `scripts/ci/` | DEAD | CI helpers not required for minimal path |
| `scripts/ops/` | DEAD | Provisioning helpers out of scope |
| `cfg/shairport-sync.conf.tmpl` | CORE | Shairport configuration template |
| `cfg/nqptp.conf.tmpl` | CORE | NQPTP configuration template |
| `cfg/avahi/` | CORE | Avahi interface restriction templates |
| `systemd/reconcile.service` | CORE | Update + converge service |
| `systemd/reconcile.timer` | CORE | Periodic trigger for reconcile |
| `systemd/converge.service` | CORE | Converge service definition |
| `systemd/converge.timer` | DEAD | Unused - only reconcile.timer needed |
| `systemd/bootstrap.service` | DEAD | Bootstrap removed from minimal path |
| `systemd/overrides/converge.service.d/` | CORE | Exit code handling for converge |
| `systemd/overrides/shairport-sync.service.d/` | CORE | Ordering dependencies for nqptp |
| `systemd/overrides/nqptp.service.d/` | DEAD | Unnecessary override |
| `tests/smoke.sh` | AUX | Single smoke test validating AP2 |
| `docs/OPERATIONS.md` | AUX | Single canonical operations doc |
| `docs/AUDIT.md` | AUX | This audit document |
| `inventory/hosts/example.yml` | CORE | Example host inventory |
| `patches/` | DEAD | Patch sets not needed in minimal plan |
| `pkg/` | DEAD | Build tooling violates immutable-ish rule |
| `lib/` | DEAD | Empty directory |
| `security/` | DEAD | Sudoers example embedded in OPERATIONS.md |
| `README.md` | AUX | Minimal project description |
| `VERSION` | CORE | Version tracking for GitOps |
| `CHANGELOG.md` | AUX | Change history |
| `Makefile` | AUX | Development helper |

## High-Risk Complexity Issues

### Identified Issues
1. **Missing pkg/install.sh**: bin/converge references non-existent pkg/install.sh
2. **Duplicate privilege wrapper**: Both bin/ and scripts/ contain airplay-sd-run
3. **Empty directories**: lib/, pkg/apt-pins.d/, scripts/ci/, scripts/ops/
4. **Missing bin/diag**: Referenced but not present

### Resolution
- Fix bin/converge to use direct APT commands via systemd-run wrapper
- Keep only scripts/airplay-sd-run as the single privilege path
- Remove all empty directories
- Create minimal bin/diag for basic diagnostics

## Files to Delete

### Directories (entire)
- `patches/` - No patching in minimal plan
- `pkg/` - No on-device builds
- `lib/` - Empty
- `security/` - Docs moved to OPERATIONS.md
- `scripts/ci/` - Not required
- `scripts/ops/` - Out of scope

### Individual Files
- `bin/airplay-sd-run` - Duplicate
- `systemd/bootstrap.service` - No bootstrap path
- `systemd/converge.timer` - Unused
- `systemd/overrides/nqptp.service.d/` - Unnecessary

### Root-level Scripts (if present)
- All `fix_*.sh` scripts
- All `deploy_*.sh` scripts
- All `test_*.sh` scripts (except tests/smoke.sh)
- All documentation files except README.md

## Final Structure

```
airplay_wyse/
├── bin/
│   ├── reconcile
│   ├── update
│   ├── converge
│   ├── alsa-probe
│   ├── health
│   └── diag
├── scripts/
│   └── airplay-sd-run
├── cfg/
│   ├── shairport-sync.conf.tmpl
│   ├── nqptp.conf.tmpl
│   └── avahi/
├── systemd/
│   ├── reconcile.service
│   ├── reconcile.timer
│   ├── converge.service
│   └── overrides/
├── tests/
│   └── smoke.sh
├── docs/
│   ├── AUDIT.md
│   └── OPERATIONS.md
├── inventory/
│   └── hosts/
└── Core files: README.md, VERSION, CHANGELOG.md, Makefile
```

## Validation Criteria

- [x] Single privilege path via systemd-run wrapper
- [x] APT-only package management (no compilers)
- [x] Idempotent converge operation
- [x] AirPlay 2 validation via version string
- [x] NQPTP service active check
- [x] mDNS advertisement verification
- [x] ALSA device detection and validation
