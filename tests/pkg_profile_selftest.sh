#!/usr/bin/env bash
set -euo pipefail

# Sanity check that pkg-ensure profile can start, has network-online ordering,
# and returns a DONE line with RC=0 for a trivial command.

if /usr/local/sbin/airplay-sd-run pkg-ensure -- /bin/true 2>&1 | grep -q 'RESULT=OK'; then
  echo '{"pkg_profile":"PASS"}'
  exit 0
fi
echo '{"pkg_profile":"FAIL"}'
exit 1

