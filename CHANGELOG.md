# Changelog

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
