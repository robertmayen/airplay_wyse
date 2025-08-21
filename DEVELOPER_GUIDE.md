# Developer Guide - AirPlay Wyse

## Quick Start for Developers

### Prerequisites
- Git with SSH key configured
- Basic understanding of Bash scripting
- Familiarity with systemd units
- Knowledge of ALSA audio system (helpful)
- Debian/Ubuntu development environment

### Setting Up Your Development Environment

```bash
# 1. Clone the repository
git clone git@github.com:robertmayen/airplay_wyse.git
cd airplay_wyse

# 2. Create a feature branch
git checkout -b feature/your-feature-name

# 3. Set up a test VM (recommended)
# Option A: Using Vagrant
cat > Vagrantfile <<'EOF'
Vagrant.configure("2") do |config|
  config.vm.box = "debian/bullseye64"
  config.vm.hostname = "wyse-test"
  config.vm.network "private_network", ip: "192.168.56.10"
  config.vm.provision "shell", inline: <<-SHELL
    useradd -m -s /bin/bash airplay
    mkdir -p /opt/airplay_wyse
    chown airplay:airplay /opt/airplay_wyse
  SHELL
end
EOF
vagrant up && vagrant ssh

# Option B: Using Docker (for non-audio testing)
docker run -it --name airplay-dev debian:bullseye bash
```

---

## Code Structure & Key Functions

### bin/converge - The Core Engine

```bash
# Main execution flow
main() {
    # 1. Guards (hold files, time sync)
    check_hold_file()
    check_time_sync()
    
    # 2. Inventory processing
    load_inventory()
    derive_variables()
    
    # 3. ALSA detection
    detect_alsa()
    configure_audio()
    
    # 4. Template rendering
    render_templates()
    deploy_configs()
    
    # 5. Package management
    ensure_packages()
    ensure_nqptp()           # APT-first, source-fallback
    ensure_raop2_shairport() # Ensures AirPlay 2
    
    # 6. Service management
    restart_services()
    
    # 7. Health checks
    perform_health_checks()
    write_health_status()
}
```

### Key Functions to Understand

#### ALSA Detection (`detect_alsa()`)
```bash
detect_alsa() {
    # Priority order:
    # 1. USB devices matching inventory vendor/product
    # 2. Any USB audio device
    # 3. First available playback device
    
    # Validates by attempting to open PCM
    # Returns: hw:CARD,DEV format
}
```

#### Template Rendering (`render_template()`)
```bash
render_template() {
    local template=$1
    local output=$2
    
    # Replaces variables:
    # {{AIRPLAY_NAME}} -> from inventory
    # {{ALSA_DEVICE}} -> from detection
    # {{AVAHI_IFACE}} -> from inventory
    
    sed -e "s/{{AIRPLAY_NAME}}/$AIRPLAY_NAME/g" \
        -e "s/{{ALSA_DEVICE}}/$ALSA_DEVICE/g" \
        "$template" > "$output"
}
```

#### Source Building Functions
```bash
ensure_nqptp() {
    # Try APT first
    if apt-get install -y nqptp 2>/dev/null; then
        return 0
    fi
    
    # Fall back to source build
    echo "[converge] Building nqptp from source"
    install_nqptp_build_deps
    build_nqptp_from_source
}
```

---

## Common Development Tasks

### 1. Adding a New Configuration Option

**Example: Add custom buffer size**

```bash
# Step 1: Update inventory schema
cat >> inventory/schema.yml <<'EOF'
alsa:
  buffer_size:
    type: integer
    default: 2048
    description: "ALSA buffer size in frames"
EOF

# Step 2: Update template
cat >> cfg/shairport-sync.conf.tmpl <<'EOF'
alsa = {
    output_device = "{{ALSA_DEVICE}}";
    buffer_time = {{BUFFER_SIZE}};
};
EOF

# Step 3: Update converge to process variable
vim bin/converge
# Add to derive_variables():
BUFFER_SIZE=${alsa_buffer_size:-2048}

# Step 4: Test
./bin/converge --dry-run
```

### 2. Implementing a New Feature

**Example: Add Bluetooth support**

```bash
# Step 1: Create feature branch
git checkout -b feature/bluetooth-support

# Step 2: Add package dependency
vim bin/converge
# In ensure_packages():
REQUIRED_PACKAGES+=" bluez bluez-alsa"

# Step 3: Create configuration template
cat > cfg/bluetooth.conf.tmpl <<'EOF'
[General]
Enable=Source,Sink,Media,Socket
Name={{AIRPLAY_NAME}} Bluetooth
EOF

# Step 4: Add to converge flow
# In main():
render_template cfg/bluetooth.conf.tmpl /tmp/bluetooth.conf
deploy_config /tmp/bluetooth.conf /etc/bluetooth/main.conf

# Step 5: Add service management
# In restart_services():
restart_service bluetooth.service

# Step 6: Test thoroughly
make test
./bin/converge --test
```

