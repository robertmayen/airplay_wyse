#!/usr/bin/env bash
set -euo pipefail

# Build a local shairport-sync .deb with AirPlay 2 (RAOP2) enabled and drop it into pkg/ as
# shairport-sync_<ver>_<arch>.deb. Run on a Debian build host.
# Optionally install the built package directly (on-device) with --install-directly.
#
# Usage:
#   pkg/build-shairport-sync.sh [--ref <git-ref>] [--repo <url>] [--no-clean] [--install-directly]

SRC_URL="https://github.com/mikebrady/shairport-sync"
GIT_REF=""
# Use writable temp location (Wyse has read-only /tmp and /var/tmp)
TMPDIR="/run/airplay/tmp"
mkdir -p "$TMPDIR" 2>/dev/null || true
WORK_DIR="$(mktemp -d -p "$TMPDIR")"
CLEAN=1
INSTALL_DIRECT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) GIT_REF="$2"; shift 2 ;;
    --repo) SRC_URL="$2"; shift 2 ;;
    --no-clean) CLEAN=0; shift ;;
    --install-directly) INSTALL_DIRECT=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

echo "[build-shairport] Using source: $SRC_URL ${GIT_REF:+(ref $GIT_REF)}"
echo "[build-shairport] Working in: $WORK_DIR"

cd "$WORK_DIR"
echo "[build-shairport] Cloning source…"
git clone "$SRC_URL" shairport-sync
cd shairport-sync
if [[ -n "$GIT_REF" ]]; then git checkout "$GIT_REF"; fi

echo "[build-shairport] Preparing and building…"
autoreconf -fi
./configure \
  --with-ssl=openssl \
  --with-avahi \
  --with-alsa \
  --with-systemd \
  --with-soxr \
  --with-metadata \
  --with-convolution \
  --with-dbus \
  --with-raop2

# Build a Debian package if supported; otherwise create a simple .deb
if grep -q '^debian' <<< "$(ls -1)" && command -v dpkg-buildpackage >/dev/null 2>&1; then
  echo "[build-shairport] Building via dpkg-buildpackage…"
  dpkg-buildpackage -b -us -uc
  cd ..
  DEB=$(ls -1 shairport-sync_*_*.deb | head -n1 || true)
else
  echo "[build-shairport] Building via make deb…"
  make deb || {
    echo "[build-shairport] make deb failed; attempting fallback packaging"
    make
    DESTDIR="$PWD/pkgroot" make install
    ver=$(git describe --tags --always | sed 's/^v//')
    mkdir -p pkgroot/DEBIAN
    cat > pkgroot/DEBIAN/control <<EOF
Package: shairport-sync
Version: ${ver}
Section: sound
Priority: optional
Architecture: $(dpkg --print-architecture)
Maintainer: airplay_wyse
Description: Shairport Sync with AirPlay 2 (RAOP2) support
EOF
    dpkg-deb --build pkgroot "../shairport-sync_${ver}_$(dpkg --print-architecture).deb"
    cd ..
    DEB=$(ls -1 shairport-sync_*_*.deb | head -n1 || true)
  }
fi

if [[ -n "${DEB:-}" && -f "$DEB" ]]; then
  echo "[build-shairport] Built package: $DEB"
  DEST_REPO="$(cd "$(dirname "$0")"/.. && pwd)"
  
  if [[ $INSTALL_DIRECT -eq 1 ]]; then
    echo "[build-shairport] Installing built package directly: $DEB"
    dpkg -i "$DEB" || apt-get -y -f install
    if command -v systemctl >/dev/null 2>&1; then
      systemctl daemon-reload || true
      systemctl enable shairport-sync.service || true
      systemctl restart shairport-sync.service || systemctl start shairport-sync.service || true
    fi
  else
    cp -v "$DEB" "$DEST_REPO/pkg/"
    echo "[build-shairport] Copied to: $DEST_REPO/pkg/$(basename "$DEB")"
  fi
else
  echo "[build-shairport] Failed to produce a .deb" >&2
  exit 1
fi

cleanup() {
  local exit_code=$?
  
  if [[ $CLEAN -eq 1 ]]; then
    echo "[build-shairport] Cleaning up $WORK_DIR"
    rm -rf "$WORK_DIR"
  else
    echo "[build-shairport] Left build dir: $WORK_DIR"
  fi
  
  # Error recovery: ensure sudo is still functional
  if [[ $exit_code -ne 0 ]]; then
    echo "[build-shairport] Build failed with exit code $exit_code"
    # Test sudo functionality
    if ! sudo -n true 2>/dev/null; then
      echo "[build-shairport] WARNING: sudo may need reconfiguration"
      echo "[build-shairport] To fix: visudo -cf /etc/sudoers.d/airplay-wyse"
    fi
  fi
  
  return $exit_code
}

# Set up cleanup trap
trap cleanup EXIT

exit 0
