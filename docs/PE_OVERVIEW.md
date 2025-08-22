# Privilege Escalation Overview

## Current Implementation

### Architecture
The AirPlay Wyse system uses a single, wrapper-based privilege path:
```
unprivileged services (airplay user) → pe_exec() → sudo /usr/local/sbin/airplay-sd-run → systemd-run → transient unit (root)
```

**Services:**
- `reconcile.service` and `converge.service` run as user `airplay`
- Single privilege path: only `/usr/local/sbin/airplay-sd-run` allowed in sudoers
- The wrapper constructs `systemd-run` with strong sandboxing and an allowlist of executables

### Implementation Details

**Core Function (simplified):**
```bash
pe_exec() {
  sudo /usr/local/sbin/airplay-sd-run "$@"
}
```

**Usage Pattern:**
- `pe_exec /usr/bin/systemctl restart shairport-sync`
- `pe_exec /usr/bin/apt-get update`
- `pe_exec /usr/bin/install -m 0644 <src> <dest>`

### Security Properties

#### Sandboxing (Applied by Wrapper)
- `ProtectSystem=strict`, `ProtectHome=yes`, `PrivateTmp=yes`, `NoNewPrivileges=yes`
- `CapabilityBoundingSet=` (empty), `AmbientCapabilities=` (empty)
- Additional restrictions depending on command kind (package/systemd/file)

#### Execution Model
- **Wrapper allowlist** - Only specific absolute executables may be invoked
- **Direct execution** - No shell interpretation; arguments are passed as-is
- **Transient units** - No persistent privileged services
- **Synchronous** - `--wait --collect` for deterministic status

### Operational Benefits

#### Simplified Debugging
- **Direct command execution** - No wrapper script interpretation
- **Standard systemd logging** - Consistent log format and location
- **Clear error messages** - Direct systemd-run error reporting
- **Predictable behavior** - Standard systemd execution model

#### Reduced Complexity
- **Single function** - `pe_exec()` replaces complex profile system
- **Consistent sandboxing** - Same security properties for all operations
- **No profile validation** - Eliminated profile-specific logic
- **Standard tooling** - Uses only systemd-run capabilities

### Risk Assessment

#### Current Risk Level: **LOW**
- **No shell injection** - Wrapper validates and executes without a shell
- **Allowlist enforcement** - Only known absolute commands are permitted
- **Sandboxing** - Strong systemd constraints per command profile
- **Single privilege path** - Only the wrapper is allowed in sudoers

#### Remaining Considerations
1. **Write paths** - Limited but still broad for some profiles
2. **Wrapper integrity** - Ensure file is `root:root` 0755 and monitored
3. **Network usage** - Allowed for package operations
4. **Syscall filtering** - Present but could be further tuned

### Future Enhancements (Optional)

#### Additional Hardening
- **Command allowlisting** - Restrict to specific executables if needed
- **Network isolation** - Add `RestrictAddressFamilies` for network-free operations
- **Syscall filtering** - Add `SystemCallFilter` for additional security
- **Minimal filesystem access** - Operation-specific `ReadWritePaths`

#### Monitoring Improvements
- **Structured logging** - Enhanced audit trail with operation context
- **Performance metrics** - Track privilege escalation usage patterns
- **Security scoring** - Regular `systemd-analyze security` assessment

### Testing

#### Current Test Coverage
- **Smoke tests** - Basic functionality verification
- **Integration tests** - End-to-end operation validation
- **Security tests** - Privilege escalation boundary verification

#### Test Commands
```bash
# Run basic functionality tests
make test

# Run privilege escalation specific tests
tests/pe/test-*.sh

# Verify sandboxing properties
systemd-analyze security <transient-unit>
```

### Success Metrics
- **Zero shell injection vulnerabilities** ✓
- **Simplified privilege escalation path** ✓
- **Consistent security properties** ✓
- **Reduced code complexity** ✓
- **Maintained functionality** ✓

### Implementation Notes
- **Backward compatibility** - All existing operations continue to work
- **Performance** - Direct execution reduces overhead
- **Maintainability** - Single function easier to audit and modify
- **Security** - Eliminates entire class of shell injection vulnerabilities
