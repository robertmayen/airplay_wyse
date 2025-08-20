#!/usr/bin/env bash
set -euo pipefail

# Ensure required packages present and meet minimum versions.
# This script is safe to re-run and should be permitted via sudoers for converge.

REQ_PKGS=(shairport-sync nqptp avahi-daemon avahi-utils jq)

have() { dpkg -s "$1" >/dev/null 2>&1; }
ver() { dpkg-query -W -f='${Version}\n' "$1" 2>/dev/null | awk -F- '{print $1}'; }

readarray -t mins < <("$(dirname "$0")/versions.sh")
declare -A gate
for line in "${mins[@]}"; do eval "$line"; done

changed=0

sudo mkdir -p /etc/apt/preferences.d
for pref in "$(dirname "$0")"/apt-pins.d/*.pref; do
  [[ -f "$pref" ]] || continue
  sudo install -m 0644 "$pref" "/etc/apt/preferences.d/$(basename "$pref")"
done

sudo apt-get update -y || true

for p in "${REQ_PKGS[@]}"; do
  if ! have "$p"; then
    sudo apt-get install -y "$p" && changed=1
    continue
  fi
  inst_ver=$(ver "$p")
  min_var="MIN_$(echo "$p" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
  min_ver="${!min_var:-}"
  if [[ -n "$min_ver" ]]; then
    dpkg --compare-versions "$inst_ver" ge "$min_ver" || { sudo apt-get install -y "$p" && changed=1; }
  fi
done

# Enable services (idempotent)
sudo systemctl enable nqptp.service shairport-sync.service avahi-daemon.service || true
sudo systemctl start nqptp.service avahi-daemon.service || true

exit $changed
