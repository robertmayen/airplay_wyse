# Repository Guidelines

## Project Structure & Module Organization
- `bin/`: Operational scripts (`converge`, `update`, `preflight`, `diag`, broker).
- `cfg/`: Templated configs for services (e.g., `shairport-sync.conf.tmpl`).
- `inventory/hosts/*.yml`: Per-host variables consumed by `bin/converge`.
- `systemd/`: Unit, path, and timer files for orchestrating runs.
- `pkg/`: Package pinning and installers (`install.sh`, `versions.sh`).
- `tests/`: Smoke and utility scripts; lightweight, host-affecting.
- `docs/`: Operational docs and runbooks.

## Build, Test, and Development Commands
- `make help`: List available targets.
- `make test`: Run smoke test (`tests/smoke.sh`). Note: may act on host.
- `make health`: Print last converge health via `./bin/health`.
- `make diag`: Collect system diagnostics (`./bin/diag`).
- `make vm-test`: Guidance for running in a local Debian 12/13 VM.
- `make install-units`: Shows commands to install systemd units as root.
- Direct: `./bin/preflight` checks deps and sudo; `./bin/converge` performs idempotent converge; `./bin/update` fetches/releases.

## Coding Style & Naming Conventions
- Language: Bash; prefer portable bash with `set -euo pipefail`.
- Indentation: 2 spaces; wrap lines at ~100 cols.
- Naming: lowercase-hyphen for scripts (`converge-broker`); UPPER_CASE for env/consts.
- Safety: `shellcheck` locally before PRs; avoid `eval`; quote variables.
- Paths: use repo‑relative (`REPO_DIR`) and absolute paths for system ops.

## Testing Guidelines
- Scope: Tests are shell scripts under `tests/`. Add new checks as `*.sh`.
- Conventions: Name by behavior (`avahi_browse.sh`, `journal_parsers.sh`).
- Run: `make test` or execute individual scripts.
- Caution: Many tests interact with the host (systemd, Avahi). Prefer a VM.

## Commit & Pull Request Guidelines
- Commits: Use Conventional Commits where practical (`feat:`, `fix(scope):`, `chore:`). Tag releases as `vX.Y.Z: ...`.
- PRs: Include a clear description, rationale, test notes (VM or logs), and any `./bin/diag` output relevant to changes. Link issues where applicable.
- Scope: Keep changes small and focused; avoid drive‑by refactors.

## Security & Configuration Tips
- Do not commit secrets or machine‑specific credentials.
- Changes under `systemd/` and `pkg/` affect privileged operations; review carefully.
- Inventory lives in `inventory/hosts/*.yml`; validate keys against `inventory/schema.yml`.
- For deployment steps, follow `make install-units` output and docs/runbook.

## Architecture Overview
- Control plane: Your Mac (controller) seeds SSH and provisions devices using `scripts/ops/*`.
- Device plane: Each Wyse box hosts this repo at `/opt/airplay_wyse` and runs systemd units:
  - `update.timer` → `update.service` runs `bin/update` to fetch/verify release tags.
  - `update-done.path` watches `/run/airplay/update.trigger` to start `converge.service`.
  - `converge.service` runs `bin/converge` (idempotent orchestrator) as `airplay` user.
- `converge-broker.path` watches `/run/airplay/queue` to trigger root `converge-broker`.

## System Logic
- Update selection: `bin/update` fetches tags, picks `inventory/hosts/<host>.yml: target_tag` if set, else highest SemVer `vX.Y.Z`.
- Tag verification: Devices must trust the maintainer key; unsigned/untrusted tags cause a verify failure.
- Converge phases (high level):
  - Prechecks: held switch (`/etc|/var/lib/airplay_wyse/hold`), time sync check, signed tag verify.
  - Inventory: Load host file and derive variables (e.g., `AIRPLAY_NAME`, `ALSA_*`, `AVAHI_IFACE`).
  - Templates: Render `cfg/*.tmpl` into `/etc/...` via `render_template` with safe placeholder substitution.
  - Packages: Ensure required packages via `pkg/install.sh` (apt pins and min versions in `pkg/versions.sh`).
  - Services: Request restarts/enablement through the broker queue when root is required.
  - Health: Emit JSON/text status under `/var/lib/airplay_wyse/last-health.*` and exit with semantic codes.

## Privilege Model & Broker
- Least privilege: `converge.service` runs as `airplay` with `NoNewPrivileges`, read-only system protection, and narrow `ReadWritePaths`.
- Root actions are pulled by `converge-broker` from `/run/airplay/queue/*.cmd` files and are allow-listed:
  - `/usr/bin/apt-get -y install ...`
  - `/usr/bin/dpkg -i /opt/airplay_wyse/pkg/*.deb`
  - `/usr/bin/systemctl restart airplay-*`
