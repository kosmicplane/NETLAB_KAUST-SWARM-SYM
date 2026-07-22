#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1

step() { printf '\n[%s] %s\n' "$1" "$2"; }

step 1/13 "Release identity"
[[ "$(cat VERSION)" == "9.0.0" ]]
[[ "$(./scripts/netlab --version)" == "9.0.0" ]]
grep -q 'version = "9.0.0"' pyproject.toml

step 2/13 "Python compilation"
python3 - <<'PY'
from pathlib import Path
excluded={'.git','__pycache__','build','install','log','.pytest_cache','.mypy_cache','.ruff_cache','dist','node_modules'}
files=[]
for path in Path('.').rglob('*.py'):
    if any(part in excluded for part in path.parts):
        continue
    compile(path.read_text(encoding='utf-8'),str(path),'exec');files.append(path)
print(f'compiled={len(files)}')
PY

step 3/13 "Shell syntax"
while IFS= read -r -d '' file; do bash -n "$file"; done < <(find scripts Docker -type f -name '*.sh' -print0)

step 4/13 "JavaScript module syntax"
if command -v node >/dev/null 2>&1; then
  while IFS= read -r -d '' file; do node --check "$file" >/dev/null; done < <(find apps/mission_control/frontend/modules -type f -name '*.js' -print0)
else
  echo '[WARN] node unavailable; JavaScript syntax verification skipped.'
fi

step 5/13 "JSON, YAML, scenarios, and active configuration"
python3 - <<'PY'
from pathlib import Path
import json
from netlab.configuration import validate_file
try:
 import yaml
except Exception:
 yaml=None
bad=[];jc=yc=0
skip={'.git','__pycache__','.pytest_cache','build','install','log','dist','node_modules'}
for p in Path('.').rglob('*'):
 if not p.is_file() or any(part in skip for part in p.parts): continue
 if p.suffix.lower()=='.json':
  try:json.loads(p.read_text(encoding='utf-8'));jc+=1
  except Exception as e:bad.append((str(p),str(e)))
 elif p.suffix.lower() in {'.yaml','.yml'} and yaml:
  try:yaml.safe_load(p.read_text(encoding='utf-8'));yc+=1
  except Exception as e:bad.append((str(p),str(e)))
scenarios=list(Path('scenarios').rglob('*.json'))
for p in scenarios:
 r=validate_file(p)
 if not r['ok']:bad.append((str(p),r['errors']))
active=validate_file(Path('Docker/workspace/shared/snaas_relay_config.json'))
if not active['ok']:bad.append(('active_configuration',active['errors']))
assert not bad,bad
print(f'json={jc} yaml={yc} scenarios={len(scenarios)}')
PY

step 6/13 "Compose and P0 startup contracts"
python3 - <<'PY'
from pathlib import Path
try:
 import yaml
except Exception as exc: raise SystemExit(f'PyYAML unavailable: {exc}')
compose=yaml.safe_load(Path('Docker/compose/docker-compose.yml').read_text(encoding='utf-8')) or {}
services=set((compose.get('services') or {}).keys());required={'sionna-engine','ros2-core','isaac'}
assert required<=services,(required-services)
ros=Path('Docker/workspace/ros2/runtime_entrypoint.sh').read_text(encoding='utf-8')
helper=Path('Docker/workspace/ros2/netlab_ros_env.sh').read_text(encoding='utf-8')
assert 'netlab_source_ros_environment --base-only' in ros
assert 'colcon build' in ros and '--packages-select netlab_swarm_demo' not in ros
assert 'set +u' in helper and ('restore_nounset' in helper or 'had_nounset' in helper)
host=Path('scripts/bootstrap_host.sh').read_text(encoding='utf-8')
assert 'command -v docker' in host and 'docker info' in host
assert 'apt-get install -y --no-install-recommends docker.io' in host
assert 'apt-get install -y --no-install-recommends containerd.io' not in host
for required_file in ('netlab/io.py','netlab/revisions.py','netlab/synchronization.py','netlab/bootstrap.py','apps/mission_control/frontend/bootstrap_guard.js'):
 assert Path(required_file).is_file(),required_file
print('services='+','.join(sorted(services)))
PY

step 7/13 "Frontend delivery and module identity"
python3 - <<'PY'
from pathlib import Path
import json,re
front=Path('apps/mission_control/frontend')
package=json.loads((front/'package.json').read_text(encoding='utf-8'))
assert package.get('type')=='module'
index=(front/'index.html').read_text(encoding='utf-8')
assert 'bootstrap_guard.js' in index and 'type="module"' in index
app=(front/'modules/app.js').read_text(encoding='utf-8')
assert 'window.__NETLAB_APP_READY__' in app
assert len(re.findall(r"\['[a-z-]+',\s*'",app))>=17
PY

