# Foundation Assessment: AirPlay Wyse Repository

NOTE: Archived for reference. Current, simplified model is documented in docs/OPERATIONS.md and PRIVILEGE_ESCALATION_REPORT.md. This assessment predates the wrapper-only privilege path and hardened converge unit.

**Date**: 2025-01-22  
**Assessor**: Senior Release Engineer  
**Repository**: airplay_wyse @ HEAD (f62843e)  
**Goal**: Wyse 5070 + USB DAC acts as an AirPlay 2 receiver via GitOps

## Executive Verdict

**⚠️ CONDITIONALLY ACCEPTABLE**

The repository provides a solid foundation with 3 critical issues requiring immediate remediation before production deployment. Once these issues are addressed (estimated 3 small commits), the system will meet all requirements for a secure, idempotent AirPlay 2 receiver.

## Evidence-Based Checklist

### CORE REQUIREMENTS

| Criterion | Status | Evidence | File:Lines |
|-----------|--------|----------|------------|
| **AirPlay 2 Enforcement** | ✅ PASS | Checks `shairport-sync -V` for "AirPlay2" | `bin/converge:645-650` |
| **NQPTP Companion Daemon** | ✅ PASS | Systemd ordering enforced | `systemd/overrides/shairport-sync.service.d/override.conf:1-3` |
| **NQPTP Service Management** | ✅ PASS | Ensures enabled/started | `bin/converge:586-594` |
| **mDNS Advertisement** | ⚠️ PARTIAL | Checks for `_airplay._tcp` but not device-specific | `bin/converge:745-756` |
| **ALSA Device Resolution** | ✅ PASS | USB DAC preference with inventory override | `bin/alsa-probe:18-78` |
| **APT-Only Packages** | ✅ PASS | No `build-essential`, `gcc`, `make` found | Search confirmed |
| **Idempotent Converge** | ✅ PASS | Returns 0 (OK) or 2 (CHANGED) | `systemd/converge.service:15` |
| **Health JSON Output** | ✅ PASS | Comprehensive JSON with all fields | `bin/health:31-39` |
| **GitOps Tag-Based** | ✅ PASS | Deterministic tag selection | `bin/update:45-73` |
| **Single Privilege Path** | ❌ FAIL | Direct `sudo systemd-run` bypass exists | `bin/converge:24-35` |
| **Systemd Hardening** | ⚠️ PARTIAL | Basic hardening, missing key restrictions | `bin/converge:26-33` |
| **Wrapper Existence** | ❌ FAIL | Referenced but not present | `scripts/` empty |

### AUXILIARY FEATURES

| Feature | Status | Notes |
|---------|--------|-------|
| GPG Verification | ✅ PASS | Optional, disabled by default |
| Rollback Support | ✅ PASS | Via tag management |
| Hold Mechanism | ✅ PASS | `/etc/airplay_wyse/hold` file |
| Smoke Tests | ✅ PASS | `tests/smoke.sh` present |
| Reconcile Timer | ✅ PASS | 10min interval with jitter |

## System Architecture

```
┌─────────────────┐
│ reconcile.timer │ (10min + 1min jitter)
└────────┬────────┘
         ↓
┌─────────────────┐
│reconcile.service│ (User: airplay)
└────────┬────────┘
         ↓
    ┌────────┐
    │bin/    │
    │reconcile│──→ bin/update (fetch tags, checkout)
    └────┬───┘     
         ↓
    ┌────────┐
    │bin/    │
    │converge│──→ pe_exec() [VULNERABILITY: Direct sudo]
    └────────┘     ↓
                   ├→ APT package management
                   ├→ Config file deployment
                   ├→ Service restarts
                   └→ Health monitoring
```

## Risk Register

