# AirPlay Wyse Ansible Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the on-device Python CLI / JSON-state / shell-wrapper / boot-time-systemd stack with an Ansible project that provisions 2–5 hand-built Debian 13 boxes into AirPlay 2 endpoints from a laptop, plus one stdlib-Python on-box diagnostic tool.

**Architecture:** An Ansible role (`airplay`) builds ALAC + nqptp + shairport-sync from source (the proven nicokaiser recipe), renders a minimal config, installs hardened systemd units, and deploys `airplay-doctor`. Idempotent re-runs are the drift/update mechanism. A `migration.yml` cleans old deployed artifacts; `doctor.yml` aggregates fleet health. Diagnostics and templates are unit-tested offline; the from-source build is validated on physical hardware per a rollout matrix.

**Tech Stack:** Ansible (ansible-core), Jinja2 templates, Python 3 stdlib (`airplay-doctor`), pytest + jinja2 (offline tests), yamllint + ansible-lint, GitHub Actions CI.

## Global Constraints

- Target OS: **Debian 13 (trixie)** on the boxes. Control node: operator laptop (macOS/Linux) with `ansible-core`.
- **Two build profiles, never one configure line.** `shairport_major: "4"` (default) flags: `--sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl --with-systemd --with-airplay-2 --with-apple-alac`. `shairport_major: "5"` flags: `--sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl --with-systemd-startup --with-airplay-2` (no `--with-apple-alac`).
- **Default pins (explicit):** `shairport_sync_version: "4.3.7"`, `nqptp_version: "1.2.8"`, `alac_ref: "master"`. Confirm against the working box's `shairport-sync -V` during rollout and adjust `shairport_sync_version` to match if different.
- **Feature verification runs every play**, independent of the build stamp: `shairport-sync -V` must report AirPlay 2 + soxr (+ ALAC for major 4); `nqptp -V` returns a version. Feature matching is **token-tolerant** (whitespace/case-insensitive: `AirPlay2`≈`AirPlay 2`).
- **`airplay-doctor --check` is non-invasive** (never opens the ALSA device); device-open/playback is `--deep` only.
- **systemd hardening must keep AirPlay 2 working:** `ProtectSystem=strict` paired with `StateDirectory=`/`CacheDirectory=` (pairing-key persistence), `DeviceAllow=char-alsa rw` + `DevicePolicy=closed` (not `PrivateDevices`), realtime scheduling left intact.
- **Identity:** only required per-host input is `airplay_name`; `airplay_device_id` is an optional per-host override. No synthetic MACs / clone-healing / boot-time regeneration.
- **CI must be able to fail** — no `|| true` anywhere.
- DRY, YAGNI, TDD, frequent commits. Stdlib-only on the box (`airplay-doctor` imports nothing outside the stdlib).
- Work happens on branch `ansible-rewrite`. The legacy tree stays in place until Task 11 so implementers can reference old logic; it is deleted in one cutover task.

---

## File Structure

**Create:**
- `requirements-dev.txt`, `.yamllint`, `.ansible-lint`, `ansible.cfg`, `pytest.ini`, `Makefile` (replace)
- `.github/workflows/ci.yml` (replace)
- `site.yml`, `migration.yml`, `doctor.yml`
- `inventory/hosts.yml`, `inventory/group_vars/airplay.yml`, `inventory/host_vars/example-box.yml`
- `roles/airplay/defaults/main.yml`
- `roles/airplay/tasks/{main,build,config,systemd,doctor}.yml`
- `roles/airplay/templates/{shairport-sync.conf.j2,shairport-override.conf.j2,airplay-health.service.j2,airplay-health.timer.j2}`
- `roles/airplay/files/airplay_doctor.py`
- `roles/airplay/handlers/main.yml`
- `tests/test_airplay_doctor.py`, `tests/test_templates.py`

**Delete (Task 11):** `src/airplay_wyse/`, `bin/`, `systemd/`, `cfg/`, `profiles/`, `tools/lints.sh`, old `.github/workflows/ci.yml` content (replaced earlier), `Makefile` legacy targets.

---

## Task 1: Repo scaffolding, dev tooling, and failing-capable CI

**Files:**
- Create: `requirements-dev.txt`, `.yamllint`, `.ansible-lint`, `ansible.cfg`, `pytest.ini`, `.github/workflows/ci.yml`, `site.yml` (stub), `inventory/hosts.yml` (stub), `tests/test_smoke.py`

**Interfaces:**
- Produces: a green lint/test baseline that every later task extends. CI runs `yamllint .`, `ansible-lint`, `ansible-playbook --syntax-check site.yml`, `pytest`.

- [ ] **Step 1: Write dev requirements and tool configs**

`requirements-dev.txt`:
```
ansible-core>=2.16
ansible-lint>=24.0
yamllint>=1.35
pytest>=8.0
jinja2>=3.1
```

`.yamllint`:
```yaml
---
extends: default
rules:
  line-length:
    max: 200
  truthy:
    allowed-values: ["true", "false"]
  comments:
    min-spaces-from-content: 1
  document-start: disable
```

`.ansible-lint`:
```yaml
---
profile: production
exclude_paths:
  - docs/
  - tests/
  - src/
  - bin/
  - systemd/
  - cfg/
  - profiles/
  - tools/
```

`ansible.cfg`:
```ini
[defaults]
inventory = inventory/hosts.yml
roles_path = roles
host_key_checking = False
stdout_callback = yaml
interpreter_python = auto_silent

[privilege_escalation]
become = True
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 2: Write stub playbook + inventory so syntax-check has a target**

`site.yml`:
```yaml
---
- name: Provision AirPlay 2 endpoints
  hosts: airplay
  become: true
  roles: []
```

`inventory/hosts.yml`:
```yaml
---
all:
  children:
    airplay:
      hosts:
        example-box:
          ansible_host: 192.0.2.10
```

- [ ] **Step 3: Write the smoke test**

`tests/test_smoke.py`:
```python
def test_smoke():
    assert True
```

- [ ] **Step 4: Write CI workflow (no `|| true`)**

`.github/workflows/ci.yml`:
```yaml
---
name: CI
on:
  push:
  pull_request:

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dev deps
        run: pip install -r requirements-dev.txt
      - name: yamllint
        run: yamllint .
      - name: ansible-lint
        run: ansible-lint
      - name: syntax-check
        run: ansible-playbook --syntax-check site.yml
      - name: pytest
        run: pytest -v
