#!/usr/bin/env bash
# Compatibility command for historical NETLAB SNaaS workflows.
# New automation is implemented by ./scripts/netlab and Mission Control.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
NETLAB="$ROOT/scripts/netlab"
COMPOSE_DIR="$ROOT/Docker/compose"

usage() {
  cat <<'EOF'
NETLAB SNaaS compatibility command

Preferred commands:
  ./scripts/netlab launch
  ./scripts/netlab start
  ./scripts/netlab packet-doctor

Compatible historical commands:
  configure | start | start-runtime | start-current | stop | doctor
  sync-isaac | apply-config | restore-protocols
  fail N | heal N | standby N | reset
  drones N | branches N | coverage RANGE WIDTH | link-range RANGE HARD
  altitude MIN MAX | pattern NAME [AMPLITUDE] [SPEED]
  motion NAME [AMPLITUDE] [SPEED] | amplitude VALUE | speed VALUE
  monitor | pretty [TOPIC] | pretty-once [TOPIC]
  px4-start | px4-stop | px4-status | px4-logs | mission-control
EOF
}

patch_config() {
  local action="$1"; shift || true
  NETLAB_ROOT="$ROOT" NETLAB_COMPAT_ACTION="$action" NETLAB_COMPAT_ARGS="$(printf '%s\n' "$@" | python3 -c 'import json,sys; print(json.dumps([x.rstrip("\n") for x in sys.stdin.readlines()]))')" \
  PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY'
import copy, json, os
from pathlib import Path
from netlab.config import default_experiment, load_experiment, save_experiment, validate_experiment
from netlab.topology import generate_branches
from netlab.state import StateStore

root=Path(os.environ['NETLAB_ROOT'])
store=StateStore(root)
try:
    cfg=load_experiment(store.paths.config)
except Exception:
    cfg=default_experiment()
action=os.environ['NETLAB_COMPAT_ACTION']
args=json.loads(os.environ.get('NETLAB_COMPAT_ARGS','[]'))

def f(i, default=0.0):
    try: return float(args[i])
    except Exception: return float(default)

def n(i, default=0):
    try: return int(float(args[i]))
    except Exception: return int(default)

if action == 'restore':
    cfg=default_experiment()
elif action == 'drones':
    total=max(1,n(0,cfg['swarm']['drone_count']))
    old={int(d['index']):copy.deepcopy(d) for d in cfg['swarm']['drones']}
    template=default_experiment()['swarm']['drones'][0]
    drones=[]
    for idx in range(1,total+1):
        d=old.get(idx,copy.deepcopy(template)); d['index']=idx; d['id']=f'drone_{idx}'
        if idx not in old: d['position']=[idx*28.0,0.0,28.0+(idx-1)%3]
        drones.append(d)
    relay=min(total,max(1,int(cfg['swarm'].get('relay_count',total))))
    for d in drones: d['role']='relay' if int(d['index'])<=relay else 'standby'
    cfg['swarm'].update(drone_count=total,relay_count=relay,standby_count=total-relay,drones=drones)
    cfg['topology']['branches']=generate_branches(relay,min(int(cfg['topology'].get('branch_count',1)),relay),cfg['topology'].get('mode','chain'))
elif action == 'branches':
    count=max(1,n(0,1)); relay=int(cfg['swarm']['relay_count'])
    mode='chain' if count==1 else 'parallel'
    cfg['topology'].update(mode=mode,branch_count=count,branches=generate_branches(relay,count,mode))
elif action == 'coverage':
    cfg['service_region']['length_m']=max(1.0,f(0,cfg['service_region']['length_m']))
    cfg['service_region']['width_m']=max(1.0,f(1,cfg['service_region']['width_m']))
elif action == 'link-range':
    operational=max(0.1,f(0,cfg['communication']['operational_range_m']))
    hard=max(operational,f(1,operational))
    cfg['communication']['operational_range_m']=operational
    cfg['communication']['hard_outage_distance_m']=hard
elif action == 'altitude':
    lo=f(0,cfg['service_region']['min_altitude_m']); hi=f(1,cfg['service_region']['max_altitude_m'])
    cfg['service_region']['min_altitude_m']=min(lo,hi); cfg['service_region']['max_altitude_m']=max(lo,hi)
elif action in {'pattern','motion'}:
    cfg['swarm']['mobility']['model']=args[0] if args else 'hold'
    if len(args)>1 and args[1]: cfg['swarm']['mobility'].setdefault('parameters',{})['amplitude_m']=f(1,0)
    if len(args)>2 and args[2]: cfg['swarm']['mobility'].setdefault('parameters',{})['speed_multiplier']=f(2,1)
elif action == 'amplitude':
    cfg['swarm']['mobility'].setdefault('parameters',{})['amplitude_m']=f(0,0)
elif action == 'speed':
    cfg['swarm']['mobility'].setdefault('parameters',{})['speed_multiplier']=f(0,1)
else:
    raise SystemExit(f'unsupported compatibility patch: {action}')

validation=validate_experiment(cfg,strict=False)
if not validation['ok']:
    print(json.dumps({'ok':False,'validation':validation},indent=2)); raise SystemExit(2)
save_experiment(store.paths.config,cfg,emit_legacy=True)
from apps.mission_control.backend.server import MissionControlApplication
result=MissionControlApplication(root).save_config(cfg,sync=True)
print(json.dumps({'ok':result.get('ok',False),'action':action,'config_hash':result.get('config_hash'),'ros':result.get('ros'),'sync_signal':result.get('sync_signal')},indent=2,default=str))
PY
}

