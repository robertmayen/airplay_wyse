#!/usr/bin/env bash
set -euo pipefail

# AirPlay Wyse Lints (Simplified Architecture)

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

PASS_COUNT=0
FAIL_COUNT=0

log() { echo "[lints] $*" >&2; }
pass() { echo "✅ $1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "❌ FAIL: $1"; FAIL_COUNT=$((FAIL_COUNT+1)); }

check() {
  local desc="$1" cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then pass "$desc"; else fail "$desc"; fi
}

cd "$REPO_ROOT"
log "Running foundation lints (simplified arch)..."

# 1) Simplified, least-privilege model
log "Checking simplified privilege model..."
check "setup script present" "[ -f bin/setup ]"
check "apply script present" "[ -f bin/apply ]"
check "No reconcile.service in repo" "[ ! -f systemd/reconcile.service ]"
check "No reconcile.timer in repo" "[ ! -f systemd/reconcile.timer ]"
check "No converge.service in repo" "[ ! -f systemd/converge.service ]"

# 2) APT-only install
log "Checking install policy (APT-only)..."
check "No source install script present" "[ ! -f bin/install-airplay2 ]"

# 3) AirPlay 2 and NQPTP integration
log "Checking AirPlay 2 requirements..."
check "Minimal shairport template present" "[ -f cfg/shairport-sync.minimal.conf.tmpl ]"
check "NQPTP ordering present" "grep -q 'Requires=nqptp.service' systemd/overrides/shairport-sync.service.d/override.conf"
check "NQPTP After present" "grep -q 'After=nqptp.service' systemd/overrides/shairport-sync.service.d/override.conf"

# 4) Idempotent apply
log "Checking apply semantics..."
check "apply writes /etc/shairport-sync.conf" "grep -q '/etc/shairport-sync.conf' bin/apply"

# 5) Health monitoring basics
log "Checking health monitoring..."
check "Health script exists" "[ -f bin/health ]"
check "Health script executable" "[ -x bin/health ]"

# 6) Systemd hardening
log "Checking systemd security..."
check "NoNewPrivileges in shairport override" "grep -q 'NoNewPrivileges=true' systemd/overrides/shairport-sync.service.d/override.conf"
check "ProtectSystem in shairport override" "grep -q 'ProtectSystem=strict' systemd/overrides/shairport-sync.service.d/override.conf"
check "MemoryDenyWriteExecute in override" "grep -q 'MemoryDenyWriteExecute=yes' systemd/overrides/shairport-sync.service.d/override.conf"
check "RestrictAddressFamilies in override" "grep -q 'RestrictAddressFamilies=' systemd/overrides/shairport-sync.service.d/override.conf"

# 7) ALSA device resolution present
log "Checking ALSA probe..."
check "ALSA probe script exists" "[ -f bin/alsa-probe ]"

# 8) Script executability (core)
log "Checking script permissions..."
for script in bin/setup bin/apply bin/health bin/diag bin/alsa-probe; do
  check "$(basename "$script") is executable" "[ -x $script ]"
done

# 9) Templates and docs
log "Checking templates and docs..."
check "Operations documentation exists" "[ -f docs/OPERATIONS.md ]"
check "Releases documentation exists" "[ -f docs/RELEASES.md ]"
check "select-tag helper exists" "[ -f bin/select-tag ]"

echo
echo "=== LINT RESULTS ==="
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"
echo "Total:  $((PASS_COUNT + FAIL_COUNT))"

if [ $FAIL_COUNT -eq 0 ]; then
  echo "✅ ALL LINTS PASSED"
  exit 0
else
  echo "❌ LINTS FAILED: $FAIL_COUNT issues must be resolved"
  exit 1
fi
