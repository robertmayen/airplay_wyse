#!/usr/bin/env bash
set -euo pipefail

# AirPlay Wyse Foundation Lints
# CI-runnable script to enforce key guarantees

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS_COUNT=0
FAIL_COUNT=0

log() {
    echo "[lints] $*" >&2
}

pass() {
    echo "✅ $1"
    ((PASS_COUNT++))
}

fail() {
    echo "❌ FAIL: $1"
    ((FAIL_COUNT++))
}

check() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd" >/dev/null 2>&1; then
        pass "$desc"
    else
        fail "$desc"
    fi
}

# Change to repo root for all checks
cd "$REPO_ROOT"

log "Running foundation lints..."

# 1. Single Privilege Path Enforcement
log "Checking privilege escalation model..."

# No direct sudo systemd-run bypasses in bin/
if grep -r "sudo systemd-run" bin/ --exclude-dir=.git 2>/dev/null; then
    fail "Direct sudo systemd-run bypass found in bin/"
else
    pass "No direct sudo bypasses in bin/"
fi

# Wrapper exists
check "Privilege wrapper exists" "[ -f scripts/airplay-sd-run ]"

# Wrapper is executable
check "Privilege wrapper is executable" "[ -x scripts/airplay-sd-run ]"

# pe_exec in converge uses the wrapper path
if grep -q "sudo /usr/local/sbin/airplay-sd-run" bin/converge; then
    pass "pe_exec uses wrapper path in converge"
else
    fail "pe_exec does not use wrapper path"
fi

# 2. No On-Device Builds
log "Checking immutable host policy..."

# No build tools in package lists
for tool in build-essential gcc g++ make cmake; do
    if grep -r "$tool" . --exclude-dir=.git --exclude-dir=node_modules 2>/dev/null | grep -v "# No $tool" | grep -q "$tool"; then
        fail "Build tool '$tool' referenced in repository"
    else
        pass "No '$tool' references found"
    fi
done

# No pkg/build-* scripts
if find . -name "build-*" -path "*/pkg/*" 2>/dev/null | grep -q .; then
    fail "Build scripts found in pkg/"
else
    pass "No build scripts in pkg/"
fi

# 3. AirPlay 2 Enforcement
log "Checking AirPlay 2 requirements..."

# shairport-sync version check exists
check "AirPlay 2 version check present" "grep -q 'shairport-sync -V.*AirPlay2' bin/converge"

# NQPTP ordering enforced
check "NQPTP systemd ordering present" "grep -q 'Requires=nqptp.service' systemd/overrides/shairport-sync.service.d/override.conf"
check "NQPTP systemd After present" "grep -q 'After=nqptp.service' systemd/overrides/shairport-sync.service.d/override.conf"

# 4. Idempotent Converge
log "Checking converge semantics..."

# SuccessExitStatus configured (must include 0 and 2 at least)
check "SuccessExitStatus configured" "grep -q '^SuccessExitStatus=' systemd/converge.service"

# Exit codes defined
check "EXIT_OK defined" "grep -q 'EXIT_OK=0' bin/converge"
check "EXIT_CHANGED defined" "grep -q 'EXIT_CHANGED=2' bin/converge"

# 5. Health Monitoring
log "Checking health monitoring..."

# Health script exists
check "Health script exists" "[ -f bin/health ]"

# Health script is executable
check "Health script executable" "[ -x bin/health ]"

# Health viewer behavior (should reference last-health.json)
check "Health viewer references last-health" "grep -q 'last-health.json' bin/health"

# 6. Systemd Hardening
log "Checking systemd security..."

# NoNewPrivileges in override
check "NoNewPrivileges in shairport override" "grep -q 'NoNewPrivileges=true' systemd/overrides/shairport-sync.service.d/override.conf"

# ProtectSystem in override
check "ProtectSystem in shairport override" "grep -q 'ProtectSystem=strict' systemd/overrides/shairport-sync.service.d/override.conf"

# Memory protection
check "MemoryDenyWriteExecute in override" "grep -q 'MemoryDenyWriteExecute=yes' systemd/overrides/shairport-sync.service.d/override.conf"

# Address family restrictions
check "RestrictAddressFamilies in override" "grep -q 'RestrictAddressFamilies=' systemd/overrides/shairport-sync.service.d/override.conf"

# 7. GitOps Requirements
log "Checking GitOps compliance..."

# Update script exists
check "Update script exists" "[ -f bin/update ]"

# Reconcile timer exists
check "Reconcile timer exists" "[ -f systemd/reconcile.timer ]"

# Tag-based updates
check "Tag-based update logic" "grep -q 'highest_semver_tag' bin/update"

# 8. ALSA Device Resolution
log "Checking ALSA requirements..."