ros_container() {
  (cd "$COMPOSE_DIR" && docker compose --env-file .env -f docker-compose.yml ps -q ros2-core) | head -1
}

topic_echo() {
  local topic="${1:-/swarm/chain/status}" once="${2:-0}" cid
  cid="$(ros_container)"
  [[ -n "$cid" ]] || { echo "[ERROR] ROS 2 service is not running."; exit 1; }
  local cmd="source /opt/ros/jazzy/setup.bash; cd /workspace/ros2; [ -f install/setup.bash ] && source install/setup.bash; ros2 topic echo '$topic'"
  [[ "$once" == "1" ]] && cmd+=" --once"
  docker exec -it "$cid" bash -lc "$cmd"
}

case "${1:-}" in
  configure) "$NETLAB" init --force; echo "Open Mission Control at http://127.0.0.1:8765 and use Mission Designer." ;;
  start|start-runtime|start-current|launch-mission|start-existing|start-mission|launch|start-sionna|build-ros|start-chain) "$NETLAB" start --no-build ;;
  stop) "$NETLAB" stop ;;
  doctor) "$NETLAB" packet-doctor ;;
  sync-isaac|isaac-command) "$NETLAB" sync ;;
  apply-config) "$NETLAB" start-experiment ;;
  restore-protocols) patch_config restore ;;
  fail) "$NETLAB" fail "${2:?UAV index is required}" ;;
  heal) "$NETLAB" heal "${2:?UAV index is required}" ;;
  standby) "$NETLAB" standby "${2:?UAV index is required}" ;;
  reset) "$NETLAB" reset-chain ;;
  drones) patch_config drones "${2:?Drone count is required}" ;;
  branches) patch_config branches "${2:?Branch count is required}" ;;
  coverage) patch_config coverage "${2:?Range is required}" "${3:?Width is required}" ;;
  link-range) patch_config link-range "${2:?Operational range is required}" "${3:-${2}}" ;;
  altitude) patch_config altitude "${2:?Minimum altitude is required}" "${3:?Maximum altitude is required}" ;;
  pattern|motion) patch_config "$1" "${2:-hold}" "${3:-}" "${4:-}" ;;
  amplitude) patch_config amplitude "${2:?Amplitude is required}" ;;
  speed) patch_config speed "${2:?Speed multiplier is required}" ;;
  pretty) topic_echo "${2:-/swarm/chain/status}" 0 ;;
  pretty-once) topic_echo "${2:-/swarm/chain/status}" 1 ;;
  monitor|dashboard|sionna-dashboard) "$NETLAB" logs "${2:-}" --tail 200 ;;
  px4-start) (cd "$COMPOSE_DIR" && docker compose --env-file .env -f docker-compose.yml --profile px4 up -d px4) ;;
  px4-stop) (cd "$COMPOSE_DIR" && docker compose --env-file .env -f docker-compose.yml stop px4) ;;
  px4-status) (cd "$COMPOSE_DIR" && docker compose --env-file .env -f docker-compose.yml ps px4) ;;
  px4-logs) (cd "$COMPOSE_DIR" && docker compose --env-file .env -f docker-compose.yml logs --tail=200 px4) ;;
  mission-control) "$ROOT/scripts/netlab_mission_control.sh" start ;;
  coverage-bubbles|indicator-size|visuals-status) exec "$ROOT/scripts/netlab_snaas_visuals.sh" "$@" ;;
  -h|--help|help|"") usage ;;
  *) echo "[ERROR] Unsupported compatibility command: $1"; usage; exit 2 ;;
esac
