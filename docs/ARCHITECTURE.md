# Architecture (Simplified)

Goals
- Minimize privileges: no periodic root jobs; privileged actions only for setup/apply.
- Keep integration simple and auditable: rely on vendor packages, minimal templating.
- Be robust by default: avoid Avahi tweaks unless required; auto-detect ALSA.

Components
- Shairport Sync (AirPlay 2) from APT when available; otherwise built from source automatically during setup
- NQPTP from APT when available; otherwise built from source automatically during setup
- `bin/setup` (root): installs packages, installs hardened shairport override, writes `/etc/shairport-sync.conf`, enables services.
- `bin/apply` (root): reapplies config when name/ALSA settings change and restarts shairport.
- `bin/alsa-probe`: resolves a suitable `hw:<card>,<device>` string with USB preference.
- Optional inventory hints in `inventory/hosts/<short-hostname>.yml` for ALSA.
 - Identity management in `bin/lib.sh`: derives a unique default name from MAC and self-heals cloned images by resetting AirPlay 2 identity on first-run/fingerprint change. A one-shot unit (`airplay-wyse-identity.service`) enforces this before `shairport-sync` starts.

## Identity & Advertisement
- Identity oneshot writes a stable, non‑zero deviceid and clears AP2 state on clone to regenerate keys.
- `_airplay._tcp` TXT must contain `pk` and `deviceid`; `_raop._tcp` must be consistent. A readiness unit waits up to 20s for valid TXT.

## Clocking & Sample Rate
- AirPlay is 44.1 kHz; shairport opens the sink at 44100 Hz.
- Probe picks a 44.1k‑capable `hw:<card>,<dev>` (verified via `/proc/.../hw_params`).
- Avoid `default`/`dmix` paths (often 48 kHz) — they cause drift/resyncs.
- If only 48k hardware exists (typical HDMI), setup creates a named `plug` PCM so shairport still opens at 44.1k; ALSA resamples behind it.
- Preflight (`preflight-alsa`) validates the configured PCM: `hw:` must show `rate: 44100` in procfs; `plug` must accept a 44.1k open.

Security
- Shairport runs as its vendor user with a hardened override:
  - NoNewPrivileges, ProtectSystem=strict, PrivateTmp, MemoryDenyWriteExecute, AF restrictions.
  - Requires/After `nqptp.service` to ensure clocking is ready.
- No on-device Git operations; no timers that write to `/etc`.

Notes
- If Shairport is built locally, setup writes a drop‑in to use `/usr/local/bin/shairport-sync`.
 - Identity state lives in `/var/lib/shairport-sync/` (managed by shairport) and `/var/lib/airplay_wyse/instance.json` (fingerprint). The latter avoids cross-host key duplication.

Operations
- Install once: `sudo ./bin/setup`
- Update config: `sudo ./bin/apply --name "Living Room"` or `--device hw:0,0 --mixer PCM`
- Observe: `journalctl -u shairport-sync -n 200`, `journalctl -u nqptp -n 200`

Migration
- If you previously used reconcile/converge/update timers, disable and remove those units on devices. The new repo no longer ships them. Use `bin/setup` once, then manage changes with `bin/apply`.