```

- [ ] **Step 5: Install tools locally and run the gate**

Run:
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
yamllint . && ansible-lint && ansible-playbook --syntax-check site.yml && pytest -v
```
Expected: all four pass (ansible-lint may warn on the stub but must exit 0; if it fails on the empty `roles: []`, set `roles: []` to an empty `tasks: []` play instead).

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt .yamllint .ansible-lint ansible.cfg pytest.ini .github/workflows/ci.yml site.yml inventory/hosts.yml tests/test_smoke.py
git commit -m "chore: scaffold ansible repo, dev tooling, failing-capable CI"
```

---

## Task 2: airplay-doctor — shairport `-V` feature parser (TDD)

**Files:**
- Create: `roles/airplay/files/airplay_doctor.py`
- Test: `tests/test_airplay_doctor.py`

**Interfaces:**
- Produces: `parse_shairport_version(text: str) -> dict` returning `{"version": str, "airplay2": bool, "soxr": bool, "alac": bool}`. Token-tolerant.

- [ ] **Step 1: Write failing tests**

`tests/test_airplay_doctor.py`:
```python
import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay/files/airplay_doctor.py"
_spec = importlib.util.spec_from_file_location("airplay_doctor", SRC)
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)


def test_parse_version_classic_tokens():
    out = "4.3.7-OpenSSL-Avahi-ALSA-soxr-sysconfdir:/etc-AirPlay2"
    r = ad.parse_shairport_version(out)
    assert r["version"] == "4.3.7"
    assert r["airplay2"] is True
    assert r["soxr"] is True
    assert r["alac"] is False


def test_parse_version_spaced_and_alac():
    out = "5.0.4 OpenSSL Avahi ALSA soxr ALAC AirPlay 2"
    r = ad.parse_shairport_version(out)
    assert r["version"] == "5.0.4"
    assert r["airplay2"] is True
    assert r["alac"] is True


def test_parse_version_dev_tag():
    r = ad.parse_shairport_version("5.1~dev-OpenSSL-AirPlay2")
    assert r["version"] == "5.1~dev"
    assert r["airplay2"] is True
```

- [ ] **Step 2: Run, verify fail**

Run: `pytest tests/test_airplay_doctor.py -v`
Expected: FAIL — `airplay_doctor.py` does not exist / no `parse_shairport_version`.

- [ ] **Step 3: Implement the parser**

`roles/airplay/files/airplay_doctor.py`:
```python
#!/usr/bin/env python3
"""airplay-doctor — diagnostics/health for an AirPlay 2 endpoint (stdlib only)."""
from __future__ import annotations

import re


def parse_shairport_version(text: str) -> dict:
    """Parse `shairport-sync -V` into a version string + feature flags.

    Token-tolerant: collapses whitespace and lowercases before matching, so
    'AirPlay2' and 'AirPlay 2' both register, regardless of feature casing.
    """
    compact = re.sub(r"\s+", "", text).lower()
    m = re.match(r"\s*([0-9][0-9A-Za-z.~+]*)", text)
    return {
        "version": m.group(1) if m else "",
        "airplay2": "airplay2" in compact,
        "soxr": "soxr" in compact,
        "alac": "alac" in compact,
    }
```

- [ ] **Step 4: Run, verify pass**

Run: `pytest tests/test_airplay_doctor.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add roles/airplay/files/airplay_doctor.py tests/test_airplay_doctor.py
git commit -m "feat(doctor): token-tolerant shairport -V parser"
```

---

## Task 3: airplay-doctor — ports, mDNS, ALSA, journal, device-id parsers (TDD)

**Files:**
- Modify: `roles/airplay/files/airplay_doctor.py`
- Test: `tests/test_airplay_doctor.py`

**Interfaces:**
- Produces:
  - `parse_listening_ports(ss_output: str, ports=(319, 320)) -> dict[int, dict]` → `{port: {"bound": bool, "nqptp": bool}}`
  - `parse_mdns(avahi_output: str) -> dict` → `{"airplay": bool, "raop": bool}`
  - `parse_alsa_cards(aplay_l_output: str) -> set[str]`
  - `parse_journal_errors(journal_text: str) -> dict` → `{"xruns": int, "sync": int}`
  - `parse_device_id(conf_text: str) -> str`
  - `is_zero_device_id(dev_id: str) -> bool`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_airplay_doctor.py`:
```python
def test_ports_owned_by_nqptp():
    ss = (
        'UNCONN 0 0 0.0.0.0:319 0.0.0.0:* users:(("nqptp",pid=42,fd=4))\n'
        'UNCONN 0 0 0.0.0.0:320 0.0.0.0:* users:(("nqptp",pid=42,fd=5))\n'
        'UNCONN 0 0 0.0.0.0:5353 0.0.0.0:* users:(("avahi-daemon",pid=7,fd=12))\n'
    )
    r = ad.parse_listening_ports(ss)
    assert r[319]["bound"] and r[319]["nqptp"]
    assert r[320]["bound"] and r[320]["nqptp"]


def test_ports_not_confused_by_substring():
    ss = 'UNCONN 0 0 0.0.0.0:31900 0.0.0.0:* users:(("other",pid=1,fd=1))\n'
    r = ad.parse_listening_ports(ss)
    assert r[319]["bound"] is False


def test_mdns_detects_services():
    out = "+ eth0 IPv4 Living Room _airplay._tcp local\n+ eth0 IPv4 Living Room _raop._tcp local\n"
    r = ad.parse_mdns(out)
    assert r["airplay"] and r["raop"]


def test_alsa_cards_from_aplay_L():
    out = (
        "default\n"
        "hw:CARD=Device,DEV=0\n"
        "    USB Audio Device, USB Audio\n"
        "plughw:CARD=Device,DEV=0\n"
        "hw:CARD=PCH,DEV=0\n"
    )
    assert ad.parse_alsa_cards(out) == {"Device", "PCH"}


def test_journal_error_counts():
    j = "underrun detected\nsomething fine\nlost sync with source\noverrun!\n"
    r = ad.parse_journal_errors(j)
    assert r["xruns"] == 2
    assert r["sync"] == 1


def test_device_id_parse_and_zero():
    assert ad.parse_device_id('  airplay_device_id = "5C:AA:FD:11:22:33";') == "5C:AA:FD:11:22:33"
    assert ad.is_zero_device_id("00:00:00:00:00:00") is True
    assert ad.is_zero_device_id("5C:AA:FD:11:22:33") is False
    assert ad.is_zero_device_id("") is True
```

