#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${1:-$ROOT/dist}"
STAGE="$OUT_DIR/stage"
ARCHIVE="$OUT_DIR/NETLAB.zip"
MANIFEST="$OUT_DIR/RELEASE_MANIFEST.json"
SHA_FILE="$OUT_DIR/NETLAB.zip.sha256"

rm -rf "$STAGE"
mkdir -p "$STAGE/NETLAB" "$OUT_DIR"

python3 - "$ROOT" "$STAGE/NETLAB" <<'PY'
from __future__ import annotations
import shutil,sys
from pathlib import Path
source=Path(sys.argv[1]).resolve();target=Path(sys.argv[2]).resolve()
excluded_dirs={'.git','.pytest_cache','__pycache__','.mypy_cache','.ruff_cache','build','install','log','node_modules','dist','.venv','venv'}
excluded_suffixes={'.pyc','.pyo','.zip','.tar','.tgz'}

def ignore(directory,names):
    base=Path(directory);ignored=set()
    for name in names:
        path=base/name
        try:rel=path.relative_to(source)
        except ValueError:continue
        if name in excluded_dirs:ignored.add(name);continue
        if path.is_file() and path.suffix.lower() in excluded_suffixes:ignored.add(name);continue
        if rel.as_posix()=='Docker/compose/.env':ignored.add(name);continue
        if rel.parts[:3]==('Docker','workspace','results') and name!='.gitkeep':ignored.add(name);continue
        if rel.parts[:2]==('Docker','data'):ignored.add(name);continue
    return ignored

shutil.copytree(source,target,dirs_exist_ok=True,ignore=ignore,symlinks=False)
results=target/'Docker/workspace/results';results.mkdir(parents=True,exist_ok=True);(results/'.gitkeep').touch()
for rel in ('Docker/workspace/results/mission_control','Docker/workspace/results/revisions','Docker/workspace/shared/revisions','Docker/workspace/plugins'):
    (target/rel).mkdir(parents=True,exist_ok=True)
PY

(
  cd "$STAGE/NETLAB"
  export PYTHONDONTWRITEBYTECODE=1
  export PYTHONPATH="$STAGE/NETLAB${PYTHONPATH:+:$PYTHONPATH}"
  ./scripts/diagnostics/validate_release.sh
)

find "$STAGE/NETLAB" -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE/NETLAB" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "$STAGE/NETLAB/Docker/workspace/results" -mindepth 1 ! -name '.gitkeep' -exec rm -rf {} + 2>/dev/null || true
touch "$STAGE/NETLAB/Docker/workspace/results/.gitkeep"
mkdir -p "$STAGE/NETLAB/Docker/workspace/results/mission_control" "$STAGE/NETLAB/Docker/workspace/results/revisions" "$STAGE/NETLAB/Docker/workspace/shared/revisions"