# ALSA probe script exists
check "ALSA probe script exists" "[ -f bin/alsa-probe ]"

# USB DAC preference
check "USB DAC preference logic" "grep -q 'idVendor.*idProduct' bin/alsa-probe"

# 9. Script Executability
log "Checking script permissions..."

for script in bin/reconcile bin/update bin/converge bin/health bin/diag bin/alsa-probe; do
    check "$(basename "$script") is executable" "[ -x $script ]"
done

# 9b. Bash syntax check
log "Checking bash syntax..."
if bash -n bin/* 2>/dev/null; then
    pass "bash -n validation passed"
else
    fail "bash -n validation failed"
fi

# 10. Template Validation
log "Checking configuration templates..."

# Shairport config template exists
check "Shairport config template exists" "[ -f cfg/shairport-sync.conf.tmpl ]"

# Template has required placeholders
check "AIRPLAY_NAME placeholder" "grep -q '{{AIRPLAY_NAME}}' cfg/shairport-sync.conf.tmpl"
check "ALSA_DEVICE placeholder" "grep -q '{{ALSA_DEVICE}}' cfg/shairport-sync.conf.tmpl"

# 11. Documentation Consistency
log "Checking documentation..."

# Operations doc exists
check "Operations documentation exists" "[ -f docs/OPERATIONS.md ]"

# Foundation assessment exists
check "Foundation assessment exists" "[ -f docs/FOUNDATION_ASSESSMENT.md ]"

# Acceptance checklist exists
check "Acceptance checklist exists" "[ -f docs/ACCEPTANCE_CHECKLIST.md ]"

# 12. Test Coverage
log "Checking test coverage..."

# Smoke test exists
check "Smoke test exists" "[ -f tests/smoke.sh ]"

# Smoke test is executable
check "Smoke test executable" "[ -x tests/smoke.sh ]"

# 13. Runtime Validation (if on target system)
if [[ "${AIRPLAY_RUNTIME_CHECKS:-}" == "1" ]]; then
    log "Running runtime validation checks..."
    
    # Check if we're on a system with the required tools
    if command -v systemctl >/dev/null 2>&1; then
        # AirPlay 2 support check
        if command -v shairport-sync >/dev/null 2>&1; then
            if shairport-sync -V 2>&1 | grep -q "AirPlay2"; then
                pass "Runtime: AirPlay 2 support present"
            else
                fail "Runtime: No AirPlay 2 support"
            fi
        fi
        
        # NQPTP service check
        if systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "nqptp.service"; then
            if systemctl is-active --quiet nqptp.service 2>/dev/null; then
                pass "Runtime: NQPTP service active"
            else
                fail "Runtime: NQPTP service not active"
            fi
        fi
        
        # Wrapper security check
        if [[ -f /usr/local/sbin/airplay-sd-run ]]; then
            uname_s=$(uname -s 2>/dev/null || echo Unknown)
            if [[ "$uname_s" == "Darwin" ]]; then
                owner=$(stat -f '%Su:%Sg' /usr/local/sbin/airplay-sd-run 2>/dev/null || echo "unknown")
                perms=$(stat -f '%Lp' /usr/local/sbin/airplay-sd-run 2>/dev/null || echo "unknown")
            else
                owner=$(stat -c '%U:%G' /usr/local/sbin/airplay-sd-run 2>/dev/null || echo "unknown")
                perms=$(stat -c '%a' /usr/local/sbin/airplay-sd-run 2>/dev/null || echo "unknown")
            fi
            if [[ "$owner" == "root:root" && "$perms" == "755" ]]; then
                pass "Runtime: Wrapper properly secured"
            else
                fail "Runtime: Wrapper insecure ($owner, $perms)"
            fi
        fi
        
        # mDNS advertisement check
        if command -v avahi-browse >/dev/null 2>&1; then
            if timeout 5 avahi-browse -rt _airplay._tcp 2>/dev/null | grep -q "_airplay._tcp"; then
                pass "Runtime: AirPlay advertised via mDNS"
            else
                fail "Runtime: No AirPlay mDNS advertisement"
            fi
        fi
    fi
fi

# Summary
echo
echo "=== LINT RESULTS ==="
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"
echo "Total:  $((PASS_COUNT + FAIL_COUNT))"

if [ $FAIL_COUNT -eq 0 ]; then
    echo "✅ ALL LINTS PASSED: Repository meets foundation requirements"
    if [[ "${AIRPLAY_RUNTIME_CHECKS:-}" == "1" ]]; then
        echo "   (Including runtime validation on target system)"
    fi
    exit 0
else
    echo "❌ LINTS FAILED: $FAIL_COUNT issues must be resolved"
    exit 1
fi
