# Troubleshooting

- Time unsynced: `timedatectl status`; ensure `systemd-timesyncd` active.
- nqptp not healthy: `systemctl status nqptp`; check UDP 319/320 reachability on LAN. On Debian where `nqptp` is not packaged, this unit may be absent; AirPlay will still function without synchronized multi‑room. If desired, build from source: `git clone https://github.com/mikebrady/nqptp && cd nqptp && autoreconf -fi && ./configure --with-systemd-startup && make && sudo make install`.
- Not visible in AirPlay picker: verify Avahi adverts with `tests/avahi_browse.sh`.
- ALSA device missing: check `aplay -l`; verify inventory vendor/product/serial.
- Unintended restarts: check hashes in `/var/lib/airplay_wyse/hashes` and journal for diffs.

## Converge failed → run ./bin/diag-converge
- Use `./bin/diag-converge` to quickly inspect the converge unit and the last 150 log lines:
  - Shows `systemctl status --no-pager converge.service`.
  - Shows `journalctl -u converge.service -n 150 --no-pager`.
  - No additional sudo is required beyond repo defaults.
  - If you see permission errors reading logs, either add your user to the `adm` or `systemd-journal` group, or run with `sudo journalctl`.
## Signed tag verification failures

- Symptom: converge exits with code 5 and status "verify_failed".
- Cause: the target git tag is unsigned, not annotated, or signed by a key not present/trusted on the device.
- Fixes:
  - Ensure the tag is an annotated, signed tag.
  - Import the maintainer GPG public key on the device: `gpg --import <pubkey.asc>`.
  - Re-run converge or the systemd unit.

## Updater failures

- verify-tag failed: device lacks maintainer GPG public key or tag is unsigned/untrusted.
- No matching SemVer: repository has no `vX.Y.Z` tags; push a signed release tag.
- Network/SSH/permissions: deploy key missing, remote denied, or no network; check `git fetch --tags origin` output and SSH config.
- Checkout failed: local changes prevent checkout; ensure working copy is clean (converge and updater assume no local edits).
- Systemd start failed: `systemctl start converge.service` requires the sudoers entry for `airplay` on the device.

## Converge fails with “sudo: The no new privileges flag is set”
- Cause: unit had NoNewPrivileges=true which forbids privilege escalation.
- Fix: remove NoNewPrivileges=true from converge.service and reload daemon.

Note: If your distro mounts `/opt` with `noexec`, converge will fail with exit 203/EXEC.
- Workarounds: remount `/opt` with `exec`; or move the repo to `/srv/airplay_wyse` and update the unit path accordingly.

## Updater cannot start converge (Access denied)
- Cause: update.service runs as 'airplay' and system units require root or policy.
- Fix: updater uses 'sudo systemctl …' and sudoers must include the exact path (/usr/bin/systemctl). Validate with `visudo -cf /etc/sudoers.d/airplay-wyse`.
- See also: systemd exit 203/EXEC indicates non-executable or wrong interpreter for scripts.

## Broker NAMESPACE errors (status=226/NAMESPACE)
- Cause: `ProtectSystem=strict` plus `ReadWritePaths` pointing at missing directories causes mount namespace setup to fail.
- Fix: ensure the broker unit includes only existing parents or broaden to `/etc` and `/var/log`. In this repo, `converge-broker.service` uses:
  - `ReadWritePaths=/run/airplay /opt/airplay_wyse /var/cache/apt /var/lib/apt /var/lib/dpkg /var/tmp /tmp /etc /var/log`
  - GitOps sync updates `/etc/systemd/system` and runs `daemon-reload` automatically.

## RAOP “not visible” but device appears in avahi-browse
- Cause: timing and matching policy. The health check now:
  - Skips checks when changes were applied in the same run (`healthy_changed`).
  - Treats healthy if either `_airplay._tcp` or `_raop._tcp` contains the friendly name (case-insensitive) or the host shortname.
- Debug:
  - `avahi-browse -rt _raop._tcp`
  - `avahi-browse -rt _airplay._tcp`

## ALSA device detection rejects valid devices
- Cause: PCM probe may fail when the device is in use or permissions block `aplay` from opening it.
- Fix: detection now tolerates “busy”/“permission denied” and skips probing while `shairport-sync` is active.
- Mixer absence on USB DACs is expected; converge selects from common controls if available and attempts unmute + 80% volume.

## Git ref lock during update
- Symptom: `cannot lock ref 'refs/remotes/origin/main'` during `git fetch`.
- Generally transient if the tag checkout succeeded. If persistent, consider pruning:
  - `git remote prune origin`
  - `git gc --prune=now`
