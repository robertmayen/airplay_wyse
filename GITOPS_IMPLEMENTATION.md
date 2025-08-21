# GitOps-Compliant Source Building Implementation

## Summary

Successfully implemented GitOps-compliant source building during converge execution, eliminating the need for binary artifacts in the repository while maintaining AirPlay 2 functionality.

## Implementation Details

### 1. Modified Build Scripts

#### `pkg/build-nqptp.sh`
- Added `--install-directly` flag for on-device building
- When flag is set, installs the built package directly instead of saving .deb
- Handles systemd service enablement and restart after installation

#### `pkg/build-shairport-sync.sh`
- Added `--install-directly` flag for on-device building  
- When flag is set, installs the built package directly instead of saving .deb
- Ensures RAOP2/AirPlay 2 support is compiled in

### 2. Enhanced Converge Logic

#### New Functions Added to `bin/converge`:

**Build Dependency Management:**
- `install_nqptp_build_deps()` - Installs compilation dependencies for nqptp
- `install_shairport_build_deps()` - Installs compilation dependencies for shairport-sync

**Source Building Functions:**
- `build_nqptp_from_source()` - Builds nqptp from source using build script
- `build_shairport_sync_from_source()` - Builds RAOP2-enabled shairport-sync from source

**Ensure Functions with Fallback:**
- `ensure_nqptp()` - APT-first, source-fallback pattern for nqptp installation
- `ensure_raop2_shairport_sync()` - Ensures RAOP2-enabled shairport-sync

### 3. Implementation Strategy

```bash
# Pseudocode for the fallback pattern:
ensure_nqptp() {
    # 1. Try APT first (fast path)
    if apt-get install -y nqptp; then
        return 0
    fi
    
    # 2. Build from source (GitOps fallback)
    echo "[converge] Building nqptp from source (APT unavailable)"
    build_nqptp_from_source
}
```

### 4. Build Dependencies

**nqptp build dependencies:**
- build-essential
- autoconf
- automake
- libtool
- pkg-config
- git
- libmd-dev
- libsystemd-dev

**shairport-sync build dependencies:**
- build-essential
- autoconf
- automake
- libtool
- pkg-config
- git
- libssl-dev
- libavahi-client-dev
- libasound2-dev
- libsoxr-dev
- libconfig-dev
- libdbus-1-dev
- libplist-dev

### 5. Privilege Model Integration

Uses existing transient privilege profiles:
- `pkg-ensure` - Install build dependencies and built packages
- `cfg-write` - Write configuration files
- `svc-restart` - Restart services after installation

### 6. Error Handling

- Graceful degradation if builds fail
- Warning messages but continues operation
- Maintains existing shairport-sync if RAOP2 upgrade fails

## GitOps Compliance

✅ **No binary artifacts** - Repository contains only source code and scripts  
✅ **Platform agnostic** - Builds on any Debian-based system  
✅ **Always current** - Builds from latest source  
✅ **Self-contained** - No external dependencies or manual steps  
✅ **Secure** - Uses existing privilege escalation model  
✅ **Idempotent** - Only builds when necessary  

## Testing

Run the test script to verify implementation:
```bash
./test_gitops_build.sh
```

All tests should pass:
- [x] Build scripts support --install-directly flag
- [x] Converge has source-building functions
- [x] No binary .deb files in repository (GitOps compliant)
- [x] APT-first, source-fallback pattern implemented
- [x] Build dependencies properly defined
- [x] Idempotency checks in place

## Usage

The converge script will automatically:
1. Try to install packages via APT (fast path)
2. If APT fails, build from source automatically
3. Install build dependencies as needed
4. Clean up build artifacts after installation
5. Enable and start services

No manual intervention required - the system self-remediates!

## Benefits

1. **GitOps Hygiene**: No binary artifacts polluting the repository
2. **Automatic Remediation**: Builds from source when needed
3. **Platform Independence**: Works on any Debian-based system
4. **Security**: Uses existing privilege model
5. **Maintainability**: Simple, clear code structure
6. **Reliability**: Graceful fallbacks at every step
