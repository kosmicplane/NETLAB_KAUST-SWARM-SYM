#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/workspace/NETLAB}"
COMPOSE_DIR="${COMPOSE_DIR:-$PROJECT_ROOT/Docker/compose}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
ENV_FILE="${ENV_FILE:-.env}"

ROS_SERVICE="${ROS_SERVICE:-ros2-core}"
ROS_CONTAINER="${ROS_CONTAINER:-netlab-ros2-core}"
SIONNA_SERVICE="${SIONNA_SERVICE:-sionna-engine}"
SIONNA_CONTAINER="${SIONNA_CONTAINER:-netlab-sionna-engine}"
ISAAC_CONTAINER="${ISAAC_CONTAINER:-isaac-sim}"

SIONNA_PORT="${SIONNA_PORT:-8090}"
SIONNA_HOST="${SIONNA_HOST:-0.0.0.0}"
SIONNA_HEALTH_URL="${SIONNA_HEALTH_URL:-http://127.0.0.1:${SIONNA_PORT}/health}"
SIONNA_URL="${SIONNA_URL:-http://127.0.0.1:${SIONNA_PORT}/link}"

SIONNA_LOG="/workspace/results/sionna_link_server.log"
BRIDGE_LOG="/workspace/results/swarm_bridge.log"

compose() {
  cd "$COMPOSE_DIR"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

usage() {
  cat <<EOF
Usage:
  $0 build-ros       Build the ROS 2 Jazzy netlab_swarm_demo package
  $0 start-sionna    Start the Sionna real-time link HTTP service
  $0 start-ros       Start the ROS 2 swarm bridge node
  $0 start           Start Sionna + build ROS package + start ROS bridge
  $0 isaac-command   Print the Isaac Script Editor command for loading the two-drone scene
  $0 monitor         Print useful ROS topic and log monitoring commands
  $0 doctor          Check Sionna health, ROS topics, logs, and expected files
  $0 stop            Stop the Sionna and ROS bridge demo processes

Environment overrides:
  PROJECT_ROOT=$PROJECT_ROOT
  COMPOSE_DIR=$COMPOSE_DIR
  ROS_CONTAINER=$ROS_CONTAINER
  SIONNA_CONTAINER=$SIONNA_CONTAINER
  ISAAC_CONTAINER=$ISAAC_CONTAINER
  SIONNA_PORT=$SIONNA_PORT
  SIONNA_URL=$SIONNA_URL
EOF
}

ensure_stack_running() {
  echo "[INFO] Checking Docker Compose services..."
  compose ps
}

ensure_results_dirs() {
  docker exec "$SIONNA_CONTAINER" bash -lc 'mkdir -p /workspace/results' || true
  docker exec "$ROS_CONTAINER" bash -lc 'mkdir -p /workspace/results' || true
}

safe_stop_sionna() {
  docker exec "$SIONNA_CONTAINER" bash -lc '
    pkill -f "[r]ealtime_link_server.py" || true
  ' 2>/dev/null || true
}

safe_stop_ros_bridge() {
  docker exec "$ROS_CONTAINER" bash -lc '
    pkill -f "[n]etlab_swarm_demo.swarm_bridge" || true
    pkill -f "ros2 run netlab_swarm_demo [s]warm_bridge" || true
  ' 2>/dev/null || true
}

wait_for_sionna_health() {
  echo "[INFO] Waiting for Sionna health endpoint: ${SIONNA_HEALTH_URL}"

  for i in $(seq 1 30); do
    if curl -fsS "$SIONNA_HEALTH_URL" >/tmp/netlab_sionna_health.json 2>/dev/null; then
      echo "[OK] Sionna service is healthy:"
      cat /tmp/netlab_sionna_health.json
      echo
      return 0
    fi
    sleep 1
  done

  echo "[ERROR] Sionna service did not become healthy on ${SIONNA_HEALTH_URL}"
  echo
  echo "[INFO] Recent Sionna log:"
  docker exec "$SIONNA_CONTAINER" bash -lc "cat ${SIONNA_LOG} 2>/dev/null || true" || true
  echo
  echo "[INFO] Sionna process list:"
  docker exec "$SIONNA_CONTAINER" bash -lc 'ps aux | grep "[r]ealtime_link_server.py" || true' || true
  return 1
}

wait_for_ros_bridge() {
  echo "[INFO] Waiting for ROS swarm bridge to start..."

  for i in $(seq 1 15); do
    if docker exec "$ROS_CONTAINER" bash -lc 'ps aux | grep "[s]warm_bridge" >/dev/null 2>&1'; then
      echo "[OK] ROS swarm bridge process is running."
      return 0
    fi
    sleep 1
  done

  echo "[ERROR] ROS swarm bridge did not start."
  echo
  echo "[INFO] Recent ROS bridge log:"
  docker exec "$ROS_CONTAINER" bash -lc "cat ${BRIDGE_LOG} 2>/dev/null || true" || true
  return 1
}

build_ros() {
  ensure_stack_running
  ensure_results_dirs

  echo "[INFO] Building ROS 2 package netlab_swarm_demo inside $ROS_CONTAINER"

  docker exec "$ROS_CONTAINER" bash -lc '
    set -e
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    colcon build --symlink-install --packages-select netlab_swarm_demo
  '

  docker exec "$ROS_CONTAINER" bash -lc '
    set -e
    cd /workspace/ros2
    test -f install/setup.bash
  '

  echo "[OK] ROS 2 package built and install/setup.bash exists."
}

start_sionna() {
  ensure_stack_running
  ensure_results_dirs

  echo "[INFO] Starting Sionna real-time link service on port ${SIONNA_PORT}"

  safe_stop_sionna

  docker exec -d "$SIONNA_CONTAINER" bash -lc "
    set -e
    mkdir -p /workspace/results
    cd /workspace/sionna
    exec env SIONNA_LINK_HOST=${SIONNA_HOST} SIONNA_LINK_PORT=${SIONNA_PORT} python3 /workspace/sionna/realtime_link_server.py \
      > ${SIONNA_LOG} 2>&1
  "

  wait_for_sionna_health

  echo "[INFO] Sionna /link smoke test:"
  curl -fsS -X POST "http://127.0.0.1:${SIONNA_PORT}/link" \
    -H "Content-Type: application/json" \
    -d '{
      "tx": [-2.75, 0.0, 3.0],
      "rx": [2.75, 0.0, 3.0],
      "frequency_hz": 3500000000.0,
      "bandwidth_hz": 20000000.0,
      "tx_power_dbm": 20.0,
      "noise_floor_dbm": -95.0
    }' >/tmp/netlab_sionna_link_test.json

  cat /tmp/netlab_sionna_link_test.json
  echo
  echo "[OK] Sionna link service is running."
}

