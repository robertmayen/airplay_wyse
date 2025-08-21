# Runbook

## Install (once per device)
- Create user `airplay` and clone repo to `/opt/airplay_wyse`.
- Install trusted GPG pubkeys under `/etc/airplay_wyse/trusted-gpg/`.
- Install sudoers drop-in from `security/sudoers/airplay-wyse` via visudo validation.
- Enable systemd units:
  - `sudo install -m0644 systemd/reconcile.service /etc/systemd/system/`
  - `sudo install -m0644 systemd/reconcile.timer /etc/systemd/system/`
  - `sudo systemctl daemon-reload && sudo systemctl enable --now reconcile.timer`

## Operations
- Reconcile now: `sudo systemctl start reconcile.service`
- Check status: `journalctl -u reconcile.service -n 100`
- Health: `./bin/health`
- Diagnostics: `./bin/diag`

## Service Restarts via Wrapper Units
- The privilege broker only restarts allow‑listed units that match `airplay-*`.
- Wrapper units are shipped to safely control core services:
  - `airplay-shairport.service` → restarts `shairport-sync.service`
  - `airplay-avahi.service` → restarts `avahi-daemon.service`
- During converge, when configs change, the orchestrator enqueues restarts of these wrapper units. The broker executes them without broad privileges.
- GitOps applies updates to `/etc/systemd/system/*.service` via the broker and runs `systemctl daemon-reload` automatically when units change.

## RAOP/AirPlay Health Expectations
- Health check deems the system degraded if Avahi advertisements for both `_airplay._tcp` and `_raop._tcp` are not visible for the configured `airplay_name`.
- Quick verification:
  - `_airplay`: `avahi-browse -rt _airplay._tcp | grep "$(grep -E '^airplay_name\s*:' inventory/hosts/$(hostname -s).yml | awk -F: '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2}')"`
  - `_raop`: `avahi-browse -rt _raop._tcp | grep "$(grep -E '^airplay_name\s*:' inventory/hosts/$(hostname -s).yml | awk -F: '{gsub(/^[[:space:]]+|[[:space:]]+$/, "", $2); print $2}')"`
- Converge renders and deploys `/etc/shairport-sync.conf` and an Avahi drop‑in when needed; it then restarts the wrapper units so adverts should appear shortly after converge.

## ALSA Autodetect and Audio Sanity
- Converge auto-detects audio devices with a preference for USB; it falls back to the first card with a playback PCM.
- It validates candidates by briefly opening the PCM (silent stream for ~1s) to ensure the device is actually usable.
- Mixer detection prefers common controls in order: `PCM`, `Master`, `Digital`, `Speaker`, `Headphone`, `Line Out`, `Line`, `Front`.
- After selection, converge attempts a best‑effort unmute and sets the chosen control to 80%.
- To force a specific device, set inventory overrides (`alsa.vendor_id`, `alsa.product_id`, optional `alsa.serial`, `alsa.device_num`, `alsa.mixer`).

## AirPlay 2 Support
- **Multi-room sync:** Install `nqptp` for AirPlay 2 time synchronization. The converge path enables/starts `nqptp.service` automatically when present and orders `shairport-sync` after it via a systemd override (`Requires=nqptp.service`).
- **RAOP2-enabled builds:** Debian's stock `shairport-sync` package may lack AirPlay 2 (RAOP2) support. To enable AirPlay 2:
  1. Build a RAOP2-enabled package: Run `pkg/build-shairport-sync.sh` on a Debian build host (produces `pkg/shairport-sync_*.deb` with `--with-raop2`, `--with-convolution`, and all required features).
  2. Attach the `.deb` to your signed release tag or let CI attach it.
  3. The updater (`bin/update`) automatically runs `dpkg -i` for any `pkg/*.deb` files found in the repo.
- **Health monitoring:** If `shairport-sync -V` doesn't report "AirPlay 2" or "RAOP2", converge marks the system degraded with reason `shairport-sync lacks AirPlay 2 (RAOP2); install RAOP2-enabled build`.
- **Verification:** Check AP2 status with `shairport-sync -V | grep -E 'AirPlay 2|RAOP2'` and nqptp with `systemctl status nqptp`.
- **Zero touch:** No manual steps required on devices — the broker installs packages and converge deploys configs and restarts services automatically.

