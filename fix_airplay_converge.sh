#!/bin/bash
# Fix script for AirPlay Wyse converge service permission issues
# Run this on each wyse machine as: bash fix_airplay_converge.sh

set -e

echo "=== AirPlay Wyse Converge Fix Script ==="
echo "Running on: $(hostname)"
echo "Date: $(date)"
echo

# Check if running with sudo capability
if [ "$EUID" -ne 0 ]; then 
   echo "This script needs sudo privileges. Will prompt for password."
   echo
fi

# 1. Check current state of sudoers file
echo "1. Checking sudoers file..."
if [ -f /etc/sudoers.d/airplay-wyse ]; then
    echo "   File exists. Current permissions:"
    ls -la /etc/sudoers.d/airplay-wyse
    echo "   Current content:"
    sudo cat /etc/sudoers.d/airplay-wyse 2>/dev/null || echo "   Cannot read file"
else
    echo "   File does not exist. Creating it..."
    sudo bash -c 'echo "airplay ALL=(root) NOPASSWD: /usr/bin/systemd-run" > /etc/sudoers.d/airplay-wyse'
    sudo chmod 440 /etc/sudoers.d/airplay-wyse
    sudo chown root:root /etc/sudoers.d/airplay-wyse
fi
echo

# 2. Fix permissions if needed
echo "2. Ensuring correct permissions on sudoers file..."
sudo chmod 440 /etc/sudoers.d/airplay-wyse
sudo chown root:root /etc/sudoers.d/airplay-wyse
echo "   Fixed permissions:"
ls -la /etc/sudoers.d/airplay-wyse
echo

# 3. Validate sudoers syntax
echo "3. Validating sudoers syntax..."
sudo visudo -cf /etc/sudoers.d/airplay-wyse
echo

# 4. Create/update systemd override for converge service
echo "4. Creating systemd override for converge service..."
sudo mkdir -p /etc/systemd/system/converge.service.d
sudo tee /etc/systemd/system/converge.service.d/override.conf > /dev/null << 'EOF'
[Service]
# Treat semantic non-zero exits as success for converge oneshot
SuccessExitStatus=2 3 6 10 11
RemainAfterExit=no

# Allow converge to read sudoers.d for bootstrap validation
# This fixes the "Permission denied" error when checking bootstrap status
ReadOnlyPaths=/etc/sudoers.d

# Additional permissions for converge to function properly
PrivateDevices=no
ProtectSystem=no
ProtectHome=no
NoNewPrivileges=no
EOF
echo "   Override created successfully"
echo

# 5. Install airplay-sd-run script if not present
echo "5. Checking airplay-sd-run script..."
if [ ! -f /usr/local/sbin/airplay-sd-run ]; then
    echo "   Installing airplay-sd-run..."
    if [ -f /opt/airplay_wyse/scripts/airplay-sd-run ]; then
        sudo install -o root -g root -m 0755 /opt/airplay_wyse/scripts/airplay-sd-run /usr/local/sbin/airplay-sd-run
        echo "   Installed successfully"
    else
        echo "   WARNING: Source script not found at /opt/airplay_wyse/scripts/airplay-sd-run"
    fi
else
    echo "   Already installed at /usr/local/sbin/airplay-sd-run"
fi
echo

# 6. Clear any stale state files
echo "6. Clearing stale state files..."
sudo rm -f /var/lib/airplay/converge.state 2>/dev/null || true
sudo rm -f /var/lib/airplay/.bootstrap_complete 2>/dev/null || true
echo "   State files cleared"
echo

# 7. Reload systemd and restart services
echo "7. Reloading systemd and restarting services..."
sudo systemctl daemon-reload
sudo systemctl stop converge.service 2>/dev/null || true
sudo systemctl stop converge.timer 2>/dev/null || true
echo "   Services stopped"
echo

# 8. Test converge directly
echo "8. Testing converge script directly..."
echo "   Running bootstrap check as airplay user..."
sudo -u airplay bash -c 'if sudo -n /usr/bin/systemd-run --uid=airplay --gid=airplay --pipe --wait --collect --service-type=exec --quiet -- /bin/true 2>/dev/null; then echo "   Bootstrap check: PASSED"; else echo "   Bootstrap check: FAILED"; fi'
echo

# 9. Start converge service
echo "9. Starting converge service..."
sudo systemctl start converge.service
sleep 2
echo

# 10. Check final status
echo "10. Final status check..."
echo "    Service status:"
sudo systemctl status converge.service --no-pager || true
echo
echo "    Recent logs:"
sudo journalctl -u converge.service -n 20 --no-pager
echo

# 11. Check if processes are starting
echo "11. Checking for AirPlay processes..."
ps aux | grep -E "(nqptp|shairport)" | grep -v grep || echo "   No AirPlay processes running yet"
echo

echo "=== Fix script completed ==="
echo
echo "Next steps:"
echo "1. If converge service is active, wait 5-10 minutes for it to install dependencies"
echo "2. Run 'sudo journalctl -fu converge.service' to monitor progress"
echo "3. Once complete, check 'systemctl status shairport-sync' and 'systemctl status nqptp'"
echo