- [ ] **Step 2: Run, verify fail**

Run: `pytest tests/test_airplay_doctor.py -v`
Expected: the 6 new tests FAIL (functions not defined).

- [ ] **Step 3: Implement parsers**

Append to `roles/airplay/files/airplay_doctor.py`:
```python
def parse_listening_ports(ss_output: str, ports=(319, 320)) -> dict:
    """From `ss -ulnp`, report which target UDP ports are bound and by nqptp."""
    result = {p: {"bound": False, "nqptp": False} for p in ports}
    for line in ss_output.splitlines():
        for p in ports:
            if re.search(rf"[:.]{p}\b", line):
                result[p]["bound"] = True
                if "nqptp" in line:
                    result[p]["nqptp"] = True
    return result


def parse_mdns(avahi_output: str) -> dict:
    return {
        "airplay": "_airplay._tcp" in avahi_output,
        "raop": "_raop._tcp" in avahi_output,
    }


def parse_alsa_cards(aplay_l_output: str) -> set:
    cards = set()
    for line in aplay_l_output.splitlines():
        m = re.match(r"\s*hw:CARD=([^,\s]+)", line)
        if m:
            cards.add(m.group(1))
    return cards


def parse_journal_errors(journal_text: str) -> dict:
    counts = {"xruns": 0, "sync": 0}
    for line in journal_text.splitlines():
        low = line.lower()
        if "underrun" in low or "overrun" in low or "xrun" in low:
            counts["xruns"] += 1
        if "lost sync" in low or "resync" in low or "out of sync" in low or "sync error" in low:
            counts["sync"] += 1
    return counts


def parse_device_id(conf_text: str) -> str:
    m = re.search(r'airplay_device_id\s*=\s*"?([0-9A-Fa-fx:]+)"?', conf_text)
    return m.group(1) if m else ""


def is_zero_device_id(dev_id: str) -> bool:
    digits = re.sub(r"[^0-9A-Fa-f]", "", dev_id)
    return digits == "" or set(digits) <= {"0"}
```

- [ ] **Step 4: Run, verify pass**

Run: `pytest tests/test_airplay_doctor.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add roles/airplay/files/airplay_doctor.py tests/test_airplay_doctor.py
git commit -m "feat(doctor): ports/mDNS/ALSA/journal/device-id parsers"
```

---

## Task 4: airplay-doctor — check orchestration, CLI, JSON, exit codes (TDD)

**Files:**
- Modify: `roles/airplay/files/airplay_doctor.py`
- Test: `tests/test_airplay_doctor.py`

**Interfaces:**
- Consumes: all parsers from Tasks 2–3.
- Produces:
  - `build_report(runner, deep: bool = False) -> dict` — `runner` is a callable `runner(name: str) -> str` mapping a probe name (`"shairport_version"`, `"ss"`, `"mdns"`, `"aplay"`, `"journal"`, `"config"`, plus `is_active:<svc>`) to captured text; lets tests inject fixtures. Returns `{"host": str, "ok": bool, "device_id": str, "checks": [{"name","ok","detail"}], "mdns": {...}}`.
  - `main(argv=None) -> int` — flags `--check` (default), `--deep`, `--json`. Exit 0 when `ok`, 1 otherwise.

- [ ] **Step 1: Add failing tests**

Append to `tests/test_airplay_doctor.py`:
```python
def _fixture_runner(overrides=None):
    base = {
        "is_active:shairport-sync": "active",
        "is_active:nqptp": "active",
        "is_active:avahi-daemon": "active",
        "shairport_version": "4.3.7-OpenSSL-ALSA-soxr-AirPlay2",
        "ss": 'UNCONN 0 0 0.0.0.0:319 0.0.0.0:* users:(("nqptp",pid=1,fd=4))\n'
              'UNCONN 0 0 0.0.0.0:320 0.0.0.0:* users:(("nqptp",pid=1,fd=5))\n',
        "mdns": "+ eth0 IPv4 X _airplay._tcp local\n+ eth0 IPv4 X _raop._tcp local\n",
        "aplay": "hw:CARD=Device,DEV=0\n",
        "journal": "all good\n",
        "config": 'airplay_device_id = "5C:AA:FD:11:22:33";\n'
                  'output_device = "hw:CARD=Device,DEV=0";\n',
    }
    if overrides:
        base.update(overrides)
    return lambda name: base.get(name, "")


def test_report_all_green():
    r = ad.build_report(_fixture_runner())
    assert r["ok"] is True
    assert r["device_id"] == "5C:AA:FD:11:22:33"
    assert r["mdns"]["airplay"] is True


def test_report_fails_when_nqptp_down():
    r = ad.build_report(_fixture_runner({"is_active:nqptp": "inactive"}))
    assert r["ok"] is False
    assert any(c["name"] == "service:nqptp" and not c["ok"] for c in r["checks"])


def test_report_fails_on_missing_airplay2_feature():
    r = ad.build_report(_fixture_runner({"shairport_version": "4.3.7-OpenSSL-ALSA"}))
    assert r["ok"] is False
    assert any(c["name"] == "feature:airplay2" and not c["ok"] for c in r["checks"])


def test_report_fails_on_zero_device_id():
    r = ad.build_report(_fixture_runner({"config": 'airplay_device_id = "00:00:00:00:00:00";'}))
    assert r["ok"] is False


def test_main_json_exit_code(capsys):
    rc = ad.main(["--json"], runner=_fixture_runner())
    out = capsys.readouterr().out
    import json
    assert json.loads(out)["ok"] is True
    assert rc == 0
```

- [ ] **Step 2: Run, verify fail**

Run: `pytest tests/test_airplay_doctor.py -v`
Expected: the 5 new tests FAIL.

- [ ] **Step 3: Implement orchestration + CLI**

