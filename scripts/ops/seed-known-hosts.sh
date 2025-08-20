#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   scripts/ops/seed-known-hosts.sh wyse-dac=192.168.8.71 wyse-sony=192.168.8.72
# or:
#   HOSTS_LIST="wyse-dac=192.168.8.71 wyse-sony=192.168.8.72" scripts/ops/seed-known-hosts.sh
# Seeds ~/.ssh/known_hosts for both hostnames AND IPs to avoid "Host key verification failed".
# Uses ssh-keygen -R to remove stale keys, then ssh-keyscan to add fresh keys.

HOST_ARGS=( "$@" )
if [[ ${#HOST_ARGS[@]} -eq 0 ]]; then
  if [[ -n "${HOSTS_LIST:-}" ]]; then
    # shellcheck disable=SC2206  # intentional split on spaces from HOSTS_LIST
    HOST_ARGS=( ${HOSTS_LIST} )
  else
    echo "Provide hosts as args: name=ip ...  or set HOSTS_LIST" >&2
    exit 2
  fi
fi
SSH_PORT="${SSH_PORT:-22}"
KEY_TYPES="${KEY_TYPES:-ed25519,ecdsa,rsa}"
KNOWN="${KNOWN_HOSTS_FILE:-$HOME/.ssh/known_hosts}"

mkdir -p "$(dirname "$KNOWN")"
touch "$KNOWN"
chmod 600 "$KNOWN"

for entry in "${HOST_ARGS[@]}"; do
  name="${entry%%=*}"
  ip="${entry#*=}"

  # drop any stale entries (works for hashed too)
  ssh-keygen -R "$name" >/dev/null 2>&1 || true
  ssh-keygen -R "$ip"   >/dev/null 2>&1 || true
  ssh-keygen -R "[$ip]:$SSH_PORT" >/dev/null 2>&1 || true

  # add fresh keys for both hostname and IP
  ssh-keyscan -T 3 -p "$SSH_PORT" -t "$KEY_TYPES" "$name" 2>/dev/null >>"$KNOWN" || true
  ssh-keyscan -T 3 -p "$SSH_PORT" -t "$KEY_TYPES" "$ip"   2>/dev/null >>"$KNOWN" || true
done

echo "known_hosts seeded: $KNOWN"