### 3. Debugging Failed Converge

**Debug Techniques:**

```bash
# 1. Enable debug mode
export DEBUG=1
bash -x ./bin/converge 2>&1 | tee debug.log

# 2. Add debug prints
debug() {
    [[ "${DEBUG:-0}" == "1" ]] && echo "[DEBUG] $*" >&2
}

# Usage in code:
debug "ALSA device detected: $ALSA_DEVICE"

# 3. Test specific functions
# Source the script then call functions
source bin/converge
detect_alsa
echo "Detected: $ALSA_DEVICE"

# 4. Check state files
ls -la /var/lib/airplay_wyse/
cat /var/lib/airplay_wyse/last-health.json | jq .
```

### 4. Testing Changes

**Test Workflow:**

```bash
# 1. Unit test individual functions
cat > test_alsa.sh <<'EOF'
#!/bin/bash
source bin/converge

# Mock inventory
alsa_vendor_id="0x08bb"
alsa_product_id="0x2902"

# Test detection
detect_alsa
if [[ -n "$ALSA_DEVICE" ]]; then
    echo "PASS: Device detected: $ALSA_DEVICE"
else
    echo "FAIL: No device detected"
fi
EOF
chmod +x test_alsa.sh
./test_alsa.sh

# 2. Integration test
# Use --dry-run to test without applying changes
./bin/converge --dry-run

# 3. System test
# On test VM only!
sudo systemctl start converge

# 4. Regression test
make test  # Runs all CI checks
```

---

## Build System

### Package Building

#### Building nqptp from Source
```bash
# Manual build for testing
./pkg/build-nqptp.sh --ref v1.2.4

# Automatic build during converge
# The system will build if APT fails:
ensure_nqptp() {
    apt-get install -y nqptp || build_nqptp_from_source
}
```

#### Building shairport-sync with AirPlay 2
```bash
# Build with RAOP2 support
./pkg/build-shairport-sync.sh --with-raop2

# Install directly on device
./pkg/build-shairport-sync.sh --install-directly
```

### Build Dependencies

```bash
# nqptp dependencies
NQPTP_BUILD_DEPS=(
    build-essential
    autoconf automake libtool
    pkg-config git
    libmd-dev libsystemd-dev
)

# shairport-sync dependencies  
SHAIRPORT_BUILD_DEPS=(
    build-essential
    autoconf automake libtool
    pkg-config git
    libssl-dev libavahi-client-dev
    libasound2-dev libsoxr-dev
    libconfig-dev libdbus-1-dev
    libplist-dev
)
```

---

## Working with Templates

### Template Variables

| Variable | Source | Example | Usage |
|----------|--------|---------|-------|
| `{{AIRPLAY_NAME}}` | inventory | "Living Room" | Display name |
| `{{ALSA_DEVICE}}` | detection | "hw:1,0" | Audio output |
| `{{AVAHI_IFACE}}` | inventory | "enp3s0" | Network interface |
| `{{HOSTNAME}}` | system | "wyse-dac" | Device hostname |
| `{{MIXER_CONTROL}}` | detection | "PCM" | Volume control |

### Creating New Templates

```bash
# 1. Create template file
cat > cfg/myservice.conf.tmpl <<'EOF'
[Service]
Name={{AIRPLAY_NAME}}
Interface={{AVAHI_IFACE}}
Device={{ALSA_DEVICE}}
EOF

# 2. Add to converge
render_template cfg/myservice.conf.tmpl /tmp/myservice.conf
deploy_config /tmp/myservice.conf /etc/myservice.conf

# 3. Track for changes
compute_hash /etc/myservice.conf myservice-conf
```

---

## Git Workflow

### Feature Development

```bash
# 1. Create feature branch
git checkout -b feature/audio-improvements

# 2. Make changes
vim bin/converge
vim cfg/shairport-sync.conf.tmpl

# 3. Test locally
make test

# 4. Commit with meaningful message
git add -A
git commit -m "feat: improve ALSA detection for USB DACs

- Add fallback to first available device
- Validate device by opening PCM
- Auto-detect mixer control"

# 5. Push and create PR
git push origin feature/audio-improvements
```

### Release Process

```bash
# 1. Update version
echo "0.3.0" > VERSION

# 2. Update changelog
cat >> CHANGELOG.md <<'EOF'
## [0.3.0] - 2025-01-21
### Added
- Bluetooth audio support
- Improved ALSA detection
### Fixed
- USB DAC detection on boot
EOF

# 3. Commit changes
git add VERSION CHANGELOG.md
git commit -m "chore: prepare v0.3.0 release"

# 4. Create signed, annotated tag
git tag -s v0.3.0 -m "Release v0.3.0

Features:
- Bluetooth audio support
- Improved ALSA detection

Fixes:
- USB DAC detection on boot

Tested on: wyse-dac, wyse-sony"

# 5. Push release
git push origin main
git push origin v0.3.0
```