Append to `roles/airplay/files/airplay_doctor.py`:
```python
import argparse
import json
import socket
import subprocess
import sys


def _system_runner(name: str) -> str:
    """Default runner: maps a probe name to real captured command output."""
    if name.startswith("is_active:"):
        svc = name.split(":", 1)[1]
        return _capture(["systemctl", "is-active", svc])
    cmds = {
        "shairport_version": ["shairport-sync", "-V"],
        "ss": ["ss", "-ulnp"],
        "mdns": ["avahi-browse", "-atp", "--no-db-lookup", "-r", "-l"],
        "aplay": ["aplay", "-L"],
        "journal": ["journalctl", "-u", "shairport-sync", "-n", "200", "--no-pager"],
    }
    if name == "config":
        try:
            with open("/etc/shairport-sync.conf", encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return ""
    return _capture(cmds.get(name, ["true"]))


def _capture(cmd) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout
    except FileNotFoundError:
        return ""


def _check(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": detail}


def build_report(runner, deep: bool = False) -> dict:
    checks = []
    for svc in ("shairport-sync", "nqptp", "avahi-daemon"):
        active = runner(f"is_active:{svc}").strip() == "active"
        checks.append(_check(f"service:{svc}", active, "active" if active else "not active"))

    feats = parse_shairport_version(runner("shairport_version"))
    checks.append(_check("feature:airplay2", feats["airplay2"], feats["version"]))
    checks.append(_check("feature:soxr", feats["soxr"]))

    ports = parse_listening_ports(runner("ss"))
    nqptp_ports = all(ports[p]["bound"] and ports[p]["nqptp"] for p in (319, 320))
    checks.append(_check("ports:319/320", nqptp_ports, "owned by nqptp" if nqptp_ports else "not owned"))

    mdns = parse_mdns(runner("mdns"))
    checks.append(_check("mdns:airplay", mdns["airplay"]))
    checks.append(_check("mdns:raop", mdns["raop"]))

    conf = runner("config")
    dev_id = parse_device_id(conf)
    checks.append(_check("identity:device-id", not is_zero_device_id(dev_id), dev_id))

    cards = parse_alsa_cards(runner("aplay"))
    m = re.search(r'output_device\s*=\s*"hw:CARD=([^,"]+)', conf)
    want_card = m.group(1) if m else None
    card_ok = (want_card in cards) if want_card else bool(cards)
    checks.append(_check("alsa:card", card_ok, want_card or "any"))

    errs = parse_journal_errors(runner("journal"))
    checks.append(_check("journal:errors", errs["xruns"] == 0 and errs["sync"] == 0, str(errs)))

    if deep:
        # opt-in only; opening hw: can disrupt shairport's exclusive access
        checks.append(_check("deep:device-open", True, "deep probe placeholder"))

    return {
        "host": socket.gethostname(),
        "ok": all(c["ok"] for c in checks),
        "device_id": dev_id,
        "mdns": mdns,
        "checks": checks,
    }


def main(argv=None, runner=None) -> int:
    parser = argparse.ArgumentParser(prog="airplay-doctor")
    parser.add_argument("--check", action="store_true", help="non-invasive checks (default)")
    parser.add_argument("--deep", action="store_true", help="add device-open/playback probe")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)
    run = runner or _system_runner
    report = build_report(run, deep=args.deep)
    if args.json:
        print(json.dumps(report))
    else:
        status = "OK" if report["ok"] else "FAIL"
        print(f"airplay-doctor: {report['host']} {status}")
        for c in report["checks"]:
            mark = "ok " if c["ok"] else "XX "
            print(f"  [{mark}] {c['name']}: {c['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

Note: `main` accepts a `runner` kwarg so tests inject fixtures; the CLI path uses `_system_runner`.

- [ ] **Step 4: Run, verify pass**

Run: `pytest -v`
Expected: all doctor tests pass.

- [ ] **Step 5: Commit**

```bash
git add roles/airplay/files/airplay_doctor.py tests/test_airplay_doctor.py
git commit -m "feat(doctor): check orchestration, CLI, JSON report, exit codes"
```

---

## Task 5: Role defaults, group_vars, host_vars, inventory

**Files:**
- Create: `roles/airplay/defaults/main.yml`, `inventory/group_vars/airplay.yml`, `inventory/host_vars/example-box.yml`
- Modify: `inventory/hosts.yml`

**Interfaces:**
- Produces: `shairport_major`, `shairport_sync_version`, `nqptp_version`, `alac_ref`, `shairport_configure_flags`, `airplay_required_features`, `airplay_health_timer`, `airplay_state_dir`, `airplay_build_root`. Per-host: `airplay_name`, `airplay_alsa_card`, `airplay_alsa_device`, optional `airplay_device_id`, optional `airplay_output_rate`.

- [ ] **Step 1: Write defaults**

`roles/airplay/defaults/main.yml`:
```yaml
---
shairport_major: "4"
shairport_sync_version: "4.3.7"
nqptp_version: "1.2.8"
alac_ref: "master"

_shairport_flags:
  "4": >-
    --sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl
    --with-systemd --with-airplay-2 --with-apple-alac
  "5": >-
    --sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl
    --with-systemd-startup --with-airplay-2
shairport_configure_flags: "{{ _shairport_flags[shairport_major] }}"

# Required runtime features (token-tolerant match against `shairport-sync -V`).
# ALAC is required only for the major-4 (apple-alac) profile.
airplay_required_features: "{{ ['AirPlay 2', 'soxr', 'ALAC'] if shairport_major == '4' else ['AirPlay 2', 'soxr'] }}"

airplay_build_root: /usr/local/src/airplay
airplay_state_dir: shairport-sync
airplay_health_timer: false

airplay_build_deps:
  - build-essential
  - git
  - autoconf
  - automake
  - libtool
  - libpopt-dev
  - libconfig-dev
  - libasound2-dev
  - avahi-daemon
  - libavahi-client-dev
  - libssl-dev
  - libsoxr-dev
  - libplist-dev
  - libsodium-dev
  - libavutil-dev
  - libavcodec-dev
  - libavformat-dev
  - uuid-dev
  - libgcrypt20-dev
  - xxd
  - systemd-dev
