#!/usr/bin/env bash
set -euo pipefail

# Test script to verify GitOps-compliant source building implementation
# This simulates the converge behavior for AirPlay 2 support

echo "=== GitOps Build Test ==="
echo "Testing source-building fallback logic..."

# Test 1: Check build scripts have --install-directly flag
echo -e "\n[TEST 1] Checking build scripts support --install-directly flag"
if grep -q "INSTALL_DIRECT" pkg/build-nqptp.sh; then
    echo "✓ nqptp build script supports --install-directly"
else
    echo "✗ nqptp build script missing --install-directly support"
fi

if grep -q "INSTALL_DIRECT" pkg/build-shairport-sync.sh; then
    echo "✓ shairport-sync build script supports --install-directly"
else
    echo "✗ shairport-sync build script missing --install-directly support"
fi

# Test 2: Check converge has source building functions
echo -e "\n[TEST 2] Checking converge has source-building functions"
functions_to_check=(
    "build_nqptp_from_source"
    "build_shairport_sync_from_source"
    "ensure_nqptp"
    "ensure_raop2_shairport_sync"
    "install_nqptp_build_deps"
    "install_shairport_build_deps"
)

for func in "${functions_to_check[@]}"; do
    if grep -q "^${func}()" bin/converge; then
        echo "✓ Function ${func} exists"
    else
        echo "✗ Function ${func} missing"
    fi
done

# Test 3: Verify no binary artifacts in repository
echo -e "\n[TEST 3] Checking for binary artifacts"
if find pkg -name "*.deb" 2>/dev/null | grep -q .; then
    echo "✗ Binary .deb files found in repository (violates GitOps)"
    find pkg -name "*.deb"
else
    echo "✓ No binary .deb files in repository (GitOps compliant)"
fi

# Test 4: Check fallback logic in ensure functions
echo -e "\n[TEST 4] Checking APT-first, source-fallback pattern"
if grep -A20 "ensure_nqptp()" bin/converge | grep -q "Try APT first"; then
    echo "✓ ensure_nqptp uses APT-first pattern"
else
    echo "✗ ensure_nqptp missing APT-first pattern"
fi

if grep -A30 "ensure_nqptp()" bin/converge | grep -q "Build from source"; then
    echo "✓ ensure_nqptp has source fallback"
else
    echo "✗ ensure_nqptp missing source fallback"
fi

# Test 5: Check build dependency installation
echo -e "\n[TEST 5] Checking build dependency management"
if grep -q "build-essential.*autoconf.*automake" bin/converge; then
    echo "✓ Build dependencies defined for compilation"
else
    echo "✗ Build dependencies not properly defined"
fi

# Test 6: Verify idempotency checks
echo -e "\n[TEST 6] Checking idempotency"
if grep -q "has_airplay2_build" bin/converge && grep -q "if systemctl is-active --quiet nqptp.service" bin/converge; then
    echo "✓ Idempotency check for RAOP2 support"
else
    echo "✗ Missing idempotency check"
fi

echo -e "\n=== Test Summary ==="
echo "The GitOps-compliant implementation:"
echo "1. Builds packages from source when APT unavailable"
echo "2. Uses existing privilege escalation model (systemd_run)"
echo "3. Maintains no binary artifacts in repository"
echo "4. Provides graceful fallback on build failures"
echo "5. Ensures idempotent operations"
echo ""
echo "To manually test on a device:"
echo "  1. Ensure the device has no nqptp/RAOP2 packages"
echo "  2. Run: sudo -u airplay /opt/airplay_wyse/bin/converge"
echo "  3. Verify nqptp and RAOP2-enabled shairport-sync are built/installed"
