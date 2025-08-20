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
