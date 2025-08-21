#!/usr/bin/env bash
set -euo pipefail

# Shared bootstrap predicate and helpers for updater + converge

# Returns 0 if configured; non-zero otherwise. Emits nothing unless asked.
is_bootstrapped() {
  # Single privileged check: prefer using wrapper; fall back to functional test.
  local sudoers="/etc/sudoers.d/airplay-wyse"
  if ! command -v sudo >/dev/null 2>&1; then return 1; fi
  # If wrapper exists, use it to run privileged validations (no unprivileged reads)
  if [[ -x /usr/local/sbin/airplay-sd-run ]]; then
    # Validate sudoers syntax under root using visudo; avoid unprivileged reads
    sudo -n /usr/local/sbin/airplay-sd-run svc-restart -- \
      "/usr/sbin/visudo -cf '$sudoers'" >/dev/null 2>&1 || return 2
  fi
  # Functional check: as airplay, attempt NOPASSWD systemd-run
  if [[ "$(id -un)" == "airplay" ]]; then
    sudo -n /usr/bin/systemd-run --wait --collect --unit "apw-selftest-$$" /bin/true >/dev/null 2>&1 || return 7
  else
    if id -u airplay >/dev/null 2>&1; then
      sudo -u airplay -n sudo -n /usr/bin/systemd-run --wait --collect --unit "apw-selftest-$$" /bin/true >/dev/null 2>&1 || return 7
    else
      return 7
    fi
  fi
  return 0
}

# Print missing conditions (one-line, semicolon-separated) for journald
bootstrap_diagnose() {
  local msgs=()
  local sudoers="/etc/sudoers.d/airplay-wyse"
  command -v sudo >/dev/null 2>&1 || msgs+=("sudo_missing")
  
  # Check if sudoers file exists first
  if [[ ! -f "$sudoers" ]]; then
    msgs+=("sudoers_file_missing")
  else
    # Only perform sudoers validations through privileged wrapper to avoid permission errors
    if [[ -x /usr/local/sbin/airplay-sd-run ]]; then
      # Try wrapper-based validation first
      if ! sudo -n /usr/local/sbin/airplay-sd-run svc-restart -- \
        "/usr/sbin/visudo -cf '$sudoers'" >/dev/null 2>&1; then
        msgs+=("sudoers_invalid_syntax")
      fi
      # Ownership and mode checks
      local meta
      meta=$(sudo -n /usr/local/sbin/airplay-sd-run svc-restart -- \
        "stat -c '%U:%G:%a' '$sudoers' 2>/dev/null || stat -f '%Su:%Sg:%Lp' '$sudoers' 2>/dev/null" 2>/dev/null || echo)
      [[ "$meta" == root:root:440 ]] || msgs+=("sudoers_meta_incorrect")
    else
      # Fallback: try direct sudo validation if wrapper missing
      if command -v visudo >/dev/null 2>&1; then
        if ! sudo -n visudo -cf "$sudoers" >/dev/null 2>&1; then
          msgs+=("sudoers_invalid_syntax")
        fi
      fi
      msgs+=("wrapper_missing")
    fi
  fi
  
  [[ -x /usr/local/sbin/airplay-sd-run ]] || msgs+=("wrapper_missing")
  
  # Functional test result with better error handling
  local functional_ok=0
  if [[ "$(id -un)" == "airplay" ]]; then
    if sudo -n /usr/bin/systemd-run --wait --collect --unit "apw-selftest-$$" /bin/true >/dev/null 2>&1; then
      functional_ok=1
    fi
  else
    if id -u airplay >/dev/null 2>&1; then
      if sudo -u airplay -n sudo -n /usr/bin/systemd-run --wait --collect --unit "apw-selftest-$$" /bin/true >/dev/null 2>&1; then
        functional_ok=1
      fi
    fi
  fi
  
  [[ $functional_ok -eq 1 ]] || msgs+=("functional_check_failed")
  
  echo "${msgs[*]:-}" | sed 's/ /;/g'
}
