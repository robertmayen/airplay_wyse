#!/bin/bash
set -euo pipefail

# Fix converge service permissions issue (run directly on the wyse machine)
# This script adds a systemd drop-in to allow converge to read sudoers.d

echo "=== Fixing converge service permissions on $(hostname) ==="
echo

# Check if running with sudo
if [[ $EUID -ne 0 ]]; then 
   echo "This script must be run with sudo" 
   echo "Usage: sudo ./fix_converge_local.sh"
   exit 1
fi

# Create the drop-in directory
echo "Creating systemd drop-in directory..."
mkdir -p /etc/systemd/system/converge.service.d

# Create the drop-in file to allow reading sudoers.d
echo "Creating drop-in configuration..."
cat > /etc/systemd/system/converge.service.d/10-sudoers-access.conf <<'EOF'
[Service]
# Allow converge to read sudoers.d for bootstrap validation
ReadOnlyPaths=/etc/sudoers.d
EOF

# Ensure correct permissions on the drop-in
chmod 644 /etc/systemd/system/converge.service.d/10-sudoers-access.conf
echo "✅ Drop-in configuration created"

# Clear any failed state
echo "Clearing any failed state..."
rm -f /var/lib/airplay_wyse/last-health.* 2>/dev/null || true

# Reload systemd
echo "Reloading systemd configuration..."
systemctl daemon-reload

# Restart converge service
echo "Restarting converge service..."
systemctl restart converge.service

# Wait a moment for service to start
sleep 3

# Check status
echo
echo "=== Checking converge service status ==="
if systemctl is-active --quiet converge.service; then
    echo "✅ converge.service is active"
    echo
    echo "Current status:"
    systemctl status converge.service --no-pager | head -15
else
    echo "⚠️  converge.service is not active"
    echo
    echo "Service status:"
    systemctl status converge.service --no-pager | head -20
    echo
    echo "Recent journal entries:"
    journalctl -xeu converge.service -n 20 --no-pager
fi

echo
echo "=== Running health check ==="
if [[ -f /opt/airplay_wyse/quick_health_check.sh ]]; then
    bash /opt/airplay_wyse/quick_health_check.sh 2>/dev/null | grep -E "converge|nqptp|RAOP2|AirPlay|✅|❌|⚠️"
elif [[ -f ~/health.sh ]]; then
    bash ~/health.sh 2>/dev/null | grep -E "converge|nqptp|RAOP2|AirPlay|✅|❌|⚠️"
else
    echo "No health check script found"
fi

echo
echo "=== Fix Complete ==="
echo "The converge service should now be able to read the sudoers configuration."
echo
echo "Next steps:"
echo "1. If converge is still failing, check the full logs with:"
echo "   sudo journalctl -xeu converge.service -n 50"
echo
echo "2. Once converge is working, it will:"
echo "   - Install nqptp (for AirPlay 2 support)"
echo "   - Build/install RAOP2-enabled shairport-sync if needed"
echo "   - Configure the services properly"
echo
echo "3. The converge service runs on a timer, so changes may take a few minutes"
echo "   You can force an immediate run with:"
echo "   sudo systemctl start converge.service"
