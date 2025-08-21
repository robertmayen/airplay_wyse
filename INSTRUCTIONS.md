# Instructions to Fix AirPlay2 on Your Wyse Machines

## The Problem
Your wyse machines have the sudo configuration correctly set up, but the converge service can't verify it due to systemd security restrictions. The service gets "Permission denied" when trying to read `/etc/sudoers.d/airplay-wyse`.

## The Solution
We've created a script that adds a systemd drop-in configuration to allow the converge service to read the sudoers directory. This will fix the permission issues while maintaining security.

## Steps to Apply the Fix

### For each wyse machine (wyse-sony and wyse-dac):

1. **Copy the fix script to the wyse machine:**
   ```bash
   # From your current machine, copy the script to wyse-sony
   scp fix_converge_local.sh rmayen@wyse-sony:/tmp/
   
   # And to wyse-dac
   scp fix_converge_local.sh rmayen@wyse-dac:/tmp/
   ```

2. **SSH into each machine and run the fix:**
   
   **On wyse-sony:**
   ```bash
   ssh rmayen@wyse-sony
   cd /tmp
   sudo ./fix_converge_local.sh
   ```
   
   **On wyse-dac:**
   ```bash
   ssh rmayen@wyse-dac
   cd /tmp
   sudo ./fix_converge_local.sh
   ```

## What the Script Does

1. Creates a systemd drop-in at `/etc/systemd/system/converge.service.d/10-sudoers-access.conf`
2. Adds `ReadOnlyPaths=/etc/sudoers.d` to allow the service to read sudoers files
3. Clears any failed state files
4. Reloads systemd configuration
5. Restarts the converge service
6. Checks if the service is now running successfully
7. Runs a health check to verify AirPlay2 components

## Expected Outcome

After running the script, you should see:
- ✅ converge.service is active
- The service will then automatically:
  - Install nqptp (required for AirPlay 2)
  - Build and install RAOP2-enabled shairport-sync if needed
  - Configure all services properly

## Monitoring Progress

The converge service runs on a timer (every ~5 minutes). After the fix:

1. **Check converge status:**
   ```bash
   sudo systemctl status converge.service
   ```

2. **Watch the logs in real-time:**
   ```bash
   sudo journalctl -fu converge.service
   ```

3. **Run the health check:**
   ```bash
   bash ~/health.sh
   ```

## Success Indicators

You'll know it's working when:
- ✅ converge completed with ExitCode=0 or ExitCode=2 (changes applied)
- ✅ nqptp active
- ✅ RAOP2 support detected in shairport-sync
- ✅ AirPlay discoverable on your network

## Troubleshooting

If the converge service still fails after applying the fix:

1. Check the detailed logs:
   ```bash
   sudo journalctl -xeu converge.service -n 100
   ```

2. Verify the drop-in was created:
   ```bash
   ls -la /etc/systemd/system/converge.service.d/
   cat /etc/systemd/system/converge.service.d/10-sudoers-access.conf
   ```

3. Check if the sudoers file is readable:
   ```bash
   sudo -u airplay cat /etc/sudoers.d/airplay-wyse
   ```

## Note on AirPlay 2 Build Process

Once converge is working, it may take 10-30 minutes to:
- Download and build nqptp from source (if not available via APT)
- Download and build shairport-sync with RAOP2 support
- Configure and start all services

Be patient - the converge service will handle everything automatically once it's running properly.