| # | Risk | Likelihood | Impact | Mitigation Required |
|---|------|------------|--------|---------------------|
| 1 | **Direct sudo bypass in converge** | CERTAIN | CRITICAL | Remove inline pe_exec(), use wrapper |
| 2 | **Missing privilege wrapper** | CERTAIN | CRITICAL | Create wrapper or remove all references |
| 3 | **Incomplete systemd sandboxing** | HIGH | HIGH | Add RestrictAddressFamilies, MemoryDenyWriteExecute |
| 4 | **MDNS validation weakness** | MEDIUM | MEDIUM | Verify device name in advertisements |
| 5 | **No SystemCallFilter** | HIGH | MEDIUM | Add syscall filtering to privilege escalation |
| 6 | **Missing CapabilityBoundingSet** | HIGH | MEDIUM | Explicitly drop all capabilities |
| 7 | **No audit trail for privilege escalation** | MEDIUM | MEDIUM | Add structured logging |
| 8 | **Reconcile failure handling** | LOW | MEDIUM | Add exponential backoff |
| 9 | **No CI/CD validation** | MEDIUM | LOW | Add automated policy checks |
| 10 | **Documentation inconsistency** | LOW | LOW | Update docs to match implementation |

## Remediation Plan

### Commit 1: "fix(security): enforce single privilege path via wrapper"
**Severity**: CRITICAL  
**Files**:
- `bin/converge`: Remove lines 24-35 (inline pe_exec function)
- `scripts/airplay-sd-run`: Create secure wrapper (new file)

**Diff Sketch**:
```diff
# bin/converge
-pe_exec() {
-  sudo systemd-run \
-    --wait --collect --quiet \
-    --uid=0 --gid=0 \
-    --property=Type=exec \
-    --property=ProtectSystem=strict \
-    --property=ProtectHome=yes \
-    --property=PrivateTmp=yes \
-    --property=NoNewPrivileges=yes \
-    --property=ReadWritePaths=/etc \
-    --property=ReadWritePaths=/var \
-    -- "$@"
-}
+pe_exec() {
+  /usr/local/sbin/airplay-sd-run "$@"
+}
```

### Commit 2: "feat(security): comprehensive systemd hardening"
**Severity**: HIGH  
**Files**:
- `scripts/airplay-sd-run`: Add security properties
- `systemd/overrides/shairport-sync.service.d/override.conf`: Complete hardening

**Diff Sketch**:
```diff
# systemd/overrides/shairport-sync.service.d/override.conf
 ProtectHome=true
 PrivateTmp=true
-CapabilityBoundingSet=
-AmbientCapabilities=
+CapabilityBoundingSet=CAP_NET_BIND_SERVICE
+AmbientCapabilities=CAP_NET_BIND_SERVICE
+RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
+MemoryDenyWriteExecute=yes
+SystemCallFilter=@system-service
+SystemCallFilter=~@privileged @resources
```

### Commit 3: "fix(health): validate device-specific MDNS"
**Severity**: MEDIUM  
**Files**:
- `bin/converge`: Update check_avahi_raop() function
- `bin/health`: Add device name validation

**Diff Sketch**:
```diff
# bin/converge:check_avahi_raop()
 check_avahi_raop() {
   command -v avahi-browse >/dev/null || return 0
   local name hostn
   name="${AIRPLAY_NAME:-}"
   hostn="$(host_key)"
-  if avahi-browse -rt _airplay._tcp 2>/dev/null | grep -Fqi -- "$name"; then return 0; fi
+  # Ensure our specific device is advertising
+  local browse_out
+  browse_out=$(avahi-browse -rt _airplay._tcp 2>/dev/null || true)
+  if echo "$browse_out" | grep -F "_airplay._tcp" | grep -Fqi -- "$name"; then return 0; fi
+  if echo "$browse_out" | grep -F "_airplay._tcp" | grep -Fqi -- "$hostn"; then return 0; fi
   return 1
 }
```

## Conclusion

The repository demonstrates strong fundamentals for an AirPlay 2 receiver implementation:
- Proper AirPlay 2 and NQPTP integration
- Clean GitOps workflow with tag-based releases
- Idempotent convergence with proper exit codes
- No on-device compilation (APT-only)

However, the critical security vulnerability (direct sudo bypass) and missing wrapper file must be addressed before production deployment. With the three commits outlined above, the repository will achieve a ✅ GOOD FOUNDATION status.

**Estimated effort**: 2-4 hours to implement and test all remediations.