start_ros() {
  ensure_stack_running
  ensure_results_dirs

  echo "[INFO] Starting ROS 2 swarm bridge using SIONNA_URL=${SIONNA_URL}"

  if ! curl -fsS "$SIONNA_HEALTH_URL" >/dev/null 2>&1; then
    echo "[ERROR] Sionna is not healthy. Run:"
    echo "  $0 start-sionna"
    return 1
  fi

  docker exec "$ROS_CONTAINER" bash -lc '
    set -e
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    if [ ! -f install/setup.bash ]; then
      echo "[ERROR] /workspace/ros2/install/setup.bash does not exist."
      echo "[ERROR] Run build-ros first."
      exit 1
    fi
  '

  safe_stop_ros_bridge

  docker exec -d "$ROS_CONTAINER" bash -lc "
    set -e
    mkdir -p /workspace/results
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    source install/setup.bash
    export SIONNA_URL='${SIONNA_URL}'
    exec ros2 run netlab_swarm_demo swarm_bridge \
      > ${BRIDGE_LOG} 2>&1
  "

  wait_for_ros_bridge

  echo "[INFO] Recent ROS bridge log:"
  docker exec "$ROS_CONTAINER" bash -lc "tail -n 40 ${BRIDGE_LOG} 2>/dev/null || true"

  echo "[OK] ROS bridge process requested."
}

start_all() {
  start_sionna
  build_ros
  start_ros
  isaac_command
  echo "[DONE] Demo backend is running. Now execute the Isaac command in the streamed Isaac Sim Script Editor."
}

isaac_command() {
  cat <<EOF

[ISAAC SIM]
Open the streamed Isaac Sim UI, then run this in Window -> Script Editor:

exec(open("/workspace/isaac/scripts/two_drone_hover_live.py").read())

Expected result:
  - Two quadrotor-style drones appear in the Isaac stage.
  - Both drones perform a hover animation.
  - Isaac publishes /swarm/drone_1/state and /swarm/drone_2/state.
  - ROS queries Sionna and publishes /swarm/sionna/link_metrics.
  - ROS relays Drone 1 telemetry to /swarm/drone_2/inbox.
  - The visual link color changes according to the Sionna link status.
EOF
}

monitor() {
  cat <<EOF
Open additional Brev terminals and use these commands:

1) Monitor Sionna link service logs:
   docker exec -it ${SIONNA_CONTAINER} bash -lc 'tail -f ${SIONNA_LOG}'

2) Monitor ROS bridge logs:
   docker exec -it ${ROS_CONTAINER} bash -lc 'tail -f ${BRIDGE_LOG}'

