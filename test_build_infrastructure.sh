#!/usr/bin/env bash
set -euo pipefail

# Test script to verify the source building infrastructure fixes
# This tests the system-level fixes for:
# 1. /var/tmp usage instead of /tmp
# 2. systemd ReadWritePaths configuration
# 3. Build dependencies installation
# 4. Error recovery for sudo state

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "$(date --iso-8601=seconds) [test-build] $*"; }
fail() { log "ERROR: $*"; exit 1; }
success() { log "SUCCESS: $*"; }

# Test 1: Verify /var/tmp is writable
test_vartmp() {
    log "Testing /var/tmp writability..."
    local test_dir
    if test_dir=$(mktemp -d -p /var/tmp); then
        success "/var/tmp is writable: $test_dir"
        rm -rf "$test_dir"
        return 0
    else
        fail "/var/tmp is not writable"
        return 1
    fi
}

# Test 2: Verify systemd-run with pkg-ensure profile has correct permissions
test_systemd_profile() {
    log "Testing systemd-run pkg-ensure profile..."
    
    # Check if airplay-sd-run wrapper exists
    if [[ ! -x /usr/local/sbin/airplay-sd-run ]]; then
        log "WARNING: airplay-sd-run wrapper not found, skipping systemd profile test"
        return 0
    fi
    
    # Test creating a temp file in /var/tmp via systemd-run
    if sudo /usr/local/sbin/airplay-sd-run pkg-ensure -- \
        "/bin/bash -c 'mktemp -p /var/tmp && echo test-write'"; then
        success "systemd-run pkg-ensure profile can write to /var/tmp"
        return 0
    else
        fail "systemd-run pkg-ensure profile cannot write to /var/tmp"
        return 1
    fi
}

# Test 3: Verify build dependencies can be checked
test_build_deps() {
    log "Testing build dependencies check..."
    
    local deps=(build-essential autoconf automake libtool pkg-config git)
    local missing=()
    
    for dep in "${deps[@]}"; do
        if ! dpkg -s "$dep" >/dev/null 2>&1; then
            missing+=("$dep")
        fi
    done
    
    if [[ ${#missing[@]} -eq 0 ]]; then
        success "All minimal build dependencies are installed"
    else
        log "INFO: Missing build dependencies: ${missing[*]}"
        log "INFO: These would be installed automatically during source build"
    fi
    return 0
}

# Test 4: Verify sudo functionality
test_sudo() {
    log "Testing sudo functionality..."
    
    if ! command -v sudo >/dev/null 2>&1; then
        fail "sudo command not found"
        return 1
    fi
    
    if sudo -n true 2>/dev/null; then
        success "sudo is functional (NOPASSWD test passed)"
        return 0
    else
        log "WARNING: sudo requires password or not configured for NOPASSWD"
        log "INFO: This is expected if not running as airplay user"
        return 0
    fi
}

# Test 5: Verify build script modifications
test_build_scripts() {
    log "Testing build script modifications..."
    
    # Check nqptp build script uses /var/tmp
    if grep -q 'mktemp -d -p /var/tmp' "$REPO_DIR/pkg/build-nqptp.sh"; then
        success "build-nqptp.sh uses /var/tmp"
    else
        fail "build-nqptp.sh not configured to use /var/tmp"
        return 1
    fi
    
    # Check shairport-sync build script uses /var/tmp
    if grep -q 'mktemp -d -p /var/tmp' "$REPO_DIR/pkg/build-shairport-sync.sh"; then
        success "build-shairport-sync.sh uses /var/tmp"
    else
        fail "build-shairport-sync.sh not configured to use /var/tmp"
        return 1
    fi
    
    # Check for error recovery in build scripts
    if grep -q 'sudo -n true' "$REPO_DIR/pkg/build-nqptp.sh" && \
       grep -q 'sudo -n true' "$REPO_DIR/pkg/build-shairport-sync.sh"; then
        success "Build scripts have sudo error recovery"
    else
        log "WARNING: Build scripts may lack complete sudo error recovery"
    fi
    
    return 0
}

# Test 6: Dry-run nqptp source detection
test_source_detection() {
    log "Testing source build detection logic..."
    
    # Check if nqptp is available in APT
    if command -v apt-cache >/dev/null 2>&1; then
        local cand
        cand=$(apt-cache policy nqptp 2>/dev/null | awk '/Candidate:/ {print $2}' || echo "(none)")
        if [[ "$cand" != "(none)" && -n "$cand" ]]; then
            log "INFO: nqptp available in APT (version: $cand)"
        else
            log "INFO: nqptp NOT available in APT - would trigger source build"
        fi
    else
        log "WARNING: apt-cache not available, cannot test APT availability"
    fi
    
    # Check if nqptp is already installed
    if dpkg -s nqptp >/dev/null 2>&1; then
        local ver
        ver=$(dpkg-query -W -f='${Version}\n' nqptp 2>/dev/null || echo "unknown")
        log "INFO: nqptp already installed (version: $ver)"
    else
        log "INFO: nqptp not installed - would trigger installation"
    fi
    
    return 0
}

# Main test execution
main() {
    log "Starting source building infrastructure tests..."
    log "Repository: $REPO_DIR"
    
    local failed=0
    
    # Run all tests
    test_vartmp || ((failed++))
    test_systemd_profile || ((failed++))
    test_build_deps || ((failed++))
    test_sudo || ((failed++))
    test_build_scripts || ((failed++))
    test_source_detection || ((failed++))
    
    echo ""
    log "============================================"
    if [[ $failed -eq 0 ]]; then
        success "All infrastructure tests passed!"
        log "The source building infrastructure is ready."
        log "Next steps:"
        log "  1. Run 'sudo bin/converge' to test the full convergence"
        log "  2. Monitor for APT failures and automatic source build fallback"
        log "  3. Check journalctl -u converge for detailed logs"
    else
        fail "$failed test(s) failed - review the output above"
    fi
    
    exit $failed
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
