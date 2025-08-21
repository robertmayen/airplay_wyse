# AirPlay Wyse (Minimal)

Minimal GitOps-driven AirPlay 2 receiver for Wyse 5070 + USB DAC.

See `docs/OPERATIONS.md` for installation, tagging, health, and rollback guidance.

Directory essentials:
- `bin/`: `reconcile`, `update`, `converge`, `health`, `diag`, `airplay-sd-run` (install to `/usr/local/sbin/airplay-sd-run`).
- `cfg/`: minimal templates for `shairport-sync`, Avahi, and (optionally) nqptp.
- `systemd/`: `reconcile.service/.timer`, `converge.service`, and necessary overrides.
- `inventory/`: `hosts/example.yml` (optional overrides for name/NIC/ALSA).
- `tests/`: `smoke.sh` (mockable). 

This repository intentionally omits on-device builds and auxiliary tooling to keep hosts immutable-ish and the operational path simple.

## Notes
- Debian 13 preferred (APT provides AirPlay2-capable `shairport-sync` and `nqptp`).
- Privileged actions use a single wrapper (`/usr/local/sbin/airplay-sd-run`).

## 🛠️ Installation

### Option A: Automated Provisioning (Recommended)

From your controller machine (Mac/Linux):

```bash
# 1. Clone this repository
git clone git@github.com:robertmayen/airplay_wyse.git
cd airplay_wyse

# 2. Configure device IPs
export WYSE_DAC_IP="192.168.8.71"
export WYSE_SONY_IP="192.168.8.72"

# 3. Seed SSH keys (avoid host key warnings)
scripts/ops/seed-known-hosts.sh \
  wyse-dac=$WYSE_DAC_IP \
  wyse-sony=$WYSE_SONY_IP

# 4. Provision devices automatically
SSH_USER=$USER scripts/ops/provision-hosts.sh \
  wyse-dac=$WYSE_DAC_IP \
  wyse-sony=$WYSE_SONY_IP
```

### Option B: Manual Installation

On each Wyse device:

```bash
# 1. Create airplay user
sudo useradd -m -s /bin/bash airplay
sudo usermod -aG audio airplay

# 2. Clone repository
sudo mkdir -p /opt/airplay_wyse
sudo chown airplay:airplay /opt/airplay_wyse
sudo -u airplay git clone https://github.com/robertmayen/airplay_wyse.git /opt/airplay_wyse

# 3. Install sudoers policy
sudo cp /opt/airplay_wyse/security/sudoers/airplay-wyse /etc/sudoers.d/
sudo visudo -cf /etc/sudoers.d/airplay-wyse

# 4. Install privilege wrapper
sudo cp /opt/airplay_wyse/scripts/airplay-sd-run /usr/local/sbin/
sudo chmod 755 /usr/local/sbin/airplay-sd-run
sudo chown root:root /usr/local/sbin/airplay-sd-run

# 5. Install systemd units
sudo cp /opt/airplay_wyse/systemd/reconcile.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now reconcile.timer

# 6. Configure device inventory
cd /opt/airplay_wyse
cp inventory/hosts/wyse-dac.yml inventory/hosts/$(hostname -s).yml
# Edit the file to match your device
```

## 🎵 Configuration

### Basic Configuration

Each device needs an inventory file at `inventory/hosts/$(hostname).yml`:

```yaml
# inventory/hosts/wyse-livingroom.yml
airplay_name: "Living Room"     # Name shown in AirPlay picker
nic: enp3s0                      # Network interface
target_tag: null                 # null = use latest, or pin to specific version
```

### Advanced Audio Configuration

For specific USB DACs:

```yaml
airplay_name: "HiFi System"
nic: enp3s0
alsa:
  vendor_id: "0x08bb"           # USB vendor ID (from lsusb)
  product_id: "0x2902"          # USB product ID
  serial: "12345"               # Optional: specific device serial
  device_num: 0                 # ALSA device number
  mixer: "PCM"                  # Mixer control name
```

## 🚀 Deployment

### Creating a Release

```bash
# 1. Update version
echo "0.3.0" > VERSION

# 2. Update changelog
vim CHANGELOG.md  # Document changes

# 3. Commit and tag
git add -A
git commit -m "Release v0.3.0: Description"
git tag -s v0.3.0 -m "Release v0.3.0

Changes:
- Feature X
- Bug fix Y

Tested on: wyse-dac, wyse-sony"

# 4. Push release
git push origin main
git push origin v0.3.0
```

Devices automatically pull and apply updates every 10 minutes.

### Canary Deployments

Test on one device before fleet-wide rollout:

```bash
# 1. Create canary tag
git tag -s v0.3.0-canary -m "Canary: v0.3.0"
git push origin v0.3.0-canary

# 2. Pin canary device
# In inventory/hosts/wyse-test.yml:
target_tag: v0.3.0-canary

# 3. Monitor for 24-48 hours
ssh airplay@wyse-test
journalctl -u reconcile -f

# 4. Promote to production
git tag -s v0.3.0 -m "Release v0.3.0"
git push origin v0.3.0
# Remove target_tag from canary device
```