step 8/13 "Automated tests"
python3 tests/run_all.py

step 9/13 "Mission Control self-test"
python3 tools/mission_control/netlab_mission_control.py --self-test

step 10/13 "Documentation and English-only interface"
python3 - <<'PY'
from pathlib import Path
import re
errors=[];checked=0
for p in Path('.').rglob('*.md'):
 if any(part in {'.git','dist','stage'} for part in p.parts):continue
 text=p.read_text(encoding='utf-8',errors='replace')
 for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',text):
  if target.startswith(('http://','https://','#','mailto:')):continue
  clean=target.split('#',1)[0]
  if clean and not (p.parent/clean).resolve().exists():errors.append(f'{p}: {target}')
  checked+=1
forbidden=('Demo con User','Ejecutar demo guiada','Primera simulación')
for p in Path('apps').rglob('*'):
 if p.is_file() and p.suffix.lower() in {'.py','.js','.html','.css','.json'}:
  text=p.read_text(encoding='utf-8',errors='replace')
  for phrase in forbidden:
   if phrase in text:errors.append(f'{p}: {phrase}')
assert not errors,'\n'.join(errors)
print(f'links_checked={checked}')
PY

step 11/13 "Repository hygiene"
if find . -path './.git' -prune -o -type f \( -iname '*PATCH*.zip' -o -iname '*HOTFIX*.zip' \) -print | grep -q .; then
  echo '[ERROR] Historical patch archives remain in the release tree.' >&2
  exit 1
fi
[[ ! -d Docker/docker/pegasus ]]

step 12/13 "OpenAPI and SBOM"
python3 - <<'PY'
from pathlib import Path
import json
try:import yaml
except Exception as exc:raise SystemExit(exc)
for path in ('openapi/netlab-openapi.yaml','schemas/api/openapi-v1.yaml'):
 spec=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
 assert str(spec['info']['version'])=='9.0.0',(path,spec['info']['version'])
sbom=json.loads(Path('security/sbom.cdx.json').read_text(encoding='utf-8'))
assert sbom.get('bomFormat')=='CycloneDX'
PY


step 13/13 "Researcher algorithm and action contracts"
python3 - <<'PYALG'
from pathlib import Path
import json,re
from netlab.algorithm_runtime import AlgorithmRegistry
root=Path('.')
registry=AlgorithmRegistry(root)
packages=registry.discover()
invalid={p.manifest.algorithm_id:list(p.errors) for p in packages if not p.valid}
assert len(packages)>=27,len(packages)
assert not invalid,invalid
required={
 'researcher_chain_spacing','connectivity_aware_formation','learn_as_you_fly_placement',
 'joint_trajectory_communication_optimizer','rotary_wing_energy_optimizer',
 'graph_connectivity_controller','voronoi_coverage_controller','distributed_flocking_controller',
 'cbf_safety_filter','data_driven_connectivity_controller','mobility_resilient_spectrum_sharing',
 'collaborative_beamforming','aoi_aware_scheduler',
}
identifiers={p.manifest.algorithm_id for p in packages}
assert required<=identifiers,sorted(required-identifiers)
registry_payload=json.loads(Path('apps/mission_control/action_registry.json').read_text(encoding='utf-8'))
actions=registry_payload.get('actions',registry_payload)
assert isinstance(actions,list) and len(actions)>=50
button_ids=set()
for path in Path('apps/mission_control/frontend/modules').glob('*.js'):
 text=path.read_text(encoding='utf-8')
 button_ids.update(re.findall(r'<button[^>]+id=["\']([^"\']+)',text))
mapped={str(item.get('frontend_control','')) for item in actions if isinstance(item,dict)}
missing=sorted(button_ids-mapped)
assert not missing,missing
for rel in (
 'Docker/workspace/ros2/src/netlab_interfaces/msg/AlgorithmObservation.msg',
 'Docker/workspace/ros2/src/netlab_interfaces/msg/AlgorithmAction.msg',
 'Docker/workspace/ros2/src/netlab_interfaces/msg/AlgorithmStatus.msg',
 'Docker/workspace/ros2/src/netlab_interfaces/srv/ValidateAlgorithm.srv',
 'Docker/workspace/ros2/src/netlab_interfaces/action/RunAlgorithm.action',
 'Docker/workspace/ros2/src/netlab_swarm_demo/netlab_swarm_demo/algorithm_bridge.py',
 'docs/developer/algorithm_sdk.md',
 'docs/research/algorithm_source_matrix.csv',
 'docs/research/algorithm_benchmark_protocol.md',
):
 assert Path(rel).is_file(),rel
print(f'algorithms={len(packages)} action_contracts={len(actions)}')
PYALG

echo '[OK] NETLAB 9 release validation completed.'