```

- [ ] **Step 2: Write group_vars and a host_vars example**

`inventory/group_vars/airplay.yml`:
```yaml
---
# Fleet-wide overrides go here (e.g. pin a tested version across all boxes).
# shairport_sync_version: "4.3.7"
```

`inventory/host_vars/example-box.yml`:
```yaml
---
airplay_name: "Living Room"
# ALSA card name from `aplay -L` (the CARD= token of your USB DAC):
airplay_alsa_card: "Device"
airplay_alsa_device: 0
# Optional: pin a stable device-id independent of hardware MAC:
# airplay_device_id: "5C:AA:FD:11:22:33"
# Optional: force output rate when the DAC cannot do native 44.1 kHz:
# airplay_output_rate: 48000
```

- [ ] **Step 3: Point inventory host at the example host_vars**

`inventory/hosts.yml` already references `example-box`; no change needed beyond confirming the name matches `host_vars/example-box.yml`.

- [ ] **Step 4: Verify lint + syntax**

Run: `yamllint . && ansible-lint && ansible-playbook --syntax-check site.yml`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add roles/airplay/defaults/main.yml inventory/
git commit -m "feat(role): defaults, build profiles, group/host vars, inventory example"
```

---

## Task 6: Config templates + render tests (TDD)

**Files:**
- Create: `roles/airplay/templates/shairport-sync.conf.j2`, `roles/airplay/templates/shairport-override.conf.j2`
- Test: `tests/test_templates.py`

**Interfaces:**
- Produces: rendered `/etc/shairport-sync.conf` and the systemd override drop-in. Templates are pure Jinja2 (no Ansible filters except `default`) so pytest renders them offline.

- [ ] **Step 1: Write failing render tests**

`tests/test_templates.py`:
```python
import pathlib
from jinja2 import Environment, FileSystemLoader

TPL = pathlib.Path(__file__).resolve().parents[1] / "roles/airplay/templates"
env = Environment(loader=FileSystemLoader(str(TPL)), keep_trailing_newline=True)


def render(name, **ctx):
    return env.get_template(name).render(**ctx)


def test_config_renders_card_and_dev():
    out = render("shairport-sync.conf.j2", airplay_name="Living Room",
                 airplay_alsa_card="Device", airplay_alsa_device=0)
    assert 'name = "Living Room"' in out
    assert 'output_device = "hw:CARD=Device,DEV=0"' in out
    assert 'interpolation = "soxr"' in out
    assert 'disable_standby_mode = "always"' in out


def test_config_omits_device_id_by_default():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="Device", airplay_alsa_device=0)
    assert "airplay_device_id" not in out


def test_config_includes_device_id_when_set():
    out = render("shairport-sync.conf.j2", airplay_name="X",
                 airplay_alsa_card="Device", airplay_alsa_device=0,
                 airplay_device_id="5C:AA:FD:11:22:33")
    assert "airplay_device_id = 5C:AA:FD:11:22:33;" in out


def test_override_has_state_and_device_directives():
    out = render("shairport-override.conf.j2", airplay_state_dir="shairport-sync")
    assert "ProtectSystem=strict" in out
    assert "StateDirectory=shairport-sync" in out
    assert "CacheDirectory=shairport-sync" in out
    assert "DeviceAllow=char-alsa rw" in out
    assert "DevicePolicy=closed" in out
    assert "PrivateDevices" not in out
    assert "Requires=nqptp.service" in out
```

- [ ] **Step 2: Run, verify fail**

Run: `pytest tests/test_templates.py -v`
Expected: FAIL (templates missing).

- [ ] **Step 3: Write the templates**

`roles/airplay/templates/shairport-sync.conf.j2`:
```jinja
// Managed by airplay_wyse Ansible. Do not edit by hand — changes are overwritten.
general = {
  name = "{{ airplay_name }}";
  mdns_backend = "avahi";
{% if airplay_device_id is defined %}
  airplay_device_id = {{ airplay_device_id }};
{% endif %}
};

sessioncontrol = {
  session_timeout = 20;
};

alsa = {
  output_device = "hw:CARD={{ airplay_alsa_card }},DEV={{ airplay_alsa_device | default(0) }}";
  interpolation = "soxr";
  disable_standby_mode = "always";
{% if airplay_output_rate is defined %}
  output_rate = {{ airplay_output_rate }};
{% endif %}
};
```

`roles/airplay/templates/shairport-override.conf.j2`:
```jinja
[Service]
# Managed by airplay_wyse Ansible.
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
SystemCallFilter=@system-service
StateDirectory={{ airplay_state_dir }}
CacheDirectory={{ airplay_state_dir }}
DeviceAllow=char-alsa rw
DevicePolicy=closed
Requires=nqptp.service
After=nqptp.service avahi-daemon.service
Restart=on-failure
```

- [ ] **Step 4: Run, verify pass**

Run: `pytest tests/test_templates.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add roles/airplay/templates/shairport-sync.conf.j2 roles/airplay/templates/shairport-override.conf.j2 tests/test_templates.py
git commit -m "feat(role): config + hardening-override templates with render tests"
```

---

## Task 7: Build tasks (from source, profile-gated, stamped, feature-verified)

**Files:**
- Create: `roles/airplay/tasks/build.yml`, `roles/airplay/handlers/main.yml`

**Interfaces:**
- Consumes: `airplay_build_deps`, `shairport_configure_flags`, version vars, `airplay_required_features`, `airplay_build_root`.
- Produces: installed `shairport-sync`, `nqptp`, ALAC; stamp `/usr/local/share/airplay/.versions`; notifies handler `restart shairport-sync`.

> Verification note: a from-source compile cannot run on the control node. This task's gate is `yamllint` + `ansible-lint` + `--syntax-check`; the real build is validated on physical hardware in Task 12's rollout matrix.

- [ ] **Step 1: Write the build tasks**

