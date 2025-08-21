#!/bin/bash
# Fix the bootstrap check to use sudo when reading sudoers file as non-root user

echo "Patching bootstrap.sh to fix sudoers permission check..."

# Create backup
sudo cp /opt/airplay_wyse/lib/bootstrap.sh /opt/airplay_wyse/lib/bootstrap.sh.backup

# Apply the fix
sudo tee /tmp/bootstrap_patch.sh > /dev/null << 'EOF'
#!/bin/bash
# Patch to fix sudoers check when running as non-root

# Read the original file
original_file="/opt/airplay_wyse/lib/bootstrap.sh"
temp_file="/tmp/bootstrap_patched.sh"

# Copy original to temp
cp "$original_file" "$temp_file"

# Replace the grep line that checks sudoers content
# Original: grep -Eq "pattern" "$sudoers"
# New: sudo cat "$sudoers" 2>/dev/null | grep -Eq "pattern"

sed -i 's/grep -Eq "^\(.*\)" "$sudoers"/sudo cat "$sudoers" 2>\/dev\/null | grep -Eq "^\1"/' "$temp_file"

# Also wrap the stat commands with sudo when checking sudoers file
sed -i 's/stat -c %U "$sudoers"/sudo stat -c %U "$sudoers"/' "$temp_file"
sed -i 's/stat -c %G "$sudoers"/sudo stat -c %G "$sudoers"/' "$temp_file"
sed -i 's/stat -c %a "$sudoers"/sudo stat -c %a "$sudoers"/' "$temp_file"
sed -i 's/stat -f %Su "$sudoers"/sudo stat -f %Su "$sudoers"/' "$temp_file"
sed -i 's/stat -f %Sg "$sudoers"/sudo stat -f %Sg "$sudoers"/' "$temp_file"
sed -i 's/stat -f %Lp "$sudoers"/sudo stat -f %Lp "$sudoers"/' "$temp_file"

# Also wrap visudo check
sed -i 's/visudo -cf "$sudoers"/sudo visudo -cf "$sudoers"/' "$temp_file"

# Move patched file back
mv "$temp_file" "$original_file"
EOF

# Run the patch
sudo bash /tmp/bootstrap_patch.sh

echo "Patch applied. Testing converge service..."

# Restart converge
sudo systemctl restart converge.service
sleep 2

# Check status
sudo systemctl status converge.service --no-pager
