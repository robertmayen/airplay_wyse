# AirPlay Wyse

A GitOps-driven AirPlay deployment for Wyse thin clients. Devices run a least‑privilege converge orchestrator as an unprivileged user, with a root broker executing a small allow‑listed set of commands via a queue. All changes are delivered by pushing signed git tags; devices pull, verify, and apply automatically.

- Converge (user: `airplay`): renders configs, detects ALSA, enqueues privileged ops.
- Broker (root oneshot): processes `/run/airplay/queue/*.cmd` with a strict allow‑list.
- Units/paths: systemd timers and path units orchestrate runs and queue processing.

See `docs/runbook.md` for operations and `AGENTS.md` for architecture.

## Highlights
- Pure GitOps: push a tag; devices fetch → verify → converge.
- Least privilege: no arbitrary sudo; root actions are queued and allow‑listed.
- Idempotent: only changed files/configs are applied; semantic exit codes.
- ALSA auto‑detect: validates devices, finds a sensible mixer, unmute/80% volume.
- AirPlay 2 ready: ensure `nqptp` is installed and attach a RAOP2‑enabled `shairport-sync` `.deb` to your release tag; converge installs it automatically and orders it after `nqptp`.

## Quick Start
- Provision devices (controller scripts): `scripts/ops/provision-hosts.sh`
- Tag a release: `git tag -s vX.Y.Z && git push --tags`
- Devices auto‑update via `update.timer` and converge via `converge.service`.
- Health snapshot: `./bin/health` on device; logs via `journalctl -u converge`.

## Key Paths
- Repo on device: `/opt/airplay_wyse`
- Queue: `/run/airplay/queue` (root broker reads `*.cmd` with optional `.in` payloads)
- State: `/var/lib/airplay_wyse` (hashes, last-health)
- Configs: `/etc/shairport-sync.conf`, `/etc/avahi/avahi-daemon.conf.d/airplay-wyse.conf`

## Docs
- Operations: `docs/runbook.md`
- Troubleshooting: `docs/troubleshooting.md`
- Architecture and policies: `AGENTS.md`
