#!/usr/bin/env bash
set -euo pipefail

# AirPlay Wyse one-shot bootstrap
# - Creates 'airplay' user and sets permissions
# - Clones repo and installs systemd units
# - Enables reconcile.timer and optionally triggers first run
#
# Usage (as root):
#   BOOTSTRAP_REPO="git@github.com:YOURORG/airplay_wyse.git" \
#   BOOTSTRAP_TARGET_TAG="v1.0.0" \  # optional
#   BOOTSTRAP_AIRPLAY_NAME="Living Room" \  # optional
#   BOOTSTRAP_NIC="enp3s0" \  # optional
#   BOOTSTRAP_DEPLOY_KEY_PATH="/root/id_ed25519" \  # optional (SSH)
#   BOOTSTRAP_KNOWN_HOSTS_PATH="/root/known_hosts" \  # optional
#   BOOTSTRAP_RUN_RECONCILE=1 \  # default 1
#   BOOTSTRAP_REPO_DIR="/opt/airplay_wyse" \  # default /opt/airplay_wyse
#   bash scripts/bootstrap.sh

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [bootstrap] $*"; }
die() { echo "[bootstrap] ERROR: $*" >&2; exit 1; }

require_root() { [[ "$(id -u)" -eq 0 ]] || die "must be run as root"; }

ensure_pkg() {
  local pkg="$1"
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    apt-get update -y
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"
  fi
}

setup_user() {
  # Optional: create 'airplay' user for audio group membership, though services run as root.
  if ! id -u airplay >/dev/null 2>&1; then
    log "creating user 'airplay'"
    useradd -r -m -s /usr/sbin/nologin airplay
  fi
  getent group audio >/dev/null 2>&1 || groupadd audio || true
  usermod -aG audio airplay || true
}

setup_ssh() {
  local key_path="${BOOTSTRAP_DEPLOY_KEY_PATH:-}"
  local known_path="${BOOTSTRAP_KNOWN_HOSTS_PATH:-}"
  [[ -z "$key_path" && -z "$known_path" ]] && return 0
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  if [[ -n "${key_path:-}" && -f "$key_path" ]]; then
    install -m 0600 "$key_path" /root/.ssh/id_ed25519
  fi
  if [[ -n "${known_path:-}" && -f "$known_path" ]]; then
    install -m 0644 "$known_path" /root/.ssh/known_hosts
  fi
}

clone_repo() {
  local repo_url="$1" repo_dir="$2"
  if [[ -d "$repo_dir/.git" ]]; then
    log "repo already present at $repo_dir"
    return 0
  fi
  install -d -m 0755 "$repo_dir"
  log "cloning $repo_url to $repo_dir"
  git clone "$repo_url" "$repo_dir"
}

install_wrapper() { :; }
configure_sudoers() { :; }

install_units() {
  local repo_dir="$1"
  install -m 0644 "$repo_dir/systemd/reconcile.service" /etc/systemd/system/reconcile.service
  install -m 0644 "$repo_dir/systemd/reconcile.timer" /etc/systemd/system/reconcile.timer
  install -m 0644 "$repo_dir/systemd/converge.service" /etc/systemd/system/converge.service
  # shairport override
  if [[ -f "$repo_dir/systemd/overrides/shairport-sync.service.d/override.conf" ]]; then
    install -d -m 0755 /etc/systemd/system/shairport-sync.service.d
    install -m 0644 "$repo_dir/systemd/overrides/shairport-sync.service.d/override.conf" \
      /etc/systemd/system/shairport-sync.service.d/override.conf
  fi
  systemctl daemon-reload
}

write_inventory() {
  local repo_dir="$1" host
  host="$(hostname -s 2>/dev/null || hostname)"
  local inv_dir="$repo_dir/inventory/hosts"
  local inv="$inv_dir/$host.yml"
  install -d -m 0755 "$inv_dir"
  {
    [[ -n "${BOOTSTRAP_AIRPLAY_NAME:-}" ]] && echo "airplay_name: \"$BOOTSTRAP_AIRPLAY_NAME\""
    [[ -n "${BOOTSTRAP_NIC:-}" ]] && echo "nic: $BOOTSTRAP_NIC"
    if [[ -n "${BOOTSTRAP_TARGET_TAG:-}" ]]; then
      echo "target_tag: $BOOTSTRAP_TARGET_TAG"
    fi
  } > "$inv"
  # Inventory is read by root-run services
}

setup_runtime_dirs() {
  local repo_dir="$1"
  log "setting up runtime directories"
  
  # Create runtime directories that converge expects
  install -d -m 0755 /run/airplay
  install -d -m 0755 /run/airplay/tmp
  # Root-run services will use these paths directly
  
  # Create state directory
  install -d -m 0755 /var/lib/airplay_wyse
  # Owned by root for root-run services
}

enable_services() {
  systemctl enable --now reconcile.timer
  if [[ "${BOOTSTRAP_RUN_RECONCILE:-1}" == "1" ]]; then
    systemctl start reconcile.service || true
  fi
}

main() {
  require_root
  command -v systemctl >/dev/null 2>&1 || die "systemd is required"

  local REPO_URL="${BOOTSTRAP_REPO:-}"
  local REPO_DIR="${BOOTSTRAP_REPO_DIR:-/opt/airplay_wyse}"
  [[ -n "$REPO_URL" ]] || die "set BOOTSTRAP_REPO to your Git URL"

  log "ensuring git is installed"
  command -v git >/dev/null 2>&1 || ensure_pkg git

  setup_user
  setup_ssh
  clone_repo "$REPO_URL" "$REPO_DIR"
  setup_runtime_dirs "$REPO_DIR"
  install_units "$REPO_DIR"
  if [[ -n "${BOOTSTRAP_AIRPLAY_NAME:-}" || -n "${BOOTSTRAP_NIC:-}" || -n "${BOOTSTRAP_TARGET_TAG:-}" ]]; then
    write_inventory "$REPO_DIR"
  fi
  enable_services

  log "bootstrap complete"
  log "health: $REPO_DIR/bin/health"
  log "logs: journalctl -u reconcile -n 50 --no-pager"
}

main "$@"
