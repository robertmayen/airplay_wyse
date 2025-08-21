# AirPlay Wyse - Complete Development & Operations Guide

## Table of Contents
1. [Quick Reference](#quick-reference)
2. [Project Overview](#project-overview)
3. [Architecture Deep Dive](#architecture-deep-dive)
4. [Development Workflow](#development-workflow)
5. [Operations Guide](#operations-guide)
6. [Troubleshooting Playbook](#troubleshooting-playbook)
7. [Security Model](#security-model)
8. [Common Tasks & Examples](#common-tasks--examples)

---

## Quick Reference

### Emergency Commands
```bash
# Stop all updates (kill switch)
sudo touch /etc/airplay_wyse/hold  # or /var/lib/airplay_wyse/hold

# Force immediate reconcile
sudo systemctl start reconcile.service

# Check system health
./bin/health

# Quick diagnostics
./bin/diag

# View recent logs
journalctl -u reconcile.service -n 100

# Rollback to previous version
./bin/rollback v0.2.0  # replace with desired version
```

### Key Paths
| Path | Purpose |
|------|---------|
| `/opt/airplay_wyse` | Main repository location on devices |
| `/var/lib/airplay_wyse` | State files (hashes, health snapshots) |
| `/etc/shairport-sync.conf` | Main AirPlay configuration |
| `/etc/avahi/avahi-daemon.conf.d/` | Avahi service discovery configs |
| `/usr/local/sbin/airplay-sd-run` | Privilege escalation wrapper |

### Exit Codes Reference
| Code | Meaning | Action Required |
|------|---------|-----------------|
| 0 | OK | None - system healthy |
| 2 | CHANGED | Normal - changes applied |
| 3 | DEGRADED | Check health output for issues |
| 4 | INVALID_INPUT | Fix inventory/config |
| 5 | VERIFY_FAILED | Import GPG key or fix signature |
| 6 | HELD | Remove hold file to resume |
| 10 | PKG_ISSUE | Check package installation logs |
| 11 | SYSTEMD_ERR | Check systemd unit status |

---

## Project Overview

This is a GitOps-driven AirPlay audio streaming solution for Wyse thin clients. The system automatically:
- Detects and configures audio hardware (USB DACs preferred)
- Enables AirPlay 2 with multi-room sync support
- Self-updates from git tags with zero manual intervention
- Runs with least-privilege security model

### Core Components

1. **Agent (`airplay` user)**: Unprivileged orchestrator that manages configuration
2. **Privilege Wrapper**: `/usr/local/sbin/airplay-sd-run` for controlled root actions
3. **Reconciliation Loop**: Timer-driven update → converge cycle
4. **Health Monitoring**: Automatic detection of AirPlay visibility issues

---

## Architecture Deep Dive

### System Flow Diagram
```
┌─────────────────┐
│ reconcile.timer │ ──triggers every 10min──►
└─────────────────┘
                ▼
┌──────────────────┐
│reconcile.service │ (runs as 'airplay' user)
└──────────────────┘
                ▼
        ┌──────────────┐
        │ bin/reconcile│
        └──────────────┘
                ▼
    ┌───────────────────────┐
    │  1. bin/update        │ (fetch tags, verify, checkout)
    │  2. bin/converge      │ (apply configuration)
    └───────────────────────┘
                ▼
        [Privilege Escalation]
                ▼
    ┌────────────────────────┐
    │ airplay-sd-run wrapper │ (maps to systemd-run profiles)
    └────────────────────────┘
                ▼
    ┌────────────────────────┐
    │  Transient Units:      │
    │  - cfg-write           │ (write configs)
    │  - pkg-ensure          │ (install packages)
    │  - unit-write          │ (systemd units)
    │  - svc-restart         │ (restart services)
    └────────────────────────┘
```

### Converge Phases (Detailed)

1. **Guards Phase**
   - Check for hold file → exit 6 if present
   - Verify time sync → warn if drift > 1 day
   - Validate inventory → exit 4 if malformed
   - Verify git tag signature → exit 5 if untrusted

2. **Inventory Phase**
   ```bash
   # Derives from inventory/hosts/$(hostname -s).yml:
   AIRPLAY_NAME="Living Room"     # or defaults to hostname
   AVAHI_IFACE="enp3s0"           # network interface
   ALSA_VENDOR="0x08bb"           # USB vendor ID (optional)
   ALSA_PRODUCT="0x2902"          # USB product ID (optional)
   ```

3. **ALSA Detection Phase**
   ```bash
   # Preference order:
   1. USB devices (if vendor/product match inventory)
   2. First available playback device
   3. Validates by opening PCM briefly
   4. Finds mixer control (PCM, Master, Digital, etc.)
   5. Sets volume to 80% and unmutes
   ```

4. **Template Rendering Phase**
   - Processes `cfg/*.tmpl` files
   - Substitutes variables: `{{AIRPLAY_NAME}}`, `{{ALSA_DEVICE}}`, etc.
   - Computes hashes to detect changes

5. **Package Management Phase**
   ```bash
   # APT-first, source-fallback pattern:
   if ! apt-get install -y nqptp; then
       echo "Building from source..."
       build_nqptp_from_source
   fi
   ```

6. **Service Orchestration Phase**
   - Deploys configs via `cfg-write` profile
   - Installs systemd drop-ins via `unit-write`
   - Restarts services via `svc-restart`
   - Uses wrapper units for safety

7. **Health Check Phase**
   - Verifies AirPlay 2 support: `shairport-sync -V | grep RAOP2`
   - Checks nqptp status: `systemctl is-active nqptp`
   - Validates Avahi advertisements
   - Writes `/var/lib/airplay_wyse/last-health.json`

---

## Development Workflow

### Setting Up Development Environment

1. **Clone and Branch**
   ```bash
   git clone git@github.com:robertmayen/airplay_wyse.git
   cd airplay_wyse
   git checkout -b feature/your-feature
   ```

2. **Test in VM First**
   ```bash
   # Use a Debian VM to avoid breaking production
   vagrant up  # or your preferred VM solution
   ```

3. **Make Changes**
   - Edit configs in `cfg/`
   - Modify scripts in `bin/`
   - Update inventory in `inventory/hosts/`

4. **Local Testing**
   ```bash
   make test           # Run CI checks locally
   ./bin/converge      # Test converge logic (VM only!)
   ./bin/health        # Check health output
   ```

### Common Development Tasks

#### Adding a New Configuration Template
1. Create template: `cfg/myconfig.conf.tmpl`
2. Use variables: `{{AIRPLAY_NAME}}`, `{{ALSA_DEVICE}}`
3. Add rendering logic to `bin/converge`
4. Test deployment path

#### Modifying ALSA Detection
1. Edit `detect_alsa()` function in `bin/converge`
2. Test with various USB DACs
3. Verify mixer detection works

#### Adding New Package
1. Update `ensure_packages()` in `bin/converge`
2. Add to build dependencies if needed
3. Test both APT and source paths

### Release Process

1. **Update Version**
   ```bash
   echo "0.3.0" > VERSION
   ```

2. **Update Changelog**
   ```bash
   # Add entry to CHANGELOG.md
   ## [0.3.0] - 2025-01-21
   ### Added
   - Feature X
   ### Fixed
   - Bug Y
   ```

3. **Create Signed Tag**
   ```bash
   git add -A
   git commit -m "Release v0.3.0: Brief description"
   git tag -s v0.3.0 -m "Release v0.3.0
   
   Changes:
   - Feature X added
   - Bug Y fixed
   
   Tested on: wyse-dac, wyse-sony"
   ```

4. **Push Release**
   ```bash
   git push origin main
   git push origin v0.3.0
   ```

---

## Operations Guide

### Initial Device Setup

1. **Controller Machine Setup** (your Mac/Linux box)
   ```bash
   # Seed SSH known hosts
   scripts/ops/seed-known-hosts.sh \
     wyse-dac=192.168.8.71 \
     wyse-sony=192.168.8.72
   
   # Provision devices
   SSH_USER=$USER scripts/ops/provision-hosts.sh \
     wyse-dac=192.168.8.71 \
     wyse-sony=192.168.8.72
   ```

2. **Device Verification**
   ```bash
   ssh airplay@wyse-dac
   cd /opt/airplay_wyse
   ./bin/health
   ```

### Canary Deployments

1. **Tag Canary Release**
   ```bash
   git tag -s v0.3.0-canary -m "Canary: v0.3.0"
   git push origin v0.3.0-canary
   ```

2. **Configure Canary Host**
   ```yaml
   # inventory/hosts/wyse-dac.yml
   airplay_name: "DAC Canary"
   target_tag: v0.3.0-canary  # Pin to canary
   nic: enp3s0
   ```

3. **Monitor Canary** (24-72 hours)
   ```bash
   ssh airplay@wyse-dac
   journalctl -u reconcile -f
   ./bin/health
   ```

4. **Promote to Production**
   ```bash
   # Remove target_tag from inventory
   git tag -s v0.3.0 -m "Release v0.3.0"
   git push origin v0.3.0
   ```

### Monitoring & Alerting

#### Key Metrics to Watch
- Reconcile success rate
- Health check status
- Service restart frequency
- ALSA device stability

#### Log Analysis
```bash
# Check reconcile patterns
journalctl -u reconcile --since "1 week ago" | \
  grep -E "exit_code|health_status"

# Find errors
journalctl -u reconcile -p err

# Track config changes
journalctl -u 'airplay-*' | grep cfg-write
```

---

## Troubleshooting Playbook

### Issue: Device Not Visible in AirPlay

**Symptoms**: iPhone/Mac doesn't show device

**Diagnosis**:
```bash
# 1. Check Avahi advertisements
avahi-browse -rt _raop._tcp
avahi-browse -rt _airplay._tcp

# 2. Verify services running
systemctl status shairport-sync
systemctl status avahi-daemon
systemctl status nqptp  # For AirPlay 2

# 3. Check network interface
ip addr show $(grep nic inventory/hosts/$(hostname -s).yml | cut -d: -f2)
```

**Solutions**:
1. Restart services: `sudo systemctl restart reconcile`
2. Check firewall: Ensure ports 5353 (mDNS), 319-320 (NQPTP) open
3. Verify network: Same subnet as client device

### Issue: No Audio Output

**Symptoms**: Device visible but no sound

**Diagnosis**:
```bash
# 1. Check ALSA device
aplay -l
cat /proc/asound/cards

# 2. Test audio directly
speaker-test -c 2 -t wav

# 3. Check mixer settings
alsamixer  # Look for muted channels (MM)
```

**Solutions**:
1. Force ALSA re-detection: `rm /var/lib/airplay_wyse/hashes/alsa-state && sudo systemctl start reconcile`
2. Override in inventory:
   ```yaml
   alsa:
     vendor_id: "0x08bb"
     product_id: "0x2902"
     mixer: "PCM"
   ```

### Issue: AirPlay 2 Not Working

**Symptoms**: No multi-room sync option

**Diagnosis**:
```bash
# Check if RAOP2 compiled in
shairport-sync -V | grep -E "AirPlay 2|RAOP2|NQPTP"

# Check nqptp service
systemctl status nqptp
ss -ulnp | grep -E "319|320"  # NQPTP ports
```

**Solutions**:
1. Force rebuild: `rm -rf /var/tmp/nqptp-build* && sudo systemctl start reconcile`
2. Check build logs: `journalctl -u reconcile | grep -A10 "Building nqptp"`

### Issue: Updates Not Applying

**Symptoms**: Old version persists

**Diagnosis**:
```bash
# 1. Check for hold
ls -la /etc/airplay_wyse/hold /var/lib/airplay_wyse/hold

# 2. Verify git status
cd /opt/airplay_wyse
git status
git describe --tags

# 3. Check update logs
journalctl -u reconcile | grep -E "Fetching|Selecting|Checking out"
```

**Solutions**:
1. Remove hold: `sudo rm -f /etc/airplay_wyse/hold`
2. Force update: `cd /opt/airplay_wyse && git fetch --tags --force && ./bin/update`
3. Clean git state: `git reset --hard && git clean -fdx`

---

## Security Model

### Privilege Escalation

The system uses a wrapper script for all privileged operations:

```bash
# /usr/local/sbin/airplay-sd-run
# Maps capability profiles to systemd-run with strict sandboxing

Profiles:
- cfg-write:   Write to /etc only
- pkg-ensure:  Package management
- unit-write:  Systemd unit files
- svc-restart: Service control

Example:
sudo /usr/local/sbin/airplay-sd-run cfg-write -- \
  cp /tmp/config /etc/shairport-sync.conf
```

### Sudoers Configuration

```sudoers
# /etc/sudoers.d/airplay-wyse
airplay ALL=(root) NOPASSWD: /usr/local/sbin/airplay-sd-run *
```

### GPG Signing

All releases must be signed:
```bash
# Import maintainer key on devices
gpg --import maintainer-public.key

# Sign tags
git tag -s v0.3.0 -m "Signed release"
```

---

## Common Tasks & Examples

### Task: Add New Audio Device Support

```bash
# 1. Identify device
lsusb  # Note vendor:product IDs

# 2. Update inventory
cat >> inventory/hosts/wyse-new.yml <<EOF
airplay_name: "New Device"
nic: enp3s0
alsa:
  vendor_id: "0x1234"
  product_id: "0x5678"
  mixer: "PCM"
EOF

# 3. Test
./bin/converge
```

### Task: Debug Failed Converge

```bash
# Quick diagnosis
./bin/diag-converge

# Detailed investigation
journalctl -u converge -n 500 | less
grep -E "ERROR|FAILED" /var/lib/airplay_wyse/last-health.txt

# Manual converge with debug
bash -x ./bin/converge 2>&1 | tee debug.log
```

### Task: Emergency Recovery

```bash
# If converge is completely broken
cd /opt/airplay_wyse
git fetch origin
git reset --hard origin/main
git clean -fdx

# Reinstall core packages
sudo apt-get install --reinstall shairport-sync avahi-daemon

# Restart from scratch
sudo systemctl restart reconcile
```

### Task: Performance Tuning

```yaml
# inventory/hosts/wyse-optimized.yml
airplay_name: "Optimized"
nic: enp3s0
alsa:
  buffer_size: 4096  # Increase for stability
  period_size: 1024
shairport:
  latency: 88200     # 2 seconds for poor networks
  volume_range: 30   # Finer volume control
```

---

## Appendix: File Structure Reference

```
airplay_wyse/
├── bin/                    # Operational scripts
│   ├── bootstrap          # Initial setup (rarely used)
│   ├── converge          # Main configuration engine
│   ├── diag              # Diagnostics collector
│   ├── diag-converge     # Converge-specific diagnostics
│   ├── health            # Health check reporter
│   ├── reconcile         # Wrapper: update + converge
│   ├── rollback          # Version rollback tool
│   └── update            # Git tag fetcher/selector
├── cfg/                   # Configuration templates
│   ├── shairport-sync.conf.tmpl
│   ├── nqptp.conf.tmpl
│   └── avahi/
│       └── avahi-daemon.conf.d/
│           └── airplay-wyse.conf.tmpl
├── docs/                  # Documentation
│   ├── runbook.md        # Operations guide
│   ├── troubleshooting.md # Problem solving
│   └── RELEASE.md        # Release procedures
├── inventory/            # Per-host configuration
│   ├── schema.yml       # Configuration schema
│   └── hosts/
│       ├── wyse-dac.yml
│       └── wyse-sony.yml
├── pkg/                  # Package building
│   ├── build-nqptp.sh   # NQPTP builder
│   ├── build-shairport-sync.sh # Shairport builder
│   ├── install.sh       # Package installer
│   └── versions.sh      # Version definitions
├── scripts/             # Utility scripts
│   ├── airplay-sd-run   # Privilege wrapper
│   └── ops/
│       ├── provision-hosts.sh
│       └── seed-known-hosts.sh
├── security/            # Security policies
│   └── sudoers/
│       └── airplay-wyse # Sudoers drop-in
├── systemd/             # Service definitions
│   ├── reconcile.service
│   ├── reconcile.timer
│   └── overrides/       # Service customizations
└── tests/               # Test suite
    ├── smoke.sh        # Basic functionality
    └── no_sudo.sh      # Security compliance
```

---

## Contact & Support

- **Primary Maintainer**: Robert Mayen
- **Repository**: github.com/robertmayen/airplay_wyse
- **Issues**: File via GitHub Issues
- **Emergency**: Check AGENTS.md Quick Reference section

Remember: When in doubt, run `./bin/diag` and share the output!
