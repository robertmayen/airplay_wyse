#!/usr/bin/env bash
set -euo pipefail
bad=$(git ls-files -z bin pkg | xargs -0 file | grep -E 'shell script' | cut -d: -f1 | xargs -I{} test -x "{}" || echo "BAD")
if [ -n "${bad:-}" ]; then
  echo "Missing +x on some scripts"; exit 1
fi