`roles/airplay/tasks/build.yml`:
```yaml
---
- name: Install build dependencies
  ansible.builtin.apt:
    name: "{{ airplay_build_deps }}"
    state: present
    update_cache: true
    cache_valid_time: 3600

- name: Ensure build root exists
  ansible.builtin.file:
    path: "{{ airplay_build_root }}"
    state: directory
    mode: "0755"

- name: Read existing build stamp
  ansible.builtin.slurp:
    src: /usr/local/share/airplay/.versions
  register: airplay_stamp_raw
  failed_when: false

- name: Compute desired build signature
  ansible.builtin.set_fact:
    airplay_build_signature: >-
      shairport={{ shairport_sync_version }}|nqptp={{ nqptp_version }}|
      alac={{ alac_ref }}|flags={{ shairport_configure_flags }}
    airplay_stamp_current: "{{ (airplay_stamp_raw.content | b64decode | from_json) if airplay_stamp_raw.content is defined else {} }}"

- name: Decide whether a rebuild is needed
  ansible.builtin.set_fact:
    airplay_needs_build: "{{ airplay_stamp_current.get('signature', '') != airplay_build_signature }}"

- name: Build and install ALAC (major 4 only)
  when: shairport_major == "4" and airplay_needs_build
  block:
    - name: Clone ALAC
      ansible.builtin.git:
        repo: https://github.com/mikebrady/alac
        dest: "{{ airplay_build_root }}/alac"
        version: "{{ alac_ref }}"
    - name: Build ALAC
      ansible.builtin.shell: |
        set -e
        autoreconf -fi
        ./configure
        make
        make install
        ldconfig
      args:
        chdir: "{{ airplay_build_root }}/alac"
        creates: /usr/local/lib/libalac.so

- name: Build and install nqptp
  when: airplay_needs_build
  block:
    - name: Clone nqptp
      ansible.builtin.git:
        repo: https://github.com/mikebrady/nqptp
        dest: "{{ airplay_build_root }}/nqptp"
        version: "{{ nqptp_version }}"
        force: true
    - name: Build nqptp
      ansible.builtin.shell: |
        set -e
        autoreconf -fi
        ./configure --with-systemd-startup
        make
        make install
      args:
        chdir: "{{ airplay_build_root }}/nqptp"

- name: Build and install shairport-sync
  when: airplay_needs_build
  block:
    - name: Clone shairport-sync
      ansible.builtin.git:
        repo: https://github.com/mikebrady/shairport-sync
        dest: "{{ airplay_build_root }}/shairport-sync"
        version: "{{ shairport_sync_version }}"
        force: true
    - name: Build shairport-sync
      ansible.builtin.shell: |
        set -e
        autoreconf -fi
        ./configure {{ shairport_configure_flags }}
        make
        make install
      args:
        chdir: "{{ airplay_build_root }}/shairport-sync"
      notify: restart shairport-sync

# --- Feature verification runs EVERY play, regardless of the stamp ---
- name: Capture shairport-sync version string
  ansible.builtin.command: shairport-sync -V
  register: airplay_sps_version
  changed_when: false

- name: Assert required shairport features are present (token-tolerant)
  ansible.builtin.assert:
    that:
      - "feature | lower | replace(' ', '') in (airplay_sps_version.stdout | lower | replace(' ', ''))"
    fail_msg: "shairport-sync is missing required feature: {{ feature }}"
  loop: "{{ airplay_required_features }}"
  loop_control:
    loop_var: feature

- name: Capture nqptp version (uppercase -V)
  ansible.builtin.command: nqptp -V
  register: airplay_nqptp_version
  changed_when: false
  failed_when: airplay_nqptp_version.rc != 0

- name: Write build stamp
  ansible.builtin.copy:
    dest: /usr/local/share/airplay/.versions
    mode: "0644"
    content: |
      {{
        {
          "signature": airplay_build_signature,
          "shairport_version": shairport_sync_version,
          "nqptp_version": nqptp_version,
          "alac_ref": alac_ref,
          "configure_flags": shairport_configure_flags,
          "shairport_v_output": airplay_sps_version.stdout,
          "nqptp_v_output": airplay_nqptp_version.stdout
        } | to_nice_json
      }}
```

`roles/airplay/handlers/main.yml`:
```yaml
---
- name: restart shairport-sync
  ansible.builtin.systemd:
    name: shairport-sync
    state: restarted
    daemon_reload: true

- name: daemon reload
  ansible.builtin.systemd:
    daemon_reload: true
```

- [ ] **Step 2: Verify lint + syntax**

Run: `yamllint roles/airplay/tasks/build.yml roles/airplay/handlers/main.yml && ansible-lint && ansible-playbook --syntax-check site.yml`
Expected: pass (after Task 9 wires `build.yml` into the role; until then `ansible-lint` runs against the file directly).

- [ ] **Step 3: Commit**

```bash
git add roles/airplay/tasks/build.yml roles/airplay/handlers/main.yml
git commit -m "feat(role): from-source build, profile-gated, stamped, feature-verified"
```

---

## Task 8: Config + systemd tasks (install config, units, hardening, optional health timer)

**Files:**
- Create: `roles/airplay/tasks/config.yml`, `roles/airplay/tasks/systemd.yml`, `roles/airplay/templates/airplay-health.service.j2`, `roles/airplay/templates/airplay-health.timer.j2`

**Interfaces:**
- Consumes: templates from Task 6, handlers from Task 7.
- Produces: `/etc/shairport-sync.conf`, override drop-in at `/etc/systemd/system/shairport-sync.service.d/10-airplay.conf`, enabled `nqptp` + `shairport-sync`, optional health timer.

- [ ] **Step 1: Write config task**

`roles/airplay/tasks/config.yml`:
```yaml
---
- name: Render shairport-sync.conf
  ansible.builtin.template:
    src: shairport-sync.conf.j2
    dest: /etc/shairport-sync.conf
    mode: "0644"
  notify: restart shairport-sync
```

- [ ] **Step 2: Write health-timer templates**

`roles/airplay/templates/airplay-health.service.j2`:
```jinja
[Unit]
Description=AirPlay Wyse health check

[Service]
Type=oneshot
ExecStart=/usr/local/bin/airplay-doctor --check
```

`roles/airplay/templates/airplay-health.timer.j2`:
```jinja
[Unit]
Description=Run AirPlay Wyse health check periodically

[Timer]
OnBootSec=2min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Write systemd task**

`roles/airplay/tasks/systemd.yml`:
```yaml
---
- name: Ensure shairport-sync override directory
  ansible.builtin.file:
    path: /etc/systemd/system/shairport-sync.service.d
    state: directory
    mode: "0755"

- name: Install hardening override
  ansible.builtin.template:
    src: shairport-override.conf.j2
    dest: /etc/systemd/system/shairport-sync.service.d/10-airplay.conf
    mode: "0644"
  notify:
    - daemon reload
    - restart shairport-sync

- name: Enable and start nqptp
  ansible.builtin.systemd:
    name: nqptp
    enabled: true
    state: started
    daemon_reload: true

