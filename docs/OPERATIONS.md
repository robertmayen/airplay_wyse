# Operations

AirPlay Wyse is managed by Ansible. All day-to-day operations are playbook runs
from the control machine. There is no on-device CLI or runtime bundle to update.

## Provisioning (first time)

```bash
ansible-playbook site.yml -l <hostname>
```

The `airplay` role:

1. Installs build dependencies and runtime packages.
2. Builds shairport-sync and nqptp from source at pinned versions, verifying
   required features after each build.
3. Renders `/etc/shairport-sync.conf` from the Jinja2 template using per-host
   `host_vars/`.
4. Writes a hardened systemd drop-in override for `shairport-sync.service`.
5. Installs `airplay-doctor` to `/usr/local/bin/`.

## Applying Changes

Configuration is idempotent — re-run `site.yml` after editing any variable:

```bash
# Change the advertised name for one host
# 1. Edit host_vars/<hostname>.yml: set airplay_name
# 2. Re-apply:
ansible-playbook site.yml -l <hostname>
```

## Migrating from the Legacy Stack

For boxes that were running the old Python/shell implementation:

```bash
ansible-playbook migration.yml -l <hostname>
ansible-playbook site.yml      -l <hostname>
airplay-doctor --check
```

`migration.yml` removes `/var/lib/airplay_wyse/`, `/usr/local/libexec/airplay_wyse/`,
and the legacy `airplay-wyse-*` systemd units before the Ansible role takes over.

## Health Checks

### On the control machine (non-invasive, fleet-wide)

```bash
ansible-playbook doctor.yml
```

Runs `airplay-doctor --check` on every host and reports failures. Also checks
for duplicate `airplay_device_id` values across the fleet.

### On the box directly

```bash
airplay-doctor --check            # exits 0 if healthy
airplay-doctor --json             # machine-readable output
airplay-doctor --deep             # adds ALSA device-open probe (optional)
```

## Updating shairport-sync

1. Update `shairport_sync_version` and `shairport_sync_sha256` in
   `group_vars/airplay.yml`.
2. Run `site.yml` against the spare box and verify the spare-box matrix
   (see README rollout runbook, step 3).
3. Roll to the fleet:

   ```bash
   ansible-playbook site.yml
   ansible-playbook doctor.yml
   ```

## Drift Correction

If a box drifts from the desired state (manual edits, package updates, etc.),
re-run `site.yml`:

```bash
ansible-playbook site.yml -l <hostname>
```

## Cloned Images

Cloned boxes may share a shairport-sync device ID. Set `airplay_device_id`
explicitly in `host_vars/<hostname>.yml` for each box to guarantee uniqueness,
then re-run `site.yml`. The fleet-wide duplicate check in `doctor.yml` will
flag any remaining conflicts.

## Systemd

Standard systemd commands apply — the role does not install any custom wrappers:

```bash
systemctl status shairport-sync
systemctl status nqptp
journalctl -u shairport-sync -n 200
journalctl -u nqptp -n 200
```

## Troubleshooting

- Confirm AirPlay 2 feature set: `shairport-sync -V | grep -i airplay2`
- Check mDNS advertisement: `avahi-browse -rt _airplay._tcp`
- ALSA sanity: `aplay -D <airplay_alsa_card> /usr/share/sounds/alsa/Front_Center.wav`
- Journal errors since last boot: `journalctl -u shairport-sync -b --no-pager`
- Full doctor report: `airplay-doctor --deep --json`
