# AirPlay Wyse

Turns a Wyse 5070 (or any small Debian 13 box with a USB DAC) into an AirPlay 2 endpoint.
Managed entirely by Ansible — no on-device Python CLI, no boot-time oneshots.

## Prerequisites

- Control machine with Python 3.11+ and Ansible.
- SSH access (key-based, passwordless sudo preferred) to every target box.
- Install dev dependencies (yamllint, ansible-lint, pytest, etc.):

  ```bash
  pip install -r requirements-dev.txt
  ```

## Inventory and host_vars

Edit `inventory/hosts.yml` to list your boxes under the `airplay` group:

```yaml
airplay:
  hosts:
    living-room:
      ansible_host: 192.168.1.10
    kitchen:
      ansible_host: 192.168.1.11
```

Create a `host_vars/<hostname>.yml` for each box with at minimum:

```yaml
airplay_name: "Living Room"
airplay_alsa_card: "hw:1,0"   # output of: aplay -L | grep ^hw:
```

Discover the correct card value on the target:

```bash
aplay -L
```

Pick the `hw:<N>,<M>` line that corresponds to your USB DAC.

## Rollout Runbook

### 1. Capture baseline on the existing working box

Run these commands on a box that is already working (or the box you are about to provision):

```bash
shairport-sync -V
cat /etc/os-release
cat /etc/shairport-sync.conf
cat /etc/asound.conf
```

Compare the reported shairport version against `shairport_sync_version` in
`group_vars/airplay.yml`. If they differ, update `shairport_sync_version` in
`group_vars/airplay.yml` to match what is installed, or pin to `4.3.7`
(the tested version) for consistency across the fleet.

### 2. Build / syntax smoke — VM or container (optional)

Verify the playbook parses and the from-source build completes:

```bash
ansible-playbook --syntax-check site.yml migration.yml doctor.yml
ansible-playbook site.yml -l <vm-or-container>
```

**Note:** AirPlay 2 timing relies on NQPTP's UDP 319/320 and precise clock
synchronisation. VMs and containers are **not valid** for audio, sync, or
pairing tests. Use this stage only to catch build errors and role logic.

### 3. Physical spare box — hardening, audio, and sync matrix

Before touching any production box, run the full role on a spare physical machine
and verify every item in the matrix:

```bash
ansible-playbook site.yml -l spare-box
```

Matrix checklist:

- [ ] `systemctl is-active shairport-sync` → active
- [ ] AirPlay 2 pairing survives `systemctl restart shairport-sync`
- [ ] DAC plays: `aplay -D hw:<N>,<M> /usr/share/sounds/alsa/Front_Center.wav`
- [ ] `airplay-doctor --check` exits 0
- [ ] Real audio stream syncs with at least one other AirPlay 2 speaker on the network

Do not proceed to production until all items are green.

### 4. Working-box cutover

For each box currently running the **old** Python/shell stack:

```bash
# Clean up legacy state, units, and libexec bundle
ansible-playbook migration.yml -l <working-box>

# Apply the Ansible role
ansible-playbook site.yml -l <working-box>

# Verify
ansible-playbook doctor.yml -l <working-box>
# or on the box:
airplay-doctor --check
```

The migration playbook removes `/var/lib/airplay_wyse/`, `/usr/local/libexec/airplay_wyse/`,
and the legacy systemd units before the role takes over.

### 5. Roll to remaining boxes

After the first production cutover is confirmed stable, repeat step 4 for every
remaining box, then run the fleet-wide doctor:

```bash
ansible-playbook site.yml
ansible-playbook doctor.yml
```

`doctor.yml` also checks for duplicate AirPlay device IDs across the fleet —
fix any duplicates by setting `airplay_device_id` in the relevant `host_vars/`.

## Day-2 Operations

### Updating shairport-sync version

1. Bump `shairport_sync_version` (and `shairport_sync_sha256`) in `group_vars/airplay.yml`.
2. Re-run `site.yml` against the spare box first (step 3 above).
3. Roll to the fleet once the spare-box matrix is green.

### Drift correction

Re-run `site.yml` — the role is fully idempotent:

```bash
ansible-playbook site.yml
```

### Major-version opt-in (5.x)

`shairport_major: "5"` is an explicit opt-in in `group_vars/airplay.yml`.
It **must** pass the full spare-box matrix (step 3) before being applied to
any production box. 5.x changes the DACP/RTSP session model; verify pairing,
sync, and audio stability before rolling out.

### Health check

```bash
ansible-playbook doctor.yml
# or on the box:
airplay-doctor --check
airplay-doctor --deep --json   # extended probe (opens ALSA device)
```

## Repository Layout

```
airplay_wyse/
├── inventory/          # hosts.yml + host_vars/
├── group_vars/         # airplay.yml (version pins, build flags)
├── roles/
│   └── airplay/        # from-source build, config, hardened systemd, doctor
│       ├── defaults/   # all tunable variables
│       ├── tasks/      # install → build → configure → units → doctor
│       ├── templates/  # shairport-sync.conf.j2, unit overrides
│       └── handlers/   # daemon-reload + service restart
├── site.yml            # full provisioning (converge)
├── migration.yml       # one-time cleanup of the old Python/shell stack
├── doctor.yml          # non-invasive fleet health + duplicate-id check
├── docs/               # ARCHITECTURE.md, OPERATIONS.md
└── tests/              # pytest suite for airplay-doctor parsers
```

## Linting and Testing

```bash
make lint    # yamllint + ansible-lint
make test    # pytest (airplay-doctor parser tests)
make check   # lint + test + syntax-check all playbooks
```
