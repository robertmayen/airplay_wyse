# Architecture (Simplified)

Goals
- Minimize privileges: no periodic root jobs; privileged actions only for setup/apply.
- Keep integration simple and auditable: rely on vendor packages, minimal templating.
- Be robust by default: avoid Avahi tweaks unless required; auto-detect ALSA.

Components
- Shairport Sync (AirPlay 2) from APT
- NQPTP from APT
- `bin/setup` (root): installs packages, installs hardened shairport override, writes `/etc/shairport-sync.conf`, enables services.
- `bin/apply` (root): reapplies config when name/ALSA settings change and restarts shairport.
- `bin/alsa-probe`: resolves a suitable `hw:<card>,<device>` string with USB preference.
- Optional inventory hints in `inventory/hosts/<short-hostname>.yml` for ALSA.

Security
- Shairport runs as its vendor user with a hardened override:
  - NoNewPrivileges, ProtectSystem=strict, PrivateTmp, MemoryDenyWriteExecute, AF restrictions.
  - Requires/After `nqptp.service` to ensure clocking is ready.
- No on-device Git operations; no timers that write to `/etc`.

Operations
- Install once: `sudo ./bin/setup`
- Update config: `sudo ./bin/apply --name "Living Room"` or `--device hw:0,0 --mixer PCM`
- Observe: `journalctl -u shairport-sync -n 200`, `journalctl -u nqptp -n 200`

Migration
- If you previously used reconcile/converge/update timers, disable and remove those units on devices. The new repo no longer ships them. Use `bin/setup` once, then manage changes with `bin/apply`.

