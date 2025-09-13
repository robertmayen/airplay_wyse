#!/usr/bin/env bash
set -euo pipefail

# AirPlay 2 (Shairport Sync + NQPTP) resampling policy helper
# - Discovers PipeWire/ALSA capabilities
# - Chooses Policy A (bit-perfect 44.1) if the sink accepts 44.1
# - Else chooses Policy B (fixed 48k graph; single resampler in PipeWire or ALSA rate plugin)
# - Can apply idempotent config snippets and generate a report
#
# Usage:
#   scripts/airplay_policy.sh discover      # Print discovery + recommended policy
#   sudo scripts/airplay_policy.sh apply    # Apply recommended policy (now verifies; will fallback if needed)
#   sudo scripts/airplay_policy.sh setup    # Apply + best-effort restarts + verify + report
#   AIRPLAY_POLICY=A sudo scripts/airplay_policy.sh apply   # Force policy
#   AIRPLAY_HW=hw:1,0 sudo scripts/airplay_policy.sh apply  # Force ALSA device
#   scripts/airplay_policy.sh report        # Summarize current state
#   sudo scripts/airplay_policy.sh rollback # Remove files created by apply
#
# Notes:
# - Does NOT set shairport output_rate to 48000 (unsupported!)
# - Avoids double-resampling; picks exactly one resampler layer when needed
# - Writes user-level PipeWire configs; writes shairport/ALSA system configs with sudo

ROOT_REQD_MSG="This operation requires root (sudo)."

log() { printf '%s\n' "$*"; }
err() { printf 'ERROR: %s\n' "$*" >&2; }

cmd_exists() { command -v "$1" >/dev/null 2>&1; }

require_root() {
  if [ "${EUID:-$(id -u)}" -ne 0 ]; then
    err "$ROOT_REQD_MSG"; exit 1
  fi
}

_PW_PRESENT=0
_PW_ALSA_DEFAULT=0
_ALSA_PRESENT=0
_SHAIRPORT_PRESENT=0
_SOXR_SUPPORTED=0

_WORKDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
_REPORT="${_WORKDIR}/airplay_policy_report.txt"
_USER_HOME="$HOME"
if [ -n "${SUDO_USER:-}" ]; then
  # Resolve invoking user's home for user-level PipeWire configs
  if cmd_exists getent; then
    _USER_HOME=$(getent passwd "$SUDO_USER" | awk -F: '{print $6}')
  fi
  [ -n "$_USER_HOME" ] || _USER_HOME="/home/$SUDO_USER"
fi

detect_stack() {
  _PW_PRESENT=0
  _PW_ALSA_DEFAULT=0
  _ALSA_PRESENT=0
  _SHAIRPORT_PRESENT=0
  _SOXR_SUPPORTED=0

  if cmd_exists pw-cli; then
    if pw-cli info 0 >/dev/null 2>&1; then _PW_PRESENT=1; fi
  fi
  if [ -e /usr/share/alsa/alsa.conf.d/50-pipewire.conf ] || [ -e /etc/alsa/conf.d/50-pipewire.conf ]; then
    _PW_ALSA_DEFAULT=1
  fi
  if cmd_exists aplay; then _ALSA_PRESENT=1; fi
  if cmd_exists shairport-sync; then _SHAIRPORT_PRESENT=1; fi
  if [ "$_SHAIRPORT_PRESENT" -eq 1 ]; then
    if shairport-sync -V 2>/dev/null | grep -qi "soxr"; then _SOXR_SUPPORTED=1; fi
  fi
}

shairport_unit_scope() {
  # Prints: system | user | none
  if cmd_exists systemctl; then
    if systemctl status shairport-sync >/dev/null 2>&1; then
      echo system; return 0
    fi
    if [ -n "${SUDO_USER:-}" ]; then
      sudo -u "$SUDO_USER" systemctl --user status shairport-sync >/dev/null 2>&1 && { echo user; return 0; }
    else
      systemctl --user status shairport-sync >/dev/null 2>&1 && { echo user; return 0; }
    fi
  fi
  echo none
}

