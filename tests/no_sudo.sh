#!/usr/bin/env bash
set -euo pipefail

# Ensure broker-only model: no direct sudo in converge path
if rg -n "\bsudo\s" bin/converge pkg 2>/dev/null; then
  echo "[no_sudo] Found forbidden 'sudo' usage in converge path" >&2
  exit 1
fi
echo "[no_sudo] OK: no direct sudo usage in converge path"