- This design avoids arbitrary root shell escalation while enabling controlled mutations (pkg install, service restart).

## State & Idempotence
- State dir: `/var/lib/airplay_wyse` with `hashes/` for change detection and `last-health.*` for reporting.
- Idempotent runs: Converge computes file hashes and only rewrites when content changes; exits with:
  - `0 OK`, `2 CHANGED`, `3 DEGRADED`, `4 INVALID_INPUT`, `5 VERIFY_FAILED`, `6 HELD`, `10 PKG_ISSUE`, `11 SYSTEMD_ERR`.
- Health access: `./bin/health` prints last JSON; `./bin/diag` bundles recent logs and environment glimpses.

## Architecture Diagram
```
 Controller (Mac)                                     Device (Wyse box)
 ───────────────────────────────                      ─────────────────────────────────────────────────────
 scripts/ops/seed-known-hosts.sh  ──────SSH──────▶   sshd  ───────────────────────────────────────────────
 scripts/ops/provision-hosts.sh   ──────SSH──────▶   systemd: preflight.service, converge-broker.path     
                                                     │
                                                     │  update.timer → update.service → bin/update
                                                     │            │
                                                     │            └─ writes /run/airplay/update.trigger
                                                     │                                 │
                                                     └─────────── update-done.path ────┘
                                                                 │
                                                                 └─ starts converge.service → bin/converge (User=airplay)
                                                                                 │
                                                                                 ├─ renders cfg/*.tmpl → /etc/* (via sudo broker when needed)
                                                                                 │
                                                                                 ├─ ensures pkgs via pkg/install.sh (via broker)
                                                                                 │
                                                                                 ├─ writes /var/lib/airplay_wyse/last-health.*
                                                                                 │
                                                                                 └─ enqueues root ops: /run/airplay/queue/*.cmd
                                                                                                   │
                                                       converge-broker.path ─▶  converge-broker.service (User=root)
                                                                                                   │
                                                                                                   └─ executes allow-listed commands
```

## Detailed Component Responsibilities
- `bin/update` (User=airplay):
  - Fetches tags from origin, selects target tag (inventory override `target_tag` > highest stable `vX.Y.Z`).
  - Verifies tag signature (`git verify-tag`); aborts on failure (no converge).
  - On change, checks out `tags/<target>` and touches `/run/airplay/update.trigger`.

- `bin/converge` (User=airplay, NNP, restricted writes):
  - Guards: hold switch, clock/ntp sanity, inventory presence, tag verification (defense-in-depth).
  - Inventory load: parses `inventory/hosts/$(hostname -s).yml` for `airplay_name`, `alsa.*`, `nic`, optional `target_tag`.
  - Template rendering: substitutes `{{AIRPLAY_NAME}}`, `{{ALSA_DEVICE}}`, `{{AVAHI_IFACE}}` into system configs.
  - Package gating: calls `pkg/install.sh` via broker to ensure `shairport-sync`, `nqptp`, `avahi-*`, `jq` at minimum versions.
  - Service management: requests safe restarts/enables through broker; never escalates directly.
  - State/health: writes JSON and txt status; returns semantic exit codes for timers/ops.

- `converge-broker` (User=root, oneshot):
  - Watches `/run/airplay/queue` (via `.path` unit).
  - Executes only allow-listed commands and arguments; everything else is denied and logged.

## Systemd Units & Relationships
- `update.timer`: periodic; runs `update.service` every 10min after boot; persistent across reboots.
- `update.service`: oneshot; triggers converge via the path file by touching `update.trigger`.
- `update-done.path`: PathChanged on `update.trigger`; starts `converge.service`.
- `converge.service`: oneshot; core idempotent orchestration; `User=airplay` with restricted `ReadWritePaths`.
- `converge-broker.path`: directory-not-empty watcher on `/run/airplay/queue`; starts root broker.
- `converge-broker.service`: oneshot; executes queued root actions.
- `preflight.service`: sanity checks (deps, sudo, dirs) during bring-up.

## Inventory Schema (practical subset)
- `airplay_name` (string): Friendly name advertised to AirPlay clients.
- `nic` (string): Interface used by Avahi/NQPTP; example `enp3s0`.
- `alsa.vendor_id` (hex), `alsa.product_id` (hex), `alsa.serial` (string, optional), `alsa.device_num` (int), `alsa.mixer` (string).
- `target_tag` (string, optional): Forces a canary or pin on this host.

