# Troubleshooting

- Time unsynced: `timedatectl status`; ensure `systemd-timesyncd` active.
- nqptp not healthy: `systemctl status nqptp`; check UDP 319/320 reachability on LAN.
- Not visible in AirPlay picker: verify Avahi adverts with `tests/avahi_browse.sh`.
- ALSA device missing: check `aplay -l`; verify inventory vendor/product/serial.
- Unintended restarts: check hashes in `/var/lib/airplay_wyse/hashes` and journal for diffs.
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
