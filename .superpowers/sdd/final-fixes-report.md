# Final Fixes Report

Date: 2026-06-20

## FIX 1 — migration.yml: add legacy shairport override drop-in removal

Added a new task before "Reload systemd" in `/Users/robertmayen/airplay_wyse/migration.yml`:

```yaml
    - name: Remove legacy shairport-sync override drop-in
      ansible.builtin.file:
        path: /etc/systemd/system/shairport-sync.service.d/override.conf
        state: absent
```

Placed at line 51, before "Reload systemd" at line 56. The whole `.service.d/` directory is NOT removed — only the `override.conf` file inside it.

Context: this removes any legacy shairport-sync systemd drop-in override left over from previous installs, preventing conflicts when the Ansible role writes its own drop-in.

## FIX 2 — Remove phantom `shairport_sync_sha256` from docs

### README.md (was line 142)
Old: `1. Bump \`shairport_sync_version\` (and \`shairport_sync_sha256\`) in \`group_vars/airplay.yml\`.`
New: `1. Bump \`shairport_sync_version\` (and \`nqptp_version\`/\`alac_ref\` as needed) in \`inventory/group_vars/airplay.yml\`.`

### docs/OPERATIONS.md (was lines 67-68)
Old:
```
1. Update `shairport_sync_version` and `shairport_sync_sha256` in
   `group_vars/airplay.yml`.
```
New:
```
1. Bump `shairport_sync_version` (and `nqptp_version`/`alac_ref` as needed) in
   `inventory/group_vars/airplay.yml`.
```

### grep confirmation
`grep -rn "shairport_sync_sha256" . | grep -v .superpowers` returns **nothing**.

## FIX 3 — Correct group_vars path in docs

All bare `group_vars/airplay.yml` and `group_vars/` references in documentation updated to `inventory/group_vars/airplay.yml` / `inventory/group_vars/`. The actual file at `inventory/group_vars/airplay.yml` was NOT moved.

### Changes made:

**README.md**
- Line 62: `group_vars/airplay.yml` → `inventory/group_vars/airplay.yml`
- Line 63: `group_vars/airplay.yml` → `inventory/group_vars/airplay.yml`
- Line 142: combined with FIX 2 fix above (already corrected to `inventory/group_vars/airplay.yml`)
- Line 156: `group_vars/airplay.yml` → `inventory/group_vars/airplay.yml`
- Line 175 (repo layout): `├── group_vars/` → `├── inventory/group_vars/`

**docs/ARCHITECTURE.md**
- Line 16: `group_vars/airplay.yml)` → `inventory/group_vars/airplay.yml)`

**docs/OPERATIONS.md**
- Combined with FIX 2 fix (already corrected to `inventory/group_vars/airplay.yml`)

### grep confirmation
```
/Users/robertmayen/airplay_wyse/docs/OPERATIONS.md:68:   `inventory/group_vars/airplay.yml`.
/Users/robertmayen/airplay_wyse/README.md:62:`inventory/group_vars/airplay.yml`. ...
/Users/robertmayen/airplay_wyse/README.md:63:`inventory/group_vars/airplay.yml` ...
/Users/robertmayen/airplay_wyse/README.md:142:... in `inventory/group_vars/airplay.yml`.
/Users/robertmayen/airplay_wyse/README.md:156:... `inventory/group_vars/airplay.yml`.
/Users/robertmayen/airplay_wyse/README.md:175:├── inventory/group_vars/  # airplay.yml ...
/Users/robertmayen/airplay_wyse/docs/ARCHITECTURE.md:16:`inventory/group_vars/airplay.yml`) ...
```
All references show `inventory/group_vars` — no bare `group_vars/` paths remain.

## Gate Output Summary

Command: `cd /Users/robertmayen/airplay_wyse && .venv/bin/yamllint . && .venv/bin/ansible-lint && .venv/bin/ansible-playbook --syntax-check site.yml migration.yml doctor.yml && .venv/bin/pytest -v`

- **yamllint**: Passed with one pre-existing warning in `.github/workflows/ci.yml` (truthy value). No new violations.
- **ansible-lint**: Passed — 0 failures, 6 warnings (all pre-existing `var-naming[no-role-prefix]` warnings in `roles/airplay/defaults/main.yml`). Profile 'min' satisfied.
- **ansible-playbook --syntax-check**: Passed for all three playbooks (site.yml, migration.yml, doctor.yml).
- **pytest**: 23 passed, 0 failures in 0.02s.

Gate result: **ALL CHECKS PASS**

## Commit

Committed with message:
`fix: migration removes legacy override drop-in; docs drop phantom sha256 var and correct group_vars path`
