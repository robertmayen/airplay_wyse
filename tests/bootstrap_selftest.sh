#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
. "$REPO_DIR/lib/bootstrap.sh" >/dev/null 2>&1 || true

if is_bootstrapped; then
  echo '{"bootstrap":"PASS"}'
  exit 0
else
  echo "{\"bootstrap\":\"FAIL\",\"reasons\":\"$(bootstrap_diagnose)\"}"
  exit 1
fi

