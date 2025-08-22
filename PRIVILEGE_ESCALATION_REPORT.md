# Technical Report: Privilege Escalation Implementation in AirPlay Wyse

**Date:** January 22, 2025  
**Repository:** airplay_wyse  
**Commit:** f62843e29eabebcdb0d4a485fe97dbc4f450e4e5  

## Executive Summary

The AirPlay Wyse repository implements a **single privilege path** security model using a locked-down systemd-run wrapper for privilege escalation. This design eliminates traditional sudo-based privilege escalation in favor of transient systemd units with fine-grained capability restrictions and sandboxing.

## Architecture Overview

### Core Components

1. **Unprivileged Service Layer**
   - `reconcile.service` - Runs as `airplay` user, orchestrates GitOps updates
   - `converge.service` - Runs as `airplay` user, performs system convergence
   - Both services use systemd sandboxing (`NoNewPrivileges=yes`, `ProtectSystem=strict`)

2. **Single Privilege Escalation Path**
   - `scripts/airplay-sd-run` - Locked-down wrapper for systemd-run
   - Replaces traditional sudo-based privilege escalation
   - Creates transient systemd units with capability-based restrictions

3. **Sudoers Configuration**
   - Minimal NOPASSWD sudo access for `airplay` user
   - Only allows execution of `/usr/local/sbin/airplay-sd-run` (no direct `systemd-run`)

## Privilege Escalation Mechanism

### 1. Wrapper-Based Privilege Escalation

The system uses `scripts/airplay-sd-run` as the sole privilege escalation mechanism. The wrapper takes an absolute path to an allowlisted executable and arguments, infers a security profile, and executes it via `systemd-run` with sandboxing.

```bash
# Example usage from converge (executed via sudo internally):
/usr/local/sbin/airplay-sd-run /usr/bin/install -m 0644 src dest
/usr/local/sbin/airplay-sd-run /usr/bin/systemctl daemon-reload
/usr/local/sbin/airplay-sd-run /usr/bin/apt-get -y install shairport-sync
```

**Key Security Features:**
- **Allowlisting**: Only specific executables are permitted
- **Profile inference**: Security profile selected by command type (pkg/file/systemd)
- **Transient units**: No persistent privileged processes
- **Capability bounding**: `CapabilityBoundingSet=` (empty)
- **Comprehensive sandboxing**: Multiple systemd security directives

### 2. Sudoers Configuration

Located in `/etc/sudoers.d/airplay-wyse`:
```
Defaults:airplay !requiretty
airplay ALL=(root) NOPASSWD: /usr/local/sbin/airplay-sd-run
```

**Security Analysis:**
- ✅ **Minimal scope** - Only the wrapper binary allowed
- ✅ **No shell access** - Cannot execute arbitrary commands via sudo
- ✅ **User-specific** - Only applies to `airplay` user
- ✅ **No TTY requirement** - Supports automated execution

### 3. Privilege Profiles

Profiles are inferred automatically by the wrapper based on the executable path:
- `pkg`: `/usr/bin/apt-get`, `/usr/bin/dpkg`
- `systemd`: `/usr/bin/systemctl`
- `file`: `/usr/bin/install`, `/bin/rm`, `/bin/mkdir`

## Security Controls

### 1. Systemd Sandboxing

Each transient unit created by the wrapper includes comprehensive sandboxing:

```ini
NoNewPrivileges=yes
ProtectHome=read-only
ProtectSystem=strict
PrivateTmp=yes
CapabilityBoundingSet=
DevicePolicy=closed
LockPersonality=yes
MemoryDenyWriteExecute=yes
```

### 2. Capability Restrictions

- **Empty capability bounding set** - No special capabilities granted
- **Profile-specific write paths** - Minimal filesystem access per operation type
- **Network isolation** - Private network namespace where applicable

### 3. Audit Trail

The wrapper provides comprehensive logging:
- **Execution logging** - All operations logged via systemd-cat
- **Result tracking** - Success/failure status with exit codes
- **Performance metrics** - Execution duration tracking
- **Log persistence** - Operations logged to `/var/lib/airplay_wyse/pkg/`

## Implementation Analysis

### Privilege Escalation Flow

