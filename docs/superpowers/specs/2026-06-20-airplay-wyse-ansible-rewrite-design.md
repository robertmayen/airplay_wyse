# AirPlay Wyse — Ansible Rewrite Design

- **Date:** 2026-06-20
- **Status:** Approved design, pre-implementation
- **Branch:** `ansible-rewrite`

## Context

`airplay_wyse` turns small Debian boxes (Wyse 5070 + USB DAC) into AirPlay 2
endpoints. The current implementation is an on-device Python CLI (`aw`, ~1,300
lines) plus ~1,085 lines of shell, carrying its own JSON state machine
(`/var/lib/airplay_wyse/config.json`), a runtime-bundle deploy step, several
boot-time oneshot systemd services, and a set of standalone awk diagnostics that
re-implement the Python logic. CI masks all failures with `|| true` and the
"tests" are file-existence greps.

The code drifted from its origin: it was borrowed from
[nicokaiser/rpi-audio-receiver](https://github.com/nicokaiser/rpi-audio-receiver),
whose `install.sh` builds ALAC + nqptp + shairport-sync **from source** with
`--with-airplay-2 --with-apple-alac`. The Python fork instead installs
shairport-sync from **apt** (which on Debian 13 trixie is an AirPlay **1** build:
`shairport-sync 4.3.7-1`, no `nqptp` packaged) and only builds nqptp from source
as a fallback. The user's box works today almost certainly because shairport was
built from source manually at some earlier point; the tooling never owned that
build.

## Goal

Replace the on-device Python/state/wrapper/systemd stack with an **Ansible
project** that provisions 2–5 hand-built Debian 13 boxes from the operator's
laptop, plus **one** small stdlib-Python diagnostic tool that lives on each box.
Restore the proven from-source build. Make idempotent re-runs the drift-detection
and update mechanism. Add real, failing-capable CI.

## Decisions (from brainstorming)

- **Scope:** full clean rebuild.
- **Tool:** Ansible for provisioning/config/update; one stdlib-Python file
  (`airplay-doctor.py`) on the box for diagnostics. (Approach "B".)
- **Fleet:** 2–5 hand-built boxes, provisioned individually. No cloned images.
- **Capabilities wanted:** real diagnostics/health, remote multi-box management,
  newer shairport features (opt-in), auto-update / drift detection.
- **Current box already works as AirPlay 2** — the rebuild must reproduce its
  working recipe and must not regress it.

## Non-goals (YAGNI)

- No cloned-image identity-healing, no synthetic MACs, no boot-time identity
  regeneration, no boot-time ALSA re-detection (these existed for a cloned-fleet
  model we are not using).
- No Bluetooth / Snapcast / Spotify receivers (nicokaiser's other roles).
- No web dashboard in this iteration.
- No `ansible-pull` self-applying agent on the box (overkill for 2–5 boxes;
  drift is corrected by re-running the playbook from the laptop).

## Architecture

Ansible-first. Everything that provisions, configures, builds, hardens, and
updates a box is an Ansible role/playbook run from the laptop. The only code that
lives and runs on the box is `airplay-doctor.py` (diagnostics/health) and the
built binaries + systemd units.

### Repo layout

```
airplay_wyse/
├── ansible.cfg
├── site.yml                    # provision/converge all boxes
├── migration.yml               # one-time cleanup of the old Python/state install
├── doctor.yml                  # run airplay-doctor across the fleet, gather reports
├── inventory/
│   ├── hosts.yml               # the 2-5 boxes
│   ├── group_vars/airplay.yml  # version pins, build profile, shared defaults
│   └── host_vars/<box>.yml     # per-box: airplay_name, alsa device, optional id
├── roles/airplay/
│   ├── defaults/main.yml       # versions, profile, feature toggles
│   ├── tasks/
│   │   ├── main.yml
│   │   ├── build.yml           # ALAC + nqptp + shairport from source (gated)
│   │   ├── config.yml          # render shairport-sync.conf
│   │   ├── systemd.yml         # units + hardening override + optional health timer
│   │   └── doctor.yml          # install airplay-doctor.py
│   ├── templates/
│   │   ├── shairport-sync.conf.j2
│   │   ├── shairport-override.conf.j2
│   │   └── nqptp.service.j2          # if not shipped by the build
│   ├── files/airplay-doctor.py       # single source of the tool
│   └── handlers/main.yml             # restart shairport-sync, daemon-reload
├── tests/test_airplay_doctor.py
├── README.md
└── .github/workflows/ci.yml          # yamllint + ansible-lint + syntax-check + pytest
```

## Build (from source, version-profiled)

Restores the nicokaiser recipe: compile **ALAC, nqptp, and shairport-sync from
source**. Versions are variables so a bump + re-run is the update path.

### Two build profiles — never one configure line

`shairport_major` selects a profile. The configure flags and config-file schema
differ between majors and must not be merged.

- **`shairport_major: "4"` (default).** Flags:
  `--sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl
  --with-systemd --with-airplay-2 --with-apple-alac`. External ALAC built and
  installed first. Config uses 4.x keys.
- **`shairport_major: "5"` (opt-in).** Flags per upstream BUILD.md:
  `--with-systemd-startup` instead of `--with-systemd`, **no** `--with-apple-alac`
  (5.x decodes ALAC via FFmpeg/libav*), 5.x config keys per
  CONFIGURATIONFILECHANGES5.md. Unlocks lossless / multichannel. Must be validated
  on a spare box before any production box because of the breaking config changes.

### Default version pins (explicit)

```yaml
shairport_major: "4"
shairport_sync_version: "4.3.7"   # matches trixie's packaged version → known config schema
nqptp_version: "1.2.8"            # current stable, beyond nicokaiser's 1.2.4
alac_ref: "master"
```

**Verification gate (plan step, not a placeholder):** before finalizing, capture
the working box's `shairport-sync -V` and OS version; if its shairport version
differs from `4.3.7`, set `shairport_sync_version` to match the working box
exactly. The defaults above are the starting point, adjusted by this captured
fact.

### Build dependencies (trixie)

```
build-essential git autoconf automake libtool libpopt-dev libconfig-dev
libasound2-dev avahi-daemon libavahi-client-dev libssl-dev libsoxr-dev
libplist-dev libsodium-dev libavutil-dev libavcodec-dev libavformat-dev
uuid-dev libgcrypt20-dev xxd systemd-dev
```

(`systemd-dev` is required on trixie; omit-on-older is not a concern here.)

### Idempotence — stamp file + mandatory feature re-verification

`/usr/local/share/airplay/.versions` (JSON) records, per component: the source
ref, the exact configure args, a build hash (deps + flags), the installed binary
path, and the captured `-V` output. The build tasks skip a component only when
its stamp matches the requested pin/flags **and** the binary exists.

A stale stamp must never mask a broken binary, so **every run** (independent of
the stamp) verifies the installed binaries expose the required features:
`shairport-sync -V` must contain `AirPlay 2`, `soxr`, and (major 4) `ALAC`;
`nqptp -v` runs clean. Missing features fail the play.

## Identity (simplified, with escape hatch)

Each box has a real NIC; shairport-sync derives a stable AirPlay device-id from
the hardware MAC. The only required per-host identity input is `airplay_name`.

- Deleted: interface selection, zero-MAC handling, synthetic MAC, clone
  fingerprinting, `/var/lib/airplay_wyse` identity state.
- **Escape hatch:** `airplay_device_id` is an optional per-host var; when set it
  is templated into the config to pin the id independent of hardware.
- `airplay-doctor` flags a zero device-id and detects **duplicate** ids across
  the fleet (from rendered config + observed mDNS), since collisions break
  multi-box AirPlay.

## Config

Minimal, templated per host:

- `name = "{{ airplay_name }}"`
- direct ALSA output pinned by **stable name**:
  `output_device = "hw:CARD={{ airplay_alsa_card }}"` (survives USB
  re-enumeration; keeps the fork's one genuine improvement over nicokaiser)
- `interpolation = "soxr"`
- `disable_standby_mode = "always"` (USB-DAC pop avoidance, upstream-recommended)
- `output_rate` only when the DAC cannot do native 44.1 kHz
- optional `airplay_device_id` when the per-host var is set
- **No `/etc/asound.conf`** — shairport opens the DAC directly.

## systemd

Use the unit shipped by the build (4.x `--with-systemd` / 5.x
`--with-systemd-startup`) plus the nqptp unit. Layer a hardening **override
drop-in**:

- `NoNewPrivileges=yes`, `ProtectSystem=strict`, `ProtectHome=yes`,
  `PrivateTmp=yes`, `ProtectKernelTunables=yes`, `ProtectKernelModules=yes`,
  `ProtectControlGroups=yes`, `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`,
  `SystemCallFilter=@system-service`.
- **Writable state for AirPlay 2 pairing:** `ProtectSystem=strict` makes the FS
  read-only, but shairport-sync persists AirPlay 2 pairing keys. Grant
  `StateDirectory=shairport-sync` and `CacheDirectory=shairport-sync` (and any
  explicit `ReadWritePaths=` the build needs). Without this, pairing breaks on
  restart. **Verify the real state path on the target build.**
- **Audio device access:** `DeviceAllow=char-alsa rw` paired with
  `DevicePolicy=closed` (do **not** use `PrivateDevices=yes` — it hides
  `/dev/snd`).
- Leave realtime scheduling intact (do not blanket `RestrictRealtime=yes`; test
  sync quality if added).
- nqptp keeps `CAP_NET_BIND_SERVICE` (ports 319/320) via `AmbientCapabilities`.
- Ordering: shairport `Requires=`/`After=` nqptp + avahi-daemon.

Deleted: all custom oneshots (`airplay-wyse-identity/alsa-policy/audio-kmods`),
the runtime-bundle libexec wrappers, the `check-airplay-device-id` ExecStartPre.

**Optional health timer** (`airplay_health_timer: false` by default): a
`.service`+`.timer` running `airplay-doctor --check` and logging to the journal.

This whole hardening set is validated on a spare box before any production box
(hardening test matrix in the rollout plan).

## airplay-doctor.py

Single stdlib file, no dependencies. Modes:

- `--check` (default, **non-invasive**): services active (shairport-sync, nqptp,
  avahi-daemon), shairport build features from `-V`, nqptp ownership of UDP
  319/320 (`ss`), mDNS advertisement of `_airplay._tcp`/`_raop._tcp`, config
  parse, ALSA card **existence** via `aplay -L` (read-only, does not open the
  device), device-id non-zero + fleet-duplicate detection, built-vs-pinned
  version, recent xrun/sync errors from journalctl. Exit non-zero on failure.
- `--deep` (opt-in): adds device-open / short playback probe. Excluded from
  default because opening `hw:` can disrupt shairport's exclusive access while it
  is streaming.
- `--json`: machine-readable output for `doctor.yml` aggregation.

**Testable structure:** all parsing (`shairport-sync -V`, `ss`, `journalctl`,
`avahi-browse`, `aplay -L`) is pure functions fed sample fixtures; system calls
are isolated at the edges. `tests/test_airplay_doctor.py` (pytest) covers the
parsers. Replaces all ~750 lines of awk diagnostics.

## Migration (`migration.yml`)

Deleting files from git does **not** clean deployed boxes. A one-time playbook
(run before/with the first converge) must, idempotently:

- `systemctl disable --now` and remove the old units:
  `airplay-wyse-identity`, `airplay-wyse-alsa-policy`, `airplay-wyse-pw-policy`,
  `airplay-wyse-audio-kmods`, `airplay-wyse-health.service`/`.timer`, and the old
  shairport override drop-in.
- Remove `/usr/local/libexec/airplay_wyse/` (old runtime bundle + wrappers).
- Remove the old **managed** `/etc/asound.conf` (only if it is the one this
  project wrote — guard on a marker/known content; do not clobber an unrelated
  hand-written one).
- Remove `/var/lib/airplay_wyse/` state.
- `systemctl daemon-reload`.

## Testing & CI

CI must be able to fail (no `|| true`):

- `yamllint`
- `ansible-lint`
- `ansible-playbook --syntax-check site.yml migration.yml doctor.yml`
- `pytest tests/` (doctor parser unit tests)

Full from-source compile is too slow to gate every push; it is an optional
manual/nightly molecule job, not part of required CI.

## Rollout plan (because a box works today)

1. **Capture baseline** from the working box: `shairport-sync -V`, OS version,
   current config. Set the version pins to match.
2. **Provision a spare/test box (or VM)** with `site.yml`.
3. Run the **hardening test matrix** on the spare: confirm shairport starts under
   the override, AirPlay 2 pairing persists across restart (validates
   `StateDirectory`), DAC plays (validates `DeviceAllow`/`DevicePolicy`),
   `airplay-doctor --check` passes, and a real stream syncs.
4. Only then run `migration.yml` + `site.yml` against the **working box**.
5. Roll to remaining boxes.

## What gets deleted

`src/airplay_wyse/` (all Python), `bin/` wrappers + awk diagnostics
(`debug-audio`, `test-airplay2`, `alsa-probe`, `verify-airplay-identity`,
`check-airplay-device-id`), `systemd/` oneshots + override, `tools/lints.sh`, the
`|| true` CI, `cfg/` template, `profiles/`. Git history is preserved; this is a
content replacement on the `ansible-rewrite` branch.

## Open verification items (resolved during implementation)

- Working box `shairport-sync -V` + OS version → exact `shairport_sync_version`
  pin (default `4.3.7` until confirmed).
- Real shairport-sync state/cache path on the target build → exact
  `StateDirectory`/`ReadWritePaths` values.
- Whether the working box currently has a project-managed `/etc/asound.conf` →
  migration guard content.
