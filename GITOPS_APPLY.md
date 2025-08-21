# Applying the Fix via GitOps

## What Was Changed

We've fixed the converge service bootstrap validation issue by modifying:
- `systemd/overrides/converge.service.d/override.conf` - Added `ReadOnlyPaths=/etc/sudoers.d`
- `CHANGELOG.md` - Documented the fix in v0.2.17
- `VERSION` - Bumped to v0.2.17

## How to Apply

### 1. Commit and Push the Changes

```bash
git add systemd/overrides/converge.service.d/override.conf CHANGELOG.md VERSION
git commit -m "fix: Allow converge to read sudoers.d for bootstrap validation

- Added ReadOnlyPaths=/etc/sudoers.d to converge service override
- Fixes false-negative bootstrap detection on properly configured systems
- Resolves Permission denied errors when checking sudo configuration"

git push
```

### 2. Pull and Apply on Each Wyse Machine

SSH into each machine and pull the changes:

**On wyse-sony:**
```bash
ssh rmayen@wyse-sony
cd /opt/airplay_wyse
sudo git pull
sudo systemctl daemon-reload
sudo systemctl restart converge.service
```

**On wyse-dac:**
```bash
ssh rmayen@wyse-dac
cd /opt/airplay_wyse
sudo git pull
sudo systemctl daemon-reload
sudo systemctl restart converge.service
```

### 3. Verify the Fix

After pulling and restarting, check that converge is working:

```bash
# Check service status
sudo systemctl status converge.service

# Run health check
bash ~/health.sh

# Watch the logs
sudo journalctl -fu converge.service
```

## Expected Results

After applying the fix:
- ✅ converge.service should be active (not failed)
- ✅ No more "Permission denied" errors in the logs
- ✅ The service will begin installing nqptp and building RAOP2-enabled shairport-sync
- ✅ After 10-30 minutes, full AirPlay 2 support will be active

## What Happens Next

The converge service will automatically:
1. Verify the bootstrap is complete (sudo configuration)
2. Install nqptp from APT or build from source
3. Build RAOP2-enabled shairport-sync if needed
4. Configure all services for AirPlay 2
5. Start the AirPlay services

The converge timer runs every ~5 minutes, so changes will be applied automatically after the initial restart.
