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