1. **Unprivileged service** (`converge` or `reconcile`) needs privileged operation
2. **Calls wrapper function** `systemd_run <profile> -- <command>`
3. **Wrapper validates profile** and constructs systemd-run arguments
4. **Sudo executes** `/usr/local/sbin/airplay-sd-run` with profile and command
5. **Wrapper creates** transient systemd unit with appropriate restrictions
6. **systemd-run executes** command in sandboxed environment
7. **Results logged** and returned to calling process

### Code Example

From `bin/converge`, privileged operations are performed via:

```bash
sudo /usr/local/sbin/airplay-sd-run /usr/bin/install -m 0644 "$src" "$dest"
sudo /usr/local/sbin/airplay-sd-run /usr/bin/systemctl restart shairport-sync.service
sudo /usr/local/sbin/airplay-sd-run /usr/bin/apt-get -y install nqptp
```

## Security Assessment

### Strengths

1. **Single Attack Surface**
   - Only one privilege escalation path reduces attack vectors
   - Eliminates complex sudo rule management

2. **Principle of Least Privilege**
   - Profile-based access control grants minimal necessary permissions
   - Empty capability bounding set prevents capability escalation

3. **Defense in Depth**
   - Multiple layers: sudoers restrictions + wrapper validation + systemd sandboxing
   - Comprehensive audit logging for forensic analysis

4. **Transient Execution**
   - No persistent privileged processes
   - Automatic cleanup of systemd units

5. **Immutable Design**
   - APT-only package management prevents local compilation
   - Configuration-driven approach reduces runtime privilege needs

### Potential Risks

1. **Wrapper Compromise**
   - If `/usr/local/sbin/airplay-sd-run` is compromised, full privilege escalation possible
   - **Mitigation:** File integrity monitoring, proper ownership (root:root 0755)

2. **systemd-run Vulnerabilities**
   - Dependency on systemd-run binary security
   - **Mitigation:** Regular system updates, minimal systemd-run usage

3. **Profile Bypass**
   - Potential for command injection within profiles
   - **Mitigation:** Input validation, shell escaping in wrapper

4. **Sudoers Misconfiguration**
   - Incorrect sudoers rules could expand attack surface
   - **Mitigation:** Automated validation, minimal rule set

## Comparison with Traditional Approaches

| Aspect | Traditional Sudo | AirPlay Wyse Approach |
|--------|------------------|----------------------|
| **Privilege Model** | User-based sudo rules | Profile-based systemd units |
| **Persistence** | Persistent sudo sessions | Transient execution only |
| **Capabilities** | Full root capabilities | Empty capability set |
| **Sandboxing** | Minimal/none | Comprehensive systemd sandboxing |
| **Audit Trail** | Basic sudo logging | Detailed systemd + custom logging |
| **Attack Surface** | Multiple sudo rules | Single wrapper path |

## Recommendations

### Immediate Actions

1. **File Integrity Monitoring**
   - Implement monitoring for `/usr/local/sbin/airplay-sd-run`
   - Alert on unauthorized modifications

2. **Wrapper Validation**
   - Add checksum verification of wrapper before execution
   - Implement signature verification for wrapper updates

3. **Enhanced Logging**
   - Forward systemd logs to centralized logging system
   - Implement alerting on privilege escalation failures

### Long-term Improvements

1. **Capability Refinement**
   - Evaluate if any profiles can use more restrictive capabilities
   - Consider file-based capabilities instead of sudo where possible

2. **Container Integration**
   - Evaluate running privileged operations in containers
   - Implement additional namespace isolation

3. **Formal Security Review**
   - Conduct penetration testing of privilege escalation mechanism
   - Review systemd security features for additional hardening

## Conclusion

The AirPlay Wyse repository implements a sophisticated privilege escalation mechanism that significantly improves security over traditional sudo-based approaches. The single privilege path design, combined with profile-based access control and comprehensive systemd sandboxing, creates a robust security model suitable for IoT and embedded deployments.

The implementation demonstrates security best practices including:
- Principle of least privilege
- Defense in depth
- Comprehensive audit logging
- Transient execution model

While the approach introduces complexity, the security benefits justify the implementation for systems requiring both automated privilege escalation and strong security controls.

---

**Report prepared by:** Automated Security Analysis  
**Classification:** Technical Documentation  
**Distribution:** Internal Use