- name: Enable and start shairport-sync
  ansible.builtin.systemd:
    name: shairport-sync
    enabled: true
    state: started

- name: Install health timer (optional)
  when: airplay_health_timer | bool
  block:
    - name: Install health service unit
      ansible.builtin.template:
        src: airplay-health.service.j2
        dest: /etc/systemd/system/airplay-health.service
        mode: "0644"
    - name: Install health timer unit
      ansible.builtin.template:
        src: airplay-health.timer.j2
        dest: /etc/systemd/system/airplay-health.timer
        mode: "0644"
    - name: Enable health timer
      ansible.builtin.systemd:
        name: airplay-health.timer
        enabled: true
        state: started
        daemon_reload: true
```

- [ ] **Step 4: Verify lint + syntax + existing render tests still pass**

Run: `yamllint . && ansible-lint && ansible-playbook --syntax-check site.yml && pytest -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add roles/airplay/tasks/config.yml roles/airplay/tasks/systemd.yml roles/airplay/templates/airplay-health.service.j2 roles/airplay/templates/airplay-health.timer.j2
git commit -m "feat(role): config + systemd units, hardening override, optional health timer"
```

---

## Task 9: Doctor install task + role main.yml + wire role into site.yml

**Files:**
- Create: `roles/airplay/tasks/doctor.yml`, `roles/airplay/tasks/main.yml`
- Modify: `site.yml`

**Interfaces:**
- Consumes: `airplay_doctor.py` (Task 4), all task files (Tasks 7–8).
- Produces: `/usr/local/bin/airplay-doctor` on the box; role executes build → config → systemd → doctor in order.

- [ ] **Step 1: Write doctor install task**

`roles/airplay/tasks/doctor.yml`:
```yaml
---
- name: Install airplay-doctor
  ansible.builtin.copy:
    src: airplay_doctor.py
    dest: /usr/local/bin/airplay-doctor
    mode: "0755"
```

- [ ] **Step 2: Write role main.yml**

`roles/airplay/tasks/main.yml`:
```yaml
---
- name: Build stack from source
  ansible.builtin.import_tasks: build.yml

- name: Render configuration
  ansible.builtin.import_tasks: config.yml

- name: Install systemd units and hardening
  ansible.builtin.import_tasks: systemd.yml

- name: Install diagnostics tool
  ansible.builtin.import_tasks: doctor.yml
```

- [ ] **Step 3: Wire role into site.yml**

`site.yml`:
```yaml
---
- name: Provision AirPlay 2 endpoints
  hosts: airplay
  become: true
  roles:
    - airplay
```

- [ ] **Step 4: Verify lint + syntax**

Run: `yamllint . && ansible-lint && ansible-playbook --syntax-check site.yml && pytest -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add roles/airplay/tasks/doctor.yml roles/airplay/tasks/main.yml site.yml
git commit -m "feat(role): doctor install, role main.yml, wire role into site.yml"
```

---

## Task 10: doctor.yml fleet playbook (aggregate reports, cross-host duplicate-id detection)

**Files:**
- Create: `doctor.yml`

**Interfaces:**
- Consumes: `/usr/local/bin/airplay-doctor --json` on each host.
- Produces: per-host pass/fail summary and a **fleet-wide** assert that no two boxes share a device-id.

- [ ] **Step 1: Write the fleet playbook**

`doctor.yml`:
```yaml
---
- name: Collect health from each box
  hosts: airplay
  become: true
  gather_facts: false
  tasks:
    - name: Run airplay-doctor
      ansible.builtin.command: /usr/local/bin/airplay-doctor --json
      register: airplay_doctor_out
      changed_when: false
      failed_when: false

    - name: Parse report
      ansible.builtin.set_fact:
        airplay_report: "{{ airplay_doctor_out.stdout | from_json }}"

    - name: Show per-host status
      ansible.builtin.debug:
        msg: "{{ inventory_hostname }}: {{ 'OK' if airplay_report.ok else 'FAIL' }} (device-id {{ airplay_report.device_id }})"

- name: Fleet-wide checks
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Gather all device-ids
      ansible.builtin.set_fact:
        fleet_ids: "{{ groups['airplay'] | map('extract', hostvars, ['airplay_report', 'device_id']) | select('string') | list }}"

    - name: Assert device-ids are unique across the fleet
      ansible.builtin.assert:
        that:
          - "fleet_ids | length == fleet_ids | unique | length"
        fail_msg: "Duplicate AirPlay device-id across the fleet: {{ fleet_ids }}"
        success_msg: "All fleet device-ids are unique."
```

- [ ] **Step 2: Verify lint + syntax**

Run: `yamllint doctor.yml && ansible-lint && ansible-playbook --syntax-check doctor.yml`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add doctor.yml
git commit -m "feat: doctor.yml fleet health + cross-host duplicate-id detection"
```

---

## Task 11: migration.yml — clean old deployed artifacts

**Files:**
- Create: `migration.yml`

**Interfaces:**
- Produces: idempotent removal of the legacy Python/state/units install from existing boxes.

- [ ] **Step 1: Write the migration playbook**

`migration.yml`:
```yaml
---
- name: Remove legacy airplay_wyse install
  hosts: airplay
  become: true
  gather_facts: false
  vars:
    legacy_units:
      - airplay-wyse-identity.service
      - airplay-wyse-alsa-policy.service
      - airplay-wyse-pw-policy.service
      - airplay-wyse-audio-kmods.service
      - airplay-wyse-health.service
      - airplay-wyse-health.timer
  tasks:
    - name: Disable and stop legacy units
      ansible.builtin.systemd:
        name: "{{ item }}"
        enabled: false
        state: stopped
      loop: "{{ legacy_units }}"
      failed_when: false

    - name: Remove legacy unit files
      ansible.builtin.file:
        path: "/etc/systemd/system/{{ item }}"
        state: absent
      loop: "{{ legacy_units }}"

    - name: Remove legacy runtime bundle
      ansible.builtin.file:
        path: /usr/local/libexec/airplay_wyse
        state: absent

    - name: Remove legacy state directory
      ansible.builtin.file:
        path: /var/lib/airplay_wyse
        state: absent

    - name: Detect project-managed asound.conf
      ansible.builtin.command: grep -ilq airplay /etc/asound.conf
      register: asound_managed
      changed_when: false
      failed_when: false

    - name: Remove project-managed asound.conf only
      ansible.builtin.file:
        path: /etc/asound.conf
        state: absent
      when: asound_managed.rc == 0

    - name: Reload systemd
      ansible.builtin.systemd:
        daemon_reload: true
```