### RAOP2 Remediation Path
- Health gate checks:
  - `shairport-sync -V` must mention AirPlay 2/RAOP2/NQPTP.
  - `systemctl is-active nqptp.service` must be `active`.
- If either check fails, converge triggers remediation using transient units:
  - `pkg-ensure`: installs `pkg/nqptp_*.deb` and `pkg/shairport-sync_*.deb` if present; otherwise attempts `apt-get install -y nqptp shairport-sync`.
  - `unit-write`: installs the `shairport-sync` drop-in that orders after `nqptp`.
  - `svc-restart`: `systemctl daemon-reload`, enable and (re)start `nqptp.service`, then restart `shairport-sync.service`.
- Post-check verifies `nqptp` is active and `shairport-sync -V` reports AirPlay 2; if successful, health is `healthy_changed` for this run.
- Networking: Ensure UDP ports 319 and 320 are allowed on the LAN; these are required for NQPTP time sync.

## Release
- Bump `VERSION`, update `CHANGELOG.md`.
- Create signed annotated tag `vX.Y.Z` and push.
- Devices will verify and converge on the next timer tick.

## Rollback
- `./bin/rollback vX.Y.(Z-1)` (verifies tag then converges).

## Hold/Kill-switch
- Create `/etc/airplay_wyse/hold` to pause updates; converge exits with code 6.
# Model A: non-root 'airplay' user with narrow sudoers — Quickstart

This quickstart sets up `converge` to run as the non-root `airplay` user, using least-privilege escalation via a sudoers drop-in. It also covers installing the systemd unit and importing the maintainer GPG public key so signed tags can be verified on-device.

Prereqs
- A local user named `airplay` exists on the device.
- This repo is installed under `/opt/airplay_wyse`.

1) Install the systemd unit (documentation-only)
- Copy the unit into place: `/etc/systemd/system/converge.service`
- The unit runs as `User=airplay` with `WorkingDirectory=/opt/airplay_wyse` and `Type=oneshot`.
- Then reload and enable:
  - `sudo systemctl daemon-reload`
  - `sudo systemctl enable converge.service`
  - `sudo systemctl start converge.service`

2) Install sudoers drop-in for least-privilege
- Copy `security/sudoers/airplay-wyse` to `/etc/sudoers.d/airplay-wyse`.
- Validate with visudo (never edit `/etc/sudoers` directly): `sudo visudo -cf /etc/sudoers.d/airplay-wyse`
- The `bin/converge` script keeps its internal sudo calls as-is and relies on this scoped policy.

3) Import maintainer GPG public key for tag verification
- Place the public key file on the device and import:
  - `gpg --import /path/to/maintainers.pub`
- Optional: set trust or import into the `airplay` user’s keyring as well if verification runs in that context.
- Converge and release workflows assume tags are annotated and signed; the device must have the public key to verify.

4) Run converge
- As `airplay` (or via the unit): `systemctl start converge.service`
- Converge will verify the target git tag before acting. If verification fails, it exits with code 5 (verify_failed).

Notes
- Working directory is `/opt/airplay_wyse` by default.
- Keep the sudoers policy as narrow as possible and validate with `visudo -cf`.
## Canary → Promotion with Signed Tags

Goal: reduce blast radius by rolling out to a single canary device before promoting to all.

1) Prepare and push a canary tag
- Create a signed, annotated tag for canary: `git tag -s vX.Y.Z-canary -m "Canary: vX.Y.Z"`
- Push the tag: `git push origin vX.Y.Z-canary`
- Ensure the device(s) have the maintainer GPG public key installed so `git verify-tag` succeeds.

2) Target the canary host only
- Update only the chosen host’s inventory selector (if applicable) or otherwise ensure only one device converges on the canary tag.
- Monitor for the agreed period (e.g., 24–72 hours): playback stability, logs, CPU/mem, network.

