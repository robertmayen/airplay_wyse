# Audit Fixes + Four Upgrades Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution step 0:** copy this plan into the repo at `docs/superpowers/plans/2026-07-06-audit-fixes-and-upgrades.md` and commit it (plan-mode forbade writing it there during planning).

**Goal:** Fix the five audit findings, then take the project to the next level: CI that actually converges the role (with idempotence gate), a build-once .deb artifact pipeline consumed via the control machine, a closed observability loop (doctor JSON on the dashboard), and automated upstream version-bump PRs.

**Architecture:** All on-box code stays stdlib-only Python; all new CI is plain docker + GitHub Actions (no molecule, no fpm, no debhelper). The role gains an `airplay_install_method: source|deb` switch; feature verification moves out of `build.yml` so both paths share it. Debs are built in a `debian:13` container with Depends auto-resolved by `dpkg-shlibdeps` (Debian 13 t64 renames make hardcoded lists a trap), published as GitHub Release assets under a tag computable from the role's version pins, and fetched on the **control machine** (`gh release download`, works for private repos) then pushed to boxes.

**Tech Stack:** Ansible (core ≥2.16), `community.docker` collection (CI only), pytest + jinja2 (existing dev deps), GitHub Actions (`ubuntu-24.04` runners), `dpkg-deb`/`dpkg-shlibdeps`, `peter-evans/create-pull-request@v7`.

## Global Constraints

- On-box Python is **stdlib only** (doctor/nowplaying/dashboard/scripts).
- Targets are Debian 13 (trixie) amd64; install prefix stays `/usr/local` (unit template hardcodes `ExecStart=/usr/local/bin/shairport-sync`).
- `make check` (yamllint + ansible-lint + pytest + syntax-check) must pass after every task.
- User-facing pin vars keep their names (`shairport_sync_version`, `nqptp_version`, `alac_ref`, `shairport_major`) — `.ansible-lint` already warn-lists `var-naming[no-role-prefix]` deliberately; do NOT rename.
- Existing test patterns: template tests render with jinja2 `Environment` (`tests/test_templates.py`); Python-tool tests load the module by path via `importlib` and inject a fake `runner` (`tests/test_airplay_doctor.py`). Follow them.
- Commit after every task; messages in the repo's `type(scope): summary` style.

---

## Part A — Audit fixes

### Task 1: Repo hygiene (yamllint truthy, stray tracked file, placeholder test)

**Files:**
- Modify: `.yamllint` (truthy rule)
- Modify: `.gitignore` (add `.superpowers/`)
- Delete (untrack): `.superpowers/sdd/final-fixes-report.md`
- Delete: `tests/test_smoke.py` (2-line placeholder; real suites exist)

**Steps:**

- [ ] **Step 1: Fix the truthy warning on workflow `on:` keys.** In `.yamllint`, extend the truthy rule:

```yaml
  truthy:
    allowed-values: ["true", "false"]
    check-keys: false
```

- [ ] **Step 2: Untrack the stray SDD artifact and ignore the directory.**

```bash
git rm --cached .superpowers/sdd/final-fixes-report.md
echo ".superpowers/" >> .gitignore
```

