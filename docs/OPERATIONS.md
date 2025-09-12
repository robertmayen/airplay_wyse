# Operations (Root-Run Model)

This document describes the operational workflow for running a Wyse 5070 + USB DAC as an AirPlay 2 receiver with GitOps. Services run as root with strong systemd hardening (ProtectSystem=strict with narrowly scoped ReadWritePaths); no sudoers or wrapper scripts are required.

## Overview
- Devices run `reconcile.timer` → `reconcile.service` as the root user under a hardened sandbox.
- `reconcile` executes `update` (fetch/select/checkout tag) then `converge` (ensure APT packages, render configs, restart services, record health).

## Prerequisites (Device)
- Debian 13 preferred (APT provides `shairport-sync` with AirPlay 2 and `nqptp`).
- Repository cloned to `/opt/airplay_wyse`.
- Systemd units installed:
  - Copy `systemd/reconcile.*`, `systemd/converge.service` to `/etc/systemd/system/`.
  - Copy overrides: `systemd/overrides/*/` to `/etc/systemd/system/`.
  - `systemctl daemon-reload && systemctl enable --now reconcile.timer`.

Important
- Run `bin/converge` as root (`sudo`) — it writes to `/etc` and manages services.
- Inventory YAML must be left-aligned keys (no leading spaces):
  ```yaml
  airplay_name: "Wyse DAC"
  nic: wlp0s12f0
  ```
  File path: `/opt/airplay_wyse/inventory/hosts/<short-hostname>.yml`.
  The `<short-hostname>` is from `hostname -s`.

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

Fixing device update errors (403)
- If `reconcile` logs show a 403 when fetching origin, update the remote URL on the device to a readable endpoint (e.g., a public HTTPS URL), or disable the timer until fixed:
  - `cd /opt/airplay_wyse && sudo git remote set-url origin https://github.com/<user>/airplay_wyse.git`
  - or `sudo systemctl disable --now reconcile.timer`

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

If your device does not appear
- Ensure `/etc/shairport-sync.conf` has no `{{...}}` placeholders.
- Ensure `/etc/avahi/avahi-daemon.conf.d/airplay-wyse.conf` shows `allow-interfaces=<your_iface>` or delete the drop-in and restart Avahi.
- Run `sudo /opt/airplay_wyse/bin/converge` again to render configs from inventory.

## Notes
- Converge installs packages via APT (no on-device compilation). Units enforce `ProtectSystem=strict` and allow writes only to:
  - `/opt/airplay_wyse`, `/var/lib/airplay_wyse`, `/run`, `/run/airplay`
  - `/etc` (for config deployment)
  - `/usr` and APT/DPKG state: `/var/lib/apt`, `/var/cache/apt`, `/var/lib/dpkg`, `/var/log`
- Avahi drop-in template is applied only if different from the current content.

## Acceptance Checklist
- `shairport-sync -V` contains `AirPlay2`.
- `systemctl is-active nqptp` returns `active`.
- `_airplay._tcp` visible via `avahi-browse -rt _airplay._tcp`.
- `bin/alsa-probe` returns an ALSA device string and `aplay -D <device>` can open it (busy tolerated).
- A second `bin/converge` run returns unchanged (idempotent).
- **Security**: Root-run model with systemd sandboxing; no sudoers or wrapper required.

## Converge Exit Codes
- 0: healthy (no changes)
- 2: healthy_changed (changes applied)
- 3: degraded (missing device, nqptp not healthy, mDNS not visible)
- 4: invalid_inventory (missing/invalid inventory)
- 5: verify_failed (tag verification failure; verification occurs in `bin/update`)
- 6: held (hold file present)
- 10: pkg_failed (package install/update failed)
- 11: systemd_failed (service restart failed)
