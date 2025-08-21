#!/usr/bin/env bash
set -euo pipefail

# Build a local nqptp .deb from source and drop it into pkg/ as nqptp_<ver>_<arch>.deb
# Optionally install the built package directly (on-device) with --install-directly.
# Usage:
#   pkg/build-nqptp.sh [--ref <git-ref>] [--repo <url>] [--no-clean] [--install-directly]
#
# Notes:
# - Run on a Debian/Ubuntu build host (not macOS). Requires: git, autoreconf (autoconf, automake, libtool),
#   make, gcc, pkg-config, dpkg-dev, libmd-dev (or equivalent), libsystemd-dev.
# - The resulting .deb is intended to be committed/tagged with this repo and installed on devices by converge
#   via the broker using: /usr/bin/dpkg -i /opt/airplay_wyse/pkg/nqptp_*.deb

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
WORK_DIR="$(mktemp -d)"
SRC_URL="https://github.com/mikebrady/nqptp"
GIT_REF=""
CLEANUP=1
INSTALL_DIRECT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)
      GIT_REF="$2"; shift 2;;
    --repo)
      SRC_URL="$2"; shift 2;;
    --no-clean)
      CLEANUP=0; shift;;
    --install-directly)
      INSTALL_DIRECT=1; shift;;
    *)
      echo "Unknown arg: $1" >&2; exit 2;;
  esac
done

echo "[build-nqptp] Using source: $SRC_URL ${GIT_REF:+(ref $GIT_REF)}"
echo "[build-nqptp] Working in: $WORK_DIR"

cleanup() {
  [[ $CLEANUP -eq 1 ]] && rm -rf "$WORK_DIR" || true
}
trap cleanup EXIT

SRC_DIR="$WORK_DIR/src"
PKG_ROOT="$WORK_DIR/pkgroot"
mkdir -p "$SRC_DIR" "$PKG_ROOT"

echo "[build-nqptp] Cloning source…"
if [[ -n "$GIT_REF" ]]; then
  git clone --depth 1 --branch "$GIT_REF" "$SRC_URL" "$SRC_DIR"
else
  git clone "$SRC_URL" "$SRC_DIR"
fi

pushd "$SRC_DIR" >/dev/null

echo "[build-nqptp] Preparing and building…"
autoreconf -fi
./configure --prefix=/usr --with-systemd-startup
make -j"$(nproc || echo 2)"

# Discover version metadata
VER_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo 0.0.0)
GIT_SHA=$(git rev-parse --short HEAD)
DEB_VER="${VER_TAG}+git${GIT_SHA}"
ARCH=$(dpkg --print-architecture)

echo "[build-nqptp] Staging install…"
make DESTDIR="$PKG_ROOT" install

# Control metadata
DEBIAN_DIR="$PKG_ROOT/DEBIAN"
mkdir -p "$DEBIAN_DIR"
cat >"$DEBIAN_DIR/control" <<EOF
Package: nqptp
Version: $DEB_VER
Section: sound
Priority: optional
Architecture: $ARCH
Maintainer: airplay_wyse <maintainers@example>
Depends: systemd
Description: NQPTP daemon for Shairport Sync (packaged by airplay_wyse)
 Built from $SRC_URL @ $GIT_SHA
EOF

cat >"$DEBIAN_DIR/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload || true
fi
exit 0
EOF
chmod 0755 "$DEBIAN_DIR/postinst"

OUT_DEB="$REPO_DIR/pkg/nqptp_${DEB_VER}_${ARCH}.deb"
echo "[build-nqptp] Building package: $OUT_DEB"
dpkg-deb --build "$PKG_ROOT" "$OUT_DEB"

popd >/dev/null

echo "[build-nqptp] Done: $OUT_DEB"

if [[ $INSTALL_DIRECT -eq 1 ]]; then
  echo "[build-nqptp] Installing built package: $OUT_DEB"
  dpkg -i "$OUT_DEB" || apt-get -y -f install
  if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
    systemctl enable nqptp.service || true
    systemctl restart nqptp.service || systemctl start nqptp.service || true
  fi
fi
