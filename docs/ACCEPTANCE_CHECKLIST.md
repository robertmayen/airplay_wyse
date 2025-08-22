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

## Manual Deployment Steps (Root-Run Model)

### 1. Install Units and Enable Timer (as root)
```bash
install -m 0644 systemd/reconcile.service /etc/systemd/system/reconcile.service
install -m 0644 systemd/reconcile.timer /etc/systemd/system/reconcile.timer
install -m 0644 systemd/converge.service /etc/systemd/system/converge.service
systemctl daemon-reload
systemctl enable --now reconcile.timer
```

### 2. Essential Validation
```bash
# Idempotence test
cd /opt/airplay_wyse
./bin/converge; FIRST_EXIT=$?
./bin/converge; SECOND_EXIT=$?

# Verify: FIRST_EXIT should be 0 or 2, SECOND_EXIT should be 0
echo "First run: $FIRST_EXIT, Second run: $SECOND_EXIT"
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
- [ ] Second converge run returns exit code 0 (idempotent)
- [ ] Audio successfully plays via AirPlay connection
- [ ] Device appears in AirPlay device list within 2 minutes of boot

## Troubleshooting

**Common Issues:**
- **No AirPlay advertisement**: Check `systemctl status avahi-daemon nqptp shairport-sync`
- **APT install failures**: Ensure `reconcile.service` allows writes to `/usr` (ReadWritePaths)
- **No audio output**: Run `./bin/alsa-probe` and check USB DAC connection
- **Converge failures**: Check `journalctl -u reconcile -n 50`

**Health Monitoring:**
```bash
# Check system health
./bin/health

# View last health status
cat /var/lib/airplay_wyse/last-health.json | jq .
```
