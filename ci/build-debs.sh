#!/usr/bin/env bash
# Build private amd64 .debs (libalac, nqptp, shairport-sync) inside debian:13.
#
# Usage: build-debs.sh <sps_ver> <sps_commit> <nqptp_ver> <nqptp_commit> <alac_sha> <outdir>
#
# Prefix is /usr/local — matches the role's unit templates and the fleet's
# existing source installs (private packages; Debian policy's /usr rule is for
# distro packages). Depends are resolved with dpkg-shlibdeps at build time:
# Debian 13's t64 transition renamed several runtime libs, so a hardcoded list
# would be a guaranteed future bug. Runnable locally:
#   docker run --rm -v "$PWD":/w -w /w debian:13 bash -c \
#     'apt-get update && apt-get install -y ... && ci/build-debs.sh ...'
set -euo pipefail

SPS_VER=$1 SPS_COMMIT=$2 NQPTP_VER=$3 NQPTP_COMMIT=$4 ALAC_SHA=$5
DEB_REVISION=1   # bump when packaging changes but upstream pins do not
ARCH=amd64
CONTROL_DIR=$(cd "$(dirname "$0")/control" && pwd)
mkdir -p "$6" && OUT=$(cd "$6" && pwd)
SRC=$(mktemp -d)

clone() { # <repo> <ref>
  git clone "https://github.com/mikebrady/$1" "$SRC/$1"
  git -C "$SRC/$1" checkout --detach "$2"
}

build() { # <repo> [configure flags...]
  local repo=$1; shift
  (cd "$SRC/$repo" && autoreconf -fi && ./configure "$@" && make -j"$(nproc)")
}

shlibdeps() { # <staged ELF file...> -> comma-separated Depends on stdout
  local scratch; scratch=$(mktemp -d)
  mkdir -p "$scratch/debian"
  printf 'Source: x\n\nPackage: x\nArchitecture: %s\n' "$ARCH" > "$scratch/debian/control"
  (cd "$scratch" && dpkg-shlibdeps -O "$@") | sed 's/^shlibs:Depends=//'
}

package() { # <name> <version> <depends> <stagedir>
  local name=$1 version=$2 depends=$3 stage=$4
  sed -e "s/@VERSION@/$version/" -e "s|@DEPENDS@|$depends|" \
    "$CONTROL_DIR/$name.control.in" > "$stage/DEBIAN/control"
  dpkg-deb --build --root-owner-group "$stage" "$OUT/${name}_${version}_${ARCH}.deb"
}

# --- libalac (first: shairport-sync links against it) -----------------------
clone alac "$ALAC_SHA"
ALAC_DATE=$(git -C "$SRC/alac" log -1 --format=%cd --date=format:%Y%m%d)
ALAC_VER="0.0~git${ALAC_DATE}.${ALAC_SHA:0:7}-${DEB_REVISION}"
build alac
STAGE=$(mktemp -d)
make -C "$SRC/alac" install DESTDIR="$STAGE"
ALAC_SO=$(find "$STAGE/usr/local/lib" -name 'libalac.so.*' -type f | head -1)
SOVER=$(objdump -p "$ALAC_SO" | awk '/SONAME/{print $2}' | sed 's/^libalac\.so\.//')
mkdir -p "$STAGE/DEBIAN"
# shlibs: lets dpkg-shlibdeps resolve libalac.so.N -> our package for shairport
printf 'libalac %s libalac (= %s)\n' "$SOVER" "$ALAC_VER" > "$STAGE/DEBIAN/shlibs"
printf '#!/bin/sh\nset -e\nldconfig\n' > "$STAGE/DEBIAN/postinst"
printf '#!/bin/sh\nset -e\nldconfig\n' > "$STAGE/DEBIAN/postrm"
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"
package libalac "$ALAC_VER" "$(shlibdeps "$ALAC_SO")" "$STAGE"
# install into the build container so ldconfig + shlibdeps see it for shairport
dpkg -i "$OUT/libalac_${ALAC_VER}_${ARCH}.deb"

# --- nqptp -------------------------------------------------------------------
clone nqptp "$NQPTP_COMMIT"
NQPTP_DEBVER="${NQPTP_VER}-${DEB_REVISION}"
build nqptp --with-systemd-startup
STAGE=$(mktemp -d)
make -C "$SRC/nqptp" install DESTDIR="$STAGE"
mkdir -p "$STAGE/DEBIAN"
package nqptp "$NQPTP_DEBVER" "$(shlibdeps "$STAGE/usr/local/bin/nqptp")" "$STAGE"

# --- shairport-sync ----------------------------------------------------------
clone shairport-sync "$SPS_COMMIT"
SPS_DEBVER="${SPS_VER}-${DEB_REVISION}"
build shairport-sync \
  --sysconfdir=/etc --with-alsa --with-soxr --with-avahi --with-ssl=openssl \
  --with-systemd --with-airplay-2 --with-apple-alac \
  --with-metadata --with-dbus-interface
STAGE=$(mktemp -d)
make -C "$SRC/shairport-sync" install DESTDIR="$STAGE"
# The role owns /etc/shairport-sync.conf (rendered template). A non-conffile
# sample in the deb would clobber it on every install — strip it. The D-Bus
# policy file stays: boxes that later enable the dashboard need no rebuild.
rm -f "$STAGE/etc/shairport-sync.conf" "$STAGE/etc/shairport-sync.conf.sample"
mkdir -p "$STAGE/DEBIAN"
package shairport-sync "$SPS_DEBVER" \
  "$(shlibdeps "$STAGE/usr/local/bin/shairport-sync"), avahi-daemon" "$STAGE"

echo "Built:"
ls -l "$OUT"/*.deb
