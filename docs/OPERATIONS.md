# Operations

AirPlay Wyse is now driven by the `aw` CLI. This document captures the operational runbook after the refactor.

## Provisioning

```bash
sudo ./bin/setup --name "Living Room"
```

This single command:

1. Installs/refreshes the runtime under `/usr/local/libexec/airplay_wyse/`.
2. Ensures `shairport-sync`, `nqptp`, `jq`, `alsa-utils`, and `avahi-daemon` are present.
3. Detects the preferred playback device (`hw:X,Y`) and writes `/etc/asound.conf` so `pcm.!default` follows it.
4. Renders `/etc/shairport-sync.conf` from the bundled template, storing all inputs in `/var/lib/airplay_wyse/config.json`.
5. Refreshes the systemd units and enables the services.

### Useful flags

| Flag | Effect |
|------|--------|
| `--name` | Advertised AirPlay name |
| `--device` | Prefer a specific ALSA device (still rendered as `default` inside shairport) |
| `--mixer` | Add a mixer control for softvol-compatible sinks |
| `--interface` | Pin mDNS to an interface; feeds into identity selection |
| `--force-identity` | Reset AirPlay identity before restarting services |
| `--statistics` / `--no-statistics` | Toggle shairport diagnostics |
| `--force-rate` | Pin PipeWire’s graph rate (44100/48000/88200/96000) |

## Applying changes

Configuration tweaks use the same options as setup:

```bash
sudo ./bin/apply --name "Kitchen" --mixer PCM
```

`apply` re-runs the ALSA probe, updates state, re-renders the shairport config, and restarts `shairport-sync`.

## Identity management

Run on boot via `airplay-wyse-identity.service` or manually:

```bash
sudo ./bin/identity-ensure [--force]
```

Identity logic:

- Picks an interface (env override → default route → first UP with carrier → first UP non-loopback).
- Reads the MAC or synthesises a stable locally-administered MAC from `/etc/machine-id`.
- Writes `general.airplay_device_id`, `general.hardware_address`, and `general.name` (defaulting to `Wyse DAC-<suffix>` when unset).
- Records a fingerprint in `/var/lib/airplay_wyse/instance.json`. When it changes—or when `--force` is supplied—Shairport state is cleared to regenerate AirPlay 2 keys on next start.

## ALSA policy

```bash
sudo ./bin/alsa-policy-ensure --json
```

The helper emits a JSON summary after ensuring `/etc/asound.conf` matches the current hardware. If only 48 kHz is available it sets `requires_soxr = true`; `setup/apply` then insists that `shairport-sync -V` advertises libsoxr support before continuing.

## PipeWire policy

```bash
sudo ./bin/pw-policy-ensure --json [--force-rate 48000]
```

If PipeWire is present, the helper writes `/etc/pipewire/pipewire.conf.d/90-airplay_wyse.conf` with the allowed rates (`44100 48000 88200 96000`) and an optional forced rate. When PipeWire is absent, it is a no-op.

## Systemd refresh

The runtime bundles the systemd files; refresh them without re-running setup:

```bash
sudo ./bin/install-units
```

This copies the units from the repo into `/etc/systemd/system`, reinstalls the shairport drop-in, and runs `systemctl daemon-reload`.

## Health snapshot

```bash
./bin/health-probe --json
```

Returns the status of the key services (`nqptp`, `shairport-sync`, `airplay-wyse-identity`).

## Updating the runtime

- Pull new code.
- Run `sudo ./bin/setup` again. It overwrites the libexec bundle and systemd units.
- Existing state in `/var/lib/airplay_wyse/config.json` is merged, so names/mixer settings persist.

## Cloning hosts

1. Ensure cloned images generate a new `/etc/machine-id` on first boot.
2. On the clone, run `sudo ./bin/identity-ensure --force && sudo systemctl restart shairport-sync`.
3. Verify: `./bin/health-probe --json` and `avahi-browse -rt _airplay._tcp`.

## Troubleshooting tips

- Confirm AirPlay 2 support: `shairport-sync -V | grep -q "AirPlay2"`.
- PipeWire clock: `pw-cli info 0 | grep default.clock.rate` (if PipeWire is running).
- ALSA playback sanity: `aplay -D default /usr/share/sounds/alsa/Front_Center.wav`.
- Full diagnostic still available via `./bin/test-airplay2` (legacy script; outputs remain useful but its internals now rely on the Python helpers).