list_alsa_hw() {
  [ "$_ALSA_PRESENT" -eq 1 ] || return 0
  aplay -l 2>/dev/null | awk '
    /^card [0-9]+:/ {
      c=$2; sub(":","",c)
      d_idx=index($0,"device "); d=substr($0,d_idx+7)
      gsub(/[^0-9].*/,"",d)
      print "hw:" c "," d
    }'
}

alsa_hw_supports_44100() {
  local dev="$1"
  # Try to open at 44.1 S16 stereo and ensure exact 44.1 (not coerced)
  local tmp
  tmp=$(mktemp)
  if ! timeout 3 aplay -D "$dev" -r 44100 -f S16_LE -c 2 -d 1 /dev/zero >"$tmp" 2>&1; then
    rm -f "$tmp"; return 1
  fi
  if grep -qi "rate is not accurate" "$tmp"; then
    rm -f "$tmp"; return 1
  fi
  rm -f "$tmp"
  return 0
}

pick_hw_device() {
  # Priority: env AIRPLAY_HW, else first hw supporting 44.1, else first hw
  local env_dev="${AIRPLAY_HW:-}"
  if [ -n "$env_dev" ]; then
    echo "$env_dev"; return 0
  fi
  local first_hw=""; local cand
  while IFS= read -r cand; do
    [ -n "$first_hw" ] || first_hw="$cand"
    if alsa_hw_supports_44100 "$cand"; then
      echo "$cand"; return 0
    fi
  done < <(list_alsa_hw)
  # fallback
  if [ -n "$first_hw" ]; then echo "$first_hw"; fi
}

recommend_policy() {
  # Output: A or B
  detect_stack
  if [ "${AIRPLAY_POLICY:-}" = "A" ] || [ "${AIRPLAY_POLICY:-}" = "B" ]; then
    echo "${AIRPLAY_POLICY}"; return 0
  fi
  if [ "$_ALSA_PRESENT" -eq 1 ]; then
    # If any hw accepts 44100, use A
    local cand
    while IFS= read -r cand; do
      if alsa_hw_supports_44100 "$cand"; then echo A; return 0; fi
    done < <(list_alsa_hw)
  fi
  echo B
}

show_discovery() {
  detect_stack
  log "=== Discovery ==="
  log "PipeWire present: $_PW_PRESENT"
  log "ALSA present: $_ALSA_PRESENT"
  log "Shairport present: $_SHAIRPORT_PRESENT"
  log "Shairport soxr support: $_SOXR_SUPPORTED"
  log "ALSA default is PipeWire: $_PW_ALSA_DEFAULT"
  if [ "$_ALSA_PRESENT" -eq 1 ]; then
    log "ALSA hw devices:" 
    list_alsa_hw | sed 's/^/  - /'
    while IFS= read -r d; do
      if alsa_hw_supports_44100 "$d"; then
        log "  * $d accepts 44.1 kHz"
      else
        log "  * $d does NOT accept 44.1 kHz"
      fi
    done < <(list_alsa_hw)
  fi
  if [ "$_SHAIRPORT_PRESENT" -eq 1 ]; then
    log "Shairport version: $(shairport-sync -V 2>/dev/null || true)"
  fi
  local pol; pol=$(recommend_policy)
  log "Recommended policy: $pol"
}

ensure_dirs() {
  mkdir -p "$_USER_HOME/.config/pipewire/pipewire.conf.d" || true
  mkdir -p "$_USER_HOME/.config/pipewire/client.conf.d" || true
}

apply_pipewire_policy_A() {
  ensure_dirs
  cat > "$_USER_HOME/.config/pipewire/pipewire.conf.d/clock.conf" <<'EOF'
context.properties = {
  default.clock.rate          = 44100
  default.clock.allowed-rates = [ 44100 48000 ]
}
EOF
  # Optional: consistent resampler quality for other clients
  cat > "$_USER_HOME/.config/pipewire/client.conf.d/resample.conf" <<'EOF'
stream.properties = { resample.quality = 10 }
EOF
}

