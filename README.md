# AirPlay Wyse

GitOps-driven AirPlay for Wyse thin clients. Devices run a least‑privilege agent as the unprivileged `airplay` user; when root is required, the agent launches hardened transient units via a small, fixed wrapper. Releases are delivered by pushing annotated/signed git tags; devices fetch, select a target tag, and converge automatically.

- Converge (user: `airplay`): renders configs, detects ALSA, applies templates, and performs scoped privileged actions via transient units.
- Transient elevation: `/usr/local/sbin/airplay-sd-run <profile> -- <cmd>` maps to `systemd-run` with strict sandboxes and fixed `ReadWritePaths`.
- Reconcile loop: `reconcile.timer` runs `bin/reconcile` which updates the repo and invokes converge.

See `docs/runbook.md` for operations and `AGENTS.md` for architecture.

## Highlights
- GitOps: push a tag; devices fetch → select → converge.
- Least privilege: no arbitrary sudo; fixed capability profiles (`svc-restart`, `cfg-write`, `unit-write`, `pkg-ensure`).
- Idempotent: only changed files/configs are applied; semantic exit codes with unit SuccessExitStatus.
- ALSA auto‑detect: validates devices, finds a sensible mixer, unmute/80% volume.
- AirPlay 2 (RAOP2): converge remediates missing AP2 automatically (installs/starts `nqptp`, upgrades shairport‑sync if needed, applies drop‑ins) using transient units.

## Quick Start
- Provision devices (controller scripts): `scripts/ops/provision-hosts.sh`
- Tag a release: `git tag -s vX.Y.Z && git push --tags` (never retcon tags; bump for fixes)
- Recommended: `reconcile.timer` drives updates and converge. Legacy `update.timer` is supported.
- Health snapshot: `./bin/health`; logs: `journalctl -u reconcile.service -u converge.service`.

## AirPlay 2 Enablement
- Build RAOP2-enabled package: `pkg/build-shairport-sync.sh` (Debian build host)
- Build `nqptp`: `pkg/build-nqptp.sh` (if not in your distro)
- Attach `.deb` files in `pkg/` to your release tag
- Converge automatically installs packages, enables `nqptp`, and enforces service ordering
- Verify: `shairport-sync -V | grep -Ei 'Air\s*Play\s*2|RAOP2|NQPTP'` and `systemctl status nqptp`

## Key Paths
- Repo on device: `/opt/airplay_wyse`
- State: `/var/lib/airplay_wyse` (hashes, last-health)
- Configs: `/etc/shairport-sync.conf`, `/etc/avahi/avahi-daemon.conf.d/airplay-wyse.conf`

## Docs
- Operations: `docs/runbook.md`
- Troubleshooting: `docs/troubleshooting.md`
- Architecture and policies: `AGENTS.md`
- Release policy: `docs/RELEASE.md`
