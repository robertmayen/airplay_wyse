#!/usr/bin/env bash
set -euo pipefail

# Guard: ensure symmetric changes to host inventories for key fields.
# Fails if one host file changes key fields while the other does not.
#
# Usage:
#   DIFF_RANGE="<git range>" scripts/ci/check-inventory-pair.sh
#   scripts/ci/check-inventory-pair.sh            # defaults to HEAD~1..HEAD

PAIR_A="inventory/hosts/wyse-sony.yml"
PAIR_B="inventory/hosts/wyse-dac.yml"

# Keys to watch (YAML keys at start of line)
KEY_REGEX='^(\+|-)\s*(nic|alsa\.vendor_id|alsa\.product_id|alsa\.serial|airplay_name)\s*:'

RANGE=${DIFF_RANGE:-"HEAD~1..HEAD"}

diff_has_key_changes() {
  local file=$1
  # Use -U0 for zero context; look only at added/removed lines for key matches
  git diff -U0 -- ${RANGE} -- "$file" | \
    sed -n '/^@@/,$p' | \
    grep -E "${KEY_REGEX}" >/dev/null 2>&1
}

changed_a=false
changed_b=false

if diff_has_key_changes "$PAIR_A"; then
  changed_a=true
fi
if diff_has_key_changes "$PAIR_B"; then
  changed_b=true
fi

if [[ "$changed_a" == false && "$changed_b" == false ]]; then
  echo "No key changes detected in either host file for range: ${RANGE}"
  exit 0
fi

if [[ "$changed_a" != "$changed_b" ]]; then
  echo "ERROR: Host-affecting keys changed in one file but not the other." >&2
  echo "       Keys watched: nic, alsa.vendor_id, alsa.product_id, alsa.serial, airplay_name" >&2
  echo "       Range: ${RANGE}" >&2
  echo "       ${PAIR_A}: ${changed_a}" >&2
  echo "       ${PAIR_B}: ${changed_b}" >&2
  echo "Hint: apply corresponding changes to both host files or document intentional divergence in PR." >&2
  exit 1
fi

echo "OK: Symmetric key changes detected in both host files for range: ${RANGE}"
exit 0

