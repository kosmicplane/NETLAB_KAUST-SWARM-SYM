#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/workspace/NETLAB}"
COMPOSE_DIR="${COMPOSE_DIR:-$PROJECT_ROOT/Docker/compose}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env}"

ISAAC_SERVICE="${ISAAC_SERVICE:-isaac}"
ISAAC_CONTAINER="${ISAAC_CONTAINER:-isaac-sim}"

WEBRTC_CLIENT="${WEBRTC_CLIENT:-$HOME/Downloads/isaacsim-webrtc-streaming-client-1.1.5-linux-x64.AppImage}"
WEBRTC_CACHE_DIR="${WEBRTC_CACHE_DIR:-/tmp/isaac-webrtc-clean}"

DEFAULT_ROS_DISTRO="jazzy"
DEFAULT_SIGNAL_PORT="49100"
DEFAULT_STREAM_PORT="47998"

usage() {
  cat <<EOF
Usage:
  $0 setup-brev      Install/check Brev-side dependencies and update .env with Tailscale IP
  $0 start-brev      Recreate Isaac container and wait for streaming readiness
  $0 doctor-brev     Diagnose Docker GPU, Tailscale, ports, Isaac logs, and NVENC sessions
  $0 monitor-brev    Live monitor tcpdump + encoder sessions instructions
  $0 start-local     Start Isaac Sim WebRTC Client on local PC
  $0 doctor-local    Check local Tailscale IP and WebRTC client file

Environment overrides:
  PROJECT_ROOT=$PROJECT_ROOT
  COMPOSE_DIR=$COMPOSE_DIR
  WEBRTC_CLIENT=$WEBRTC_CLIENT
  ISAAC_CONTAINER=$ISAAC_CONTAINER
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[ERROR] Missing command: $1"
    return 1
  }
}

