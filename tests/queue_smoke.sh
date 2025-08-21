#!/usr/bin/env bash
set -euo pipefail

# Broker smoke: enqueue a harmless allowed command and ensure broker processes it.
QUEUE=/run/airplay/queue
mkdir -p "$QUEUE" || true
ts=$(date +%s); rand=$(od -An -N2 -tx2 /dev/urandom | tr -d ' \n')
cmdf="$QUEUE/${ts}.${rand}.cmd"
echo "/usr/bin/systemctl restart airplay-nop" >"$cmdf"

./bin/converge-broker || true

base="${cmdf%.cmd}"
if [[ -f "${base}.ok" || -f "${base}.err" ]]; then
  echo "[queue_smoke] broker produced result for $(basename "$cmdf")"
  exit 0
fi
echo "[queue_smoke] broker did not process queue file" >&2
exit 1

