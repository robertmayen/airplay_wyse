# Security Model

This project runs a non‑root agent (`converge`) and escalates privilege for specific, narrowly defined actions. Key principles:

- No wildcard elevation: we do not allow `sudo systemd-run *` because flags/args can be abused to bypass intended constraints.
- Capabilities via wrapper: the only root entrypoint is `/usr/local/sbin/airplay-sd-run`, a small wrapper that launches hardened transient units with a fixed security profile.
- Profiles (capabilities):
  - `svc-restart` — restart services only; no filesystem writes.
  - `cfg-write` — allow writes under `/etc` only.
  - `unit-write` — allow writes under `/etc/systemd/system` only.
  - `pkg-ensure` — apt/dpkg writes only; reads repo package artifacts.
- All transient units include: `--wait --collect`, `Type=exec`, `NoNewPrivileges=`, strict namespaces, and minimal `ReadWritePaths`.

Sudoers policy
- The `airplay` user can run exactly:
  - `/usr/local/sbin/airplay-sd-run`
- No wildcards; no direct `systemd-run` elevation.

Auditability
- Each privileged action is its own transient unit, named `airplay-tx-<host>-<profile>-<RUN_ID>`, with a Description including `CAP` and `RUN_ID`.
- Logs are tagged with `SYSLOG_IDENTIFIER=airplay-agent` and a one‑line summary is emitted with `RESULT`, `CAP`, `RUN_ID`, `DURATION_MS`, and `RC`.

Why not wildcard `systemd-run`?
- Wildcards apply to arguments; a malicious or buggy call could pass additional `--property` flags or environment that weakens the sandbox. The fixed wrapper prevents this by baking in all properties and rejecting unknown profiles.

