# Repository Audit and Reduction Plan

This audit classifies repository contents into CORE, AUX, and DEAD for the
minimal target: "Wyse 5070 + USB DAC → AirPlay 2 receiver" with GitOps.

Definitions
- CORE: strictly required for update/reconcile, converge, AP2 config (shairport-sync + nqptp + Avahi), minimal ALSA detection, systemd units, health.
- AUX: supporting docs and a single smoke test directly validating CORE.
- DEAD: on-device build paths, fix scripts, patches, multi-path privilege fallbacks, deploy helpers, CI helpers not required for minimal path.

Note: Timestamps and sizes are omitted from this static report; classification is based on current repo state and the constraints provided.

## CORE
- bin/reconcile: Timer entrypoint sequencing update → converge.
- bin/update: GitOps tag fetch/select/checkout (GPG verify optional).
- bin/converge: Idempotent converge: package ensure (APT or local .deb), ALSA detect, template render, systemd reload/restart, health.
- bin/health: Health JSON reporter.
- bin/diag: Basic diagnostics collector (retained minimally for AUX/ops).
- bin/airplay-sd-run: Single privilege wrapper (to be installed at /usr/local/sbin/airplay-sd-run).
- cfg/shairport-sync.conf.tmpl: Shairport configuration template.
- cfg/avahi/avahi-daemon.conf.d/airplay-wyse.conf.tmpl: Avahi configuration template (kept minimal).
- cfg/nqptp.conf.tmpl: NQPTP configuration template (kept if needed).
- systemd/reconcile.service: Update + converge service, runs as airplay.
- systemd/reconcile.timer: Periodic trigger for reconcile.service.
- systemd/converge.service: Converge service (single path).
- systemd/overrides/shairport-sync.service.d/override.conf: Ordering/sandboxing.
- systemd/overrides/converge.service.d/override.conf: Exit code handling.
- inventory/hosts/example.yml: Example host inventory.

## AUX
- docs/OPERATIONS.md: Single canonical operations one-pager (install, tag, health, rollback via git tags).
- tests/smoke.sh: Single smoke test (mockable) validating AP2 build string, nqptp active, AirPlay advertisement, and ALSA openability.
- README.md: Trimmed to reference OPERATIONS.md and the minimal workflow.

## DEAD (to remove)
- fix_*.sh: Ad-hoc fix scripts. Rationale: not part of minimal converge path.
- patches/: Patch sets and docs. Rationale: no patching flow in minimal plan.
- pkg/build-*.sh, pkg/versions.sh, pkg/README.md: On-device build tooling. Rationale: violates immutable-ish host rule (no compilers/builds).
- pkg/apt-pins.d/*: APT pinning not required for Debian 13 minimal path; keep APT-only converge.
- scripts/ops/*: Provisioning helpers. Rationale: controller-side ops; out of scope for minimal repo.
- scripts/ci/*: CI helpers not required for minimal smoke-only validation.
- systemd/update.service, systemd/update.timer, systemd/preflight.service, systemd/airplay-avahi.service: Alternate orchestration paths; retain only reconcile/converge.
- bin/bootstrap, lib/bootstrap.sh: Multi-path bootstrap; replaced with a single wrapper requirement.
- bin/rollback: Not mandatory; rollback can occur by tagging to a prior version.
- bin/preflight, bin/diag-converge, bin/diag-sudo: Ancillary; not required for minimal converge.
- tests/* except tests/smoke.sh: Reduce to a single smoke test as per constraints.
- docs/* except OPERATIONS.md and AUDIT.md: Consolidate to a single canonical operations doc and this audit.
- security/*: Sudoers sample will be embedded in OPERATIONS.md; single privilege path retained.
- deploy_*.sh, test_* infrastructure scripts: Out of scope for minimal target.

## Deletion Plan (Summary)
- Remove all DEAD files/dirs above to meet minimal structure.
- Keep only the directories: bin/, cfg/, systemd/, tests/, docs/, inventory/.
- Ensure all privileged actions go through a single wrapper (/usr/local/sbin/airplay-sd-run).

