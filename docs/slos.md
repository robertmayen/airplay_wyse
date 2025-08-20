# SLOs

- Visibility: endpoints appear via `_airplay._tcp` and `_raop._tcp` within 10s of service start.
- Timing: nqptp steady-state offset |offset| ≤ 10–20 ms.
- Idempotence: no restarts unless config/package/systemd diffs.
- Reliability: survive reboot/power/network flap without operator action.
- Health: 7-day green health with exit codes 0 or 2 predominating.
