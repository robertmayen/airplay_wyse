# Technical Report: Privilege Model (Archived)

NOTE: The repository now uses the root-run model with hardened systemd units. This document describes an earlier wrapper-based design and is retained for historical context.

## Current Model (Summary)

- Services (`reconcile.service`, `converge.service`) run as root with strong systemd hardening (e.g., `NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`, `RestrictSUIDSGID`).
- Privileged actions such as package installation and config deployment happen directly within these sandboxed services.
- No sudoers entries or wrapper binaries are required.

## Legacy Wrapper Model (Historical)

The prior design implemented a single privilege-escalation path via an allowlisted systemd-run wrapper and a minimal sudoers entry. It reduced the sudo attack surface but introduced additional moving parts (wrapper binary, sudoers, transient unit management). This path has been superseded by the simpler, hardened root-run approach.

## Security Controls (Current)

- Hardened systemd services with restrictive filesystem access and sandboxing.
- Minimal `ReadWritePaths` to required locations (state, runtime, and config paths).
- No persistent privileged daemons beyond systemd services themselves.

## Rationale for Change

- Simplifies operations and reduces failure points (no sudoers or wrapper maintenance).
- Leverages first-class systemd hardening in a single execution context.
- Retains strong isolation with fewer moving parts.

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
