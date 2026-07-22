#!/usr/bin/env bash
# Compatibility adapter for historical SNaaS visual-control commands.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export NETLAB_ROOT="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  cat <<'TXT'
Usage:
  netlab_snaas_visuals.sh coverage-bubbles on|off
  netlab_snaas_visuals.sh indicator-size STATUS_SCALE [PACKET_SCALE]
  netlab_snaas_visuals.sh visuals-status

This compatibility adapter updates the authoritative the authoritative NETLAB experiment configuration
and requests automatic ROS 2/Isaac synchronization. Isaac Script Editor is not
required.
TXT
}

case "${1:-}" in
  coverage-bubbles|indicator-size|visuals-status) ;;
  -h|--help|help|"") usage; exit 0 ;;
  *) echo "[ERROR] Unsupported visual command: ${1:-}" >&2; usage >&2; exit 2 ;;
esac

NETLAB_VISUAL_ACTION="$1" NETLAB_VISUAL_ARG1="${2:-}" NETLAB_VISUAL_ARG2="${3:-}" python3 - <<'PY'
import json, os
from pathlib import Path
from apps.mission_control.backend.server import MissionControlApplication

root=Path(os.environ['NETLAB_ROOT'])
app=MissionControlApplication(root)
config=app.load_config()
visual=config['visualization']
action=os.environ['NETLAB_VISUAL_ACTION']

if action == 'visuals-status':
    print(json.dumps({'ok': True, 'visualization': visual}, indent=2, sort_keys=True))
    raise SystemExit(0)

if action == 'coverage-bubbles':
    value=os.environ.get('NETLAB_VISUAL_ARG1','').strip().lower()
    if value not in {'on','off','true','false','1','0','yes','no'}:
        raise SystemExit('coverage-bubbles expects on or off')
    visual['show_coverage_preview']=value in {'on','true','1','yes'}
elif action == 'indicator-size':
    raw=os.environ.get('NETLAB_VISUAL_ARG1','').strip()
    if not raw:
        raise SystemExit('indicator-size requires STATUS_SCALE')
    visual['status_marker_scale']=max(0.05,min(5.0,float(raw)))
    packet=os.environ.get('NETLAB_VISUAL_ARG2','').strip()
    if packet:
        visual['packet_marker_scale']=max(0.05,min(5.0,float(packet)))

result=app.save_config(config,sync=True)
print(json.dumps({
    'ok': bool(result.get('ok')),
    'durable_saved': result.get('durable_saved'),
    'runtime_applied': result.get('runtime_applied'),
    'runtime_application_status': result.get('runtime_application_status'),
    'visualization': result.get('config',{}).get('visualization'),
    'sync_signal': result.get('sync_signal'),
}, indent=2, sort_keys=True, default=str))
PY
