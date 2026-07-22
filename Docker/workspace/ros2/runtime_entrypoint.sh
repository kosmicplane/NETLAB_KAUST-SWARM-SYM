#!/usr/bin/env bash
# NETLAB ROS 2 runtime supervisor.
# Nounset is deliberately deferred until every ROS-generated setup file has
# been sourced. This prevents AMENT_TRACE_SETUP_FILES restart loops.
set -eo pipefail

export ROS_DISTRO="${ROS_DISTRO:-jazzy}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"
export PYTHONPATH="/workspace/netlab${PYTHONPATH:+:$PYTHONPATH}"
export SNAAS_CONFIG="${SNAAS_CONFIG:-/workspace/shared/snaas_relay_config.json}"
export SNAAS_RESULTS_DIR="${SNAAS_RESULTS_DIR:-/workspace/results}"
export SNAAS_LATEST_STATUS="${SNAAS_LATEST_STATUS:-/workspace/results/snaas_relay_latest_status.json}"
export SNAAS_PACKET_HEARTBEAT="${SNAAS_PACKET_HEARTBEAT:-/workspace/results/snaas_packet_runtime_heartbeat.json}"
export SNAAS_ROS_REVISION_ACK="${SNAAS_ROS_REVISION_ACK:-/workspace/results/revision_ros_ack.json}"
export SNAAS_ALGORITHM_HEARTBEAT="${SNAAS_ALGORITHM_HEARTBEAT:-/workspace/results/snaas_algorithm_runtime_heartbeat.json}"
export SNAAS_PLUGIN_SELECTION="${SNAAS_PLUGIN_SELECTION:-/workspace/results/snaas_active_algorithm.json}"
export SIONNA_URL="${SIONNA_URL:-http://127.0.0.1:8090/link}"
export SNAAS_PLUGINS_DIR="${SNAAS_PLUGINS_DIR:-/workspace/plugins}"
export NETLAB_SHARED_FILE_MODE="${NETLAB_SHARED_FILE_MODE:-0664}"
export NETLAB_SHARED_DIR_MODE="${NETLAB_SHARED_DIR_MODE:-2775}"
export NETLAB_SHARED_DIR="${NETLAB_SHARED_DIR:-/workspace/shared}"
export NETLAB_RESULTS_DIR="${NETLAB_RESULTS_DIR:-/workspace/results}"

# shellcheck disable=SC1091
source /workspace/ros2/netlab_ros_env.sh
netlab_source_ros_environment --base-only

mkdir -p /workspace/results /workspace/shared /workspace/ros2/log
chmod 2775 /workspace/results /workspace/shared 2>/dev/null || true
cd /workspace/ros2

needs_build=0
if [[ ! -r install/setup.bash ]]; then
  needs_build=1
elif find src -type f -newer install/setup.bash -print -quit 2>/dev/null | grep -q .; then
  needs_build=1
fi

if [[ "$needs_build" == "1" ]]; then
  echo "[NETLAB-ROS] Building complete ROS 2 workspace..."
  rm -rf build install log
  colcon build \
    --symlink-install \
    --event-handlers console_direct+ \
    --cmake-args -DCMAKE_BUILD_TYPE=RelWithDebInfo
fi

netlab_source_ros_environment /workspace/ros2/install/setup.bash

# Fail before process launch if generated interfaces or runtime packages are missing.
python3 - <<'PYIMPORT'
from netlab_interfaces.msg import AlgorithmAction, AlgorithmObservation, AlgorithmStatus
from netlab_interfaces.srv import ValidateAlgorithm
from netlab_swarm_demo.algorithm_bridge import ResearcherAlgorithmBridge
from netlab_swarm_demo.snaas_relay_chain import SnaasRelayChain
print("[NETLAB-ROS] Interface and runtime import validation passed.")
PYIMPORT

# Strict undefined-variable checking is safe only after ROS and the overlay are loaded.
set -u

python3 - <<'PY'
import os, time
from pathlib import Path
from netlab.io import atomic_write_json, ensure_shared_directory
results = ensure_shared_directory(os.environ.get('SNAAS_RESULTS_DIR', '/workspace/results'))
atomic_write_json(Path(os.environ['SNAAS_PACKET_HEARTBEAT']), {
    'timestamp': time.time(),
    'ready': False,
    'state': 'STARTING',
    'pid': os.getpid(),
    'component': 'packet_runtime_supervisor',
})
PY

# Remove only known stale NETLAB children. Never kill unrelated ROS nodes.
pkill -f "ros2 run netlab_swarm_demo snaas_relay_chain" 2>/dev/null || true
pkill -f "/workspace/ros2/netlab_revision_agent.py" 2>/dev/null || true
pkill -f "ros2 run netlab_swarm_demo algorithm_bridge" 2>/dev/null || true

python3 -u /workspace/ros2/netlab_revision_agent.py &
REVISION_AGENT_PID=$!
ros2 run netlab_swarm_demo algorithm_bridge &
ALGORITHM_BRIDGE_PID=$!
ros2 run netlab_swarm_demo snaas_relay_chain &
PACKET_RUNTIME_PID=$!

echo "[NETLAB-ROS] Revision agent PID: ${REVISION_AGENT_PID}"
echo "[NETLAB-ROS] Researcher algorithm bridge PID: ${ALGORITHM_BRIDGE_PID}"
echo "[NETLAB-ROS] Authoritative packet runtime PID: ${PACKET_RUNTIME_PID}"

shutdown() {
  local code="${1:-0}"
  trap - TERM INT EXIT
  kill -TERM "$PACKET_RUNTIME_PID" "$ALGORITHM_BRIDGE_PID" "$REVISION_AGENT_PID" 2>/dev/null || true
  wait "$PACKET_RUNTIME_PID" 2>/dev/null || true
  wait "$ALGORITHM_BRIDGE_PID" 2>/dev/null || true
  wait "$REVISION_AGENT_PID" 2>/dev/null || true
  exit "$code"
}
trap 'shutdown 143' TERM
trap 'shutdown 130' INT
trap 'shutdown $?' EXIT

# Exit if either critical child exits; Compose will surface the exact exit code.
set +e
wait -n "$PACKET_RUNTIME_PID" "$ALGORITHM_BRIDGE_PID" "$REVISION_AGENT_PID"
code=$?
set -e
printf '[NETLAB-ROS][ERROR] A critical ROS runtime child exited with code %s.\n' "$code" >&2
shutdown "$code"
