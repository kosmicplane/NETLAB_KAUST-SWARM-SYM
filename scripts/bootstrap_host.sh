#!/usr/bin/env bash
# NETLAB host bootstrap. Safe on managed GPU images such as Brev: an existing
# Docker installation is never replaced and containerd packages are never mixed.
set -eo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_PACKAGES=0
NON_INTERACTIVE=0
NO_BUILD=0
for arg in "$@"; do
  case "$arg" in
    --install-packages) INSTALL_PACKAGES=1 ;;
    --non-interactive) NON_INTERACTIVE=1 ;;
    --no-build) NO_BUILD=1 ;;
    -h|--help)
      cat <<'HELP'
Usage: ./scripts/bootstrap_host.sh [--install-packages] [--non-interactive] [--no-build]

--install-packages installs only missing host utilities. Existing Docker and
containerd installations are preserved to avoid package conflicts.
HELP
      exit 0
      ;;
  esac
done

log() { printf '[NETLAB-BOOTSTRAP] %s\n' "$*"; }
fail() { printf '[NETLAB-BOOTSTRAP][ERROR] %s\n' "$*" >&2; exit 1; }

if [[ "$INSTALL_PACKAGES" == 1 ]]; then
  export DEBIAN_FRONTEND=noninteractive
  log 'Installing missing host utilities without replacing managed Docker packages.'
  sudo apt-get update
  utilities=(ca-certificates curl jq unzip rsync git python3 python3-pip)
  missing=()
  for pkg in "${utilities[@]}"; do
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed' || missing+=("$pkg")
  done
  if ((${#missing[@]})); then
    sudo apt-get install -y --no-install-recommends "${missing[@]}"
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  [[ "$INSTALL_PACKAGES" == 1 ]] || fail 'Docker is unavailable. Re-run with --install-packages or install Docker first.'
  log 'Docker is absent; installing the Ubuntu docker.io stack only.'
  sudo apt-get install -y --no-install-recommends docker.io
fi

# Never install containerd.io when Ubuntu containerd is already present.
if ! docker compose version >/dev/null 2>&1; then
  [[ "$INSTALL_PACKAGES" == 1 ]] || fail 'Docker Compose v2 is unavailable.'
  log 'Docker Compose v2 is missing; installing an Ubuntu-compatible plugin.'
  if apt-cache show docker-compose-v2 >/dev/null 2>&1; then
    sudo apt-get install -y --no-install-recommends docker-compose-v2
  elif apt-cache show docker-compose-plugin >/dev/null 2>&1; then
    sudo apt-get install -y --no-install-recommends docker-compose-plugin
  else
    fail 'No Docker Compose v2 package is available from the configured repositories.'
  fi
fi

if ! docker info >/dev/null 2>&1; then
  sudo systemctl start docker 2>/dev/null || true
  if ! docker info >/dev/null 2>&1; then
    sudo usermod -aG docker "$USER" 2>/dev/null || true
    fail 'Docker is installed but the current session cannot reach the daemon. Reconnect after group membership is updated.'
  fi
fi

chmod +x "$ROOT/scripts/netlab" "$ROOT/scripts/"*.sh 2>/dev/null || true
chmod +x "$ROOT/Docker/scripts/"*.sh 2>/dev/null || true
chmod +x "$ROOT/Docker/workspace/ros2/"*.sh 2>/dev/null || true

args=(bootstrap --non-interactive)
[[ "$NO_BUILD" == 1 ]] && args+=(--no-build)
log "Invoking canonical bootstrap from $ROOT"
exec "$ROOT/scripts/netlab" "${args[@]}"
