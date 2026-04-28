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
SIONNA_URL="${SIONNA_URL:-http://127.0.0.1:${SIONNA_PORT}/link}"

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
  SIONNA_URL=$SIONNA_URL
EOF
}

ensure_stack_running() {
  echo "[INFO] Checking Docker Compose services..."
  compose ps
}

build_ros() {
  ensure_stack_running
  echo "[INFO] Building ROS 2 package netlab_swarm_demo inside $ROS_CONTAINER"
  docker exec "$ROS_CONTAINER" bash -lc '
    set -e
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    colcon build --symlink-install --packages-select netlab_swarm_demo
  '
  echo "[OK] ROS 2 package built."
}

start_sionna() {
  ensure_stack_running
  echo "[INFO] Starting Sionna real-time link service on port ${SIONNA_PORT}"
  docker exec "$SIONNA_CONTAINER" bash -lc 'pkill -f "[r]ealtime_link_server.py" || true'
  docker exec -d "$SIONNA_CONTAINER" bash -lc "
    cd /workspace/sionna && \
    SIONNA_LINK_PORT=${SIONNA_PORT} python3 realtime_link_server.py \
      > /workspace/results/sionna_link_server.log 2>&1
  "
  sleep 2
  echo "[INFO] Sionna health check from Brev host:"
  curl -s "http://127.0.0.1:${SIONNA_PORT}/health" || true
  echo
}

start_ros() {
  ensure_stack_running
  echo "[INFO] Starting ROS 2 swarm bridge using SIONNA_URL=${SIONNA_URL}"
  docker exec "$ROS_CONTAINER" bash -lc 'pkill -f "[n]etlab_swarm_demo.swarm_bridge" || true; pkill -f "ros2 run netlab_swarm_demo [s]warm_bridge" || true'
  docker exec -d "$ROS_CONTAINER" bash -lc "
    set -e
    source /opt/ros/jazzy/setup.bash
    cd /workspace/ros2
    if [ -f install/setup.bash ]; then source install/setup.bash; fi
    export SIONNA_URL='${SIONNA_URL}'
    ros2 run netlab_swarm_demo swarm_bridge \
      > /workspace/results/swarm_bridge.log 2>&1
  "
  sleep 2
  echo "[OK] ROS bridge process requested. Check /workspace/results/swarm_bridge.log if needed."
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
   docker exec -it ${SIONNA_CONTAINER} bash -lc 'tail -f /workspace/results/sionna_link_server.log'

2) Monitor ROS bridge logs:
   docker exec -it ${ROS_CONTAINER} bash -lc 'tail -f /workspace/results/swarm_bridge.log'

3) List swarm ROS topics:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic list | grep /swarm'

4) Echo the Sionna link metrics:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic echo /swarm/sionna/link_metrics'

5) Echo Drone 2 inbox messages:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 topic echo /swarm/drone_2/inbox'

6) Run the compact ROS monitor node:
   docker exec -it ${ROS_CONTAINER} bash -lc 'source /opt/ros/jazzy/setup.bash && cd /workspace/ros2 && source install/setup.bash && ros2 run netlab_swarm_demo swarm_monitor'
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
  echo "== Sionna health =="
  curl -s "http://127.0.0.1:${SIONNA_PORT}/health" || true
  echo

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
  echo "== Recent Sionna log =="
  docker exec "$SIONNA_CONTAINER" bash -lc 'tail -n 60 /workspace/results/sionna_link_server.log 2>/dev/null || true' || true

  echo
  echo "== Recent ROS bridge log =="
  docker exec "$ROS_CONTAINER" bash -lc 'tail -n 80 /workspace/results/swarm_bridge.log 2>/dev/null || true' || true

  echo
  echo "========== Doctor completed =========="
}

stop_demo() {
  echo "[INFO] Stopping demo processes."
  docker exec "$ROS_CONTAINER" bash -lc 'pkill -f "[n]etlab_swarm_demo.swarm_bridge" || true; pkill -f "ros2 run netlab_swarm_demo [s]warm_bridge" || true' || true
  docker exec "$SIONNA_CONTAINER" bash -lc 'pkill -f "[r]ealtime_link_server.py" || true' || true
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
