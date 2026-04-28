#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/workspace/NETLAB}"
COMPOSE_DIR="${COMPOSE_DIR:-$PROJECT_ROOT/Docker/compose}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env}"

ISAAC_SERVICE="${ISAAC_SERVICE:-isaac}"
ISAAC_CONTAINER="${ISAAC_CONTAINER:-isaac-sim}"

ROS_SERVICE="${ROS_SERVICE:-ros2-core}"
ROS_CONTAINER="${ROS_CONTAINER:-netlab-ros2-core}"

SIONNA_SERVICE="${SIONNA_SERVICE:-sionna-engine}"
SIONNA_CONTAINER="${SIONNA_CONTAINER:-netlab-sionna-engine}"

WEBRTC_CLIENT="${WEBRTC_CLIENT:-$HOME/Downloads/isaacsim-webrtc-streaming-client-1.1.5-linux-x64.AppImage}"
WEBRTC_CACHE_DIR="${WEBRTC_CACHE_DIR:-/tmp/isaac-webrtc-clean}"

DEFAULT_ROS_DISTRO="jazzy"
DEFAULT_SIGNAL_PORT="49100"
DEFAULT_STREAM_PORT="47998"

usage() {
  cat <<EOF
Usage:
  $0 setup-brev      Install/check Brev-side dependencies and update .env with Tailscale IP
  $0 build-stack     Build ROS 2 Jazzy and Sionna Docker services
  $0 start-stack     Start Isaac, ROS 2 Jazzy, and Sionna together
  $0 start-brev      Recreate Isaac container and wait for streaming readiness
  $0 doctor-stack    Diagnose Isaac/WebRTC, ROS 2, and Sionna
  $0 doctor-brev     Diagnose Docker GPU, Tailscale, ports, Isaac logs, and NVENC sessions
  $0 ros-check       Check ROS 2 Jazzy container
  $0 sionna-check    Check Sionna container
  $0 monitor-brev    Live monitor tcpdump + encoder sessions instructions
  $0 start-local     Start Isaac Sim WebRTC Client on local PC
  $0 doctor-local    Check local Tailscale IP and WebRTC client file

Environment overrides:
  PROJECT_ROOT=$PROJECT_ROOT
  COMPOSE_DIR=$COMPOSE_DIR
  COMPOSE_FILE=$COMPOSE_FILE
  ENV_FILE=$ENV_FILE
  ISAAC_SERVICE=$ISAAC_SERVICE
  ISAAC_CONTAINER=$ISAAC_CONTAINER
  ROS_SERVICE=$ROS_SERVICE
  ROS_CONTAINER=$ROS_CONTAINER
  SIONNA_SERVICE=$SIONNA_SERVICE
  SIONNA_CONTAINER=$SIONNA_CONTAINER
  WEBRTC_CLIENT=$WEBRTC_CLIENT
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

service_exists() {
  local service="$1"
  compose config --services 2>/dev/null | grep -qx "$service"
}

get_container_for_service() {
  local service="$1"
  local fallback_container="$2"
  local cid=""

  cid="$(compose ps -q "$service" 2>/dev/null || true)"

  if [ -n "$cid" ]; then
    echo "$cid"
    return 0
  fi

  if docker inspect "$fallback_container" >/dev/null 2>&1; then
    echo "$fallback_container"
    return 0
  fi

  return 1
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

  mkdir -p "$COMPOSE_DIR"
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

build_stack() {
  echo "[INFO] Building NETLAB Docker stack."

  cd "$COMPOSE_DIR"

  echo "[INFO] Validating compose..."
  compose config >/tmp/netlab_compose_config.yml

  echo "[INFO] Compose services:"
  compose config --services

  if service_exists "$ROS_SERVICE"; then
    echo "[INFO] Building ROS service: $ROS_SERVICE"
    compose build "$ROS_SERVICE"
  else
    echo "[WARN] ROS service not found in compose: $ROS_SERVICE"
  fi

  if service_exists "$SIONNA_SERVICE"; then
    echo "[INFO] Building Sionna service: $SIONNA_SERVICE"
    compose build "$SIONNA_SERVICE"
  else
    echo "[WARN] Sionna service not found in compose: $SIONNA_SERVICE"
  fi

  if service_exists "$ISAAC_SERVICE"; then
    echo "[INFO] Checking Isaac service build/pull path: $ISAAC_SERVICE"
    compose build "$ISAAC_SERVICE" || {
      echo "[WARN] Isaac service may use a prebuilt image. Continuing."
    }
  else
    echo "[WARN] Isaac service not found in compose: $ISAAC_SERVICE"
  fi

  echo "[DONE] build-stack completed."
}

start_stack() {
  echo "[INFO] Starting full NETLAB stack: Isaac + ROS 2 Jazzy + Sionna."

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

  echo "[INFO] Starting all services with build if needed..."
  compose up -d --build

  echo "[INFO] Current containers:"
  compose ps

  wait_for_isaac_ready

  echo "[INFO] Running ROS check..."
  ros_check || true

  echo "[INFO] Running Sionna check..."
  sionna_check || true

  echo "[INFO] Encoder sessions:"
  nvidia-smi encodersessions || true

  echo "[DONE] Full stack started. Connect WebRTC Client to:"
  grep '^ISAACSIM_HOST=' "$COMPOSE_DIR/$ENV_FILE" | cut -d= -f2
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

ros_check() {
  echo "========== ROS 2 Jazzy Check =========="

  local ros_target
  ros_target="$(get_container_for_service "$ROS_SERVICE" "$ROS_CONTAINER" || true)"

  if [ -z "$ros_target" ]; then
    echo "[ERROR] ROS container not found. Service=$ROS_SERVICE fallback=$ROS_CONTAINER"
    return 1
  fi

  docker exec "$ros_target" bash -lc '
    set -e
    if [ -f /opt/ros/jazzy/setup.bash ]; then
      source /opt/ros/jazzy/setup.bash
    else
      echo "[ERROR] /opt/ros/jazzy/setup.bash not found"
      exit 1
    fi

    echo "ROS_DISTRO=${ROS_DISTRO:-unknown}"

    if [ "${ROS_DISTRO:-}" != "jazzy" ]; then
      echo "[ERROR] ROS_DISTRO is not jazzy"
      exit 1
    fi

    echo
    echo "ROS topics:"
    ros2 topic list || true

    echo
    echo "ROS nodes:"
    ros2 node list || true
  '

  echo "========== ROS check completed =========="
}

sionna_check() {
  echo "========== Sionna Check =========="

  local sionna_target
  sionna_target="$(get_container_for_service "$SIONNA_SERVICE" "$SIONNA_CONTAINER" || true)"

  if [ -z "$sionna_target" ]; then
    echo "[ERROR] Sionna container not found. Service=$SIONNA_SERVICE fallback=$SIONNA_CONTAINER"
    return 1
  fi

  docker exec "$sionna_target" bash -lc '
    set -e

    echo "Python:"
    python3 --version || python --version || true

    echo
    echo "Checking Sionna import:"
    if command -v python3 >/dev/null 2>&1; then
      PYTHON_BIN=python3
    else
      PYTHON_BIN=python
    fi

    "$PYTHON_BIN" - <<PY
try:
    import sionna
    print("Sionna import: OK")
    print("Sionna version:", getattr(sionna, "__version__", "unknown"))
except Exception as e:
    print("Sionna import: FAILED")
    print(e)
    raise
PY
  '

  echo "========== Sionna check completed =========="
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
  ros_check || true

  echo
  echo "========== Doctor completed =========="
}

doctor_stack() {
  echo "========== NETLAB Full Stack Doctor =========="

  echo
  echo "========== Brev + Isaac/WebRTC Layer =========="
  doctor_brev || true

  echo
  echo "========== ROS 2 Jazzy Layer =========="
  ros_check || true

  echo
  echo "========== Sionna Layer =========="
  sionna_check || true

  echo
  echo "========== Docker Compose PS =========="
  compose ps || true

  echo
  echo "========== Recent logs: Isaac =========="
  compose logs --tail=80 "$ISAAC_SERVICE" || true

  echo
  echo "========== Recent logs: ROS =========="
  compose logs --tail=80 "$ROS_SERVICE" || true

  echo
  echo "========== Recent logs: Sionna =========="
  compose logs --tail=80 "$SIONNA_SERVICE" || true

  echo
  echo "========== Full stack doctor completed =========="
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

Full-stack checks:
  ./Scripts/netlab_brev_webrtc.sh ros-check
  ./Scripts/netlab_brev_webrtc.sh sionna-check
  ./Scripts/netlab_brev_webrtc.sh doctor-stack
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
  build-stack)
    build_stack
    ;;
  start-stack)
    start_stack
    ;;
  start-brev)
    start_brev
    ;;
  doctor-stack)
    doctor_stack
    ;;
  doctor-brev)
    doctor_brev
    ;;
  ros-check)
    ros_check
    ;;
  sionna-check)
    sionna_check
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