## 🔍 Monitoring & Troubleshooting

### Check System Health

```bash
# Quick health check
./bin/health

# Detailed diagnostics
./bin/diag

# View logs
journalctl -u reconcile -n 100

# Watch live logs
journalctl -u reconcile -f
```

### Common Issues

#### Device Not Visible in AirPlay

```bash
# Check if services are running
systemctl status shairport-sync avahi-daemon nqptp

# Verify network advertisements
avahi-browse -rt _raop._tcp
avahi-browse -rt _airplay._tcp

# Check firewall (ports needed)
# - 5353/udp (mDNS)
# - 319-320/udp (NQPTP for AirPlay 2)
# - 3689/tcp, 5000-5005/tcp (AirPlay)
```

#### No Audio Output

```bash
# Check audio devices
aplay -l
cat /proc/asound/cards

# Test speakers
speaker-test -c 2 -t wav

# Check mixer settings
alsamixer  # Look for muted channels (MM)

# Force audio re-detection
rm /var/lib/airplay_wyse/hashes/alsa-state
sudo systemctl start reconcile
```

#### AirPlay 2 Not Working

```bash
# Verify AirPlay 2 support
shairport-sync -V | grep -E "AirPlay 2|RAOP2|NQPTP"

# Check NQPTP service
systemctl status nqptp

# Force rebuild if needed
rm -rf /var/tmp/nqptp-build*
sudo systemctl start reconcile
```

## 🏗️ Architecture

### System Components

```
┌─────────────────┐
│ reconcile.timer │──every 10min──►┌──────────────────┐
└─────────────────┘                 │reconcile.service │
                                    └──────────────────┘
                                            │
                                            ▼
                                    ┌──────────────┐
                                    │ bin/reconcile│
                                    └──────────────┘
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    ▼                                               ▼
            ┌──────────────┐                               ┌──────────────┐
            │  bin/update  │                               │ bin/converge │
            └──────────────┘                               └──────────────┘
            (fetch & verify tags)                          (apply configs)
                                                                   │
                                                                   ▼
                                                        ┌──────────────────┐
                                                        │airplay-sd-run    │
                                                        │(privilege wrapper)│
                                                        └──────────────────┘
```

### Security Model

- **Least Privilege**: Agent runs as unprivileged `airplay` user
- **Controlled Escalation**: Fixed capability profiles via systemd-run
- **No Direct Sudo**: Only specific actions through wrapper script
- **Sandboxed Operations**: Each privileged action in isolated transient unit

### Key Features

- **GitOps Workflow**: Push tag → Devices auto-update
- **AirPlay 2 Support**: Multi-room sync with NQPTP
- **Auto-detection**: USB DACs preferred, fallback to onboard
- **Self-healing**: Automatic package installation and service recovery
- **Idempotent**: Only applies necessary changes
- **Observable**: Comprehensive logging and health monitoring

## 📚 Documentation

- **[AGENTS.md](AGENTS.md)** - Complete operations and architecture guide
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** - Development workflow and coding guide
- **[docs/runbook.md](docs/runbook.md)** - Operational procedures
- **[docs/troubleshooting.md](docs/troubleshooting.md)** - Problem-solving guide
- **[GITOPS_IMPLEMENTATION.md](GITOPS_IMPLEMENTATION.md)** - GitOps architecture details
- **[SOURCE_BUILD_FIXES.md](SOURCE_BUILD_FIXES.md)** - Build system documentation

## 🧪 Testing

```bash
# Run all tests
make test

# Check shell scripts
shellcheck bin/*

# Test converge (VM only!)
./bin/converge --dry-run

# Health check
./bin/health
```

## 📁 Project Structure

```
airplay_wyse/
├── bin/              # Core operational scripts
├── cfg/              # Configuration templates
├── docs/             # Documentation
├── inventory/        # Per-device configuration
├── pkg/              # Package building scripts
├── scripts/          # Utility and provisioning scripts
├── security/         # Security policies
├── systemd/          # Service definitions
└── tests/            # Test suite
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Test thoroughly in a VM
4. Commit changes: `git commit -m 'feat: add amazing feature'`
5. Push branch: `git push origin feature/amazing-feature`
6. Open a Pull Request

## 📝 License

This project is maintained by Robert Mayen. See LICENSE file for details.

## 🆘 Support

- **Quick Help**: Run `./bin/diag` and share output
- **Issues**: File via [GitHub Issues](https://github.com/robertmayen/airplay_wyse/issues)
- **Logs**: `journalctl -u reconcile -n 500`
- **Emergency**: See Quick Start section for recovery commands

---

**Remember**: Always test changes in a VM first! Production devices auto-update from git tags.
