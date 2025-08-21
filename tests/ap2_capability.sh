#!/usr/bin/env bash
set -euo pipefail

has_raop2=false
if command -v shairport-sync >/dev/null 2>&1; then
  if shairport-sync -V 2>&1 | grep -Eqi 'Air[[:space:]]*Play[[:space:]]*2|RAOP2|NQPTP'; then
    has_raop2=true
  fi
fi

nqptp_installed=false
if systemctl list-unit-files --type=service --no-legend 2>/dev/null | awk '{print $1}' | grep -qx "nqptp.service"; then
  nqptp_installed=true
fi

nqptp_active=false
if systemctl is-active --quiet nqptp.service 2>/dev/null; then
  nqptp_active=true
fi

printf '{"shairport_has_raop2":%s,"nqptp_installed":%s,"nqptp_active":%s}\n' "$has_raop2" "$nqptp_installed" "$nqptp_active"

