#!/usr/bin/env bash
set -euo pipefail

# Shared helpers for AirPlay Wyse scripts

ts() {
  # Portable ISO-8601 UTC timestamp
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

STATE_DIR="/var/lib/airplay_wyse"
IDENTITY_FILE="$STATE_DIR/instance.json"
AUDIO_SETTINGS_ERROR=""

json_field() {
  # Extract a single JSON field from a compact object string.
  # Prefers jq when available; falls back to a light awk parser.
  local json="$1" key="$2"
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$json" | jq -r --arg key "$key" '.[$key] // empty'
  else
    printf '%s' "$json" |
      awk -v key="$key" '
        BEGIN { FS="[:,{}]" }
        {
          for (i = 1; i <= NF; i++) {
            gsub(/^[ \t\r\n\"]+|[ \t\r\n\"]+$/, "", $i)
            if ($i == key) {
              val=$(i+1)
              gsub(/^[ \t\r\n\"]+|[ \t\r\n\"]+$/, "", val)
              print val
              exit
            }
          }
        }
      '
  fi
}

shairport_has_soxr() {
  if command -v shairport-sync >/dev/null 2>&1; then
    shairport-sync -V 2>&1 | grep -q 'soxr'
  else
    return 1
  fi
}

resolve_audio_settings() {
  # Decide ALSA device/output/interpolation based on alsa-policy-ensure output when present.
  # Args: <repo_dir> [manual_device]
  local repo_dir="$1" manual_device="${2:-}"
  local device output_rate interp policy_json anchor soxr_required
  AUDIO_SETTINGS_ERROR=""

  if [[ -x "$repo_dir/bin/alsa-policy-ensure" ]]; then
    policy_json=$("$repo_dir/bin/alsa-policy-ensure")
    anchor=$(json_field "$policy_json" "anchor_hz" | tr -dc '0-9')
    soxr_required=$(json_field "$policy_json" "soxr_required" | tr -dc '0-9')
    device="default"
    if [[ "${soxr_required:-0}" -eq 1 ]]; then
      output_rate="${anchor:-}"
      if shairport_has_soxr; then
        interp="soxr"
      else
        AUDIO_SETTINGS_ERROR="hardware anchored at ${anchor:-48000} Hz but shairport-sync lacks libsoxr; rebuild with --with-soxr or install the AirPlay 2 package"
        return 1
      fi
    else
      output_rate=""
      if shairport_has_soxr; then interp="soxr"; else interp=""; fi
    fi
  else
    device="$manual_device"
    if [[ -z "$device" ]]; then
      if [[ -x "$repo_dir/bin/alsa-probe" ]]; then
        device="$($repo_dir/bin/alsa-probe || true)"
        device="${device:-hw:0,0}"
      else
        device="hw:0,0"
      fi
    fi
    output_rate=""
    interp=""
  fi

  printf '%s|%s|%s\n' "$device" "${output_rate:-}" "${interp:-}"
}

render_shairport_conf() {
  # Args: <template> <target> <name> <device> <mixer> <iface> <hwaddr> [output_rate] [statistics] [interpolation]
  local tmpl="$1" tgt="$2" name="$3" device="$4" mixer="$5" iface="$6" hwaddr="$7" rate="${8:-}" stats="${9:-}" interp="${10:-}"
  [[ -f "$tmpl" ]] || { echo "[lib] missing template: $tmpl" >&2; return 1; }

  local tmp
  tmp=$(mktemp)
  sed \
    -e "s/{{AIRPLAY_NAME}}/${name//\//\/}/g" \
    -e "s/{{ALSA_DEVICE}}/${device//\//\/}/g" \
    -e "s/{{ALSA_MIXER}}/${mixer//\//\/}/g" \
    -e "s/{{AVAHI_IFACE}}/${iface//\//\/}/g" \
    -e "s/{{HW_ADDR}}/${hwaddr//\//\/}/g" \
    -e "s/{{ALSA_OUTPUT_RATE}}/${rate//\//\/}/g" \
    -e "s/{{STATISTICS}}/${stats//\//\/}/g" \
    -e "s/{{INTERPOLATION}}/${interp//\//\/}/g" \
    "$tmpl" > "$tmp"
  # Drop optional fields if unset
  if [[ -z "$mixer" ]]; then
    grep -v 'mixer_control_name' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  if [[ -z "$rate" ]]; then
    grep -v '^[[:space:]]*output_rate[[:space:]]*=' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  if [[ -z "$interp" ]]; then
    grep -v '^[[:space:]]*interpolation[[:space:]]*=' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  if [[ -z "$iface" ]]; then
    grep -v '^[[:space:]]*interface[[:space:]]*=' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  if [[ -z "$hwaddr" ]]; then
    grep -v '^[[:space:]]*hardware_address[[:space:]]*=' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  if [[ -z "$stats" ]]; then
    grep -v '^[[:space:]]*statistics[[:space:]]*=' "$tmp" > "${tmp}.2" && mv "${tmp}.2" "$tmp"
  fi
  install -m 0644 "$tmp" "$tgt"
  rm -f "$tmp"
}

derive_hwaddr_from_iface() {
  local iface="$1"
  [[ -n "$iface" ]] || { echo ""; return 0; }
  cat "/sys/class/net/$iface/address" 2>/dev/null | head -n1 || true
}

state_dir_from_systemd() {
  if command -v systemctl >/dev/null 2>&1; then
    local sd
    sd=$(systemctl show -p StateDirectory shairport-sync 2>/dev/null | awk -F= '/StateDirectory=/{print $2}')
    if [[ -n "$sd" ]]; then
      case "$sd" in
        /*) echo "$sd" ;;
        *) echo "/var/lib/$sd" ;;
      esac
    fi
  fi
}

shairport_state_dirs() {
  # Echo candidate state directories, one per line, first the most likely
  local sd
  sd=$(state_dir_from_systemd || true)
  if [[ -n "$sd" ]]; then echo "$sd"; fi
  echo "/var/lib/shairport-sync"
  echo "/var/cache/shairport-sync"
  echo "/var/lib/shairport"
  echo "/var/cache/shairport"
}

clear_shairport_state() {
  # Stop service then clear likely state dirs; tolerant if absent
  systemctl stop shairport-sync.service >/dev/null 2>&1 || true
  local d
  while IFS= read -r d; do
    [[ -n "$d" ]] || continue
    rm -rf "$d"/* 2>/dev/null || true
  done < <(shairport_state_dirs)
  # Also try service user's XDG directories if any
  if command -v systemctl >/dev/null 2>&1; then
    local sv_user homedir
    sv_user=$(systemctl show -p User shairport-sync 2>/dev/null | awk -F= '/User=/{print $2}')
    if [[ -n "$sv_user" ]]; then
      homedir=$(getent passwd "$sv_user" 2>/dev/null | awk -F: '{print $6}')
      if [[ -n "$homedir" && -d "$homedir" ]]; then
        rm -rf "$homedir/.config/shairport-sync" 2>/dev/null || true
        rm -rf "$homedir/.local/share/shairport-sync" 2>/dev/null || true
        rm -rf "$homedir/.cache/shairport-sync" 2>/dev/null || true
      fi
    fi
  fi
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
  # Uses fingerprint of machine-id, hostname and MAC. Only resets when fingerprint absent or changed.
  local mac="$1"
  local machine_id host fp current_fp
  machine_id=$(cat /etc/machine-id 2>/dev/null || true)
  host=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo unknown)
  fp="${machine_id}|${host}|${mac}"

  ensure_state_dir

  if [[ ! -f "$IDENTITY_FILE" ]]; then
    # First-time initialization: clear any pre-populated identity from image
    echo "[lib] initializing identity (clearing shairport state)" >&2
    clear_shairport_state
    printf '{"machine_id":"%s","host":"%s","mac":"%s","created":"%s"}\n' "$machine_id" "$host" "$mac" "$(ts)" >"$IDENTITY_FILE"
    return 0
  fi

  if command -v jq >/dev/null 2>&1; then
    current_fp=$(jq -r '((.machine_id//empty)+"|"+(.host//empty)+"|"+(.mac//empty)) // empty' "$IDENTITY_FILE" 2>/dev/null || true)
  else
    # Fallback: parse JSON with awk/sed (best-effort)
    current_fp=$(awk -F'"' '/"machine_id"/{mid=$4} /"host"/{h=$4} /"mac"/{mac=$4} END{if(mid!="" && mac!="") print mid"|"h"|"mac}' "$IDENTITY_FILE" 2>/dev/null || true)
  fi
  if [[ "$current_fp" != "$fp" && -n "$fp" ]]; then
    echo "[lib] identity fingerprint changed; resetting shairport identity" >&2
    clear_shairport_state
    printf '{"machine_id":"%s","host":"%s","mac":"%s","updated":"%s"}\n' "$machine_id" "$host" "$mac" "$(ts)" >"$IDENTITY_FILE"
  fi
}
