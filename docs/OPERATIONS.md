# Operations (Minimal)

This document describes the minimal operational workflow for turning a Wyse 5070 + USB DAC into an AirPlay 2 receiver with GitOps.

## Overview
- Devices run `reconcile.timer` → `reconcile.service` as the `airplay` user.
- `reconcile` executes `update` (fetch/select/checkout tag) then `converge` (install packages, render configs, restart services, record health).
- Privileged actions are executed only through `/usr/local/sbin/airplay-sd-run`.

## Prerequisites (Device)
- Debian 13 preferred (APT provides `shairport-sync` with AirPlay 2 and `nqptp`).
- User `airplay` exists and can run the wrapper with NOPASSWD sudo.
- Wrapper installed:
  - Copy `scripts/airplay-sd-run` to `/usr/local/sbin/airplay-sd-run` (root-owned, 0755).
  - **CRITICAL**: Verify wrapper integrity after installation.
- **Sudoers configuration (SINGLE PRIVILEGE PATH)**:
  ```
  # /etc/sudoers.d/airplay-wyse
  Defaults:airplay !requiretty
  airplay ALL=(root) NOPASSWD: /usr/local/sbin/airplay-sd-run
  ```
  **Note**: Only the wrapper is allowed. Direct `systemd-run` access has been removed for security.
- Repository cloned to `/opt/airplay_wyse` (owned by `airplay` user).
- Systemd units installed:
  - Copy `systemd/reconcile.*`, `systemd/converge.service` to `/etc/systemd/system/`.
  - Copy overrides: `systemd/overrides/*/` to `/etc/systemd/system/`.
  - `systemctl daemon-reload && systemctl enable --now reconcile.timer`.

## Inventory (Optional)
`inventory/hosts/<short-hostname>.yml`:
```yaml
airplay_name: "Living Room"
nic: enp3s0
alsa:
  mixer: "PCM"        # optional
  device_num: 0       # optional
  vendor_id: "0x08bb" # optional (USB)
  product_id: "0x2902"# optional (USB)
```

## Controller Workflow (GitOps)
1. Commit changes to templates or scripts.
2. Tag a release: `git tag -s v1.0.0 -m "minimal release"` (signing optional).
3. Push: `git push origin main v1.0.0`.
4. Devices fetch and converge on the next timer tick.

## Health & Troubleshooting
- Health JSON: `/var/lib/airplay_wyse/last-health.json`.
- Quick view: `./bin/health` (read-only viewer; prints JSON and quick probes; does not modify state).
- Logs: `journalctl -u reconcile -n 200`.
- Hold updates: `sudo touch /etc/airplay_wyse/hold` (remove to resume).

## Rollback
- Tag or retag a previous known-good version (e.g., `v0.9.0`) and push the tag.
- Devices will fetch and converge to the new target tag on next run.

## Validation (On Device)
- Verify AirPlay 2 capability: `shairport-sync -V | grep -q "AirPlay2"`.
- Verify nqptp active: `systemctl is-active nqptp`.
- Verify advertisement: `avahi-browse -rt _airplay._tcp`.

## Notes
- No compilers/build toolchains are required on the host. Converge installs packages via APT; if a local `.deb` is present in the repo checkout, it may be installed by `converge` via `dpkg -i`.
- Avahi drop-in template is provided and applied only if different from the current content.

## Security Update

The wrapper has been updated to fix a critical shell injection vulnerability. Key changes:
- **No shell invocation**: Commands are executed directly via systemd-run
- **Input validation**: Executable paths must be absolute and exist
- **Allowlisting**: Each profile only allows specific executables
- **Sandboxing**: Comprehensive systemd security properties applied

### Installation
```bash
sudo cp scripts/airplay-sd-run /usr/local/sbin/airplay-sd-run
sudo chown root:root /usr/local/sbin/airplay-sd-run
sudo chmod 755 /usr/local/sbin/airplay-sd-run
sudo visudo -c  # Verify sudoers syntax
```

## Acceptance Checklist
- `shairport-sync -V` contains `AirPlay2`.
- `systemctl is-active nqptp` returns `active`.
- `_airplay._tcp` visible via `avahi-browse -rt _airplay._tcp`.
- `bin/alsa-probe` returns an ALSA device string and `aplay -D <device>` can open it (busy tolerated).
- A second `bin/converge` run returns unchanged (idempotent).
- **Security**: Wrapper owned by root:root with 755 permissions.
- **Security**: Only wrapper allowed in sudoers (no direct systemd-run access).

## Converge Exit Codes
- 0: healthy (no changes)
- 2: healthy_changed (changes applied)
- 3: degraded (missing device, nqptp not healthy, mDNS not visible)
- 4: invalid_inventory (missing/invalid inventory)
- 5: verify_failed (tag verification failure; verification occurs in `bin/update`)
- 6: held (hold file present)
- 10: pkg_failed (package install/update failed)
- 11: systemd_failed (service restart failed)
