#!/usr/bin/env bash
set -euo pipefail

# Ensure required packages present and meet minimum versions.
# Broker-only: enqueue root-required operations to /run/airplay/queue; never call sudo.

# Core packages required for basic AirPlay. nqptp is optional on Debian.
REQ_PKGS=(shairport-sync avahi-daemon avahi-utils jq alsa-utils)
OPT_PKGS=(nqptp)

have() { dpkg -s "$1" >/dev/null 2>&1; }
ver() { dpkg-query -W -f='${Version}\n' "$1" 2>/dev/null | awk -F- '{print $1}'; }

# Source versions with repo-relative path; ignore stdout from helper.
# shellcheck disable=SC1091
. "$(dirname "$0")/versions.sh" >/dev/null 2>&1 || true

changed=0
QUEUE_DIR="/run/airplay/queue"
mkdir -p "$QUEUE_DIR" 2>/dev/null || true
did_update=0

# Ensure apt preferences directory via broker, then stage preference files via broker tee (with .in payloads)
# Only enqueue writes when content differs or target file missing.
ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
printf '/usr/bin/install -d -m 0755 /etc/apt/preferences.d\n' >"$QUEUE_DIR/${ts}.${rand}.cmd"
for pref in "$(dirname "$0")"/apt-pins.d/*.pref; do
  [[ -f "$pref" ]] || continue
  base=$(basename "$pref")
  dest="/etc/apt/preferences.d/$base"
  if [[ -f "$dest" ]] && cmp -s "$pref" "$dest"; then
    continue
  fi
  ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
  echo "/usr/bin/tee /etc/apt/preferences.d/$base" >"$QUEUE_DIR/${ts}.${rand}.cmd"
  cp "$pref" "$QUEUE_DIR/${ts}.${rand}.in"
  changed=1
done

# Package installs via broker (best-effort without apt-get update)
for p in "${REQ_PKGS[@]}"; do
  if ! have "$p"; then
    if [[ $did_update -eq 0 ]]; then
      ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
      echo "/usr/bin/apt-get update" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1; did_update=1
    fi
    ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
    echo "/usr/bin/apt-get -y install $p" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1
    continue
  fi
  inst_ver=$(ver "$p")
  min_var="MIN_$(echo "$p" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
  min_ver="${!min_var:-}"
  if [[ -n "$min_ver" ]]; then
    dpkg --compare-versions "$inst_ver" ge "$min_ver" || {
      if [[ $did_update -eq 0 ]]; then
        ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
        echo "/usr/bin/apt-get update" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1; did_update=1
      fi
      ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
      echo "/usr/bin/apt-get -y install $p" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1;
    }
  fi
done

# Optional packages: install only if available in APT or already present
apt_candidate() { apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/ {print $2}'; }
for p in "${OPT_PKGS[@]}"; do
  if have "$p"; then
    inst_ver=$(ver "$p")
    min_var="MIN_$(echo "$p" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
    min_ver="${!min_var:-}"
    if [[ -n "$min_ver" ]]; then
      dpkg --compare-versions "$inst_ver" ge "$min_ver" || {
        ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
        echo "/usr/bin/apt-get -y install $p" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1;
      }
    fi
    continue
  fi
  cand=$(apt_candidate "$p" || echo none)
  if [[ -n "$cand" && "$cand" != "(none)" ]]; then
    if [[ $did_update -eq 0 ]]; then
      ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
      echo "/usr/bin/apt-get update" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1; did_update=1
    fi
    ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
    echo "/usr/bin/apt-get -y install $p" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1
  fi
done

# If a local nqptp .deb exists in the repo, install/upgrade it via broker.
REPO_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
shopt -s nullglob
for deb in "$REPO_DIR"/pkg/nqptp_*.deb; do
  # Compare versions to avoid re-installing the same build repeatedly
  deb_ver=$(dpkg-deb -f "$deb" Version 2>/dev/null || echo "")
  if have nqptp; then
    inst_ver=$(ver nqptp)
    if [[ -n "$deb_ver" ]] && dpkg --compare-versions "$inst_ver" ge "$deb_ver"; then
      continue
    fi
  fi
  ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
  echo "/usr/bin/dpkg -i /opt/airplay_wyse/pkg/$(basename "$deb")" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1
done

# If a local shairport-sync .deb is provided, install/upgrade it via broker too
for deb in "$REPO_DIR"/pkg/shairport-sync_*.deb; do
  deb_ver=$(dpkg-deb -f "$deb" Version 2>/dev/null || echo "")
  if have shairport-sync; then
    inst_ver=$(ver shairport-sync)
    if [[ -n "$deb_ver" ]] && dpkg --compare-versions "$inst_ver" ge "$deb_ver"; then
      continue
    fi
  fi
  ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
  echo "/usr/bin/dpkg -i /opt/airplay_wyse/pkg/$(basename "$deb")" >"$QUEUE_DIR/${ts}.${rand}.cmd"; changed=1
done

exit $changed