apply_pipewire_policy_B() {
  ensure_dirs
  cat > "$_USER_HOME/.config/pipewire/pipewire.conf.d/clock.conf" <<'EOF'
context.properties = {
  default.clock.rate          = 48000
  default.clock.allowed-rates = [ 48000 44100 ]
}
EOF
  cat > "$_USER_HOME/.config/pipewire/client.conf.d/resample.conf" <<'EOF'
stream.properties = { resample.quality = 10 }
EOF
}

apply_shairport_conf() {
  require_root
  local device="$1"; shift
  local policy="$1"; shift
  local out_rate="auto"
  if [ "$policy" = "A" ]; then out_rate="44100"; fi
  local target_dir="/etc/shairport-sync.conf.d"
  local file="$target_dir/90-airplay.conf"
  mkdir -p "$target_dir"
  # Minimal, idempotent override: only the keys we care about
  local interp="auto"
  if [ "$_SOXR_SUPPORTED" -eq 1 ]; then interp="soxr"; fi
  cat > "$file" <<EOF
// Managed by airplay_policy.sh
general = {
  interpolation = "${interp}";
};
alsa = {
  output_device = "${device}";
  output_rate   = "${out_rate}";
  output_format = "S24_3LE";
};
EOF
  log "Wrote $file"
}

# Verify helpers
verify_policy_A() {
  local device="$1"
  if alsa_hw_supports_44100 "$device"; then return 0; fi
  return 1
}

verify_policy_B_pipewire() {
  # Ensure we can open default at 44.1 which PipeWire will accept and resample if graph is 48
  if [ -n "${SUDO_USER:-}" ]; then
    sudo -u "$SUDO_USER" timeout 3 aplay -D default -r 44100 -f S16_LE -c 2 -d 1 /dev/zero >/dev/null 2>&1
  else
    timeout 3 aplay -D default -r 44100 -f S16_LE -c 2 -d 1 /dev/zero >/dev/null 2>&1
  fi
}

verify_policy_B_alsa() {
  # Ensure the rate PCM opens 44.1 and resamples to 48 for the hw slave
  timeout 3 aplay -D airplay48 -r 44100 -f S16_LE -c 2 -d 1 /dev/zero >/dev/null 2>&1
}

_LAST_POLICY=""
_LAST_DEVICE=""
_LAST_PATH=""

apply_alsa_rate_plugin_policy_B() {
  # ALSA-only host, define a single high-quality rate-conversion PCM
  require_root
  local hwdev="$1"; shift
  local converter="${1:-samplerate_best}"
  local file="/etc/asound.conf"
  # Append or replace a managed block
  local tmp
  tmp=$(mktemp)
  if [ -f "$file" ]; then
    # Remove previous managed block
    awk 'BEGIN{inblk=0}
      /BEGIN AIRPLAY48/ {inblk=1; next}
      /END AIRPLAY48/ {inblk=0; next}
      { if(!inblk) print }' "$file" > "$tmp"
    cat "$tmp" > "$file"
  fi
  cat >> "$file" <<EOF
# BEGIN AIRPLAY48 (managed by airplay_policy.sh)
pcm.airplay48 {
  type rate
  slave {
    pcm "${hwdev}"
    rate 48000
  }
  # Prefer libsamplerate (samplerate_best). Fallback to speexrate quality 10 if unavailable.
  converter "${converter}"
}
# END AIRPLAY48
EOF
  log "Defined pcm.airplay48 in $file"
}

ensure_alsa_rate_pcm_works() {
  # Try a sequence of converters until airplay48 opens
  local hwdev="$1"
  local try
  for try in samplerate_best speexrate_best speexrate_10; do
    apply_alsa_rate_plugin_policy_B "$hwdev" "$try"
    if verify_policy_B_alsa; then return 0; fi
  done
  # As last resort, write without converter line (ALSA default)
  require_root
  local file="/etc/asound.conf" tmp
  tmp=$(mktemp)
  if [ -f "$file" ]; then
    awk 'BEGIN{inblk=0}
      /BEGIN AIRPLAY48/ {inblk=1; next}
      /END AIRPLAY48/ {inblk=0; next}
      { if(!inblk) print }' "$file" > "$tmp"
    cat "$tmp" > "$file"
  fi
  cat >> "$file" <<EOF
# BEGIN AIRPLAY48 (managed by airplay_policy.sh)
pcm.airplay48 {
  type rate
  slave {
    pcm "${hwdev}"
    rate 48000
  }
}
# END AIRPLAY48
EOF
  rm -f "$tmp"
  verify_policy_B_alsa
}

