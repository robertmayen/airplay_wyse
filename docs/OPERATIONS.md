# Operations (Simplified, Least‑Privilege)

This document describes a simplified operational workflow for running a Wyse 5070 + USB DAC as an AirPlay 2 receiver. There is no periodic, root‑run GitOps loop. Privileged work is limited to one‑time setup and on‑demand config application.

## Overview
- Install once with `bin/setup` (root): installs packages, writes `/etc/shairport-sync.conf`, installs hardened shairport override, enables nqptp + shairport.
- Apply config changes with `bin/apply` (root) when name or ALSA settings change.
- Shairport runs as its vendor user with a hardened systemd override. NQPTP runs via its vendor unit.

## Prerequisites (Device)
- Debian 13 preferred (APT provides `shairport-sync` with AirPlay 2 and `nqptp`).
- Repository cloned to `/opt/airplay_wyse`.

## Setup
Run once (as root):
```
sudo ./bin/setup
```
Options:
- Default device name is unique per host (e.g., "Wyse DAC-ABCD", derived from MAC).
- ALSA device is auto‑detected via `bin/alsa-probe`.
  - USB DACs are selected as raw `hw:<card>,<dev>`.
  - If no USB DAC is present, onboard codecs fall back to `plughw:<card>,<dev>` so ALSA can resample 44.1 kHz → 48 kHz when needed.
 - AirPlay 2 only: `bin/setup` guarantees `nqptp` is installed. If `shairport-sync` with AirPlay 2 or `nqptp` are not available via APT, they are built from source automatically.

Validate after setup:
```
./bin/test-airplay2
```

## Update Configuration
Apply new name, ALSA settings, or bind to a specific network interface (as root):
```
sudo ./bin/apply --name "Living Room"
sudo ./bin/apply --device hw:0,0 --mixer PCM
sudo ./bin/apply --interface wlp0s12f0
```

You can also set environment variables when running `setup`/`apply`:
- `AIRPLAY_NAME`, `ALSA_DEVICE`, `ALSA_MIXER`, `AVAHI_IFACE`, `HW_ADDR`
If `AVAHI_IFACE` is set and `HW_ADDR` is not, the hardware address is derived from the interface.

Identity management
- Identity self-heals automatically: a one-shot unit (`airplay-wyse-identity.service`) runs before `shairport-sync` (and after the network is online) to ensure:
  - A non-zero AirPlay 2 device identity: sets `general.airplay_device_id` from the primary NIC MAC (format `0xAABBCCDDEEFFL`). If no real MAC is readable, it synthesizes a stable locally-administered MAC from `/etc/machine-id` (sets LAA bit, clears multicast) and derives the AP2 ID from it.
  - A unique default name (Wyse DAC-<MACSUFFIX>) if the name is generic or missing.
  - Cloned images are reset safely: on first-run or when the host fingerprint changes, it purges Shairport’s AP2 state so a fresh keypair is generated on next start. TXT `pk` changes accordingly.
  - Fingerprint includes `machine-id`, hostname and MAC; state recorded at `/var/lib/airplay_wyse/instance.json`.

## Cloning Checklist
When cloning images across multiple hosts, ensure identity is unique and RAOP does not collide:

- Ensure each clone has a unique `/etc/machine-id`.
  - On systemd systems, this is regenerated automatically on first boot; see https://unix.stackexchange.com/questions/402999.
  - The identity oneshot waits briefly for `machine-id` to exist to avoid using an empty or duplicated value.
- After cloning, run once (as root):
  - `sudo /opt/airplay_wyse/bin/identity-ensure --force && sudo systemctl restart shairport-sync`
  - This purges Shairport-Sync’s AirPlay-2 state (usually under `/var/lib/shairport-sync/` via the unit’s StateDirectory) so a fresh keypair is generated. The `_airplay._tcp` TXT `pk` will change as a result.
- Verify from the device:
  - `./bin/verify-airplay-identity` prints a summary and fails if `pk` is missing or if `deviceid` is `00:00:00:00:00:00`.
  - `./bin/test-airplay2 --mdns` includes the same checks.

- Notes
- The identity step writes `interface = "...";`, `airplay_device_id = 0x...L;` (AP2), and `hardware_address = "...";` (RAOP) into `/etc/shairport-sync.conf`.
  - AP2 identity uses `airplay_device_id` and TXT `pk`.
  - Classic RAOP uses a MAC-like prefix for its instance name; we ensure it is non‑zero by setting `hardware_address` when missing or zero.
- The chosen interface is stable and deterministic: explicit `AIRPLAY_WYSE_IFACE` → default route NIC → first UP with carrier → first UP non-loopback.

