#!/usr/bin/env bash
set -eo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS="$ROOT/Docker/workspace/results/mission_control"; PIDFILE="$RESULTS/server.pid"; LOG="$RESULTS/server.log"
mkdir -p "$RESULTS"; chmod 2775 "$RESULTS" 2>/dev/null || true
is_running(){ [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }
case "${1:-start}" in
 start)
  if is_running; then echo "[OK] Mission Control already running with PID $(cat "$PIDFILE")"; exit 0; fi
  export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
  nohup python3 "$ROOT/apps/mission_control/backend/server.py" --host 0.0.0.0 --port "${NETLAB_MISSION_PORT:-8765}" >>"$LOG" 2>&1 &
  echo $! > "$PIDFILE"; chmod 664 "$PIDFILE"; sleep 1
  if ! is_running; then echo '[ERROR] Mission Control failed to start.' >&2; tail -100 "$LOG" >&2; exit 1; fi
  echo "[OK] Mission Control running with PID $(cat "$PIDFILE")"
  ;;
 stop)
  if is_running; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; for _ in {1..20};do is_running||break;sleep .2;done; fi
  rm -f "$PIDFILE"; echo '[OK] Mission Control stopped.';;
 restart) "$0" stop;exec "$0" start;;
 status) if is_running;then echo running;else echo stopped;exit 1;fi;;
 logs) tail -f "$LOG";;
 *) echo "usage: $0 {start|stop|restart|status|logs}" >&2;exit 2;;
esac
