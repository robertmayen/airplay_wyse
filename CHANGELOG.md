# Changelog

## v0.3.0 - 2025-08-21
### Major - Repository-Level Bootstrap Fixes
- **Breaking**: Replaced runtime shell patches with permanent repository-level fixes
- Enhanced systemd override configuration with comprehensive permissions
- Improved bootstrap error handling and diagnostics in lib/bootstrap.sh
- Enhanced converge script with better logging and validation
- Added comprehensive documentation and test validation

### systemd Service Improvements
- Added ReadOnlyPaths=/etc/sudoers.d for proper sudoers file access
- Relaxed sandbox restrictions (PrivateDevices=no, ProtectSystem=no, etc.)
- Added necessary ReadWritePaths for state directories (/var/lib/airplay_wyse, /run/airplay, /tmp)
- Enabled network access with PrivateNetwork=no for package operations
- Set environment variables for non-interactive operations (DEBIAN_FRONTEND, etc.)

### Bootstrap Logic Enhancements
- Added explicit sudoers file existence checks before validation
- Enhanced bootstrap_diagnose() with detailed error categorization
- Added fallback validation methods when airplay-sd-run wrapper is missing
- Improved functional test error handling with better diagnostics
- Enhanced logging in bootstrap_sudo_config() with step-by-step feedback

### Documentation & Testing
- Added docs/bootstrap-fixes.md with comprehensive migration guide
- Created test_bootstrap_fixes.sh for validation of all fixes
- Added BOOTSTRAP_FIXES_SUMMARY.md with deployment instructions
- Documented error categories and troubleshooting procedures

### Deprecated Shell Scripts
- fix_bootstrap_check.sh - Replaced by enhanced lib/bootstrap.sh
- fix_converge_permissions.sh - Replaced by systemd override
- fix_converge_local.sh - Replaced by systemd override  
- fix_airplay_converge.sh - Replaced by integrated repository fixes

### Impact
- Eliminates need for runtime shell patches and manual interventions
- Provides consistent, maintainable solution across all deployments
- Better error diagnostics and troubleshooting capabilities
- Self-documenting with comprehensive test validation

## v0.2.17 - 2025-08-21
### Fixed
- **Critical**: Fixed converge service bootstrap validation failures on properly configured systems
- Added ReadOnlyPaths=/etc/sudoers.d to converge service override to allow sudoers validation
- Resolves "Permission denied" errors when converge checks bootstrap status
- Fixes false-negative bootstrap detection even when sudo is correctly configured

### Impact
- Converge service now correctly validates sudo configuration without permission errors
- Enables proper AirPlay 2 deployment on systems with correct sudo setup
- Eliminates need for manual intervention when sudo is already properly configured

## v0.2.16 - 2025-01-21
### Fixed
- **Critical**: Fixed read-only filesystem issues on Wyse thin clients
- All temp file operations now use `/run/airplay/tmp` instead of read-only `/tmp` or `/var/tmp`
- Added TMPDIR variable pointing to `/run/airplay/tmp` in bin/converge
- Updated ensure_dirs() to create the writable temp directory
- Modified all 8 mktemp calls in bin/converge to use $TMPDIR
- Updated pkg/build-nqptp.sh to use /run/airplay/tmp for builds
- Updated pkg/build-shairport-sync.sh to use /run/airplay/tmp for builds
- Added /run/airplay to ReadWritePaths in scripts/airplay-sd-run for pkg-ensure profile

### Impact
- Resolves all "Read-only file system" errors on Wyse devices
- Enables successful source builds on systems with read-only /tmp and /var/tmp
- AirPlay 2 (RAOP2) support now works on Wyse thin clients

## v0.2.15 - 2025-01-21
### Fixed
- **Critical**: Fixed REPO_DIR unbound variable error in pkg/install.sh by moving definition before first use
- **Critical**: Fixed all mktemp calls in bin/converge to use `/var/tmp` instead of read-only `/tmp`
- **Critical**: Added /tmp and /var/tmp to ReadWritePaths in systemd-run bootstrap fallback
- All 8 mktemp invocations now correctly use `-p /var/tmp` parameter
- Bootstrap fallback for pkg-ensure profile now includes temp directory permissions

### Impact
- Resolves "Read-only file system" errors during source builds
- Fixes sudo corruption issues after failed builds
- Enables successful APT-to-source fallback for nqptp and shairport-sync
- AirPlay 2 (RAOP2) support now works correctly

## v0.2.14 - 2025-01-21
### Added (Attempted - Failed)
- System-level infrastructure fixes for source building
- /var/tmp usage in build scripts
- Build dependencies installation
- Error recovery for sudo state

### Known Issues
- REPO_DIR unbound variable causing immediate failure
- mktemp still using /tmp in converge script
- Incomplete systemd-run fallback configuration

## v0.2.13 - 2025-01-21
### Added
- Comprehensive source building infrastructure
- APT-first, source-fallback pattern for nqptp
- RAOP2-enabled shairport-sync building capability
- Build scripts for both nqptp and shairport-sync
- Automatic build dependency installation

## v0.2.12 - 2025-01-20
### Added
- Initial AirPlay 2 (RAOP2) support implementation
- nqptp integration for AirPlay 2 functionality
- Source building fallback when APT packages unavailable

## Previous Versions
[Previous changelog entries...]
