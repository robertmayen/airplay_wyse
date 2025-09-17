# Architecture (Simplified)

Goals
- Minimize privileges: no periodic root jobs; privileged actions only for setup/apply.
- Keep integration simple and auditable: rely on vendor packages, minimal templating.
- Be robust by default: avoid Avahi tweaks unless required; auto-detect ALSA.

Components
- Shairport Sync (AirPlay 2) from APT when available; otherwise built from source automatically during setup. AP2 requires NQPTP. See Shairport Sync docs: https://github.com/mikebrady/shairport-sync#readme
- NQPTP from APT when available; otherwise built from source automatically during setup. NQPTP owns UDP 319/320 and runs unprivileged via AmbientCapabilities. See: https://github.com/mikebrady/nqptp#readme
- `aw` CLI (Python): owns every privileged action. Thin wrappers in `bin/` exist for ergonomics (`bin/setup`, `bin/apply`, `bin/identity-ensure`, `bin/alsa-policy-ensure`, etc.) but each simply execs `aw <subcommand>`.
- ALSA policy (`aw policy-alsa`): probes DAC capabilities and writes `/etc/asound.conf` as `plug -> hw`, anchored at either 44.1 kHz (AirPlay-native) or 48 kHz (hardware-native + soxr). State lives in `/var/lib/airplay_wyse/config.json` under `alsa_policy`.
- PipeWire policy (`aw policy-pipewire`): when PipeWire exists, writes `/etc/pipewire/pipewire.conf.d/90-airplay_wyse.conf` setting `default.clock.allowed-rates = [44100 48000 88200 96000]`, optionally forcing a rate.
- Identity management (`aw identity ensure`): derives a stable default name from the MAC, generates AirPlay IDs, clears stale Shairport state on fingerprint changes, and persists the fingerprint in `/var/lib/airplay_wyse/instance.json`. A one-shot unit (`airplay-wyse-identity.service`) enforces this before `shairport-sync` starts.
- `airplay-wyse-audio-kmods.service`: best-effort oneshot that loads common audio modules (`snd_usb_audio`, `snd_hda_intel`) early in boot. `shairport-sync` is ordered after this, identity, and the ALSA policy units.
- Optional inventory hints: `bin/alsa-probe` reads `inventory/hosts/<short-hostname>.yml` when present; the repo does not ship inventory data by default.

Security
- Shairport runs as its vendor user with a hardened override:
  - NoNewPrivileges, ProtectSystem=strict, PrivateTmp, MemoryDenyWriteExecute, AF restrictions.
  - Requires/After `nqptp.service` to ensure clocking is ready.
- No on-device Git operations; no timers that write to `/etc`.
- Systemd ordering for Shairport: `Requires=airplay-wyse-identity.service airplay-wyse-audio-kmods.service airplay-wyse-alsa-policy.service nqptp.service` and `After=` the same, ensuring identity, kernel modules, and the ALSA policy are in place with NQPTP clocking ready.
- Avahi must be active to advertise `_airplay._tcp`. See Debian avahi-daemon: https://manpages.debian.org/trixie/avahi-daemon/avahi-daemon.8.en.html

Dependency semantics
- `Requires=` ensures the required unit is started/stopped with the dependent; `After=` imposes ordering only; `PartOf=`/`BindsTo=` propagate stop/restart semantics. See systemd.unit: https://www.freedesktop.org/software/systemd/man/systemd.unit.html

Notes
- If Shairport is built locally, setup writes a drop-in to use `/usr/local/bin/shairport-sync`.
- Identity state lives in `/var/lib/shairport-sync/` (managed by shairport) and `/var/lib/airplay_wyse/instance.json` (fingerprint). The latter avoids cross-host key duplication.
- ALSA policy state lives in `/var/lib/airplay_wyse/config.json` under `alsa_policy`; `/etc/asound.conf` mirrors that selection. The policy is idempotent and regenerates only when the device fingerprint changes (card id/device num/anchor/format).

Anchoring modes (adaptive)
- 44.1-anchored (default): selected if the DAC natively supports 44,100 Hz. AirPlay 2 audio (44.1 kHz) flows bit-stably to ALSA without resampling; other clients are converted by the `plug` layer.
- 48-anchored + soxr: selected when the device does not support 44.1 kHz (e.g., HDMI-only sinks). Shairport is configured to use libsoxr interpolation and `output_rate = 48000` to preserve sync and quality; ALSA is anchored at 48 kHz for stability.

PipeWire policy
- If PipeWire is present, configure rate-following via allowed-rates; do not force a fixed rate in AUTO mode. See pipewire(1): https://docs.pipewire.org/page_man_pipewire.html and pipewire.conf(5): https://docs.pipewire.org/page_man_pipewire.conf.html

Why this design
- Predictable, minimal stack: ALSA policy keeps configuration deterministic and easy to audit.
- AirPlay-first: 44.1 kHz is favored to keep the AirPlay path resampling-free when the hardware allows it.
- Clone-safe: policy generation uses stable card IDs, not indices; unit ordering ensures the policy is in place before Shairport starts.

Operations
- Install once: `sudo ./bin/setup`
- Update config: `sudo ./bin/apply --name "Living Room"` or `--device hw:0,0 --mixer PCM`
- Observe: `journalctl -u shairport-sync -n 200`, `journalctl -u nqptp -n 200`

Migration
- If you previously used reconcile/converge/update timers, disable and remove those units on devices. The new repo no longer ships them. Use `bin/setup` once, then manage changes with `bin/apply`.
