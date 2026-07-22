#!/usr/bin/env bash
# Compatibility adapter for importing a local world asset into World Lab.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSET_DIR="$ROOT/Docker/workspace/isaac/local_assets/worlds"
export NETLAB_ROOT="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  cat <<'TXT'
Usage:
  netlab_world_loader.sh setup
  netlab_world_loader.sh list
  netlab_world_loader.sh select PATH_TO_USD_ASSET
  netlab_world_loader.sh status
  netlab_world_loader.sh clear

Supported compatibility-import extensions: .usd, .usda, .usdc, .usdz.
The selected asset is registered in the authoritative experiment and synchronized
automatically. Isaac Script Editor is not required.
TXT
}

mkdir -p "$ASSET_DIR"
case "${1:-}" in
  setup) echo "[OK] World asset directory: $ASSET_DIR" ;;
  list) find "$ASSET_DIR" -maxdepth 4 -type f \( -iname '*.usd' -o -iname '*.usda' -o -iname '*.usdc' -o -iname '*.usdz' \) -print | sort ;;
  status)
    python3 - <<'PY'
import json, os
from pathlib import Path
from apps.mission_control.backend.server import MissionControlApplication
app=MissionControlApplication(Path(os.environ['NETLAB_ROOT']))
print(json.dumps({'ok':True,'world':app.load_config()['world']},indent=2,sort_keys=True))
PY
    ;;
  select)
    [[ -n "${2:-}" ]] || { echo "[ERROR] select requires a path." >&2; exit 2; }
    SOURCE="$(realpath "$2")"
    [[ -f "$SOURCE" ]] || { echo "[ERROR] Asset not found: $SOURCE" >&2; exit 1; }
    case "${SOURCE,,}" in *.usd|*.usda|*.usdc|*.usdz) ;; *) echo "[ERROR] Unsupported extension." >&2; exit 1 ;; esac
    TARGET="$ASSET_DIR/$(basename "$SOURCE")"
    cp -f "$SOURCE" "$TARGET"
    NETLAB_WORLD_CONTAINER_PATH="/workspace/isaac/local_assets/worlds/$(basename "$TARGET")" python3 - <<'PY'
import json, os
from pathlib import Path
from apps.mission_control.backend.server import MissionControlApplication
root=Path(os.environ['NETLAB_ROOT'])
app=MissionControlApplication(root)
config=app.load_config()
path=os.environ['NETLAB_WORLD_CONTAINER_PATH']
asset_id=Path(path).stem.replace(' ','_')
entry={
  'id': asset_id,
  'path': path,
  'position':[0.0,0.0,0.0],
  'rotation_rpy_deg':[0.0,0.0,0.0],
  'scale':[1.0,1.0,1.0],
  'semantic_type':'unknown',
  'collision':True,
  'electromagnetic_material':'unknown',
  'material_provenance':'unknown',
}
assets=config['world'].setdefault('assets',[])
assets[:]=[item for item in assets if item.get('id') != asset_id]
assets.append(entry)
result=app.save_config(config,sync=True)
print(json.dumps({'ok':result.get('ok'),'asset':entry,'runtime_applied':result.get('runtime_applied'),'sync_signal':result.get('sync_signal')},indent=2,sort_keys=True,default=str))
PY
    ;;
  clear)
    python3 - <<'PY'
import json, os
from pathlib import Path
from apps.mission_control.backend.server import MissionControlApplication
app=MissionControlApplication(Path(os.environ['NETLAB_ROOT']))
config=app.load_config(); config['world']['assets']=[]
result=app.save_config(config,sync=True)
print(json.dumps({'ok':result.get('ok'),'assets':[],'runtime_applied':result.get('runtime_applied'),'sync_signal':result.get('sync_signal')},indent=2,sort_keys=True,default=str))
PY
    ;;
  -h|--help|help|"") usage ;;
  *) echo "[ERROR] Unsupported command: ${1:-}" >&2; usage >&2; exit 2 ;;
esac
