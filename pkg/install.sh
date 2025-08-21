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

# Define REPO_DIR early before any usage
REPO_DIR="$(cd "$(dirname "$0")"/.. && pwd)"

changed=0
systemd_run() { sudo /usr/local/sbin/airplay-sd-run pkg-ensure -- "$*"; }
did_update=0

# Ensure apt preferences directory via broker, then stage preference files via broker tee (with .in payloads)
# Only enqueue writes when content differs or target file missing.
systemd_run "/usr/bin/install -d -m 0755 /etc/apt/preferences.d"
for pref in "$(dirname "$0")"/apt-pins.d/*.pref; do
  [[ -f "$pref" ]] || continue
  base=$(basename "$pref")
  dest="/etc/apt/preferences.d/$base"
  if [[ -f "$dest" ]] && cmp -s "$pref" "$dest"; then
    continue
  fi
  systemd_run "/usr/bin/install -m 0644 '$pref' '/etc/apt/preferences.d/$base'"
  changed=1
done

# Package installs via broker (best-effort without apt-get update)
for p in "${REQ_PKGS[@]}"; do
  if ! have "$p"; then
    if [[ $did_update -eq 0 ]]; then
      systemd_run "/usr/bin/apt-get update"; changed=1; did_update=1
    fi
    systemd_run "/usr/bin/apt-get -y install $p"; changed=1
    continue
  fi
  inst_ver=$(ver "$p")
  min_var="MIN_$(echo "$p" | tr '[:lower:]' '[:upper:]' | tr '-' '_')"
  min_ver="${!min_var:-}"
  if [[ -n "$min_ver" ]]; then
    dpkg --compare-versions "$inst_ver" ge "$min_ver" || {
      if [[ $did_update -eq 0 ]]; then systemd_run "/usr/bin/apt-get update"; changed=1; did_update=1; fi
      systemd_run "/usr/bin/apt-get -y install $p"; changed=1;
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
    if [[ $did_update -eq 0 ]]; then systemd_run "/usr/bin/apt-get update"; changed=1; did_update=1; fi
    systemd_run "/usr/bin/apt-get -y install $p"; changed=1
  else
    # No APT candidate for optional package - prepare for source build
    echo "[INFO] Package $p not available in APT - will attempt source build if needed"
  fi
done

# Install minimal build dependencies if we need to build from source
BUILD_DEPS=(build-essential autoconf automake libtool pkg-config git)
need_build_deps=0

# Check if we need to build nqptp from source
if ! have nqptp; then
  cand=$(apt_candidate nqptp || echo none)
  if [[ -z "$cand" || "$cand" == "(none)" ]]; then
    # No APT package and not installed - we'll need to build
    if [[ ! -f "$REPO_DIR"/pkg/nqptp_*.deb ]]; then
      need_build_deps=1
      echo "[INFO] nqptp needs to be built from source - ensuring build dependencies"
    fi
  fi
fi

# Install build dependencies if needed
if [[ $need_build_deps -eq 1 ]]; then
  for dep in "${BUILD_DEPS[@]}"; do
    if ! have "$dep"; then
      echo "[INFO] Installing build dependency: $dep"
      systemd_run "/usr/bin/apt-get -y install $dep" || {
        echo "[WARN] Failed to install $dep - build may fail"
      }
      changed=1
    fi
  done
fi

# If a local nqptp .deb exists in the repo, install/upgrade it via broker.
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
  systemd_run "/usr/bin/dpkg -i /opt/airplay_wyse/pkg/$(basename "$deb")"; changed=1
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
  systemd_run "/usr/bin/dpkg -i /opt/airplay_wyse/pkg/$(basename "$deb")"; changed=1
done

exit $changed