python3 - "$STAGE/NETLAB" <<'PY'
from __future__ import annotations
import hashlib,json,stat,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path(sys.argv[1]).resolve();entries=[]
self_files={'RELEASE_MANIFEST.json'}
for path in sorted(root.rglob('*')):
    if not path.is_file():continue
    rel=path.relative_to(root).as_posix()
    if rel in self_files:continue
    data=path.read_bytes();entries.append({'path':rel,'size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'mode':oct(stat.S_IMODE(path.stat().st_mode))})
manifest={
 'release':'9.0.0','generated_utc':datetime.now(timezone.utc).isoformat(),'root':'NETLAB/','file_count':len(entries),'total_file_bytes':sum(x['size_bytes'] for x in entries),
 'entrypoints':{'bootstrap':'scripts/bootstrap_host.sh --non-interactive','launch':'scripts/netlab launch','status':'scripts/netlab status','packet_doctor':'scripts/netlab packet-doctor','sync_doctor':'scripts/netlab sync-doctor','target_acceptance':'scripts/netlab target-acceptance','stop':'scripts/netlab stop'},
 'components':{'mission_control':'apps/mission_control','core':'netlab','compose':'Docker/compose/docker-compose.yml','ros2':'Docker/workspace/ros2','isaac':'Docker/workspace/isaac','sionna':'Docker/workspace/sionna','plugins':'plugins','scenarios':'scenarios'},
 'members':entries,
}
(root/'RELEASE_MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
PY

rm -f "$ARCHIVE" "$MANIFEST" "$SHA_FILE"
python3 - "$STAGE/NETLAB" "$ARCHIVE" <<'PYZIP'
from __future__ import annotations
import stat,sys,zipfile
from pathlib import Path
root=Path(sys.argv[1]).resolve();archive=Path(sys.argv[2]).resolve()
files=[path for path in sorted(root.rglob('*')) if path.is_file()]
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as output:
    for path in files:
        relative=(Path('NETLAB')/path.relative_to(root)).as_posix()
        info=zipfile.ZipInfo(relative,date_time=(2026,7,15,0,0,0))
        info.create_system=3
        info.external_attr=(stat.S_IFREG|stat.S_IMODE(path.stat().st_mode))<<16
        info.compress_type=zipfile.ZIP_DEFLATED
        output.writestr(info,path.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
print(f'packed_files={len(files)}')
PYZIP

python3 - "$ARCHIVE" "$MANIFEST" "$SHA_FILE" <<'PY'
from __future__ import annotations
import hashlib,json,sys,zipfile
from datetime import datetime,timezone
from pathlib import Path
archive,manifest_path,sha_path=map(Path,sys.argv[1:])
sha=hashlib.sha256(archive.read_bytes()).hexdigest()
with zipfile.ZipFile(archive) as zf:
    bad=zf.testzip()
    if bad:raise SystemExit(f'ZIP integrity failure: {bad}')
    infos=[x for x in zf.infolist() if not x.is_dir()]
    roots={x.filename.split('/',1)[0] for x in infos}
    if roots!={'NETLAB'}:raise SystemExit(f'Unexpected archive roots: {roots}')
    members=[]
    for info in infos:
        data=zf.read(info.filename)
        members.append({'path':info.filename,'size_bytes':info.file_size,'compressed_bytes':info.compress_size,'sha256':hashlib.sha256(data).hexdigest(),'mode':oct((info.external_attr>>16)&0o7777)})
payload={'release':'9.0.0','archive':archive.name,'sha256':sha,'size_bytes':archive.stat().st_size,'file_count':len(infos),'root':'NETLAB/','integrity':'PASS','generated_utc':datetime.now(timezone.utc).isoformat(),'members':members}
manifest_path.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8')
sha_path.write_text(f'{sha}  {archive.name}\n',encoding='utf-8')
summary={k:v for k,v in payload.items() if k!='members'}
print(json.dumps(summary,indent=2,sort_keys=True))
PY

EXTRACT_TEST="$OUT_DIR/extract-test"
rm -rf "$EXTRACT_TEST";mkdir -p "$EXTRACT_TEST"
unzip -q "$ARCHIVE" -d "$EXTRACT_TEST"
[[ "$($EXTRACT_TEST/NETLAB/scripts/netlab --version)" == "9.0.0" ]]
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$EXTRACT_TEST/NETLAB" python3 - <<PY
from pathlib import Path
from netlab.configuration import validate_file
root=Path('$EXTRACT_TEST/NETLAB')
result=validate_file(root/'Docker/workspace/shared/snaas_relay_config.json')
assert result['ok'],result['errors']
assert (root/'apps/mission_control/frontend/bootstrap_guard.js').is_file()
assert (root/'Docker/workspace/ros2/netlab_ros_env.sh').is_file()
print('packaged_configuration_valid=true')
PY
rm -rf "$EXTRACT_TEST"

echo "[OK] $ARCHIVE"
echo "[OK] $SHA_FILE"