## Queue Mechanics (Root Broker)
- Enqueue file: `/run/airplay/queue/<ts>.<rand>.cmd` with a single shell line to execute.
- Allowed patterns only:
  - `/usr/bin/apt-get -y install <pkg>`
  - `/usr/bin/dpkg -i /opt/airplay_wyse/pkg/*.deb`
  - `/usr/bin/systemctl restart airplay-*`
- Result files:
  - Success: `... .ok`
  - Failure: `... .err` containing stderr; the `.cmd` is removed in all cases.

## Security Considerations
- Trust root: Devices must have maintainer GPG/SSH signing keys to verify tags; reject unverified releases.
- Principle of least privilege: converge runs unprivileged with `NoNewPrivileges`, bounded capabilities, and strict filesystem protection.
- Broker allow-list: Prefer additive allow-lists; review diffs to `converge-broker` and `systemd/*.path|*.service` carefully.
- Sudo is not assumed: Controller-side provisioning ensures units and dirs exist even before deploying the repo.

## Failure Modes & Recovery
- Tag verify failed (exit 5): Inspect maintainer keys on device; run `bin/diag`; verify tag with `git verify-tag`.
- Degraded converge (exit 3): Check `.err` files in `/run/airplay/queue`; journal for `converge` and `converge-broker`.
- Package issues (exit 10): Validate apt pins and network; `pkg/install.sh` output.
- Held (exit 6): Remove `/etc/airplay_wyse/hold` or `/var/lib/airplay_wyse/hold`.
- Name/SSH trust: Run controller `scripts/ops/seed-known-hosts.sh` again to refresh host keys.

## Observability
- Logs: `journalctl -u update -u converge -u converge-broker`.
- Health snapshot: `/var/lib/airplay_wyse/last-health.json` and `.txt`; `make health` convenience.
- Diagnostics bundle: `./bin/diag` prints systemd status, sudoers glimpse, deps, and recent logs.

## End-to-End Sequence (Happy Path)
1) Controller provisions devices: users, dirs, minimal units (`scripts/ops/provision-hosts.sh`).
2) Maintainer pushes signed tag `vX.Y.Z` to origin.
3) `update.timer` fires → `update.service` runs `bin/update`.
4) Device fetches tags, picks target, verifies signature, checks out tag if changed.
5) `bin/update` touches `/run/airplay/update.trigger`.
6) `update-done.path` reacts → starts `converge.service`.
7) `bin/converge` reads inventory, renders configs, requests package ensures and restarts via queue.
8) `converge-broker.path` triggers → broker executes allowed root commands.
9) `bin/converge` writes health and exits with `0` or `2` if changes applied.

## Inventory & Templates
- Host files: `inventory/hosts/<host>.yml` drive device behavior (AirPlay name, NIC, ALSA IDs, mixer, optional serial).
- Templates: `cfg/shairport-sync.conf.tmpl`, `cfg/nqptp.conf.tmpl`, and Avahi stanzas render with variables like `{{AIRPLAY_NAME}}`, `{{ALSA_DEVICE}}`, `{{AVAHI_IFACE}}`.
- Validation: Keep keys aligned with `inventory/schema.yml`; unknown keys may be ignored.

## Controller Workflow
- Name resolution and SSH trust: Use `scripts/ops/seed-known-hosts.sh` to remove stale keys and pre-load fresh host keys for both hostnames and IPs.
- First-time provisioning: `scripts/ops/provision-hosts.sh` creates the `airplay` user, runtime dirs (`/run/airplay{,/queue}`), installs minimal units, and enables watchers.
- Post-provision: Push signed tags; devices `update` and then `converge` automatically.

## Operational Tips
- Run in a VM when testing host-affecting changes; `make vm-test` describes the flow.
- Keep sudoers minimal (see `security/`); validate with `visudo -cf` before deploying.
- For debugging service discovery, use `tests/avahi_browse.sh`; for timing/audio, check `tests/journal_parsers.sh`.

## Contribute
- CI gates: push/PR runs policy (`tests/no_sudo.sh`) and smoke (`tests/smoke.sh`, `tests/queue_smoke.sh`).
- Local: `make test` mirrors CI; install `ripgrep` for the policy check.
- Broker-only: never use `sudo` in converge or pkg paths; enqueue root ops to `/run/airplay/queue` as `.cmd` (with optional `.in` for tee payloads).
- Units: keep `converge-broker.path` pointing at `DirectoryNotEmpty=/run/airplay/queue` with `Unit=converge-broker.service`.
- Commits: small, focused; prefer Conventional Commits (feat:, fix:, chore:).
