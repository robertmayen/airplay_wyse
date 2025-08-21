#!/bin/bash
# Apply AirPlay 2 (RAOP2) GitOps enhancement patches

echo "Applying AirPlay 2 GitOps enhancement patches..."
echo ""

# Note: bin/converge already has the changes applied
echo "✓ bin/converge - Already updated with AP2 detection and logging"
echo ""

# Apply individual patches
echo "Applying systemd override patch..."
git apply patches/systemd-override.patch && echo "✓ Applied" || echo "✗ Failed"

echo "Applying build-shairport-sync patch..."
git apply patches/build-shairport-sync.patch && echo "✓ Applied" || echo "✗ Failed"

echo "Applying docs/runbook.md patch..."
git apply patches/docs-runbook.patch && echo "✓ Applied" || echo "✗ Failed"

echo "Applying README.md patch..."
git apply patches/readme.patch && echo "✓ Applied" || echo "✗ Failed"

echo ""
echo "Patches applied. Review changes with: git status"
echo ""
echo "To commit these changes:"
echo "  git add -A"
echo "  git commit -F patches/commit-message.txt"
echo ""
echo "To create release tag:"
echo "  git tag -s v0.2.0 -F patches/tag-message.txt"
echo "  git push origin main --tags"
