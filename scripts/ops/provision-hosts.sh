#!/usr/bin/env bash
set -euo pipefail

# Run from your Mac (controller). Do NOT run on the Wyse boxes.
# Usage:
#   scripts/ops/provision-hosts.sh wyse-dac=192.168.8.71 wyse-sony=192.168.8.72
# or:
#   HOSTS_LIST="wyse-dac=192.168.8.71 wyse-sony=192.168.8.72" scripts/ops/provision-hosts.sh

HOST_ARGS=( "$@" )
if [[ ${#HOST_ARGS[@]} -eq 0 ]]; then
  if [[ -n "${HOSTS_LIST:-}" ]]; then
    # shellcheck disable=SC2206  # intentional split on spaces from HOSTS_LIST
    HOST_ARGS=( ${HOSTS_LIST} )
  else
    echo "Provide hosts as args: name=ip ...  or set HOSTS_LIST" >&2
    exit 2
  fi
fi
SSH_USER="${SSH_USER:-rmayen}"
SSH_PORT="${SSH_PORT:-22}"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -p "$SSH_PORT")

APP_ROOT=/opt/airplay_wyse
RUN_DIR=/run/airplay

for entry in "${HOST_ARGS[@]}"; do
  name="${entry%%=*}"
  ip="${entry#*=}"
  echo "=== $name ($ip) ==="

  ssh "${SSH_OPTS[@]}" "${SSH_USER}@${ip}" "sudo bash -s" <<'REMOTE'
set -euo pipefail
APP_ROOT=/opt/airplay_wyse
RUN_DIR=/run/airplay
STATE_DIR=/var/lib/airplay_wyse

# 1) Basics
id airplay >/dev/null 2>&1 || adduser --system --group --home /nonexistent --no-create-home airplay
install -d -m 0755 -o airplay -g airplay "$APP_ROOT" || true
install -d -m 0755 -o airplay -g airplay "$STATE_DIR" || true
install -d -m 0700 -o airplay -g airplay "$STATE_DIR/hashes" || true

# deps
export DEBIAN_FRONTEND=noninteractive
apt-get update -y -o=Dpkg::Use-Pty=0
apt-get install -y -o=Dpkg::Use-Pty=0 jq git gpg

# 2) Runtime dirs (setgid to keep group=airplay)
install -d -o root -g airplay -m 2775 "$RUN_DIR"
install -d -o root -g airplay -m 2770 "$RUN_DIR/queue"

# 3) Units
cat >/etc/systemd/system/preflight.service <<'EOF'
[Unit]
Description=Airplay preflight checks
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=airplay
WorkingDirectory=/opt/airplay_wyse
ExecStart=/opt/airplay_wyse/bin/preflight
StandardOutput=journal+console

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/converge.service <<'EOF'
[Unit]
Description=Airplay Converge (idempotent orchestrator)
After=update.service
ConditionPathIsReadWrite=/opt/airplay_wyse

[Service]
Type=oneshot
User=airplay
WorkingDirectory=/opt/airplay_wyse
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/opt/airplay_wyse/bin/converge
NoNewPrivileges=yes
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=/opt/airplay_wyse /run/airplay
AmbientCapabilities=
CapabilityBoundingSet=
LockPersonality=yes

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/update-done.path <<'EOF'
[Unit]
Description=Trigger converge when update.trigger changes

[Path]
PathChanged=/run/airplay/update.trigger
Unit=converge.service
MakeDirectory=yes
DirectoryMode=2775

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/converge-broker.service <<'EOF'
[Unit]
Description=Airplay root broker (exec allow-listed privileged ops)
Documentation=man:systemd.path(5)
ConditionPathIsReadWrite=/run/airplay/queue

[Service]
Type=oneshot
ExecStart=/opt/airplay_wyse/bin/converge-broker
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/run/airplay /opt/airplay_wyse \
  /var/cache/apt /var/lib/apt /var/lib/dpkg \
  /var/tmp /tmp \
  /etc/apt/preferences.d \
  /var/log/apt /var/log/dpkg
User=root

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/converge-broker.path <<'EOF'
[Unit]
Description=Watch /run/airplay/queue to run root broker

[Path]
DirectoryNotEmpty=/run/airplay/queue
Unit=converge-broker.service
MakeDirectory=yes
DirectoryMode=2770

[Install]
WantedBy=multi-user.target
EOF

# 4) Broker script
cat >"$APP_ROOT/bin/converge-broker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
QUEUE=/run/airplay/queue

is_allowed() {
  case "$1" in
    /usr/bin/apt-get) shift; if [ "${1:-}" = "update" ]; then return 0; fi; [ "${1:-}" = "-y" ] && [ "${2:-}" = "install" ] && return 0 ;;
    /usr/bin/dpkg) shift; [ "${1:-}" = "-i" ] && [[ "${2:-}" == /opt/airplay_wyse/pkg/*.deb ]] && return 0 ;;
    /usr/bin/systemctl) shift; if [ "${1:-}" = "daemon-reload" ]; then return 0; fi; if [ "${1:-}" = "set-property" ] && [ "${2:-}" = "converge-broker.service" ]; then return 0; fi; if [ "${1:-}" = "restart" ]; then case "${2:-}" in airplay-*) return 0 ;; converge-broker.path) return 0 ;; converge-broker.service) return 0 ;; esac; fi ;;
    /usr/bin/install) shift; if [ "${1:-}" = "-d" ] && [ "${2:-}" = "-m" ] && [ "${3:-}" = "0755" ]; then case "${4:-}" in /etc/apt/preferences.d) return 0 ;; /run/systemd/system/converge-broker.service.d) return 0 ;; esac; fi ;;
    /usr/bin/tee) shift; case "${1:-}" in /etc/apt/preferences.d/*.pref) return 0 ;; /run/systemd/system/converge-broker.service.d/*.conf) return 0 ;; /etc/systemd/system/converge-broker.service) return 0 ;; /etc/systemd/system/converge-broker.path) return 0 ;; /etc/systemd/system/converge.service) return 0 ;; /etc/systemd/system/update.service) return 0 ;; /etc/systemd/system/update-done.path) return 0 ;; /etc/systemd/system/preflight.service) return 0 ;; esac ;;
  esac
  return 1
}

log() { systemd-cat -t airplay-broker echo "$*"; }

process_one() {
  local f="$1"; local okf="${f%.cmd}.ok"; local errf="${f%.cmd}.err"; local inf="${f%.cmd}.in"
  local line; line="$(cat "$f")"
  # shellcheck disable=SC2206
  args=( $line )
  if ! is_allowed "${args[@]}"; then echo "DENY: $line" >"$errf"; rm -f "$f"; return 0; fi
  if [[ "${args[0]}" == "/usr/bin/tee" && -f "$inf" ]]; then
    if "${args[@]}" <"$inf" 2> >(tee "$errf".tmp >&2); then : > "$okf"; rm -f "$errf".tmp "$inf"; else mv "$errf".tmp "$errf"; fi
    rm -f "$f"; return 0
  fi
  if "${args[@]}" 2> >(tee "$errf".tmp >&2); then : > "$okf"; rm -f "$errf".tmp; else mv "$errf".tmp "$errf"; fi
  rm -f "$f"
}

shopt -s nullglob
for f in "$QUEUE"/*.cmd; do process_one "$f"; done
EOF
chmod 0755 "$APP_ROOT/bin/converge-broker"
chown root:root "$APP_ROOT/bin/converge-broker"

# 5) Minimal preflight if missing (until repo is deployed)
/bin/bash -lc 'test -x /opt/airplay_wyse/bin/preflight' || {
  cat >"$APP_ROOT/bin/preflight"<<'EOF'
#!/usr/bin/env bash
set -euo pipefail
for c in git gpg jq systemctl; do command -v "$c" >/dev/null || { echo "missing $c"; exit 1; }; done
[ -w . ] || { echo "not writable: $(pwd)"; exit 1; }
[ -d /var/lib/airplay_wyse ] || { echo "missing /var/lib/airplay_wyse"; exit 1; }
[ -d /run/airplay/queue ] || { echo "missing /run/airplay/queue"; exit 1; }
echo "preflight OK"
EOF
  chmod 0755 "$APP_ROOT/bin/preflight"
  chown airplay:airplay "$APP_ROOT/bin/preflight"
}

# 6) Enable watchers
systemctl daemon-reload
systemctl enable --now preflight.service converge-broker.path update-done.path

# 7) Smoke
: > /run/airplay/update.trigger || true
REMOTE

  echo "Provisioned $name"
done

echo "All done."