- [ ] **Step 3: Delete `tests/test_smoke.py`.**
- [ ] **Step 4: Verify** — `make check` passes and `yamllint .` reports zero warnings (run it without the Makefile's `&&`-short-circuit to see output).
- [ ] **Step 5: Commit** — `chore: silence workflow-key truthy lint, untrack sdd artifact, drop placeholder test`

### Task 2: Doctor journal check heals (scope to current boot + last hour)

Problem: `journal:errors` counts xruns/sync errors in the last 200 lines forever — one historical underrun fails health until logs scroll. Scope the probe to `-b --since -1h`. To make the command list testable, hoist the probe map to module level.

**Files:**
- Modify: `roles/airplay/files/airplay_doctor.py:80-98`
- Test: `tests/test_airplay_doctor.py`

**Interfaces:**
- Produces: module-level `PROBE_CMDS: dict[str, list[str]]` in `airplay_doctor.py` (consumed by `_system_runner` and Task 3's test).

- [ ] **Step 1: Write failing test** (append to `tests/test_airplay_doctor.py`):

```python
def test_journal_probe_is_scoped_to_recent_boot():
    cmd = ad.PROBE_CMDS["journal"]
    assert "-b" in cmd
    assert "--since" in cmd
```

- [ ] **Step 2: Run it** — `pytest tests/test_airplay_doctor.py::test_journal_probe_is_scoped_to_recent_boot -v` → FAIL (`no attribute 'PROBE_CMDS'`).
- [ ] **Step 3: Implement.** In `airplay_doctor.py`, move the `cmds` dict out of `_system_runner` to module level (below the imports at line 73ff) and scope the journal probe:

```python
PROBE_CMDS = {
    "shairport_version": ["shairport-sync", "-V"],
    "ss": ["ss", "-ulnp"],
    "mdns": ["avahi-browse", "-atp", "--no-db-lookup", "-r", "-l"],
    "aplay": ["aplay", "-L"],
    # -b + --since: only current boot, only the last hour — a historical xrun
    # must not fail health forever (journal lines otherwise linger for days).
    "journal": ["journalctl", "-u", "shairport-sync", "-b", "--since", "-1h",
                "-n", "200", "--no-pager"],
}
```

`_system_runner` uses `PROBE_CMDS.get(name, ["true"])`.

- [ ] **Step 4: Run full doctor suite** — `pytest tests/test_airplay_doctor.py -v` → all PASS.
- [ ] **Step 5: Commit** — `fix(doctor): scope journal error check to current boot + last hour`

### Task 3: Implement the real `--deep` ALSA probe

Problem: `--deep` returns a hardcoded pass (`airplay_doctor.py:147-149`) while docs promise a device-open probe. Implement it: parse the configured `output_device` from the config, probe it with `aplay --dump-hw-params` (prints hw params when the device opens; error text otherwise). aplay prints params to **stderr**, so the probe capture must merge stderr.

**Files:**
- Modify: `roles/airplay/files/airplay_doctor.py`
- Test: `tests/test_airplay_doctor.py`

**Interfaces:**
- Produces: `parse_output_device(conf_text: str) -> str` (returns e.g. `"hw:CARD=Device,DEV=0"` or `""`); runner probe name `f"deep_open:{device}"` whose output contains `"HW Params of device"` on success.

- [ ] **Step 1: Write failing tests:**

```python
def test_parse_output_device():
    conf = 'output_device = "hw:CARD=Device,DEV=0";\n'
    assert ad.parse_output_device(conf) == "hw:CARD=Device,DEV=0"
    assert ad.parse_output_device("") == ""


def test_deep_probe_pass_and_fail():
    ok_out = "HW Params of device \"hw:CARD=Device,DEV=0\":\nACCESS: MMAP_INTERLEAVED\n"
    r = ad.build_report(_fixture_runner(
        {"deep_open:hw:CARD=Device,DEV=0": ok_out}), deep=True)
    assert any(c["name"] == "deep:device-open" and c["ok"] for c in r["checks"])

    r = ad.build_report(_fixture_runner(
        {"deep_open:hw:CARD=Device,DEV=0": "aplay: main:834: audio open error: Device or resource busy\n"}), deep=True)
    assert r["ok"] is False
    assert any(c["name"] == "deep:device-open" and not c["ok"] for c in r["checks"])


def test_no_deep_check_without_flag():
    r = ad.build_report(_fixture_runner())
    assert not any(c["name"].startswith("deep:") for c in r["checks"])
```

- [ ] **Step 2: Run** → FAIL (`parse_output_device` undefined; deep check currently always-true placeholder).
- [ ] **Step 3: Implement.** In `airplay_doctor.py`:

```python
def parse_output_device(conf_text: str) -> str:
    m = re.search(r'output_device\s*=\s*"([^"]+)"', conf_text)
    return m.group(1) if m else ""
```

In `_system_runner`, handle the probe prefix (before the `PROBE_CMDS` lookup):

```python
    if name.startswith("deep_open:"):
        dev = name.split(":", 1)[1]
        # aplay prints hw params to stderr; merge so the token check sees them.
        try:
            r = subprocess.run(
                ["aplay", "-D", dev, "--dump-hw-params", "-d", "1", "/dev/zero"],
                capture_output=True, text=True, check=False, timeout=10)
            return r.stdout + r.stderr
        except (OSError, subprocess.SubprocessError):
            return ""
```

In `build_report`, replace the placeholder block; it must reuse `conf` (already read) and the check reports the probed device as detail:

```python
    if deep:
        # Opt-in only: opening hw: can disrupt shairport's exclusive access.
        dev = parse_output_device(conf)
        if dev:
            out = runner(f"deep_open:{dev}")
            opened = "HW Params of device" in out
            checks.append(_check("deep:device-open", opened, dev))
        else:
            checks.append(_check("deep:device-open", False, "no output_device in config"))
```

- [ ] **Step 4: Run full suite** — `pytest -v` → PASS.
- [ ] **Step 5: Update docs** — README `--deep` line and ARCHITECTURE doctor paragraph now say: probes the configured ALSA device via `aplay --dump-hw-params` (1s of silence from `/dev/zero`; may briefly contend with an active stream).
- [ ] **Step 6: Commit** — `feat(doctor): real --deep ALSA device-open probe (replaces placeholder pass)`

### Task 4: Dashboard bind default → 127.0.0.1

**Files:**
- Modify: `roles/airplay/defaults/main.yml:31-36`, `docs/ARCHITECTURE.md` (Security Notes), `docs/OPERATIONS.md` (dashboard section), README if it mentions the bind.

- [ ] **Step 1: Flip the default** in `defaults/main.yml`:

```yaml
# Address the dashboard binds to. It is an UNAUTHENTICATED control surface
# (volume + disconnect over D-Bus). Default is loopback-only: set this to a
# LAN IP or "0.0.0.0" per-host/group to allow phones on the LAN to reach it.
airplay_dashboard_bind: "127.0.0.1"
```

- [ ] **Step 2: Update docs** — ARCHITECTURE/OPERATIONS: "loopback-only by default; LAN access is an explicit opt-in via `airplay_dashboard_bind`". Add a migration note: existing deployments using the dashboard from phones must now set `airplay_dashboard_bind: "0.0.0.0"` (or a LAN IP) in `inventory/group_vars/airplay.yml`.
- [ ] **Step 3: Verify** — `make check`. (Template tests pass the bind explicitly, so no test change; the default lives in defaults, which jinja tests don't load.)
- [ ] **Step 4: Commit** — `fix(role): dashboard binds loopback by default; LAN reach is explicit opt-in`

### Task 5: Pin builds to commit SHAs (immutable-ref supply chain)

Tags are mutable; `alac_ref: master` floats. Add companion commit vars (resolved from the pinned tags at implementation time via `git ls-remote https://github.com/mikebrady/<repo> <tag>`), check out **commits**, and fold them into the build signature. Version strings remain the naming/deb-versioning truth; SHAs become the checkout truth.

**Files:**
- Modify: `roles/airplay/defaults/main.yml`, `roles/airplay/tasks/build.yml`
- Docs: README "Updating shairport-sync version" gains "and refresh the `_commit` vars (`git ls-remote`)" — Task 10's bump automation does this for you.

**Interfaces:**
- Produces: vars `shairport_sync_commit`, `nqptp_commit`, `alac_ref` (now a 40-char SHA) — consumed by Task 10's rewrite logic and referenced by Task 7's deb build (which reads the same pins).

- [ ] **Step 1: Resolve the SHAs** (implementation-time, network read-only):

```bash
git ls-remote https://github.com/mikebrady/shairport-sync 4.3.7   # take the ^{} peeled line if present
git ls-remote https://github.com/mikebrady/nqptp 1.2.8
git ls-remote https://github.com/mikebrady/alac HEAD
```

- [ ] **Step 2: Add to `defaults/main.yml`** (directly under each version pin, real SHAs from step 1):

```yaml
shairport_sync_version: "4.3.7"
shairport_sync_commit: "<sha from step 1>"   # tag 4.3.7 — checkout truth (tags are mutable)
nqptp_version: "1.2.8"
nqptp_commit: "<sha>"                        # tag 1.2.8
alac_ref: "<sha>"                            # was floating "master"
```

- [ ] **Step 3: Use them in `build.yml`** — the three `ansible.builtin.git` tasks switch `version:` to `{{ shairport_sync_commit }}` / `{{ nqptp_commit }}` / (alac already uses `{{ alac_ref }}`, now a SHA). Extend the signature fact so a SHA change alone triggers a rebuild:

```yaml
    airplay_build_signature: >-
      shairport={{ shairport_sync_version }}@{{ shairport_sync_commit }}|nqptp={{ nqptp_version }}@{{ nqptp_commit }}|
      alac={{ alac_ref }}|flags={{ shairport_configure_flags }}
```

- [ ] **Step 4: Verify** — `make check`; also `ansible-playbook --syntax-check site.yml`.
- [ ] **Step 5: Commit** — `feat(role): pin source builds to commit SHAs, not mutable tags`

---

## Part B — The four upgrades

### Task 6: CI converge + idempotence job (systemd container, plain docker)

Design (validated by Plan agent): plain docker + `community.docker.docker` connection — molecule adds a dependency tree to do the same recap-grep. A **real ALSA card via `snd-aloop` on the runner** is load-bearing: the config sets `disable_standby_mode = "always"`, so shairport crash-loops without an openable device → run 2 would flake on `state: started`. Privileged container inherits `/dev/snd`.

**Files:**
- Create: `ci/Dockerfile`, `ci/inventory.yml`
- Modify: `.github/workflows/ci.yml` (add `converge` job)

**Interfaces:**
- Produces: the container recipe (`ci/Dockerfile` + docker-run flags) reused verbatim by Task 8's deb smoke job; inventory hostname `wyse-ci` anchors the recap grep.

- [ ] **Step 1: `ci/Dockerfile`:**

```dockerfile
FROM debian:13
ENV container=docker DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      systemd systemd-sysv dbus python3 ca-certificates \
 && rm -rf /var/lib/apt/lists/*
# Units that fail or are pointless inside a container
RUN systemctl mask systemd-udevd.service systemd-udevd-kernel.socket \
      systemd-udevd-control.socket systemd-networkd.service \
      systemd-resolved.service getty@tty1.service
STOPSIGNAL SIGRTMIN+3
CMD ["/lib/systemd/systemd"]
```

Only `python3` (for Ansible modules) is pre-installed — git/toolchain/avahi must come from the role's own apt task or CI isn't testing it.

- [ ] **Step 2: `ci/inventory.yml`:**

```yaml
all:
  children:
    airplay:
      hosts:
        wyse-ci:
          ansible_connection: community.docker.docker
          ansible_user: root
          ansible_python_interpreter: /usr/bin/python3
          # ansible.cfg sets become=True globally; container has no sudo and
          # we're already root — connection vars outrank play keywords.
          ansible_become: false
          airplay_name: "CI Test Box"
          airplay_alsa_card: "Loopback"   # snd-aloop on the runner, via --privileged
          airplay_alsa_device: 0
```

- [ ] **Step 3: Add the `converge` job to `.github/workflows/ci.yml`** (keep `lint-test` untouched for fast feedback):

```yaml
  converge:
    runs-on: ubuntu-24.04    # pinned: systemd-in-docker/cgroup behavior
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install ansible + docker connection plugin
        run: |
          pip install -r requirements-dev.txt
          ansible-galaxy collection install 'community.docker:>=3.13.0'
      - name: Load ALSA loopback on runner
        run: |
          sudo apt-get update
          sudo apt-get install -y "linux-modules-extra-$(uname -r)"
          sudo modprobe snd-aloop
      - name: Build systemd container image
        run: docker build -t airplay-wyse-ci ci/
      - name: Start container
        run: |
          docker run -d --name wyse-ci --privileged --cgroupns=host \
            -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
            --tmpfs /run --tmpfs /run/lock airplay-wyse-ci
          timeout 60 docker exec wyse-ci bash -c \
            'until systemctl is-system-running --wait 2>/dev/null; do sleep 2; done; true'
      - name: "Converge (run 1: build from source)"
        run: ansible-playbook -i ci/inventory.yml site.yml
      - name: "Idempotence (run 2: must report changed=0)"
        run: |
          ansible-playbook -i ci/inventory.yml site.yml --diff | tee /tmp/run2.log
          grep -E 'wyse-ci\s*:\s*ok=[0-9]+\s+changed=0\s+unreachable=0\s+failed=0' /tmp/run2.log \
            || { echo "::error::Second run not idempotent"; exit 1; }
      - name: Verify services actually running
        run: |
          docker exec wyse-ci systemctl is-active nqptp shairport-sync
          docker exec wyse-ci shairport-sync -V
      - name: Dump logs on failure
        if: failure()
        run: |
          docker exec wyse-ci journalctl -u shairport-sync -u nqptp -u avahi-daemon --no-pager -n 200 || true
          docker exec wyse-ci systemctl --failed --no-pager || true
```

- [ ] **Step 4: Local pre-flight (optional but cheap)** — `docker` on this Mac can't do `--privileged` systemd + snd-aloop faithfully; rely on `make check` locally and the Actions run for the real signal.
- [ ] **Step 5: Update README** Linting/Testing section: CI now converges the role twice in a Debian 13 systemd container and fails on any second-run change.
- [ ] **Step 6: Commit + push branch; watch the Actions run** — `feat(ci): converge + idempotence gate in a Debian 13 systemd container`. Known trap if `DevicePolicy=closed` blocks `/dev/snd` under the BPF device controller in-container: add a CI-only pre-step drop-in (`99-ci.conf` with `DevicePolicy=auto`) via `docker exec` *before* run 1 (persists across both runs → idempotence unaffected). Only add if it actually bites.

### Task 7: Deb packaging workflow (build once in CI, release as assets)

Design: `make install DESTDIR` staging + hand-written `DEBIAN/control` + `dpkg-deb --build`. **Depends comes from `dpkg-shlibdeps`, never hardcoded** — Debian 13's t64 transition renamed `libasound2`→`libasound2t64`, `libssl3`→`libssl3t64`, etc. Build shairport with metadata+dbus **always baked in** (runtime-inert when the config omits the metadata block; no extra runtime deps — GDBus comes with the already-linked glib) so one deb serves both dashboard profiles. Prefix `/usr/local` (matches the unit template and existing fleet; private packages, policy caveat documented in the workflow header).

**Files:**
- Create: `ci/build-debs.sh`, `ci/control/shairport-sync.control.in`, `ci/control/nqptp.control.in`, `ci/control/libalac.control.in`, `.github/workflows/debs.yml`

**Interfaces:**
- Produces (consumed by Task 8): release tag `debs-shairport{{ shairport_sync_version }}-nqptp{{ nqptp_version }}-r{{ airplay_deb_revision }}` (e.g. `debs-shairport4.3.7-nqptp1.2.8-r1`); assets `shairport-sync_<v>-<r>_amd64.deb`, `nqptp_<v>-<r>_amd64.deb`, `libalac_*_amd64.deb`, `SHA256SUMS`; CI artifact name `debs-amd64`.
- `ci/build-debs.sh <sps_ver> <sps_commit> <nqptp_ver> <nqptp_commit> <alac_sha> <outdir>` — reads pins as args so it's runnable locally in `docker run -it debian:13`.

- [ ] **Step 1: control templates.** `ci/control/shairport-sync.control.in` (others analogous, minus avahi/libalac deps):

```
Package: shairport-sync
Version: @VERSION@
Architecture: amd64
Maintainer: airplay_wyse CI <r.mayen@live.de>
Section: sound
Priority: optional
Depends: @DEPENDS@
Description: AirPlay 2 audio receiver (airplay_wyse build)
 shairport-sync @VERSION@ built with alsa/soxr/avahi/openssl/systemd/
 airplay-2/apple-alac/metadata/dbus. Installs to /usr/local (private
 package; pairs with the airplay_wyse Ansible role).
```

- [ ] **Step 2: `ci/build-debs.sh`.** One script, `set -euo pipefail`, doing for each package (order: **libalac → nqptp → shairport-sync**, `dpkg -i` the libalac deb into the build container before shairport's shlibdeps so the intra-repo dep resolves):
  1. `git clone` + `git checkout <commit>` (the SHA pins from Task 5)
  2. `autoreconf -fi && ./configure <flags> && make -j$(nproc)`
     - shairport flags: `--sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl --with-systemd --with-airplay-2 --with-apple-alac --with-metadata --with-dbus-interface`
     - nqptp flags: `--with-systemd-startup`
  3. `make install DESTDIR="$STAGE"`
  4. Depends: `dpkg-shlibdeps -O` against the staged binary (minimal throwaway `debian/control` scaffold as shlibdeps requires one), captured and `sed`-substituted into the `.control.in` along with `@VERSION@`; shairport additionally appends `, avahi-daemon, libalac (= <alacver>)`.
  5. `mkdir $STAGE/DEBIAN`, write control; libalac also gets `postinst`/`postrm` containing `ldconfig`.
  6. `dpkg-deb --build --root-owner-group "$STAGE" "$OUT/<name>_<ver>-${DEB_REVISION}_amd64.deb"`
  - Versions: `shairport-sync 4.3.7-1`, `nqptp 1.2.8-1`, libalac `0.0~git<YYYYMMDD>.<sha7>-1` (deterministic now that alac is SHA-pinned); `DEB_REVISION` is a variable at the top of the script (bump when packaging changes but pins don't).
- [ ] **Step 3: `.github/workflows/debs.yml`** — three jobs:

```yaml
name: debs
on:
  push:
    branches: [main]
    paths: ['roles/airplay/defaults/main.yml', 'ci/build-debs.sh', 'ci/control/**', '.github/workflows/debs.yml']
  workflow_dispatch:
permissions:
  contents: write
jobs:
  build-debs:
    runs-on: ubuntu-24.04
    container: debian:13      # dpkg-shlibdeps must see trixie package names
    steps:
      - name: Install build + packaging deps
        run: |
          apt-get update
          apt-get install -y --no-install-recommends build-essential git autoconf automake \
            libtool libpopt-dev libconfig-dev libasound2-dev libavahi-client-dev libssl-dev \
            libsoxr-dev libplist-dev libglib2.0-dev libsodium-dev libavutil-dev libavcodec-dev \
            libavformat-dev uuid-dev libgcrypt20-dev xxd systemd-dev ca-certificates dpkg-dev
      - uses: actions/checkout@v4
      - name: Read pins from role defaults
        id: pins
        run: |
          for k in shairport_sync_version shairport_sync_commit nqptp_version nqptp_commit alac_ref; do
            echo "$k=$(grep -oP "^$k: \"\K[^\"]+" roles/airplay/defaults/main.yml)" >> "$GITHUB_OUTPUT"
          done
      - name: Build debs
        run: |
          ci/build-debs.sh \
            "${{ steps.pins.outputs.shairport_sync_version }}" "${{ steps.pins.outputs.shairport_sync_commit }}" \
            "${{ steps.pins.outputs.nqptp_version }}" "${{ steps.pins.outputs.nqptp_commit }}" \
            "${{ steps.pins.outputs.alac_ref }}" out/
      - name: SHA256SUMS
        run: cd out && sha256sum *.deb > SHA256SUMS
      - uses: actions/upload-artifact@v4
        with:
          name: debs-amd64
          path: out/

  smoke-debs:               # upgraded to a full role converge in Task 8 step 5
    needs: build-debs
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: debs-amd64
          path: out
      - name: Install debs in systemd container and sanity-check
        run: |
          docker build -t airplay-wyse-ci ci/
          docker run -d --name wyse-ci --privileged --cgroupns=host \
            -v /sys/fs/cgroup:/sys/fs/cgroup:rw --tmpfs /run --tmpfs /run/lock \
            -v "$PWD/out":/debs:ro airplay-wyse-ci
          docker exec wyse-ci bash -c 'apt-get update && apt-get install -y /debs/*.deb'
          docker exec wyse-ci shairport-sync -V
          docker exec wyse-ci nqptp -V

  release:
    needs: [build-debs, smoke-debs]
    if: github.event_name == 'workflow_dispatch' || github.ref == 'refs/heads/main'
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with:
          name: debs-amd64
          path: out
      - name: Create/replace release
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          SPS=$(grep -oP '^shairport_sync_version: "\K[^"]+' roles/airplay/defaults/main.yml)
          NQPTP=$(grep -oP '^nqptp_version: "\K[^"]+' roles/airplay/defaults/main.yml)
          TAG="debs-shairport${SPS}-nqptp${NQPTP}-r1"
          gh release view "$TAG" >/dev/null 2>&1 && gh release delete "$TAG" --cleanup-tag -y
          gh release create "$TAG" out/*.deb out/SHA256SUMS \
            --title "$TAG" --notes "amd64 debs for Debian 13 (trixie). Prefix: /usr/local."
```

- [ ] **Step 4: Verify** — `make check` (yamllint the new workflow), `bash -n ci/build-debs.sh`, then push and confirm the `debs` workflow goes green and the release appears with 4 assets. Trap: use `apt-get install /debs/*.deb` (not bare `dpkg -i`) so runtime Depends resolve from trixie repos.
- [ ] **Step 5: Commit** — `feat(ci): build shairport/nqptp/libalac debs in CI, release as versioned assets`

### Task 8: Role deb install path (control-machine download → push → apt install)

The user's chosen delivery: control machine downloads release assets (using operator `gh auth`, so private repos work; boxes get no tokens), pushes to boxes, installs with apt. Feature-verification moves to a shared `verify.yml`; the stamp stays source-only (deb versioning replaces it).

**Files:**
- Modify: `roles/airplay/defaults/main.yml`, `roles/airplay/tasks/main.yml`, `roles/airplay/tasks/build.yml` (extract verify block)
- Create: `roles/airplay/tasks/verify.yml`, `roles/airplay/tasks/install_deb.yml`
- Modify: `.github/workflows/debs.yml` (smoke job → full converge with deb method), `docs/ARCHITECTURE.md`, README

**Interfaces:**
- Consumes: Task 7's tag scheme + asset names; Task 6's container recipe.
- Produces: vars `airplay_install_method` (`source`|`deb`), `airplay_deb_revision`, `airplay_deb_release_tag`, `airplay_deb_repo`, `airplay_deb_dir`.

- [ ] **Step 1: defaults additions:**

```yaml
# How binaries get onto the box. "source": clone+compile on the box (original
# path). "deb": install CI-built debs — downloaded on the CONTROL MACHINE via
# `gh release download` (works for private repos; boxes never need tokens).
airplay_install_method: source
airplay_deb_revision: 1
airplay_deb_repo: robertmayen/airplay_wyse
airplay_deb_release_tag: "debs-shairport{{ shairport_sync_version }}-nqptp{{ nqptp_version }}-r{{ airplay_deb_revision }}"
# Pre-downloaded deb dir on the control machine (skips the gh download).
# CI's smoke job uses this; operators can too for air-gapped runs.
airplay_deb_dir: ""
```

- [ ] **Step 2: extract `verify.yml`** — move the four tasks "Capture shairport-sync version string" → "Assert required shairport features" → "Capture nqptp version" out of `build.yml` (lines 93-112) into `roles/airplay/tasks/verify.yml` unchanged. The stamp tasks (114-135) stay at the end of `build.yml` (source-only). The token-tolerant assert already tolerates the deb's extra `metadata`/`dbus` `-V` tokens.
- [ ] **Step 3: `install_deb.yml`:**

```yaml
---
- name: Download release debs on the control machine
  when: airplay_deb_dir | length == 0
  become: false
  delegate_to: localhost
  run_once: true
  block:
    - name: Create download dir
      ansible.builtin.tempfile:
        state: directory
        suffix: airplay-debs
      register: airplay_deb_tmp
    - name: Fetch release assets (uses your gh auth; private repos OK)
      ansible.builtin.command: >-
        gh release download {{ airplay_deb_release_tag }}
        -R {{ airplay_deb_repo }} -D {{ airplay_deb_tmp.path }}
      changed_when: true
    - name: Verify checksums
      ansible.builtin.command: shasum -a 256 --check SHA256SUMS
      args:
        chdir: "{{ airplay_deb_tmp.path }}"
      changed_when: false
    - name: Point deb dir at the download
      ansible.builtin.set_fact:
        airplay_deb_dir: "{{ airplay_deb_tmp.path }}"

- name: Find debs to push
  become: false
  delegate_to: localhost
  ansible.builtin.find:
    paths: "{{ airplay_deb_dir }}"
    patterns: "*.deb"
  register: airplay_debs_found

- name: Push debs to the box
  ansible.builtin.copy:
    src: "{{ item.path }}"
    dest: "/var/cache/airplay-debs/{{ item.path | basename }}"
    mode: "0644"
  loop: "{{ airplay_debs_found.files }}"
  loop_control:
    label: "{{ item.path | basename }}"

# libalac first (shairport-sync Depends on it), then nqptp, then shairport.
# apt deb-install is idempotent: same version already installed -> no change.
- name: Install debs (dependency order)
  ansible.builtin.apt:
    deb: "/var/cache/airplay-debs/{{ item }}"
  loop: "{{ airplay_debs_found.files | map(attribute='path') | map('basename')
            | sort | select('match', pkg ~ '_.*') | list }}"
  loop_control:
    loop_var: item
  vars:
    pkg: "{{ pkg_order }}"
  # NOTE to implementer: express the ordering plainly instead of the vars trick —
  # three explicit apt tasks (libalac_*, nqptp_*, shairport-sync_*) selected with
  # `airplay_debs_found.files | map(...) | select('match', '^libalac_') | first`
  # is clearer and is the intended final shape. Each notifies the matching restart
  # handler (nqptp / shairport-sync).
```

(Implement as the three explicit `apt: deb:` tasks per the NOTE — one per package, `notify: Restart nqptp` / `Restart shairport-sync` on the respective installs. That keeps ordering literal and lint-clean.)

- [ ] **Step 4: branch in `main.yml`:**

```yaml
- name: Build stack from source
  ansible.builtin.import_tasks: build.yml
  when: airplay_install_method == "source"

- name: Install stack from CI-built debs
  ansible.builtin.import_tasks: install_deb.yml
  when: airplay_install_method == "deb"

- name: Verify required features
  ansible.builtin.import_tasks: verify.yml
```

- [ ] **Step 5: upgrade the smoke job in `debs.yml`** to a full role converge over the deb path — replace its "Install debs…" step body with the Task 6 recipe (snd-aloop, container start) followed by:

```bash
pip install -r requirements-dev.txt
ansible-galaxy collection install 'community.docker:>=3.13.0'
ansible-playbook -i ci/inventory.yml site.yml \
  -e airplay_install_method=deb -e airplay_deb_dir="$PWD/out"
docker exec wyse-ci systemctl is-active nqptp shairport-sync
```

(setup-python + checkout already present; `airplay_deb_dir` set ⇒ no `gh` needed in CI.)

- [ ] **Step 6: syntax + lint** — `make check`.
- [ ] **Step 7: Docs** — README Day-2 gains a "Fast rollout via debs" subsection: prerequisite `gh` CLI authenticated on the control machine; `ansible-playbook site.yml -e airplay_install_method=deb`; note boxes no longer need `build-essential` (existing toolchains are left in place, not purged). ARCHITECTURE components section describes both install methods and the tag scheme.
- [ ] **Step 8: Commit; push; watch the debs workflow's converge-smoke go green** — `feat(role): install CI-built debs via control machine (airplay_install_method=deb)`

### Task 9: Close the observability loop — doctor JSON on the dashboard

Health timer writes `airplay-doctor --json` to `/run/airplay-doctor.json` (atomic, exit code preserved so the oneshot unit still signals failure); dashboard reads it and shows a doctor badge. Timer default flips to **true** (writes only to `/run` tmpfs — ARCHITECTURE's "no periodic timers that write to /etc" holds).

**Files:**
- Modify: `roles/airplay/templates/airplay-health.service.j2`, `roles/airplay/defaults/main.yml` (`airplay_health_timer: true`), `roles/airplay/files/airplay_dashboard.py`, `docs/ARCHITECTURE.md`, `docs/OPERATIONS.md`
- Test: `tests/test_dashboard.py`, `tests/test_templates.py`

**Interfaces:**
- Produces: `/run/airplay-doctor.json` (doctor's `--json` report, plus dashboard-side mtime as `updated`); dashboard `read_doctor() -> dict` and a `doctor` key in `/api/status`.

- [ ] **Step 1: failing template test** (append to `tests/test_templates.py`):

```python
def test_health_service_writes_json_atomically():
    out = render("airplay-health.service.j2")
    assert "--json" in out
    assert "/run/airplay-doctor.json.tmp" in out
    assert "mv /run/airplay-doctor.json.tmp /run/airplay-doctor.json" in out
```

- [ ] **Step 2: run → FAIL. Implement** `airplay-health.service.j2`:

```
[Unit]
Description=AirPlay Wyse health check
# Managed by airplay_wyse Ansible.

[Service]
Type=oneshot
# Atomic write; doctor's exit code is preserved so an unhealthy box still
# flips this unit (and `systemctl --failed`) red.
ExecStart=/bin/sh -c '/usr/local/bin/airplay-doctor --json > /run/airplay-doctor.json.tmp; rc=$?; mv /run/airplay-doctor.json.tmp /run/airplay-doctor.json; exit $rc'
```

- [ ] **Step 3: failing dashboard tests** (append to `tests/test_dashboard.py`, same importlib-by-path pattern):

```python
def test_read_doctor_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(dash, "DOCTOR_FILE", str(tmp_path / "nope.json"))
    d = dash.read_doctor()
    assert d == {"ok": None, "failed": [], "updated": 0}


def test_read_doctor_parses_report(tmp_path, monkeypatch):
    f = tmp_path / "doctor.json"
    f.write_text('{"ok": false, "checks": [{"name": "mdns:raop", "ok": false},'
                 ' {"name": "service:nqptp", "ok": true}]}')
    monkeypatch.setattr(dash, "DOCTOR_FILE", str(f))
    d = dash.read_doctor()
    assert d["ok"] is False
    assert d["failed"] == ["mdns:raop"]
    assert d["updated"] > 0
```

- [ ] **Step 4: run → FAIL. Implement** in `airplay_dashboard.py`:

```python
DOCTOR_FILE = os.environ.get("AIRPLAY_DOCTOR_FILE", "/run/airplay-doctor.json")


def read_doctor() -> dict:
    """Summarize the health timer's last airplay-doctor report, if any."""
    try:
        with open(DOCTOR_FILE, encoding="utf-8") as fh:
            report = json.load(fh)
        return {
            "ok": bool(report.get("ok")),
            "failed": [c["name"] for c in report.get("checks", []) if not c.get("ok")],
            "updated": os.path.getmtime(DOCTOR_FILE),
        }
    except (OSError, ValueError):
        return {"ok": None, "failed": [], "updated": 0}
```

`build_status()` gains `"doctor": read_doctor()`. In `PAGE`'s `tick()`, render a doctor badge into the existing `.svc` row: green dot `doctor` when `ok===true`, red dot with `title` listing `failed` names when `false`, plain `doctor —` when `null` (timer not yet fired / disabled).

- [ ] **Step 5: run full suite → PASS.** Flip `airplay_health_timer: true` in defaults.
- [ ] **Step 6: Docs** — ARCHITECTURE: health timer is on by default, writes JSON to `/run/airplay-doctor.json` (tmpfs), dashboard surfaces it; OPERATIONS: `systemctl status airplay-health` + the badge meaning.
- [ ] **Step 7: Commit** — `feat: health timer publishes doctor JSON; dashboard shows fleet-box health badge`

### Task 10: Automated upstream version-bump PRs

Weekly workflow checks `mikebrady/{shairport-sync,nqptp}` latest releases, rewrites the pins **and their commit SHAs** (Task 5's vars) via a stdlib-only script with a pure, pytest-covered core, and opens/updates a single PR via `peter-evans/create-pull-request@v7`. **Never auto-bumps shairport across `shairport_major`** (configure-flag profiles and required features differ per major — that's a human decision, surfaced in the PR body).

**Files:**
- Create: `scripts/check_upstream.py`, `.github/workflows/version-bump.yml`
- Test: `tests/test_check_upstream.py`
- Modify: README (Day-2 section + one-time setup note)

**Interfaces:**
- Consumes: `defaults/main.yml` pin lines (`^shairport_sync_version: "..."` etc., regex-anchored — no YAML lib needed; the yamllint CI job guards the rewrite).
- Produces: `parse_pins(text) -> dict[str, str]`, `plan_bumps(current: dict, latest: dict) -> dict` (bump map + `_notices` list), `rewrite_pins(text, bumps: dict[str, str]) -> str`; CLI `--check` (print JSON plan) and `--apply <path> --summary-out <md>`.

- [ ] **Step 1: failing tests** (`tests/test_check_upstream.py`, importlib-by-path pattern):

```python
import importlib.util
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "scripts/check_upstream.py"
_spec = importlib.util.spec_from_file_location("check_upstream", SRC)
cu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cu)

PINS = (
    'shairport_major: "4"\n'
    'shairport_sync_version: "4.3.7"\n'
    'shairport_sync_commit: "aaaa111"\n'
    'nqptp_version: "1.2.8"\n'
    'nqptp_commit: "bbbb222"\n'
)


def test_parse_pins():
    p = cu.parse_pins(PINS)
    assert p["shairport_sync_version"] == "4.3.7"
    assert p["shairport_major"] == "4"


def test_plan_bumps_minor_within_major():
    plan = cu.plan_bumps(cu.parse_pins(PINS),
                         {"shairport-sync": "4.3.8", "nqptp": "1.2.9"})
    assert plan["shairport_sync_version"] == {"from": "4.3.7", "to": "4.3.8"}
    assert plan["nqptp_version"] == {"from": "1.2.8", "to": "1.2.9"}


def test_plan_bumps_never_crosses_major():
    plan = cu.plan_bumps(cu.parse_pins(PINS),
                         {"shairport-sync": "5.0.4", "nqptp": "1.2.8"})
    assert "shairport_sync_version" not in plan
    assert any("major" in n for n in plan["_notices"])


def test_plan_bumps_noop_and_v_prefix():
    plan = cu.plan_bumps(cu.parse_pins(PINS),
                         {"shairport-sync": "v4.3.7", "nqptp": "1.2.8"})
    assert plan == {"_notices": []}


def test_rewrite_pins_roundtrip():
    out = cu.rewrite_pins(PINS, {"nqptp_version": "1.2.9", "nqptp_commit": "cccc333"})
    assert 'nqptp_version: "1.2.9"' in out
    assert 'nqptp_commit: "cccc333"' in out
    assert 'shairport_sync_version: "4.3.7"' in out
```

- [ ] **Step 2: run → FAIL. Implement `scripts/check_upstream.py`** — pure core:

```python
def _vtuple(tag: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", tag))


def parse_pins(text: str) -> dict:
    return dict(re.findall(r'^([a-z_]+): "([^"]*)"', text, re.M))


def plan_bumps(current: dict, latest: dict) -> dict:
    plan = {"_notices": []}
    sps = latest.get("shairport-sync", "").lstrip("v")
    if sps:
        if str(_vtuple(sps)[0]) != current["shairport_major"]:
            if _vtuple(sps) > _vtuple(current["shairport_sync_version"]):
                plan["_notices"].append(
                    f"shairport-sync {sps} available but crosses major "
                    f"{current['shairport_major']}->{_vtuple(sps)[0]}; not auto-bumped")
        elif _vtuple(sps) > _vtuple(current["shairport_sync_version"]):
            plan["shairport_sync_version"] = {"from": current["shairport_sync_version"], "to": sps}
    nq = latest.get("nqptp", "").lstrip("v")
    if nq and _vtuple(nq) > _vtuple(current["nqptp_version"]):
        plan["nqptp_version"] = {"from": current["nqptp_version"], "to": nq}
    return plan


def rewrite_pins(text: str, new_values: dict) -> str:
    for key, value in new_values.items():
        text = re.sub(rf'^{key}: "[^"]*"', f'{key}: "{value}"', text, flags=re.M)
    return text
```

I/O layer (network only in `main()`): `urllib.request` GET `https://api.github.com/repos/mikebrady/<repo>/releases/latest` with `Authorization: Bearer $GITHUB_TOKEN` when set; treat 404 as "no data, skip". Tag→commit resolution for the `_commit` vars: GET `/git/ref/tags/<tag>`; if `object.type == "tag"` (annotated) follow `/git/tags/<sha>` to the commit (mikebrady mixes lightweight and annotated tags). `--apply` maps each planned version bump to `{key: to, key.replace('_version','_commit'): resolved_sha}` and rewrites; `--summary-out` writes a markdown table (old→new, tag→SHA lines, release-notes links, notices).

- [ ] **Step 3: run tests → PASS.**
- [ ] **Step 4: `.github/workflows/version-bump.yml`:**

```yaml
name: version-bump
on:
  schedule:
    - cron: "17 6 * * 1"   # Mondays 06:17 UTC, off the :00 herd
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
jobs:
  bump:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Check upstream and rewrite pins
        id: bump
        env:
          GITHUB_TOKEN: ${{ github.token }}   # API rate limit only
        run: |
          python scripts/check_upstream.py --apply roles/airplay/defaults/main.yml \
            --summary-out /tmp/bump-summary.md
          echo "changed=$(git diff --quiet && echo false || echo true)" >> "$GITHUB_OUTPUT"
      - uses: peter-evans/create-pull-request@v7
        if: steps.bump.outputs.changed == 'true'
        with:
          token: ${{ secrets.VERSION_BUMP_TOKEN }}
          branch: ci/version-bump
          commit-message: "chore: bump upstream version pins"
          title: "chore: bump shairport-sync/nqptp pins"
          body-path: /tmp/bump-summary.md
```

- [ ] **Step 5: README one-time setup note** (the trap that makes or breaks this): PRs created with the default `GITHUB_TOKEN` **do not trigger CI workflows** — the bump PR would show zero checks. Create a fine-grained PAT (this repo; Contents RW + Pull requests RW), store as secret `VERSION_BUMP_TOKEN`, note its expiry as a maintenance item; also enable *Settings → Actions → General → Allow GitHub Actions to create and approve pull requests*. Pipeline composition note: merging the bump PR touches `defaults/main.yml`, which triggers the `debs` workflow via its `paths:` filter → new release tag → fleet rollout via `-e airplay_install_method=deb`.
- [ ] **Step 6: `make check`; commit** — `feat(ci): weekly upstream version-bump PRs (stdlib checker, SHA-resolved pins)`

### Task 11: Docs sweep + end-to-end verification

- [ ] **Step 1: README Repository Layout** — add `ci/`, `scripts/`, the two new workflows; Rollout Runbook step 2 note: CI now runs the container converge automatically. ARCHITECTURE: install-method section, health-timer default, doctor badge, deb pipeline diagram (bump PR → CI converge → merge → debs release → fleet).
- [ ] **Step 2: Full local verification:**

```bash
make check                     # lint + all pytest + syntax-check
.venv/bin/pytest -v            # expect: all suites green incl. new tests
bash -n ci/build-debs.sh
```

- [ ] **Step 3: Push and verify all three workflows on GitHub:** `ci.yml` (lint-test + converge, idempotence gate green), `debs.yml` (release `debs-shairport4.3.7-nqptp1.2.8-r1` exists with 4 assets; smoke converge green), `version-bump.yml` via `workflow_dispatch` (expect either a no-op or a PR flagging the 4→5 major availability as a notice).
- [ ] **Step 4: Real-box verification (operator, after merge):** on the spare box — `ansible-playbook site.yml -l spare-box -e airplay_install_method=deb`, then `airplay-doctor --check`, `airplay-doctor --deep` (probe reports the real device), dashboard shows the doctor badge after ≤30 min or after `systemctl start airplay-health`.
- [ ] **Step 5: Commit** — `docs: architecture + runbook for deb pipeline, converge CI, health badge`

---

## Verification (whole plan)

1. `make check` green at every task boundary.
2. GitHub Actions: `converge` job proves run-2 `changed=0` (the README's idempotence claim becomes a regression test); `debs` workflow proves the packages install and the role converges over the deb path in a clean Debian 13 systemd container.
3. `pytest -v`: doctor deep-probe pass/fail cases, journal scoping, dashboard doctor parsing, bump-planner rules (major guard, v-prefix, no-op) all covered.
4. Spare box (hardware, operator-run): deb-path converge + `--deep` probe + dashboard badge + AirPlay pairing per the existing README matrix — CI cannot cover audio/sync; the runbook still gates production on the spare box.

## Task order & dependencies

1→2→3→4→5 (independent small fixes, any order, 5 before 7) → 6 (container recipe) → 7 (debs, uses 5's SHAs + 6's recipe) → 8 (role deb path, uses 7's tag scheme) → 9 (independent, any time after 4) → 10 (uses 5's `_commit` vars) → 11 (last).
