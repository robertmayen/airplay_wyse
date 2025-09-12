# Deployment Acceptance Checklist

**Purpose**: Essential validation steps for AirPlay Wyse deployment readiness.

## Quick Validation

Use the lints script for comprehensive validation:

```bash
# Repository structure validation (CI/development)
./tools/lints.sh

# Runtime validation on target device
AIRPLAY_RUNTIME_CHECKS=1 ./tools/lints.sh
```

## Manual Deployment Steps (Simplified Model)

### 1. One-time Setup (as root)
```bash
cd /opt/airplay_wyse
sudo ./bin/setup
```

### 2. Essential Validation
```bash
shairport-sync -V | grep -q AirPlay2 && echo "AirPlay 2 OK" || echo "AirPlay 2 missing"
systemctl is-active --quiet nqptp && echo "nqptp active" || echo "nqptp not active"
avahi-browse -rt _airplay._tcp | grep -q _airplay._tcp && echo "mDNS visible" || echo "mDNS missing"
```

### 3. Audio Test
```bash
# Test ALSA device detection
DEVICE=$(./bin/alsa-probe)
echo "Detected ALSA device: $DEVICE"

# Test audio output (optional)
speaker-test -D "$DEVICE" -c 2 -t wav -l 1
```

### 4. AirPlay Connection Test
- **iOS**: Settings → AirPlay → Select your device
- **macOS**: Sound preferences → Output → Select your device
- **Verify**: Audio plays through USB DAC

## Success Criteria

✅ **Ready for production** when:
- [ ] `./tools/lints.sh` passes (0 failures)
- [ ] `AIRPLAY_RUNTIME_CHECKS=1 ./tools/lints.sh` passes on target device
- [ ] Audio successfully plays via AirPlay connection
- [ ] Device appears in AirPlay device list within 2 minutes of boot

## Troubleshooting

**Common Issues:**
- **No AirPlay advertisement**: Check `systemctl status avahi-daemon nqptp shairport-sync`
- **No audio output**: Run `./bin/alsa-probe` and check USB DAC connection
- **Config not applied**: Re-run `sudo ./bin/apply --name "..."` or specify `--device`/`--mixer`

**Health Monitoring:**
```bash
# Check system health
./bin/health

# View logs
journalctl -u shairport-sync -n 100 --no-pager
```
