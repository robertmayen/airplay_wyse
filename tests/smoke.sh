#!/usr/bin/env bash
set -euo pipefail

echo "[smoke] Minimal smoke test"

# Validate script presence
for f in bin/reconcile bin/update bin/converge bin/health; do
  [[ -x "$f" ]] || { echo "[smoke] missing or not executable: $f" >&2; exit 1; }
done

echo "[smoke] Running health (may be unknown on CI):"
./bin/health || true

if command -v shairport-sync >/dev/null 2>&1; then
  v=$(shairport-sync -V 2>&1 || true)
  echo "[smoke] shairport-sync -V: $(echo "$v" | head -1)"
  if echo "$v" | grep -q "AirPlay2"; then
    echo "[smoke] AirPlay2 string detected"
  else
    echo "[smoke] AirPlay2 string not detected (ok in CI)"
  fi
else
  echo "[smoke] shairport-sync not present (ok in CI)"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl --version >/dev/null 2>&1 || true
  echo "[smoke] systemctl available"
else
  echo "[smoke] systemctl not available (ok in CI)"
fi

echo "[smoke] Done"