3) List swarm ROS topics:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic list | grep /swarm'

4) Echo the Sionna link metrics:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic echo /swarm/sionna/link_metrics'

5) Echo Drone 2 inbox messages:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic echo /swarm/drone_2/inbox'

6) Echo Drone 2 ACK messages:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic echo /swarm/drone_2/ack'

7) Run the compact ROS monitor node:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 run netlab_swarm_demo swarm_monitor'

8) Record evidence with rosbag:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && mkdir -p bags && ros2 bag record /swarm/drone_1/state /swarm/drone_2/state /swarm/sionna/link_metrics /swarm/drone_2/inbox /swarm/drone_2/ack'
EOF
}

doctor() {
  echo "========== NETLAB Two-Drone Demo Doctor =========="
  echo

  echo "== Expected files =="
  ls -l "$PROJECT_ROOT/Docker/workspace/isaac/scripts/two_drone_hover_live.py" || true
  ls -l "$PROJECT_ROOT/Docker/workspace/sionna/realtime_link_server.py" || true
  ls -l "$PROJECT_ROOT/Docker/workspace/ros2/src/netlab_swarm_demo/package.xml" || true

  echo
  echo "== Compose services =="
  compose ps || true

  echo
  echo "== Sionna process =="
  docker exec "$SIONNA_CONTAINER" bash -lc 'ps aux | grep "[r]ealtime_link_server.py" || true' || true

  echo
  echo "== Sionna health =="
  curl -s "http://127.0.0.1:${SIONNA_PORT}/health" || true
  echo

  echo
  echo "== Sionna /link smoke test =="
  curl -s -X POST "http://127.0.0.1:${SIONNA_PORT}/link" \
    -H "Content-Type: application/json" \
    -d '{
      "tx": [-2.75, 0.0, 3.0],
      "rx": [2.75, 0.0, 3.0],
      "frequency_hz": 3500000000.0,
      "bandwidth_hz": 20000000.0,
      "tx_power_dbm": 20.0,
      "noise_floor_dbm": -95.0
    }' || true
  echo

  echo
  echo "== ROS bridge process =="
  docker exec "$ROS_CONTAINER" bash -lc 'ps aux | grep "[s]warm_bridge" || true' || true

  echo
  echo "== ROS package check =="
  docker exec "$ROS_CONTAINER" bash -lc '
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    if [ -f install/setup.bash ]; then source install/setup.bash; fi
    ros2 pkg list | grep netlab_swarm_demo || true
  ' || true

  echo
  echo "== ROS swarm topics =="
  docker exec "$ROS_CONTAINER" bash -lc '
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    if [ -f install/setup.bash ]; then source install/setup.bash; fi
    ros2 topic list | grep /swarm || true
  ' || true

  echo
  echo "== Topic info: /swarm/sionna/link_metrics =="
  docker exec "$ROS_CONTAINER" bash -lc '
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    if [ -f install/setup.bash ]; then source install/setup.bash; fi
    ros2 topic info /swarm/sionna/link_metrics -v || true
  ' || true

  echo
  echo "== One message: /swarm/sionna/link_metrics =="
  docker exec "$ROS_CONTAINER" bash -lc '
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    if [ -f install/setup.bash ]; then source install/setup.bash; fi
    timeout 5 ros2 topic echo --once /swarm/sionna/link_metrics || true
  ' || true

  echo
  echo "== One message: /swarm/drone_2/inbox =="
  docker exec "$ROS_CONTAINER" bash -lc '
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    if [ -f install/setup.bash ]; then source install/setup.bash; fi
    timeout 5 ros2 topic echo --once /swarm/drone_2/inbox || true
  ' || true

  echo
  echo "== Recent Sionna log =="
  docker exec "$SIONNA_CONTAINER" bash -lc "tail -n 80 ${SIONNA_LOG} 2>/dev/null || true" || true

  echo
  echo "== Recent ROS bridge log =="
  docker exec "$ROS_CONTAINER" bash -lc "tail -n 100 ${BRIDGE_LOG} 2>/dev/null || true" || true

  echo
  echo "========== Doctor completed =========="
}

stop_demo() {
  echo "[INFO] Stopping demo processes."

  safe_stop_ros_bridge
  safe_stop_sionna

  echo "[OK] Demo backend processes stopped. The Isaac visual script can be stopped by reloading the stage or restarting Isaac."
}

case "${1:-}" in
  build-ros)
    build_ros
    ;;
  start-sionna)
    start_sionna
    ;;
  start-ros)
    start_ros
    ;;
  start)
    start_all
    ;;
  isaac-command)
    isaac_command
    ;;
  monitor)
    monitor
    ;;
  doctor)
    doctor
    ;;
  stop)
    stop_demo
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