---

## Troubleshooting Development Issues

### Common Build Errors

```bash
# Error: /tmp read-only
# Solution: Use /var/tmp
export TMPDIR=/var/tmp

# Error: sudo not working after failed build
# Solution: Reset sudo
sudo -k
sudo -v

# Error: Package conflicts
# Solution: Clean and rebuild
apt-get clean
apt-get update
apt-get install -f

# Error: Git dirty state
# Solution: Clean working directory
git stash
git clean -fdx
```

### Debugging Tips

```bash
# 1. Check function execution
set -x  # Enable trace
set +x  # Disable trace

# 2. Validate templates
./bin/converge --validate-templates

# 3. Test privilege escalation
sudo /usr/local/sbin/airplay-sd-run cfg-write -- \
    echo "test" > /tmp/test.txt

# 4. Monitor systemd units
journalctl -f -u 'airplay-*'

# 5. Check state consistency
diff -u /var/lib/airplay_wyse/hashes/old \
        /var/lib/airplay_wyse/hashes/new
```

---

## Performance Optimization

### Converge Speed

```bash
# Profile converge execution
time ./bin/converge
strace -c ./bin/converge

# Optimize slow sections
# Example: Parallel package checks
check_packages_parallel() {
    for pkg in $REQUIRED_PACKAGES; do
        dpkg -l "$pkg" &
    done
    wait
}
```

### Memory Usage

```bash
# Monitor memory during converge
./bin/converge &
PID=$!
while kill -0 $PID 2>/dev/null; do
    ps -o pid,vsz,rss,comm -p $PID
    sleep 1
done
```

---

## Code Style Guide

### Bash Best Practices

```bash
# 1. Use shellcheck
shellcheck bin/*

# 2. Quote variables
BAD:  cd $DIR
GOOD: cd "$DIR"

# 3. Use [[ ]] for conditionals
BAD:  if [ "$var" = "value" ]; then
GOOD: if [[ "$var" == "value" ]]; then

# 4. Handle errors
set -euo pipefail
trap 'echo "Error on line $LINENO"' ERR

# 5. Use meaningful variable names
BAD:  d="/opt/airplay_wyse"
GOOD: REPO_DIR="/opt/airplay_wyse"

# 6. Comment complex logic
# Detect USB audio devices first, as they typically
# provide better quality than onboard audio
detect_usb_audio() {
    # Implementation
}
```

### Commit Message Format

```
type(scope): brief description

Longer explanation if needed. Wrap at 72 characters.

- Bullet points for multiple changes
- Keep related changes together

Fixes: #123
Tested-on: wyse-dac, wyse-sony
```

Types: feat, fix, docs, style, refactor, test, chore

---

## Testing Checklist

Before submitting changes:

- [ ] Run `make test` - passes all CI checks
- [ ] Run `shellcheck bin/*` - no warnings
- [ ] Test on VM - converge completes successfully
- [ ] Check logs - no errors in journal
- [ ] Verify health - `./bin/health` shows healthy
- [ ] Test rollback - can revert changes
- [ ] Update docs - README/AGENTS.md if needed
- [ ] Add tests - for new features

---

## Advanced Topics

### Custom Privilege Profiles

```bash
# Add new profile to airplay-sd-run
case "$profile" in
    my-custom)
        READ_WRITE_PATHS="/custom/path"
        EXTRA_FLAGS="--property=PrivateNetwork=yes"
        ;;
esac

# Use in converge
sudo /usr/local/sbin/airplay-sd-run my-custom -- \
    custom_command
```

### Integration with External Systems

```bash
# Example: Send metrics to monitoring
send_health_metrics() {
    local health_json="/var/lib/airplay_wyse/last-health.json"
    curl -X POST https://metrics.example.com/airplay \
        -H "Content-Type: application/json" \
        -d @"$health_json"
}
```

### Extending ALSA Detection

```bash
# Add support for specific hardware
detect_custom_dac() {
    local vendor="$1"
    local product="$2"
    
    # Custom detection logic
    for card in /proc/asound/card*; do
        if grep -q "$vendor:$product" "$card/usbid"; then
            # Extract card number
            # Return device string
        fi
    done
}
```

---

## Resources & References

- **Repository**: github.com/robertmayen/airplay_wyse
- **shairport-sync**: github.com/mikebrady/shairport-sync
- **nqptp**: github.com/mikebrady/nqptp
- **ALSA Documentation**: alsa-project.org
- **systemd**: freedesktop.org/wiki/Software/systemd

## Getting Help

1. Check existing issues on GitHub
2. Review logs: `journalctl -u reconcile -n 500`
3. Run diagnostics: `./bin/diag`
4. Ask in development channel
5. Contact: Robert Mayen (maintainer)

Remember: Always test in a VM first!