Why pk uniqueness matters
- Controllers use AirPlay‑2 TXT `pk` as the stable device identity (see OpenAirplay service_discovery notes). If two hosts share the same `pk`, only one will be usable. This repo enforces uniqueness by purging the Shairport‑Sync AP2 state on clone or fingerprint change so a fresh keypair and `pk` are generated.
What `airplay_device_id` does
- Shairport‑Sync uses `general.airplay_device_id` (48‑bit integer) as the AirPlay‑2 device ID, typically derived from the NIC MAC. We compute and write it explicitly to avoid zero IDs and make boot ordering deterministic.

Interface override and timing
- The identity step chooses the primary interface deterministically: env override `AIRPLAY_WYSE_IFACE` (or `/etc/default/airplay_wyse`) → default route NIC → first UP with carrier → first UP non‑loopback. It waits up to 10s for an interface to appear before synthesizing a fallback device identity.

Notes on MAC randomization
- If NetworkManager MAC randomization is enabled, the broadcast MAC may change between boots. For AirPlay receivers, prefer a permanent/stable MAC policy on the receiver NIC to keep identity stable. The identity step will still provide a stable synthetic fallback if a real MAC is unavailable.

Verification
- Use `./bin/verify-airplay-identity` to validate the local AirPlay identity. It fails if `_airplay._tcp` TXT `pk` is missing or if `deviceid` is zero; prints a one‑line summary.

## Optional Host Inventory
For environments with multiple similar hosts, `bin/alsa-probe` continues to honor optional hints at `inventory/hosts/<short-hostname>.yml`:
```yaml
alsa:
  mixer: "PCM"        # optional
  device_num: 0       # optional
  vendor_id: "0x08bb" # optional (USB)
  product_id: "0x2902"# optional (USB)
```

## Clocking & Sample Rate
- AirPlay is 44.1 kHz; shairport must open at 44100 Hz.
- Good: raw `hw:<card>,<dev>` with `/proc/.../hw_params` rate: 44100.
- If only 48k hardware exists (HDMI), we create a named `plug` PCM; shairport still opens at 44.1k (resampling hidden).
- Avoid `default`/`dmix` unless explicitly configured and verified at 44.1k.
- Good stats: `Output FPS (r) ≈ 44100.xx`; Bad: `≈ 47xxx` → you’re on a 48k path.
- If preflight blocks start, re-run `bin/apply` to select a 44.1k sink or attach a USB DAC.

## Health & Troubleshooting
- Quick view: `./bin/test-airplay2` (strict checks).
- Detailed view: `./bin/test-airplay2 --logs --mdns --alsa`.
- Logs: `journalctl -u shairport-sync -n 200` and `journalctl -u nqptp -n 200`.
- Verify AirPlay 2 capability: `shairport-sync -V | grep -q "AirPlay2"`.
- Verify nqptp active: `systemctl is-active nqptp`.
- Verify advertisement: `avahi-browse -rt _airplay._tcp` (RAOP `_raop._tcp` may appear as a fallback).

If your device does not appear
- Ensure `/etc/shairport-sync.conf` has no leftover template markers.
- Try binding to your active NIC using `--interface <iface>`; find it via `ip -o link show | grep 'state UP'`.
- Remove any custom Avahi restrictions if you previously limited interfaces.
- Re-run: `sudo ./bin/apply`.

## Security Notes
- Shairport runs as its vendor user with hardened limits via `systemd/overrides/shairport-sync.service.d/override.conf`.
- No root‑run timers or on‑device Git operations.

Note on NQPTP
- AirPlay 2 requires `nqptp`. Setup installs it; if the package is unavailable, it is built from source automatically. The service override requires `nqptp` and orders shairport after it.

## Acceptance Checklist
- `./bin/test-airplay2` completes without errors.
- `shairport-sync -V` contains `AirPlay2`.
- `systemctl is-active nqptp` returns `active`.
- `_airplay._tcp` visible via `avahi-browse -rt _airplay._tcp` (or `_raop._tcp`).
- `bin/alsa-probe` returns an ALSA device string and `aplay -D <device>` can open it (busy tolerated).
- Debugging
- To enable extra runtime statistics in Shairport logs and run extensive checks, set:
  - `sudo sh -c 'echo AIRPLAY_WYSE_DEBUG=1 >> /etc/default/airplay_wyse'`
  - Re-render config: `sudo ./bin/apply`
  - Check: `journalctl -u shairport-sync -n 200 | rg -i "underrun|overrun|xruns|buffer|latency"`
  - Use `./bin/debug-audio` for a comprehensive diagnostic; it prints `Sink rate OK` when Output FPS is ~44100 and shows active hw_params when on `hw:`.

Decision tree (≤10 lines):
- Output FPS ~47k or preflight fails → you’re on 48k.
- If USB DAC available → it will be auto-selected (`hw:` 44.1k) → OK.
- If analog PCH supports 44.1k → use `hw:0,0` → OK.
- If HDMI-only → we create a `plug` PCM; shairport opens at 44.1k → OK.
- Still failing → stop other apps using ALSA; avoid `default`/`dmix`; attach a USB DAC.
