#!/bin/bash
set -euo pipefail

# Fix converge service permissions issue
# This script adds a systemd drop-in to allow converge to read sudoers.d

echo "=== Fixing converge service permissions ==="
echo

# Function to apply fix on a host
apply_fix() {
    local host="$1"
    echo "[$host] Applying fix..."
    
    # Create the drop-in directory
    ssh "$host" "sudo mkdir -p /etc/systemd/system/converge.service.d"
    
    # Create the drop-in file to allow reading sudoers.d
    ssh "$host" "sudo tee /etc/systemd/system/converge.service.d/10-sudoers-access.conf > /dev/null" <<'EOF'
[Service]
# Allow converge to read sudoers.d for bootstrap validation
ReadOnlyPaths=/etc/sudoers.d
EOF
    
    # Ensure correct permissions on the drop-in
    ssh "$host" "sudo chmod 644 /etc/systemd/system/converge.service.d/10-sudoers-access.conf"
    
    # Clear any failed state
    ssh "$host" "sudo rm -f /var/lib/airplay_wyse/last-health.*" 2>/dev/null || true
    
    # Reload systemd and restart converge
    ssh "$host" "sudo systemctl daemon-reload"
    ssh "$host" "sudo systemctl restart converge.service"
    
    # Wait a moment for service to start
    sleep 2
    
    # Check status
    echo "[$host] Checking converge service status..."
    if ssh "$host" "sudo systemctl is-active --quiet converge.service"; then
        echo "[$host] ✅ converge.service is active"
    else
        echo "[$host] ⚠️  converge.service is not active, checking status..."
        ssh "$host" "sudo systemctl status converge.service --no-pager | head -20"
    fi
    
    echo
}

# Check if we can SSH to the hosts
echo "Checking SSH connectivity..."
for host in wyse-sony wyse-dac; do
    if ssh -o ConnectTimeout=5 "$host" "echo '✅ Connected to $host'" 2>/dev/null; then
        :
    else
        echo "❌ Cannot connect to $host via SSH"
        echo "Please ensure:"
        echo "  1. SSH is configured for passwordless access"
        echo "  2. The host is reachable"
        echo "  3. Your SSH config includes the host"
        exit 1
    fi
done

echo
echo "Applying fixes to both hosts..."
echo

# Apply fix to both hosts
for host in wyse-sony wyse-dac; do
    apply_fix "$host"
done

echo "=== Running health check on both hosts ==="
echo

for host in wyse-sony wyse-dac; do
    echo "[$host] Health check:"
    ssh "$host" "bash /opt/airplay_wyse/quick_health_check.sh 2>/dev/null || bash ~/health.sh 2>/dev/null" | grep -E "converge|nqptp|RAOP2|AirPlay|✅|❌|⚠️" || true
    echo
done

echo "=== Fix applied to both hosts ==="
echo
echo "The converge service should now be able to read the sudoers configuration."
echo "If the service is still failing, check the journal logs with:"
echo "  ssh wyse-sony 'sudo journalctl -xeu converge.service -n 50'"
echo "  ssh wyse-dac 'sudo journalctl -xeu converge.service -n 50'"
