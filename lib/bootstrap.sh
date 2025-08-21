#!/usr/bin/env bash
set -euo pipefail

# Shared bootstrap predicate and helpers for updater + converge

# Returns 0 if configured; non-zero otherwise. Emits nothing unless asked.
is_bootstrapped() {
  # Preconditions: sudo present, wrapper or systemd-run allowed, functional check
  # 1) sudoers drop-in exists, owned root:root, mode 0440, and validates
  local sudoers="/etc/sudoers.d/airplay-wyse"
  if ! command -v sudo >/dev/null 2>&1; then return 1; fi
  if [[ ! -f "$sudoers" ]]; then return 2; fi
  # Ownership and mode
  local owner group mode
  owner=$(stat -c %U "$sudoers" 2>/dev/null || stat -f %Su "$sudoers" 2>/dev/null || echo unknown)
  group=$(stat -c %G "$sudoers" 2>/dev/null || stat -f %Sg "$sudoers" 2>/dev/null || echo unknown)
  mode=$(stat -c %a "$sudoers" 2>/dev/null || stat -f %Lp "$sudoers" 2>/dev/null || echo unknown)
  if [[ "$owner" != "root" || "$group" != "root" || "$mode" != "440" ]]; then return 3; fi
  # Syntax check (best effort)
  if command -v visudo >/dev/null 2>&1; then
    visudo -cf "$sudoers" >/dev/null 2>&1 || return 4
  fi
  # Content must allow either wrapper or systemd-run
  if ! grep -Eq "^\s*airplay\s+ALL=\(root\)\s+NOPASSWD:\s+(/usr/local/sbin/airplay-sd-run|/usr/bin/systemd-run)\b" "$sudoers"; then
    return 5
  fi
  # Wrapper present (preferred)
  if [[ ! -x /usr/local/sbin/airplay-sd-run ]]; then
    # Allow direct systemd-run path if permitted by sudoers content
    if ! grep -Eq "^\s*airplay\s+ALL=\(root\)\s+NOPASSWD:\s+/usr/bin/systemd-run\b" "$sudoers"; then
      return 6
    fi
  fi
  # Functional check: as airplay, run a no-op systemd-run and expect RC=0
  if [[ "$(id -un)" == "airplay" ]]; then
    sudo -n /usr/bin/systemd-run --wait --collect --unit "apw-selftest-$$" /bin/true >/dev/null 2>&1 || return 7
  else
    # If root or another user, test from airplay context
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
  [[ -f "$sudoers" ]] || msgs+=("sudoers_dropin_missing")
  if [[ -f "$sudoers" ]]; then
    local owner group mode
    owner=$(stat -c %U "$sudoers" 2>/dev/null || stat -f %Su "$sudoers" 2>/dev/null || echo unknown)
    group=$(stat -c %G "$sudoers" 2>/dev/null || stat -f %Sg "$sudoers" 2>/dev/null || echo unknown)
    mode=$(stat -c %a "$sudoers" 2>/dev/null || stat -f %Lp "$sudoers" 2>/dev/null || echo unknown)
    [[ "$owner" == "root" ]] || msgs+=("sudoers_owner_not_root")
    [[ "$group" == "root" ]] || msgs+=("sudoers_group_not_root")
    [[ "$mode" == "440" ]] || msgs+=("sudoers_mode_not_0440")
    if command -v visudo >/dev/null 2>&1; then
      visudo -cf "$sudoers" >/dev/null 2>&1 || msgs+=("sudoers_invalid_syntax")
    fi
    grep -Eq "^\s*airplay\s+ALL=\(root\)\s+NOPASSWD:\s+(/usr/local/sbin/airplay-sd-run|/usr/bin/systemd-run)\b" "$sudoers" || msgs+=("nopass_rule_missing")
  fi
  [[ -x /usr/local/sbin/airplay-sd-run ]] || msgs+=("wrapper_missing")
  # Functional test result
  if [[ "$(id -un)" == "airplay" ]]; then
    sudo -n /usr/bin/systemd-run --wait --collect --unit "apw-selftest-$$" /bin/true >/dev/null 2>&1 || msgs+=("functional_check_failed")
  else
    if id -u airplay >/dev/null 2>&1; then
      sudo -u airplay -n sudo -n /usr/bin/systemd-run --wait --collect --unit "apw-selftest-$$" /bin/true >/dev/null 2>&1 || msgs+=("functional_check_failed")
    else
      msgs+=("functional_check_failed")
    fi
  fi
  echo "${msgs[*]:-}" | sed 's/ /;/g'
}

