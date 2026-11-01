#!/usr/bin/env bash
# Converge the airplay role inside a Debian 13 systemd container.
# One script for CI (ci.yml, debs.yml) and local runs (make converge).
#
# Usage: ci/converge.sh <command> [ansible-playbook args...]
#   up                start a fresh container and wait until systemd is ready
#   play  [args]      run site.yml against it
#   idempotent [args] run site.yml again; fail unless the run reports changed=0
#   check [args]      run site.yml in --check --diff mode; fail unless changed=0
#   exec  <cmd...>    run a command inside the container
#   logs              dump unit status and journal (failure diagnostics)
#   down              remove the container
set -euo pipefail

NAME=wyse-ci                       # must match the host name in ci/inventory.yml
IMAGE=${CONVERGE_IMAGE:-airplay-wyse-ci}
INVENTORY=${CONVERGE_INVENTORY:-ci/inventory.yml}
cd "$(dirname "$0")/.."

# In GitHub Actions, surface lines as error annotations (readable via the
# public checks API, unlike raw job logs).
annotate() {
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    while IFS= read -r line; do echo "::error::$line"; done
  else
    cat
  fi
}

up() {
  docker build -q -t "$IMAGE" ci/ >/dev/null
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker run -d --name "$NAME" --privileged --cgroupns=host \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    --tmpfs /run --tmpfs /run/lock "$IMAGE" >/dev/null
  # "degraded" is the normal steady state in a container (some units always
  # fail there); only starting/initializing mean "not ready yet".
  # shellcheck disable=SC2016  # expanded by the container's bash, not here
  timeout 120 docker exec "$NAME" bash -c '
    until state=$(systemctl is-system-running 2>/dev/null)
          [ "$state" = running ] || [ "$state" = degraded ]; do sleep 2; done'
  echo "container $NAME ready ($(docker exec "$NAME" systemctl is-system-running || true))"
}

play() {
  ansible-playbook -i "$INVENTORY" site.yml "$@"
}

# Run the play, tee its output, and require changed=0 in the recap.
expect_unchanged() {
  local label=$1 log
  shift
  log=$(mktemp)
  play "$@" | tee "$log"
  if ! grep -Eq "^${NAME}[[:space:]]*:[[:space:]]*ok=[0-9]+[[:space:]]+changed=0[[:space:]]+unreachable=0[[:space:]]+failed=0" "$log"; then
    echo "$label run reported changes or failures" | annotate
    exit 1
  fi
}

cmd=${1:-}
shift || true
case "$cmd" in
  up) up ;;
  play) play "$@" ;;
  idempotent) expect_unchanged "Idempotence (second)" "$@" ;;
  check) expect_unchanged "Check-mode" --check --diff "$@" ;;
  exec) docker exec "$NAME" "$@" ;;
  logs)
    {
      docker exec "$NAME" systemctl --failed --no-pager || true
      docker exec "$NAME" journalctl --no-pager -n 150 \
        -u shairport-sync -u nqptp -u avahi-daemon \
        -u airplay-nowplaying -u airplay-dashboard -u airplay-health || true
    } 2>&1 | tail -60 | annotate
    ;;
  down) docker rm -f "$NAME" >/dev/null ;;
  *)
    sed -n '2,13p' "$0" >&2
    exit 2
    ;;
esac
