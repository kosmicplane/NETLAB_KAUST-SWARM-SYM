#!/usr/bin/env bash
# Compatibility adapter for the historical two-drone/swarm demo entry point.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETLAB="$ROOT/scripts/netlab"

usage() {
  cat <<'TXT'
Usage:
  netlab_swarm_demo.sh start
  netlab_swarm_demo.sh doctor
  netlab_swarm_demo.sh monitor
  netlab_swarm_demo.sh stop
  netlab_swarm_demo.sh isaac-command

The historical manual Sionna/ROS/Isaac demo has been superseded by the complete
NETLAB lifecycle. Start Stack now launches the link service, ROS 2 packet runtime,
and Isaac autoload automatically.
TXT
}

case "${1:-}" in
  start|start-sionna|start-ros|build-ros) exec "$NETLAB" start ;;
  doctor) exec "$NETLAB" packet-doctor ;;
  monitor) exec "$NETLAB" logs --tail 200 ;;
  stop) exec "$NETLAB" stop ;;
  isaac-command)
    cat <<'TXT'
No Isaac Script Editor command is required in NETLAB.
Use Mission Control or run:
  ./scripts/netlab sync
Isaac consumes the authoritative scenario signal and writes a scene acknowledgement.
TXT
    ;;
  -h|--help|help|"") usage ;;
  *) echo "[ERROR] Unsupported compatibility command: ${1:-}" >&2; usage >&2; exit 2 ;;
esac
