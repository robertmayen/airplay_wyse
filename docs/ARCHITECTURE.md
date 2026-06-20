# Architecture

## Overview

AirPlay Wyse provisions Debian 13 boxes as AirPlay 2 endpoints using a single
Ansible role (`roles/airplay`). There is no on-device Python CLI, no periodic
root timers, and no boot-time oneshot services beyond what the role installs.
All privileged actions are idempotent Ansible tasks executed from the control
machine.

## Components

### shairport-sync

Built from source at a pinned version (`shairport_sync_version` in
`group_vars/airplay.yml`) with an explicit feature flag set
(`airplay_required_features`). The build is stamped and re-run only when the
stamp file does not exist or the version pin changes. After building, the role
verifies that the installed binary advertises every required feature before
proceeding.

### nqptp

Built from source at a pinned version alongside shairport-sync. nqptp owns
UDP 319/320 for AirPlay 2 precision timing and runs unprivileged via
`AmbientCapabilities=CAP_NET_BIND_SERVICE`.

### Role layout (`roles/airplay`)

```
roles/airplay/
├── defaults/main.yml   # all tunable variables (version pins, build flags,
│                       # ALSA card, device name, feature list)
├── tasks/
│   ├── main.yml        # orchestration: build → configure → systemd → doctor
│   ├── build.yml       # build dependencies, from-source compile, feature verification
│   ├── config.yml      # shairport-sync.conf from template, ALSA config
│   ├── systemd.yml     # hardened systemd units + drop-in override
│   └── doctor.yml      # install airplay-doctor tool
├── templates/
│   ├── shairport-sync.conf.j2
│   └── shairport-override.conf.j2
└── handlers/main.yml   # daemon-reload, restart shairport-sync + nqptp
```

### Playbooks

| Playbook | Purpose |
|---|---|
| `site.yml` | Full idempotent converge — runs the `airplay` role against all hosts |
| `migration.yml` | One-time cleanup of the legacy Python/shell stack: removes `/var/lib/airplay_wyse/`, `/usr/local/libexec/airplay_wyse/`, and legacy systemd units |
| `doctor.yml` | Non-invasive fleet health check: runs `airplay-doctor --check` on every host and checks for duplicate AirPlay device IDs across the fleet |

### airplay-doctor

A small Python tool installed to `/usr/local/bin/airplay-doctor` on each box
by the role. It performs non-invasive checks (service state, listening ports,
mDNS advertisement, ALSA card presence, journal errors, device-id uniqueness)
and reports via human-readable or `--json` output. `--deep` adds an optional
ALSA device-open probe. The tool is designed to exit 0 when healthy and non-zero
when any check fails, making it suitable for use in scripts and CI.

## systemd Units

The role writes a hardened drop-in override for the vendor `shairport-sync`
service (`shairport-override.conf.j2`). Hardening directives present:

- `NoNewPrivileges=yes`
- `ProtectSystem=strict`
- `ProtectHome=yes`
- `PrivateTmp=yes`
- `ProtectKernelTunables=yes`
- `ProtectKernelModules=yes`
- `ProtectControlGroups=yes`
- `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6`
- `SystemCallFilter=@system-service`
- `StateDirectory` / `CacheDirectory` (replaces any legacy `ReadWritePaths`)
- `DeviceAllow=char-alsa rw` + `DevicePolicy=closed` (explicit DAC access
  without `PrivateDevices` — which blocks ALSA)
- `Requires=nqptp.service` / `After=nqptp.service avahi-daemon.service`
- `Restart=on-failure`

Note: `MemoryDenyWriteExecute` is intentionally NOT set — it breaks
FFmpeg/codec libraries used by shairport-sync.

There are **no** boot-time oneshot services for identity, ALSA policy, or
PipeWire policy. Configuration is applied at provision time by Ansible and
does not change between runs unless the role is re-applied.

## Identity and Configuration

`airplay_name` and `airplay_alsa_card` are set per-host in `host_vars/`. The
role renders `/etc/shairport-sync.conf` from a Jinja2 template using those
values. If `airplay_device_id` is not set, shairport-sync generates its own
stable identifier; set it explicitly in `host_vars/` to prevent duplicates on
cloned images.

## Security Notes

- No on-device Git operations.
- No periodic timers that write to `/etc`.
- nqptp runs unprivileged with a capability ambient set.
- shairport-sync runs as its vendor user under the hardened drop-in.
- Avahi must be active to advertise `_airplay._tcp`.

## Dependencies

- `Requires=nqptp.service` and `After=nqptp.service` on shairport-sync ensures
  AirPlay 2 precision timing is ready before the AirPlay service starts.
- See [shairport-sync](https://github.com/mikebrady/shairport-sync#readme) and
  [nqptp](https://github.com/mikebrady/nqptp#readme) upstream docs.
