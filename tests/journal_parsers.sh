#!/usr/bin/env bash
set -euo pipefail

echo "[nqptp offsets last 10min]"
journalctl -u nqptp --since "-10min" | grep -E "offset|clock" || true

echo "[shairport-sync sessions last 10min]"
journalctl -u shairport-sync --since "-10min" | grep -E "Start|End|Client" || true
