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
- `bin/alsa-policy-ensure` (root): probes DAC capabilities and generates `/etc/asound.conf` with a deterministic chain `plug -> softvol -> dmix -> hw`, anchored at either 44.1 kHz (AirPlay‑native) or 48 kHz (hardware‑native + soxr). Writes `/var/lib/airplay_wyse/alsa-policy.json` with the fingerprint and selected mode.
- `airplay-wyse-audio-kmods.service`: best‑effort oneshot that loads common audio modules (`snd_usb_audio`, `snd_hda_intel`) early in boot. `shairport-sync` is ordered after this, identity, and the ALSA policy units.
- Optional inventory hints in `inventory/hosts/<short-hostname>.yml` for ALSA.
 - Identity management in `bin/lib.sh`: derives a unique default name from MAC and self-heals cloned images by resetting AirPlay 2 identity on first-run/fingerprint change. A one-shot unit (`airplay-wyse-identity.service`) enforces this before `shairport-sync` starts.

Security
- Shairport runs as its vendor user with a hardened override:
  - NoNewPrivileges, ProtectSystem=strict, PrivateTmp, MemoryDenyWriteExecute, AF restrictions.
  - Requires/After `nqptp.service` to ensure clocking is ready.
- No on-device Git operations; no timers that write to `/etc`.
- Systemd ordering for Shairport: `Requires=airplay-wyse-identity.service airplay-wyse-audio-kmods.service airplay-wyse-alsa-policy.service nqptp.service` and `After=` the same, ensuring identity, kernel modules, and the ALSA policy are in place with NQPTP clocking ready.

Notes
- If Shairport is built locally, setup writes a drop‑in to use `/usr/local/bin/shairport-sync`.
- Identity state lives in `/var/lib/shairport-sync/` (managed by shairport) and `/var/lib/airplay_wyse/instance.json` (fingerprint). The latter avoids cross-host key duplication.
- ALSA policy state lives in `/var/lib/airplay_wyse/alsa-policy.json` and `/etc/asound.conf`. The policy is idempotent and regenerates only when the device fingerprint changes (card id/device num/anchor/format).

Anchoring modes
- 44.1‑anchored (default): selected if the DAC natively supports 44,100 Hz. AirPlay 2 audio (44.1 kHz) flows bit‑stably to ALSA without resampling; other clients are converted by the `plug` layer into the anchored dmix at 44.1 kHz.
- 48‑anchored + soxr: selected when the device does not support 44.1 kHz (e.g., HDMI‑only sinks). Shairport is configured to use libsoxr interpolation and `output_rate = 48000` to preserve sync and quality; ALSA is anchored at 48 kHz for multi‑client stability.

Why this design
- Predictable, minimal stack: ALSA‑only policy centered around dmix provides deterministic mixing with a fixed clock domain.
- AirPlay‑first: 44.1 kHz is favored to keep the AirPlay path resampling‑free when the hardware allows it.
- Clone‑safe: policy generation uses stable card IDs, not indices; unit ordering ensures the policy is in place before Shairport starts.

Operations
- Install once: `sudo ./bin/setup`
- Update config: `sudo ./bin/apply --name "Living Room"` or `--device hw:0,0 --mixer PCM`
- Observe: `journalctl -u shairport-sync -n 200`, `journalctl -u nqptp -n 200`

Migration
- If you previously used reconcile/converge/update timers, disable and remove those units on devices. The new repo no longer ships them. Use `bin/setup` once, then manage changes with `bin/apply`.
