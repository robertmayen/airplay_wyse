#!/usr/bin/env bash
set -euo pipefail

# Shared helpers for AirPlay Wyse scripts

ts() {
  # Portable ISO-8601 UTC timestamp
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

STATE_DIR="/var/lib/airplay_wyse"
IDENTITY_FILE="$STATE_DIR/instance.json"

render_shairport_conf() {
  # Args: <template> <target> <name> <device> <mixer> <iface> <hwaddr>
  local tmpl="$1" tgt="$2" name="$3" device="$4" mixer="$5" iface="$6" hwaddr="$7"
  [[ -f "$tmpl" ]] || { echo "[lib] missing template: $tmpl" >&2; return 1; }

  local tmp
  tmp=$(mktemp)
  sed \
    -e "s/{{AIRPLAY_NAME}}/${name//\//\/}/g" \
    -e "s/{{ALSA_DEVICE}}/${device//\//\/}/g" \
    -e "s/{{ALSA_MIXER}}/${mixer//\//\/}/g" \
    -e "s/{{AVAHI_IFACE}}/${iface//\//\/}/g" \
    -e "s/{{HW_ADDR}}/${hwaddr//\//\/}/g" \
    "$tmpl" > "$tmp"
  # Drop optional fields if unset
  if [[ -z "$mixer" ]]; then
    grep -v 'mixer_control_name' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  if [[ -z "$iface" ]]; then
    grep -v '^[[:space:]]*interface[[:space:]]*=' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  if [[ -z "$hwaddr" ]]; then
    grep -v '^[[:space:]]*hardware_address[[:space:]]*=' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  install -m 0644 "$tmp" "$tgt"
  rm -f "$tmp"
}

derive_hwaddr_from_iface() {
  local iface="$1"
  [[ -n "$iface" ]] || { echo ""; return 0; }
  cat "/sys/class/net/$iface/address" 2>/dev/null | head -n1 || true
}

primary_iface() {
  if command -v ip >/dev/null 2>&1; then
    ip route 2>/dev/null | awk '/^default/ {print $5; exit}'
  fi
}

mac_suffix() {
  local mac="$1"
  echo "$mac" | awk -F: '{print toupper($(NF-1)$(NF))}'
}

default_airplay_name() {
  # Build a stable, unique default name from MAC if available
  local mac="$1"
  if [[ -n "$mac" ]]; then
    echo "Wyse DAC-$(mac_suffix "$mac")"
  else
    echo "Wyse DAC"
  fi
}

ensure_state_dir() {
  install -d -m 0755 "$STATE_DIR"
}

maybe_reset_identity() {
  # Reset shairport AirPlay 2 identity if this looks like a cloned image
  # Uses fingerprint of machine-id and MAC. Only resets when fingerprint absent or changed.
  local mac="$1"
  local machine_id fp current_fp
  machine_id=$(cat /etc/machine-id 2>/dev/null || true)
  fp="${machine_id}|${mac}"

  ensure_state_dir

  if [[ ! -f "$IDENTITY_FILE" ]]; then
    # First-time initialization: clear any pre-populated identity from image
    if [[ -d /var/lib/shairport-sync ]]; then
      echo "[lib] initializing identity (clearing shairport-sync state)" >&2
      systemctl stop shairport-sync.service >/dev/null 2>&1 || true
      rm -rf /var/lib/shairport-sync/* 2>/dev/null || true
    fi
    printf '{"machine_id":"%s","mac":"%s","created":"%s"}\n' "$machine_id" "$mac" "$(ts)" >"$IDENTITY_FILE"
    return 0
  fi

  if command -v jq >/dev/null 2>&1; then
    current_fp=$(jq -r '(.machine_id+"|"+.mac) // empty' "$IDENTITY_FILE" 2>/dev/null || true)
  else
    # Fallback: do not reset on mismatch if jq is unavailable; preserve existing identity
    current_fp="$fp"
  fi
  if [[ "$current_fp" != "$fp" && -n "$fp" ]]; then
    echo "[lib] identity fingerprint changed; resetting shairport identity" >&2
    systemctl stop shairport-sync.service >/dev/null 2>&1 || true
    rm -rf /var/lib/shairport-sync/* 2>/dev/null || true
    printf '{"machine_id":"%s","mac":"%s","updated":"%s"}\n' "$machine_id" "$mac" "$(ts)" >"$IDENTITY_FILE"
  fi
}
