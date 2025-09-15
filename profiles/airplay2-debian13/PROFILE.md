#!/usr/bin/env markdown

# Profile: AirPlay 2 on Debian 13 (trixie)

Target
- Wyse 5070 (or similar x86) running Debian 13
- AirPlay 2 only; no Bluetooth/Spotify features by default

Adaptive resampling policy
- PipeWire-first, rate-following: configure `default.clock.allowed-rates = [44100 48000 88200 96000]` and do not force a fixed graph rate.
- Shairport Sync uses ALSA backend to the system `default` device, which is an anchored chain `plug -> softvol -> dmix -> hw` at 44.1 kHz when supported, otherwise 48 kHz.
- When anchored at 48 kHz, Shairport uses libsoxr interpolation with `output_rate = 48000` so only one high-quality resampler operates in the path. PipeWire does not resample a second time.

Service graph
- `airplay-wyse-identity.service` (oneshot) ensures non-zero AP2 device identity and stable interface selection.
- `airplay-wyse-audio-kmods.service` (oneshot) preloads common audio kernel modules.
- `airplay-wyse-alsa-policy.service` (oneshot) generates `/etc/asound.conf` deterministically.
- `airplay-wyse-pw-policy.service` (oneshot) writes PipeWire allowed-rates drop-in (no-op if PipeWire absent).
- `shairport-sync.service` requires and starts after: identity, kmods, ALSA policy, `nqptp.service`, and `avahi-daemon.service`. It is `PartOf=nqptp.service` for causal restart.

Acceptance checklist
- `_airplay._tcp` visible on the LAN.
- `nqptp` owns UDP 319/320; no other PTP daemons.
- With a 44.1-capable DAC: AP2 runs at 44.1 without resampling.
- With a 48-only sink: AP2 runs at 48; Shairport shows libsoxr and performs a single 44.1→48 conversion; PipeWire not resampling.
- Group playback stable; recovery after `nqptp` restart works.
- Hotplug DAC: ALSA policy regenerates on apply/boot and Shairport restarts with correct anchor.

Failure playbooks
- Advertises but drifts: check 319/320 conflicts and multicast reachability for PTP.
- Not visible: confirm `avahi-daemon` active and UDP 5353 allowed; scope interfaces if multi-NIC.
- 48-only sink: expect `anchor=48000 + soxr` in diagnostics.

Notes
- PipeWire presence is optional; ALSA fallback remains deterministic.
- Forcing a PipeWire graph rate is supported via `PW_FORCE_RATE=...` but is off by default.

