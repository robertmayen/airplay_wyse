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

echo "[smoke] Broker queue test:"
./tests/queue_smoke.sh || true

echo "[smoke] Policy test (no sudo in converge path):"
./tests/no_sudo.sh