compose() {
  cd "$COMPOSE_DIR"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

get_tailscale_ip() {
  if command -v tailscale >/dev/null 2>&1; then
    tailscale ip -4 2>/dev/null | head -n 1 || true
  fi
}

update_env_key() {
  local key="$1"
  local value="$2"
  local file="$COMPOSE_DIR/$ENV_FILE"

  touch "$file"

  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf "\n%s=%s\n" "$key" "$value" >> "$file"
  fi
}

wait_for_isaac_ready() {
  echo "[INFO] Waiting for Isaac streaming readiness..."
  echo "[INFO] Target log line: Isaac Sim Full Streaming App is loaded."

  local timeout="${ISAAC_READY_TIMEOUT:-600}"
  local elapsed=0

  while [ "$elapsed" -lt "$timeout" ]; do
    if docker logs "$ISAAC_CONTAINER" 2>&1 | grep -q "Isaac Sim Full Streaming App is loaded"; then
      echo "[OK] Isaac Sim Full Streaming App is loaded."
      return 0
    fi

    if docker logs "$ISAAC_CONTAINER" 2>&1 | grep -q "Waiting for RtPso async group async compilation"; then
      echo "[INFO] RTX shader/RtPso warmup still running..."
    fi

    sleep 5
    elapsed=$((elapsed + 5))
  done

  echo "[ERROR] Isaac did not become ready within ${timeout}s."
  echo "[INFO] Recent logs:"
  docker logs "$ISAAC_CONTAINER" 2>&1 | tail -n 120 || true
  return 1
}

setup_brev() {
  echo "[INFO] Brev setup/check started."

  require_cmd docker
  require_cmd curl

  if ! command -v tailscale >/dev/null 2>&1; then
    echo "[INFO] Installing Tailscale..."
    curl -fsSL https://tailscale.com/install.sh | sh
  fi

  if ! tailscale status >/dev/null 2>&1; then
    echo "[INFO] Running tailscale up. Authenticate in the URL shown by Tailscale if required."
    sudo tailscale up --hostname netlab-kaust-brev
  fi

  local ts_ip
  ts_ip="$(get_tailscale_ip)"

  if [ -z "$ts_ip" ]; then
    echo "[ERROR] Could not detect Brev Tailscale IPv4."
    echo "[INFO] Run: sudo tailscale up --hostname netlab-kaust-brev"
    exit 1
  fi

  echo "[OK] Brev Tailscale IP: $ts_ip"

  echo "[INFO] Updating .env..."
  update_env_key "ROS_DISTRO" "$DEFAULT_ROS_DISTRO"
  update_env_key "ISAACSIM_HOST" "$ts_ip"
  update_env_key "ISAACSIM_SIGNAL_PORT" "$DEFAULT_SIGNAL_PORT"
  update_env_key "ISAACSIM_STREAM_PORT" "$DEFAULT_STREAM_PORT"
  update_env_key "ISAACSIM_TAG" "5.1.0"

  echo "[INFO] Testing Docker GPU..."
  docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/tmp/netlab_gpu_test.log 2>&1 || {
    echo "[WARN] Docker GPU test failed."
    echo "[INFO] Trying NVIDIA container runtime configuration..."
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
  }

  echo "[OK] Docker GPU works."

  echo "[INFO] Compose services:"
  compose config --services

  echo "[INFO] Checking final .env values:"
  grep -E 'ROS_DISTRO|ISAACSIM_HOST|ISAACSIM_SIGNAL_PORT|ISAACSIM_STREAM_PORT|ISAACSIM_TAG' "$COMPOSE_DIR/$ENV_FILE" || true

  echo "[DONE] setup-brev completed."
}

start_brev() {
  echo "[INFO] Starting Isaac on Brev."

  cd "$COMPOSE_DIR"

  echo "[INFO] Validating compose..."
  compose config >/tmp/netlab_compose_config.yml

  echo "[INFO] Checking livestream flags in rendered compose..."
  if grep -q "primaryStream" /tmp/netlab_compose_config.yml; then
    echo "[WARN] Rendered compose still contains old primaryStream flags."
    echo "[WARN] Recommended Isaac 5.1 flags are:"
    echo "       --/app/livestream/publicEndpointAddress=\${ISAACSIM_HOST}"
    echo "       --/app/livestream/port=\${ISAACSIM_SIGNAL_PORT}"
  fi

  grep -E 'publicEndpointAddress|/app/livestream|primaryStream|ISAACSIM_HOST' -n /tmp/netlab_compose_config.yml || true

  echo "[INFO] Recreating Isaac container..."
  compose up -d --force-recreate "$ISAAC_SERVICE"

  wait_for_isaac_ready

  echo "[INFO] Current containers:"
  compose ps

  echo "[INFO] Encoder sessions:"
  nvidia-smi encodersessions || true

  echo "[DONE] Isaac is ready. Connect WebRTC Client to:"
  grep '^ISAACSIM_HOST=' "$COMPOSE_DIR/$ENV_FILE" | cut -d= -f2
}

doctor_brev() {
  echo "========== NETLAB Brev WebRTC Doctor =========="

  echo
  echo "== Host =="
  hostname || true
  uname -a || true

  echo
  echo "== Tailscale =="
  if command -v tailscale >/dev/null 2>&1; then
    tailscale ip -4 || true
    tailscale status | head -n 20 || true
  else
    echo "[WARN] tailscale not installed."
  fi

  echo
  echo "== NVIDIA Host =="
  nvidia-smi || true

  echo
  echo "== Docker GPU Test =="
  docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi || true

  echo
  echo "== Compose Services =="
  compose config --services || true

  echo
  echo "== .env =="
  grep -E 'ROS_DISTRO|ROS_DOMAIN_ID|RMW_IMPLEMENTATION|ISAACSIM_HOST|ISAACSIM_SIGNAL_PORT|ISAACSIM_STREAM_PORT|ISAACSIM_TAG' "$COMPOSE_DIR/$ENV_FILE" || true

  echo
  echo "== Isaac NVIDIA Env =="
  docker inspect "$ISAAC_CONTAINER" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep NVIDIA || true

  echo
  echo "== NVENC/NVDEC Libraries Inside Isaac =="
  docker exec "$ISAAC_CONTAINER" bash -lc 'ls -l /usr/lib/x86_64-linux-gnu/libnvidia-encode.so* 2>/dev/null || true' 2>/dev/null || true
  docker exec "$ISAAC_CONTAINER" bash -lc 'ls -l /usr/lib/x86_64-linux-gnu/libnvcuvid.so* 2>/dev/null || true' 2>/dev/null || true

  echo
  echo "== Listening Ports =="
  sudo ss -lntu | grep -E '49100|47998' || true
  sudo ss -lunp | grep -E '49100|47998' || true

  echo
  echo "== Encoder Sessions =="
  nvidia-smi encodersessions || true

  echo
  echo "== GPU Usage =="
  nvidia-smi --query-gpu=name,driver_version,utilization.gpu,utilization.encoder,utilization.decoder,memory.used --format=csv || true

  echo
  echo "== Recent Isaac Streaming Logs =="
  docker logs "$ISAAC_CONTAINER" 2>/dev/null | grep -Ei 'Full Streaming|webrtc|stream|livestream|encoder|nvenc|h264|error|warning|RtPso' | tail -n 120 || true

  echo
  echo "== ROS Jazzy Check =="
  docker exec netlab-ros2-core bash -lc 'source /opt/ros/jazzy/setup.bash && echo ROS_DISTRO=$ROS_DISTRO && ros2 topic list | head -n 40' 2>/dev/null || true

  echo
  echo "========== Doctor completed =========="
}

monitor_brev() {
  cat <<EOF
Open three Brev terminals:

Terminal A - Isaac logs:
  docker logs -f $ISAAC_CONTAINER

Terminal B - Tailscale WebRTC traffic:
  sudo tcpdump -ni tailscale0 '(tcp port 49100 or udp port 47998)'

Terminal C - NVENC sessions:
  watch -n 1 "nvidia-smi encodersessions; echo; nvidia-smi --query-gpu=utilization.gpu,utilization.encoder,utilization.decoder,memory.used --format=csv"

Expected:
  TCP 49100 bidirectional between Brev Tailscale IP and local PC Tailscale IP.
  UDP 47998 bidirectional between Brev Tailscale IP and local PC Tailscale IP.
  Encoder session appears after WebRTC Client connects.
EOF
}

start_local() {
  echo "[INFO] Starting Isaac Sim WebRTC Client locally."

  if command -v tailscale >/dev/null 2>&1; then
    echo "[INFO] Local Tailscale IP:"
    tailscale ip -4 || true
  else
    echo "[WARN] tailscale command not found on local PC."
  fi

  if [ ! -f "$WEBRTC_CLIENT" ]; then
    echo "[ERROR] WebRTC client not found:"
    echo "        $WEBRTC_CLIENT"
    echo "[INFO] Download Isaac Sim WebRTC Streaming Client 1.1.5 for Linux x86_64."
    exit 1
  fi

  chmod +x "$WEBRTC_CLIENT"

  pkill -f isaacsim-webrtc || true
  rm -rf "$WEBRTC_CACHE_DIR"

  echo "[INFO] Launching client:"
  echo "$WEBRTC_CLIENT"
  echo
  echo "[INFO] Connect to the Brev Tailscale IP, for example:"
  echo "       100.72.58.116"
  echo

  "$WEBRTC_CLIENT" \
    --no-sandbox \
    --ozone-platform=x11 \
    --user-data-dir="$WEBRTC_CACHE_DIR"
}

doctor_local() {
  echo "========== NETLAB Local WebRTC Doctor =========="

  echo
  echo "== Tailscale =="
  if command -v tailscale >/dev/null 2>&1; then
    tailscale ip -4 || true
    tailscale status | head -n 20 || true
  else
    echo "[WARN] tailscale command not found."
  fi

  echo
  echo "== Public IPv4 =="
  curl -4 -s ifconfig.me || true
  echo

  echo
  echo "== WebRTC Client =="
  ls -lh "$WEBRTC_CLIENT" || true

  echo
  echo "== Suggested launch =="
  echo "$0 start-local"

  echo
  echo "========== Doctor completed =========="
}

case "${1:-}" in
  setup-brev)
    setup_brev
    ;;
  start-brev)
    start_brev
    ;;
  doctor-brev)
    doctor_brev
    ;;
  monitor-brev)
    monitor_brev
    ;;
  start-local)
    start_local
    ;;
  doctor-local)
    doctor_local
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    echo "[ERROR] Unknown command: $1"
    usage
    exit 1
    ;;
esac