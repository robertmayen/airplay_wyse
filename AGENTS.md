# Repository Guidelines (Updated Architecture)

## Project Structure
- `bin/`: Operational scripts (`update`, `converge`, `reconcile`, `preflight`, `diag`, `health`).
- `cfg/`: Templated configs (e.g., `shairport-sync.conf.tmpl`, Avahi drop-ins).
- `inventory/hosts/*.yml`: Per-host variables consumed by `bin/converge`.
- `systemd/`: Units and timers (`reconcile.service`, `reconcile.timer`, wrapper units).
- `pkg/`: Package pins and installers (`install.sh`, `versions.sh`, attachable `*.deb`).
- `tests/`: Smoke/utility scripts; many are host-affecting — prefer a VM.
- `docs/`: Operational docs and runbooks.

## Commands
- `make help` — list targets
- `make test` — lightweight checks (may affect host)
- `make health` — print last converge health
- `make diag` — gather diagnostics
- `make install-units` — docs-only install steps for reconcile units
- Direct scripts: `./bin/update`, `./bin/converge`, `./bin/reconcile`

## Architecture Overview
- Control plane (controller/Mac): seeds SSH, provisions hosts (see `scripts/ops/*`).
- Device plane (Wyse): repo at `/opt/airplay_wyse`; single reconciliation loop:
  - Recommended: `reconcile.timer` → `reconcile.service` runs `bin/reconcile` (update + converge) as `airplay`.
  - Supported: legacy `update.timer` → `update.service` runs `bin/update`, which immediately invokes `bin/converge`.
  - No `.path` watchers; no queue/broker.

## System Logic
- Update: fetch tags, select target (inventory `target_tag` or highest SemVer), optionally verify signature, checkout tag.
- Converge phases:
  - Guards: hold switch (`/etc|/var/lib/airplay_wyse/hold`), time sync sanity, inventory/tag verify.
  - Inventory: derive `AIRPLAY_NAME`, `AVAHI_IFACE`, and ALSA overrides.
  - ALSA detection: prefer USB; fallback to first playback card. Validate candidates by briefly opening PCM (tolerates in‑use/permissions), choose sensible mixer from common controls, unmute + set to 80%.
  - Templates: render `cfg/*.tmpl` and deploy to `/etc` via hardened transient units.
  - Packages: ensure `shairport-sync`, `avahi-*`, `jq`, `alsa-utils`; optionally install AP2‑capable `shairport-sync_*.deb` and `nqptp_*.deb` from `pkg/`.
  - Services: restart via wrapper units (`airplay-shairport`, `airplay-avahi`) under a restart‑only profile.
  - Health: write JSON/txt; if changes occurred this run, emit `healthy_changed` and skip synchronous visibility checks. Otherwise, require adverts.

## Privilege Model (Transient Root Actions)
- Agent runs as `airplay` with `NoNewPrivileges` and `ProtectSystem=strict`.
- Elevation is restricted to a root‑owned wrapper `/usr/local/sbin/airplay-sd-run` (allowed via sudoers). The wrapper maps capability profiles to fixed `systemd-run` properties and refuses unknown profiles or extra flags.
- When root is needed, the agent calls `sudo /usr/local/sbin/airplay-sd-run <profile> -- <command...>` to launch a hardened transient unit with minimal writes (`ReadWritePaths`) and strong sandboxing:
  - `svc-restart` — restart services; no FS writes.
  - `cfg-write` — write under `/etc` only; used for config deployment.
  - `unit-write` — write under `/etc/systemd/system` for unit sync; followed by `daemon-reload` under `svc-restart`.
  - `pkg-ensure` — apt/dpkg writes only: `/var/lib/apt`, `/var/lib/dpkg`, `/var/cache/apt`, `/etc/apt`, `/var/log`; reads `/opt/airplay_wyse/pkg`.
- Each privileged action is a discrete transient unit with full journald context. No queues or brokers.

## State & Idempotence
- State dir: `/var/lib/airplay_wyse` with `hashes/` and `last-health.*`.
- Exit codes: `0 OK`, `2 CHANGED`, `3 DEGRADED`, `4 INVALID_INPUT`, `5 VERIFY_FAILED`, `6 HELD`, `10 PKG_ISSUE`, `11 SYSTEMD_ERR`.

## Health & Observability
- RAOP/AirPlay visibility: healthy if either `_airplay._tcp` or `_raop._tcp` advertises the friendly name (case‑insensitive) or host shortname. Skipped on runs that made changes.
- Logs: `journalctl -u reconcile.service -u update.service` and `journalctl --unit 'airplay-*'` for transient actions.
- Health snapshot: `/var/lib/airplay_wyse/last-health.json` and `.txt`.

## Systemd Units
- `reconcile.timer`: periodic; triggers `reconcile.service` (single agent loop).
- `reconcile.service`: oneshot; runs `bin/reconcile` as `airplay`.
- Wrapper units: `airplay-shairport.service`, `airplay-avahi.service` to safely restart core services.
- Legacy `.path` and broker units were removed; converge prunes on-device remnants.

## Inventory Schema (practical subset)
- `airplay_name` (string) — advertised name; default host shortname.
- `nic` (string) — interface (e.g., `enp3s0`).
- `alsa.vendor_id`/`alsa.product_id` (hex) — optional USB target; `alsa.serial` optional.
- `alsa.device_num` (int) — ALSA subdevice index (default auto first playback).
- `alsa.mixer` (string) — optional mixer override.
- `target_tag` (string) — pin/canary.

## Security Notes
- Devices must trust the maintainer’s signing key if tag verification is enabled.
- Sudoers: allow `airplay` to run `/usr/bin/systemd-run` (NOPASSWD) only; do not grant general shells.

## Operational Tips
- Prefer a VM for testing host‑affecting changes.
- Use `./bin/diag` and journals for quick triage.
- Attach `.deb` artifacts for AP2 rollout under `pkg/` in a signed tag; devices install them automatically.

## Contribute
- Keep changes small and focused; PRs should include rationale and logs.
- `make test` mirrors CI; tests may interact with the host.