> Note on the asound.conf guard: the legacy `/etc/asound.conf` written by the old code may not contain the literal string `airplay`. During rollout (Task 12 baseline capture), inspect the working box's `/etc/asound.conf`; if it lacks an identifying marker, add a one-line marker comment to the guard's `grep` pattern to match the actual managed file, and never remove a file you cannot positively identify as project-managed.

- [ ] **Step 2: Verify lint + syntax**

Run: `yamllint migration.yml && ansible-lint && ansible-playbook --syntax-check migration.yml`
Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add migration.yml
git commit -m "feat: migration.yml to clean legacy units/state/asound on existing boxes"
```

---

## Task 12: Delete legacy tree, rewrite docs + rollout runbook, finalize CI

**Files:**
- Delete: `src/airplay_wyse/`, `bin/`, `systemd/`, `cfg/`, `profiles/`, `tools/lints.sh`
- Modify/Replace: `README.md`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`, `Makefile`, `.github/workflows/ci.yml` (extend syntax-check to all playbooks)

**Interfaces:**
- Produces: a clean Ansible-only repo; README rollout runbook; CI covering all three playbooks.

- [ ] **Step 1: Remove the legacy tree**

```bash
git rm -r src/airplay_wyse bin systemd cfg profiles tools/lints.sh
```

- [ ] **Step 2: Extend CI syntax-check to all playbooks**

In `.github/workflows/ci.yml`, change the syntax-check step:
```yaml
      - name: syntax-check
        run: ansible-playbook --syntax-check site.yml migration.yml doctor.yml
```

- [ ] **Step 3: Replace Makefile**

`Makefile`:
```make
.PHONY: lint test check
lint:
	yamllint . && ansible-lint
test:
	pytest -v
check: lint test
	ansible-playbook --syntax-check site.yml migration.yml doctor.yml
```

- [ ] **Step 4: Rewrite README with usage + rollout runbook**

`README.md` must document: prerequisites (`pip install -r requirements-dev.txt`, SSH access), editing `inventory/hosts.yml` + `host_vars/<box>.yml` (set `airplay_name`, `airplay_alsa_card` from `aplay -L`), and the **rollout runbook**:

1. **Capture baseline** on the working box: `shairport-sync -V`, `cat /etc/os-release`, `cat /etc/shairport-sync.conf`, `cat /etc/asound.conf`. If shairport version ≠ `4.3.7`, set `shairport_sync_version` in `group_vars/airplay.yml` to match.
2. **Build/syntax smoke (VM/container, optional):** verify the playbook runs and the build completes — NOT valid for audio/timing (AirPlay 2 timing is unreliable in VMs).
3. **Physical spare box — hardening/audio/sync matrix:** `ansible-playbook site.yml -l spare-box`; confirm shairport starts under the override, AirPlay 2 pairing survives `systemctl restart shairport-sync`, the DAC plays, `airplay-doctor --check` exits 0, and a real stream syncs with another AirPlay 2 speaker.
4. **Working box cutover:** `ansible-playbook migration.yml -l working-box && ansible-playbook site.yml -l working-box`, then `airplay-doctor --check`.
5. **Roll to remaining boxes**, then `ansible-playbook doctor.yml`.

Also document: updating = bump version vars + re-run `site.yml`; drift correction = re-run `site.yml`; `shairport_major: "5"` is opt-in and must pass the spare-box matrix before any production box.

`docs/ARCHITECTURE.md` and `docs/OPERATIONS.md`: replace stale Python/CLI/state descriptions with the Ansible model (role layout, playbooks, doctor, no boot-time oneshots).

- [ ] **Step 5: Verify full gate**

Run: `yamllint . && ansible-lint && ansible-playbook --syntax-check site.yml migration.yml doctor.yml && pytest -v`
Expected: all pass; no references to deleted paths remain (`grep -rndresult airplay_wyse . --include=*.yml` returns nothing relevant).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy Python/shell tree, Ansible-only repo + rollout runbook"
```

---

## Self-Review

**Spec coverage:**
- Ansible project / repo layout → Tasks 1, 5, 9. ✓
- From-source build, two profiles, explicit pins → Task 7 + defaults (Task 5) + Global Constraints. ✓
- Stamp + mandatory feature re-verification → Task 7. ✓
- Identity simplification + `airplay_device_id` escape hatch → Tasks 5, 6. ✓
- Config (hw:CARD+DEV, soxr, disable_standby, no asound.conf) → Task 6. ✓
- systemd hardening (StateDirectory/CacheDirectory, DeviceAllow+DevicePolicy, no PrivateDevices) → Tasks 6, 8. ✓
- Optional health timer (off by default) → Tasks 5, 8. ✓
- airplay-doctor (non-invasive --check, --deep opt-in, --json, tested parsers) → Tasks 2, 3, 4. ✓
- Fleet duplicate-id detection in doctor.yml (not on-box) → Task 10. ✓
- migration.yml cleanup → Task 11. ✓
- Real failing-capable CI (yamllint, ansible-lint, syntax-check, pytest) → Tasks 1, 12. ✓
- Rollout matrix (VM smoke vs physical spare) → Task 12 runbook. ✓
- Delete legacy tree → Task 12. ✓

**Placeholder scan:** The only intentional `--deep` "placeholder" detail (device-open probe) is documented as opt-in and out of scope for unit tests; everything else contains concrete code/commands. No "TBD/TODO/handle edge cases" instructions.

**Type consistency:** `parse_shairport_version`/`parse_listening_ports`/`parse_mdns`/`parse_alsa_cards`/`parse_journal_errors`/`parse_device_id`/`is_zero_device_id`/`build_report(runner, deep)`/`main(argv, runner)` names are consistent between definition (Tasks 2–4) and use (tests, `_system_runner`). Var names (`airplay_alsa_card`, `airplay_alsa_device`, `airplay_device_id`, `airplay_state_dir`, `shairport_configure_flags`, `airplay_required_features`) are consistent across defaults, templates, and tasks.