3) Promote to full release
- Create the final signed, annotated tag: `git tag -s vX.Y.Z -m "Release vX.Y.Z"`
- Push the tag: `git push origin vX.Y.Z`
- Remove any canary-only overrides so both hosts converge on `vX.Y.Z`.

Notes
- Devices verify signed tags; missing or untrusted keys cause converge to exit with code 5 (verify_failed).
- Keep inventories for both `wyse-sony` and `wyse-dac` in sync for host-affecting keys (`nic`, `alsa.vendor_id`, `alsa.product_id`, `alsa.serial`, `airplay_name`).

## Updater

The updater periodically fetches signed release tags and ensures the working copy points at the desired tag before starting `converge`.

- Service/Timer: `reconcile.service` (oneshot) and `reconcile.timer` run as `airplay` in `/opt/airplay_wyse`.
- Timer cadence: `OnBootSec=2min`, `OnUnitActiveSec=10min`, `RandomizedDelaySec=1min`, `Persistent=true`.
- Tag selection:
  - If the host inventory defines `target_tag: vX.Y.Z` in `inventory/hosts/$(hostname -s).yml`, the updater uses that tag (useful for canaries).
  - Otherwise, it selects the highest SemVer tag matching `^v\d+\.\d+\.\d+$` (pre-releases like `-rc1` are ignored).
- Security:
  - Tags must be signed; the device must trust the signer key so `git verify-tag <tag>` succeeds (GPG or SSH signatures supported by your git build).
  - `git fetch --tags origin` uses your configured deploy key/SSH credentials.
- Flow:
  1) Fetch tags, 2) pick target, 3) verify signature, 4) checkout `tags/<target>` if needed, 5) run converge in the same service.
- State: writes `/var/lib/airplay_wyse/last-update.txt` with timestamp, status, and revision.

Canary via per-host `target_tag`
- Set `target_tag: vX.Y.Z-canary` on the chosen host in `inventory/hosts/*.yml` to canary that release; others will follow the highest stable tag.
- After validation, clear `target_tag` and push a final `vX.Y.Z` tag to promote fleet-wide.

## Controller deploy

- Run these from your Mac (controller), not on the Wyse boxes.
- Step 1: seed SSH known_hosts to avoid host key prompts and mismatches.
  - fish: `scripts/ops/seed-known-hosts.sh wyse-dac=192.168.8.71 wyse-sony=192.168.8.72`
  - or POSIX shells: `HOSTS_LIST="wyse-dac=192.168.8.71 wyse-sony=192.168.8.72" scripts/ops/seed-known-hosts.sh`
- Step 2: provision both hosts (creates user, runtime dirs, units, watchers).
  - fish: `SSH_USER=$USER scripts/ops/provision-hosts.sh wyse-dac=192.168.8.71 wyse-sony=192.168.8.72`
  - or POSIX shells: `HOSTS_LIST="wyse-dac=192.168.8.71 wyse-sony=192.168.8.72" SSH_USER=$USER scripts/ops/provision-hosts.sh`

## CI

- GitHub Actions workflow: `.github/workflows/ci.yml` runs on push/PR.
- Checks:
  - Policy: `tests/no_sudo.sh` enforces broker-only model (no direct `sudo` in converge path).
  - Smoke: `tests/smoke.sh` runs converge and health; `tests/queue_smoke.sh` validates the broker queue processes a command.
- Local: `make test` runs the same checks; ensure `ripgrep` is installed for the policy test.

## NQPTP Packaging (Optional)

On Debian where `nqptp` is not packaged, you can build a local `.deb` and include it in a signed release tag so devices auto-install it during converge.

- Build dependencies on a Debian build host: `sudo apt-get install -y git autoconf automake libtool pkg-config dpkg-dev libsystemd-dev libmd-dev build-essential`
- Build the package: `./pkg/build-nqptp.sh` (optionally `--ref vX.Y.Z`)
- The script produces `pkg/nqptp_*.deb`. Commit it and tag a release.
- During converge, if `pkg/nqptp_*.deb` is present on the device, the broker runs `/usr/bin/dpkg -i /opt/airplay_wyse/pkg/nqptp_*.deb` to install/upgrade it.