restart_services_note() {
  log "To apply user-level PipeWire changes:"
  log "  systemctl --user restart pipewire pipewire-pulse  # or log out/in"
  log "To apply Shairport changes:"
  log "  sudo systemctl restart shairport-sync"
}

apply_all() {
  detect_stack
  local policy; policy=$(recommend_policy)
  log "Applying policy $policy"

  # Decide output device for shairport
  local device=""
  local scope; scope=$(shairport_unit_scope)
  if [ "$policy" = "A" ]; then
    device=$(pick_hw_device)
    if [ -z "$device" ]; then err "No ALSA hw device found"; exit 1; fi
  else
    if [ "$_PW_PRESENT" -eq 1 ] && [ "$_PW_ALSA_DEFAULT" -eq 1 ] && [ "$scope" = "user" ]; then
      device="default"   # via pipewire-alsa in the same user session
    else
      device=$(pick_hw_device)
      if [ -z "$device" ]; then err "No ALSA hw device found"; exit 1; fi
      ensure_alsa_rate_pcm_works "$device" || true
      device="airplay48"
    fi
  fi

  if [ "$_PW_PRESENT" -eq 1 ]; then
    if [ "$policy" = "A" ]; then apply_pipewire_policy_A; else apply_pipewire_policy_B; fi
  fi

  apply_shairport_conf "$device" "$policy"
  _LAST_POLICY="$policy"; _LAST_DEVICE="$device"; _LAST_PATH="/etc/shairport-sync.conf.d/90-airplay.conf"
  restart_services_note
}

best_effort_restart_services() {
  # Try to restart services automatically when possible
  if cmd_exists systemctl; then
    if [ "$_PW_PRESENT" -eq 1 ]; then
      if [ -n "${SUDO_USER:-}" ]; then
        sudo -u "$SUDO_USER" systemctl --user restart pipewire pipewire-pulse 2>/dev/null || true
      else
        systemctl --user restart pipewire pipewire-pulse 2>/dev/null || true
      fi
    fi
    systemctl restart shairport-sync 2>/dev/null || true
  fi
}

apply_and_verify_with_fallback() {
  apply_all
  local ok=1
  if [ "$_LAST_POLICY" = "A" ]; then
    if verify_policy_A "$_LAST_DEVICE"; then ok=0; fi
  else
    if [ "$_LAST_DEVICE" = "default" ]; then
      if verify_policy_B_pipewire; then ok=0; fi
    else
      if verify_policy_B_alsa; then ok=0; fi
    fi
  fi

  if [ $ok -ne 0 ]; then
    log "Primary policy verification failed; attempting automatic fallback."
    # Flip policy and re-apply once
    if [ "$_LAST_POLICY" = "A" ]; then
      AIRPLAY_POLICY=B apply_all
      if [ "$_LAST_DEVICE" = "default" ]; then
        verify_policy_B_pipewire && ok=0 || ok=1
      else
        verify_policy_B_alsa && ok=0 || ok=1
      fi
    else
      AIRPLAY_POLICY=A apply_all
      verify_policy_A "$_LAST_DEVICE" && ok=0 || ok=1
    fi
  fi

  if [ $ok -ne 0 ]; then
    err "Verification still failing. Please run 'scripts/airplay_policy.sh discover' and check logs."
    return 1
  fi
  return 0
}

