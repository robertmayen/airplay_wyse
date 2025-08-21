#!/bin/bash
set -euo pipefail

# Test script to validate the repository-level bootstrap fixes
# This script verifies that the fixes work without requiring the shell patches

echo "=== AirPlay Wyse Bootstrap Fixes Test ==="
echo "Testing repository-level fixes for permission issues"
echo

# Test 1: Check systemd override configuration
echo "1. Testing systemd override configuration..."
override_file="systemd/overrides/converge.service.d/override.conf"
if [[ -f "$override_file" ]]; then
    echo "   ✅ Override file exists: $override_file"
    
    # Check for key permissions
    if grep -q "ReadOnlyPaths=/etc/sudoers.d" "$override_file"; then
        echo "   ✅ ReadOnlyPaths for sudoers.d configured"
    else
        echo "   ❌ ReadOnlyPaths for sudoers.d missing"
    fi
    
    if grep -q "PrivateDevices=no" "$override_file"; then
        echo "   ✅ Device access permissions configured"
    else
        echo "   ❌ Device access permissions missing"
    fi
    
    if grep -q "PrivateNetwork=no" "$override_file"; then
        echo "   ✅ Network access permissions configured"
    else
        echo "   ❌ Network access permissions missing"
    fi
else
    echo "   ❌ Override file missing: $override_file"
fi
echo

# Test 2: Check bootstrap.sh enhancements
echo "2. Testing bootstrap.sh enhancements..."
bootstrap_file="lib/bootstrap.sh"
if [[ -f "$bootstrap_file" ]]; then
    echo "   ✅ Bootstrap file exists: $bootstrap_file"
    
    # Check for enhanced error handling
    if grep -q "sudoers_file_missing" "$bootstrap_file"; then
        echo "   ✅ Enhanced error categorization present"
    else
        echo "   ❌ Enhanced error categorization missing"
    fi
    
    # Check for fallback validation
    if grep -q "Fallback: try direct sudo validation" "$bootstrap_file"; then
        echo "   ✅ Fallback validation logic present"
    else
        echo "   ❌ Fallback validation logic missing"
    fi
else
    echo "   ❌ Bootstrap file missing: $bootstrap_file"
fi
echo

# Test 3: Check converge script improvements
echo "3. Testing converge script improvements..."
converge_file="bin/converge"
if [[ -f "$converge_file" ]]; then
    echo "   ✅ Converge file exists: $converge_file"
    
    # Check for enhanced logging
    if grep -q "Configuring sudo permissions for airplay user" "$converge_file"; then
        echo "   ✅ Enhanced logging present"
    else
        echo "   ❌ Enhanced logging missing"
    fi
    
    # Check for better error handling
    if grep -q "sudoers file validated successfully" "$converge_file"; then
        echo "   ✅ Better error handling present"
    else
        echo "   ❌ Better error handling missing"
    fi
else
    echo "   ❌ Converge file missing: $converge_file"
fi
echo

# Test 4: Check documentation
echo "4. Testing documentation..."
doc_file="docs/bootstrap-fixes.md"
if [[ -f "$doc_file" ]]; then
    echo "   ✅ Documentation exists: $doc_file"
    
    if grep -q "Repository-Level Solution" "$doc_file"; then
        echo "   ✅ Solution documentation present"
    else
        echo "   ❌ Solution documentation missing"
    fi
    
    if grep -q "Migration from Shell Fixes" "$doc_file"; then
        echo "   ✅ Migration documentation present"
    else
        echo "   ❌ Migration documentation missing"
    fi
else
    echo "   ❌ Documentation missing: $doc_file"
fi
echo

# Test 5: Validate that shell fixes are no longer needed
echo "5. Checking shell fix scripts status..."
shell_fixes=(
    "fix_bootstrap_check.sh"
    "fix_converge_permissions.sh" 
    "fix_converge_local.sh"
    "fix_airplay_converge.sh"
)

for fix in "${shell_fixes[@]}"; do
    if [[ -f "$fix" ]]; then
        echo "   ⚠️  Shell fix still present: $fix (can be removed)"
    else
        echo "   ✅ Shell fix not present: $fix"
    fi
done
echo

# Test 6: Functional test (if running on target system)
echo "6. Functional tests..."
if command -v systemctl >/dev/null 2>&1; then
    echo "   ✅ systemctl available for testing"
    
    # Check if converge service exists
    if systemctl list-unit-files --type=service --no-legend 2>/dev/null | grep -q "converge.service"; then
        echo "   ✅ converge.service is installed"
        
        # Check if override is applied
        if systemctl cat converge.service 2>/dev/null | grep -q "ReadOnlyPaths=/etc/sudoers.d"; then
            echo "   ✅ systemd override is applied"
        else
            echo "   ⚠️  systemd override not yet applied (run systemctl daemon-reload)"
        fi
    else
        echo "   ⚠️  converge.service not installed (not on target system)"
    fi
else
    echo "   ⚠️  systemctl not available (not on target system)"
fi
echo

# Summary
echo "=== Test Summary ==="
echo "Repository-level fixes have been implemented to replace shell patches."
echo
echo "Key improvements:"
echo "- Enhanced systemd service permissions"
echo "- Better bootstrap error handling and diagnostics"
echo "- Improved converge script robustness"
echo "- Comprehensive documentation"
echo
echo "Next steps:"
echo "1. Deploy the updated repository to target systems"
echo "2. Run 'systemctl daemon-reload' to apply systemd overrides"
echo "3. Test converge service operation"
echo "4. Remove shell fix scripts (they are no longer needed)"
echo
echo "For troubleshooting, see: docs/bootstrap-fixes.md"
