#!/usr/bin/env bash
set -euo pipefail

# Diagnostics for ALSA policy / shairport dependency failures.
# Collects environment details, validates prerequisites, and replays the
# alsa-policy helper inside the same sanitized environment systemd uses.

OUT_DIR="${AW_DEBUG_DIR:-/tmp/aw-debug}"
LOG="$OUT_DIR/alsa-policy-debug.log"
HELPER="${AW_HELPER:-/usr/local/libexec/airplay_wyse/alsa-policy-ensure}"
DEFAULTS_FILE="/etc/default/airplay_wyse"

mkdir -p "$OUT_DIR"
: >"$LOG"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { printf '%s [debug-alsa-policy] %s\n' "$(ts)" "$*" | tee -a "$LOG"; }
hr() { printf '%s\n' "----------------------------------------------------------------------" | tee -a "$LOG"; }

ensure_root() {
  if [[ $(id -u) -ne 0 ]]; then
    log "ERROR: run as root (sudo) so we can read system state and execute the helper."
    exit 1
  fi
}

capture() {
  local title="$1"; shift
  hr
  log "$title"
  if ! "${@}" >>"$LOG" 2>&1; then
    log "command failed: $*"
    return 1
  fi
}

capture_cmd() {
  local title="$1"; shift
  hr
  log "$title"
  { printf '$ %s\n' "$*"; "$@"; } >>"$LOG" 2>&1 || {
    log "command failed: $*"
    return 1
  }
}

check_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    log "found: $path"
  else
    log "MISSING: $path"
  fi
}

collect_env() {
  capture_cmd "System identifiers" uname -a
  capture_cmd "OS release" bash -lc 'cat /etc/os-release'
  capture_cmd "Audio hardware" bash -lc 'aplay -l || true'
  capture_cmd "Current ALSA policy JSON" bash -lc 'cat /var/lib/airplay_wyse/alsa-policy.json 2>/dev/null || true'
  capture_cmd "Current /etc/asound.conf" bash -lc 'cat /etc/asound.conf 2>/dev/null || true'
  capture_cmd "airplay_wyse defaults" bash -lc "cat '$DEFAULTS_FILE' 2>/dev/null || true"
  capture_cmd "shairport-sync version" bash -lc 'command -v shairport-sync >/dev/null 2>&1 && shairport-sync -V 2>&1 || echo "shairport-sync not in PATH"'
  capture_cmd "shairport-sync linked libs" bash -lc 'command -v shairport-sync >/dev/null 2>&1 && ldd "$(command -v shairport-sync)" 2>/dev/null || true'
  capture_cmd "nqptp version" bash -lc 'command -v nqptp >/dev/null 2>&1 && nqptp -V 2>/dev/null || true'
  capture_cmd "Systemd status (shairport + policy)" bash -lc 'systemctl status shairport-sync.service airplay-wyse-alsa-policy.service --no-pager || true'
}

run_helper_trace() {
  if [[ ! -x "$HELPER" ]]; then
    log "ERROR: helper not executable at $HELPER"
    return 1
  fi
  hr
  log "Tracing helper inside sanitized environment: $HELPER"
  local trace="$OUT_DIR/alsa-policy-trace.sh"
  cat >"$trace" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
exec >/tmp/aw-helper-trace.log 2>&1
set -x
"$HELPER"
EOS
  chmod +x "$trace"
  if ! env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
      HELPER="$HELPER" bash "$trace"; then
    log "helper exited non-zero (expected if it is failing under systemd)"
  fi
  capture_cmd "Helper trace" bash -lc 'cat /tmp/aw-helper-trace.log 2>/dev/null'
  rm -f "$trace"
}

summarize() {
  hr
  if command -v shairport-sync >/dev/null 2>&1; then
    local sh_v
    sh_v=$(shairport-sync -V 2>/dev/null || true)
    if grep -qi 'AirPlay2' <<<"$sh_v"; then
      log "Shairport reports AirPlay 2 support."
    else
      log "WARN: shairport-sync -V did not mention AirPlay 2."
    fi
    if grep -qi 'soxr' <<<"$sh_v"; then
      log "Shairport reports libsoxr support."
    else
      log "WARN: shairport-sync lacks libsoxr; helper will require ALSA_FORCE_ANCHOR=44100 or a rebuilt binary."
    fi
  else
    log "WARN: shairport-sync not found in PATH."
  fi
  if grep -q 'soxr_required":1' /var/lib/airplay_wyse/alsa-policy.json 2>/dev/null; then
    log "Current policy demands soxr (anchor=48000)."
  fi
  log "Detailed log saved to $LOG"
}

main() {
  ensure_root
  log "Starting ALSA policy diagnostics"
  check_file "$HELPER"
  collect_env
  run_helper_trace
  summarize
}

main "$@"
