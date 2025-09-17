# AirPlay Wyse

AirPlay Wyse turns a Wyse 5070 (or any small Debian box with a USB DAC) into a lean AirPlay 2 endpoint.  The repo now ships a single Python-driven `aw` CLI that owns every privileged action: provisioning packages, writing `/etc/shairport-sync.conf`, keeping ALSA/PipeWire policy in sync, and maintaining a stable AirPlay identity.

## Why the rewrite?

Previous revisions accreted shell helpers that called each other in unpredictable ways. The new layout replaces that pile with:

- **One CLI (`aw`)** with well-defined subcommands (`setup`, `apply`, `identity`, `policy-alsa`, `policy-pipewire`, `systemd`, `health`).  All wrappers under `bin/` simply defer to it.
- **State in one place** – `/var/lib/airplay_wyse/config.json` tracks the rendered Shairport settings, ALSA probe results, PipeWire policy and identity fingerprints.
- **Deterministic rendering** – every run re-renders config from a template using that state, so there is no post-hoc file surgery.
- **Runtime bundle** – `aw setup` copies the minimal runtime (Python package + templates + wrappers) to `/usr/local/libexec/airplay_wyse/`, so systemd services execute the same code as the CLI.

## Quick Start

Clone the repo on the target host and run (as root):

```bash
sudo ./bin/setup --name "Living Room"
```

`setup` performs the entire bootstrap in one pass:

1. Installs `shairport-sync`, `nqptp`, and supporting packages if missing.
2. Detects the preferred ALSA card (`hw:X,Y`), writes a simple `/etc/asound.conf`, and stores the probe in state.
3. Generates `/etc/shairport-sync.conf` from the template with sane defaults and unique identity placeholders.
4. Copies the runtime bundle to `/usr/local/libexec/airplay_wyse/` and refreshes the systemd units.
5. Enables/starts `nqptp`, `shairport-sync`, and the AirPlay Wyse helper units.

You can update settings later with:

```bash
sudo ./bin/apply --name "Kitchen" --mixer PCM
```

Both commands accept the same overrides:

| Flag            | Purpose                                   |
|-----------------|--------------------------------------------|
| `--name`        | Advertised name (default still auto-unique)|
| `--mixer`       | Optional ALSA mixer control                |
| `--interface`   | Bind mDNS to a specific NIC                |
| `--device`      | Hint the preferred hw:X,Y card             |
| `--statistics` / `--no-statistics` | Toggle Shairport diagnostics |
| `--force-identity` (setup/apply) | Rebuild AirPlay identity before restart |
| `--force-rate` (setup) | Pin PipeWire clock (44100/48000/88200/96000) |

## What runs on boot?

Three oneshot services remain, but now they are thin wrappers around `aw`:

| Unit | Action |
|------|--------|
| `airplay-wyse-audio-kmods.service` | (Optional) pre-loads kernel modules – unchanged |
| `airplay-wyse-alsa-policy.service` | Executes `aw policy-alsa --json` to ensure `/etc/asound.conf` matches the current hardware |
| `airplay-wyse-pw-policy.service`   | Executes `aw policy-pipewire --json` if PipeWire is present |
| `airplay-wyse-identity.service`    | Executes `aw identity ensure` before `shairport-sync` starts |

Because the CLI writes state and config idempotently, these oneshots no longer mutate files that `setup`/`apply` subsequently touch by hand.

## Identity management

`aw identity ensure` (and the service above) guarantees:

- A stable Shairport AirPlay 2 identifier derived from the chosen interface MAC (falling back to a synthetic, locally-administered MAC when necessary).
- `hardware_address` is always non-zero so classic RAOP advertising stays selectable.
- Cloned images are auto-healed by clearing Shairport’s state the first time a new fingerprint (machine-id + hostname + MAC) is detected.

Calling `./bin/identity-ensure --force` resets identity immediately and re-renders the Shairport config with the updated values.

## ALSA & PipeWire policy

`aw policy-alsa` inspects `/proc/asound/card*/stream*` when available to decide whether the DAC natively supports 44.1 kHz. It writes a small `/etc/asound.conf` that maps `pcm.!default` to the preferred hardware device. If only 48 kHz is available, the CLI ensures Shairport is compiled with libsoxr and sets `output_rate`/`interpolation` accordingly.

PipeWire is optional: if detected, `aw policy-pipewire` writes `/etc/pipewire/pipewire.conf.d/90-airplay_wyse.conf` with a conservative set of allowed clock rates (and an optional forced rate).

## Health & diagnostics

- `./bin/health-probe` → short JSON or human summary of service status.
- `./bin/identity-ensure --force` → reset identity on cloned hosts.
- Legacy helpers such as `bin/debug-audio` and `bin/test-airplay2` remain for now; they execute unchanged, but the underlying helpers now route through the Python CLI.

## Repository layout

```
airplay_wyse/
├── bin/              # Thin wrappers around the aw CLI
├── cfg/              # Shairport template
├── docs/             # Operations/architecture notes
├── src/airplay_wyse/ # Python runtime used by the CLI and systemd units
├── systemd/          # Service definitions and shairport override
└── tools/            # Optional troubleshooting helpers
```

## Runtime installation

`aw setup` copies the runtime to `/usr/local/libexec/airplay_wyse/`. Systemd services call scripts in that directory, so you can safely delete the git checkout afterwards or switch to an artifact-based workflow. To update, refresh the repo, rerun `sudo ./bin/setup`, and the runtime bundle + units will be refreshed automatically.

## Looking ahead

This rewrite focuses on determinism and clarity. Future work can layer better diagnostics on top of the Python core or shrink the remaining shell helpers, but the foundation is now a small, testable codebase instead of a web of shell snippets.
