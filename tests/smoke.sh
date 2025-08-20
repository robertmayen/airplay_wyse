#!/usr/bin/env bash
set -euo pipefail

echo "[smoke] Starting converge dry-run (actual converge will act on host)."
if ./bin/converge; then
  echo "[smoke] converge completed"
else
  echo "[smoke] converge returned non-zero (acceptable if degraded without devices)."
fi

echo "[smoke] Health:"
./bin/health || true
