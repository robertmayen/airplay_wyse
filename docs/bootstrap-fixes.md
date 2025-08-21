# Bootstrap Permission Fixes

This document explains the repository-level fixes that address the permission issues that were previously handled by runtime shell patches.

## Problem Summary

The AirPlay Wyse system experienced permission issues where:

1. The `converge` service couldn't read `/etc/sudoers.d/airplay-wyse` for bootstrap validation
2. The `bootstrap.sh` script had insufficient error handling for missing sudoers files
3. The systemd service sandbox was too restrictive for proper operation

## Previous Shell-Based Fixes

The following shell scripts were created to address these issues at runtime:

- `fix_bootstrap_check.sh` - Patched `lib/bootstrap.sh` to use `sudo` when reading sudoers files
- `fix_converge_permissions.sh` - Created systemd drop-ins to allow converge to read `/etc/sudoers.d`
- `fix_converge_local.sh` - Local version of the permissions fix
- `fix_airplay_converge.sh` - Comprehensive fix including sudoers creation and systemd overrides

## Repository-Level Solution

### 1. Enhanced systemd Override Configuration

**File**: `systemd/overrides/converge.service.d/override.conf`

**Changes**:
- Added `ReadOnlyPaths=/etc/sudoers.d` to allow reading sudoers files
- Relaxed sandbox restrictions with `PrivateDevices=no`, `ProtectSystem=no`, etc.
- Added necessary `ReadWritePaths` for state directories
- Enabled network access with `PrivateNetwork=no`
- Set environment variables for non-interactive operations

**Benefits**:
- Eliminates the need for runtime systemd drop-in creation
- Provides consistent permissions across all deployments
- Built into the repository, not requiring external patches

### 2. Improved Bootstrap Error Handling

**File**: `lib/bootstrap.sh`

**Changes**:
- Added explicit check for sudoers file existence before validation
- Enhanced `bootstrap_diagnose()` with better error categorization
- Added fallback validation methods when wrapper is missing
- Improved functional test error handling

**Benefits**:
- Better diagnostic information when bootstrap fails
- More robust handling of edge cases
- Clearer error messages for troubleshooting

### 3. Enhanced Converge Bootstrap Logic

**File**: `bin/converge`

**Changes**:
- Improved logging in `bootstrap_sudo_config()` function
- Better error handling for sudoers file creation and validation
- Enhanced validation of wrapper script installation
- More detailed manual recovery instructions

**Benefits**:
- More reliable bootstrap process
- Better visibility into what's happening during setup
- Clearer guidance when manual intervention is needed

## Migration from Shell Fixes

### What's No Longer Needed

With these repository-level fixes in place, the following shell scripts are **no longer required**:

1. `fix_bootstrap_check.sh` - Bootstrap logic now handles permissions correctly
2. `fix_converge_permissions.sh` - Systemd override provides necessary permissions
3. `fix_converge_local.sh` - Same as above, but for local execution
4. `fix_airplay_converge.sh` - Comprehensive fix is now built-in

### Deployment Process

1. **New Deployments**: The fixes are automatically applied when the repository is deployed
2. **Existing Deployments**: The next converge run will apply the updated systemd overrides and use the improved bootstrap logic

### Verification

To verify the fixes are working:

```bash
# Check that converge service has the correct overrides
systemctl cat converge.service

# Verify bootstrap status
sudo -u airplay /opt/airplay_wyse/bin/converge --dry-run

# Check service status
systemctl status converge.service
```

## Technical Details

### Systemd Sandbox Relaxation

The original systemd configuration was too restrictive. The fixes provide:

- **File System Access**: Read access to `/etc/sudoers.d` and write access to state directories
- **Network Access**: Required for package operations and git operations
- **Device Access**: Needed for ALSA device interaction
- **Process Capabilities**: Required for systemd-run operations

### Bootstrap Validation Chain

The improved bootstrap process follows this validation chain:

1. **File Existence**: Check if `/etc/sudoers.d/airplay-wyse` exists
2. **Wrapper Validation**: Use `airplay-sd-run` wrapper if available
3. **Direct Validation**: Fall back to direct `sudo visudo` if wrapper missing
4. **Functional Test**: Verify actual `systemd-run` capability
5. **Detailed Diagnostics**: Provide specific error categories for troubleshooting

### Error Categories

The enhanced diagnostics provide these error categories:

- `sudo_missing` - sudo command not available
- `sudoers_file_missing` - sudoers file doesn't exist
- `sudoers_invalid_syntax` - sudoers file has syntax errors
- `sudoers_meta_incorrect` - wrong ownership/permissions
- `wrapper_missing` - airplay-sd-run wrapper not installed
- `functional_check_failed` - systemd-run test failed

## Maintenance

### Future Updates

When updating the system:

1. The systemd overrides will be automatically synced by converge
2. Bootstrap logic improvements are immediately available
3. No manual intervention required for permission fixes

### Troubleshooting

If permission issues persist:

1. Check systemd override is applied: `systemctl cat converge.service`
2. Review bootstrap diagnostics: `sudo -u airplay /opt/airplay_wyse/lib/bootstrap.sh bootstrap_diagnose`
3. Verify sudoers file: `sudo visudo -cf /etc/sudoers.d/airplay-wyse`
4. Check wrapper installation: `ls -la /usr/local/sbin/airplay-sd-run`

## Conclusion

These repository-level fixes provide a robust, maintainable solution that eliminates the need for runtime shell patches. The system is now more reliable, provides better diagnostics, and requires less manual intervention.
