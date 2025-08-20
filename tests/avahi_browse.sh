#!/usr/bin/env bash
set -euo pipefail

if ! command -v avahi-browse >/dev/null; then
  echo "avahi-browse not installed"
  exit 0
fi

echo "_airplay._tcp"
avahi-browse -rt _airplay._tcp | sed -n '1,80p' || true

echo "_raop._tcp"
avahi-browse -rt _raop._tcp | sed -n '1,80p' || true