report_state() {
  detect_stack
  local outfile="${1:-$_REPORT}"
  : > "$outfile"
  {
    echo "=== Discovery (snapshot) ==="
    show_discovery
    echo
    echo "=== PipeWire configs (user) ==="
    if [ -f "$_USER_HOME/.config/pipewire/pipewire.conf.d/clock.conf" ]; then
      echo "$_USER_HOME/.config/pipewire/pipewire.conf.d/clock.conf:"; sed -n '1,120p' "$_USER_HOME/.config/pipewire/pipewire.conf.d/clock.conf"
    else
      echo "(none)"
    fi
    if [ -f "$_USER_HOME/.config/pipewire/client.conf.d/resample.conf" ]; then
      echo; echo "$_USER_HOME/.config/pipewire/client.conf.d/resample.conf:"; sed -n '1,120p' "$_USER_HOME/.config/pipewire/client.conf.d/resample.conf"
    fi
    echo
    echo "=== Shairport override ==="
    if [ -f "/etc/shairport-sync.conf.d/90-airplay.conf" ]; then
      echo "/etc/shairport-sync.conf.d/90-airplay.conf:"; sed -n '1,160p' "/etc/shairport-sync.conf.d/90-airplay.conf"
    else
      echo "(none)"
    fi
    echo
    echo "=== ALSA rate plugin (if present) ==="
    if [ -f "/etc/asound.conf" ]; then
      rg -n "BEGIN AIRPLAY48|pcm.airplay48|converter|rate 48000" /etc/asound.conf || true
    else
      echo "(no /etc/asound.conf)"
    fi
  } >> "$outfile"
  log "Report written to $outfile"
}

rollback() {
  require_root
  local changed=0
  if [ -f "/etc/shairport-sync.conf.d/90-airplay.conf" ]; then
    rm -f "/etc/shairport-sync.conf.d/90-airplay.conf" && log "Removed /etc/shairport-sync.conf.d/90-airplay.conf" && changed=1
  fi
  if [ -f "/etc/asound.conf" ]; then
    local tmp; tmp=$(mktemp)
    awk 'BEGIN{inblk=0}
      /BEGIN AIRPLAY48/ {inblk=1; next}
      /END AIRPLAY48/ {inblk=0; next}
      { if(!inblk) print }' "/etc/asound.conf" > "$tmp"
    if cmp -s "$tmp" "/etc/asound.conf"; then
      :
    else
      cat "$tmp" > "/etc/asound.conf" && log "Stripped AIRPLAY48 block from /etc/asound.conf" && changed=1
    fi
    rm -f "$tmp"
  fi
  log "User-level PipeWire files (not removed by rollback):"
  log "  ~/.config/pipewire/pipewire.conf.d/clock.conf"
  log "  ~/.config/pipewire/client.conf.d/resample.conf"
  log "You can remove them manually if desired."
  if [ $changed -eq 1 ]; then
    restart_services_note
  fi
}

case "${1:-}" in
  discover)
    show_discovery ;;
  apply)
    if apply_and_verify_with_fallback; then
      best_effort_restart_services
      log "Apply complete and verified (policy: $_LAST_POLICY, device: $_LAST_DEVICE)."
    else
      exit 1
    fi ;;
  setup)
    # Capture baseline snapshot, then apply+verify, then after snapshot
    before="${_WORKDIR}/airplay_policy_report.before.txt"
    after="${_WORKDIR}/airplay_policy_report.after.txt"
    report_state "$before"
    if apply_and_verify_with_fallback; then
      best_effort_restart_services
      report_state "$after"
      log "Setup complete. Reports:"
      log "  Before: $before"
      log "  After : $after"
    else
      exit 1
    fi ;;
  report)
    report_state ;;
  rollback)
    rollback ;;
  *)
    cat <<USAGE
Usage:
  $0 discover            # Probe and recommend a policy
  sudo $0 apply          # Apply recommended (or AIRPLAY_POLICY=A|B) policy
  $0 report              # Write a snapshot report to airplay_policy_report.txt
  sudo $0 rollback       # Remove files created by apply

Environment overrides:
  AIRPLAY_POLICY=A|B     # Force policy
  AIRPLAY_HW=hw:X,Y      # Force ALSA device (e.g., hw:1,0)
USAGE
    ;;
esac
