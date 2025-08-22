#!/usr/bin/env bash
set -euo pipefail

echo "[smoke] Minimal smoke test"

# Validate script presence
for f in bin/reconcile bin/update bin/converge bin/health bin/diag bin/alsa-probe; do
  [[ -x "$f" ]] || { echo "[smoke] missing or not executable: $f" >&2; exit 1; }
done

echo "[smoke] Running health (may be unknown on CI):"
./bin/health || true

if command -v shairport-sync >/dev/null 2>&1; then
  v=$(shairport-sync -V 2>&1 || true)
  echo "[smoke] shairport-sync -V: $(echo "$v" | head -1)"
  echo "$v" | grep -q "AirPlay2" && echo "[smoke] AirPlay2 OK" || echo "[smoke] AirPlay2 missing"
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl is-active nqptp >/dev/null 2>&1 && echo "[smoke] nqptp active" || echo "[smoke] nqptp not active"
fi

if command -v avahi-browse >/dev/null 2>&1; then
  timeout 5 avahi-browse -rt _airplay._tcp 2>/dev/null | grep -q "_airplay._tcp" && echo "[smoke] mdns _airplay visible" || echo "[smoke] mdns _airplay missing"
fi

# ALSA probe and simple play test (tolerate busy)
if [[ -x bin/alsa-probe ]]; then
  dev=$(bin/alsa-probe || true)
  if [[ -n "$dev" && -f /usr/share/sounds/alsa/Front_Center.wav ]]; then
    if aplay -q -D "$dev" /usr/share/sounds/alsa/Front_Center.wav 2>aplay.err; then
      echo "[smoke] ALSA play OK"
    else
      if grep -qi 'busy\|Device or resource busy' aplay.err; then
        echo "[smoke] ALSA device busy (acceptable)"
      else
        echo "[smoke] ALSA play failed"
      fi
    fi
    rm -f aplay.err
  fi
fi

# shellcheck on scripts if installed
if command -v shellcheck >/dev/null 2>&1; then
  shellcheck bin/* || true
fi

echo "[smoke] Done"
