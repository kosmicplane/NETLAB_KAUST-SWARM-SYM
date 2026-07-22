from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports" / "validation"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

report = {
    "release": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
    "started_at": time.time(),
    "root": str(ROOT),
    "checks": [],
    "ok": True,
}


def check(name: str, command: list[str], timeout: float = 300.0, cwd: Path = ROOT) -> dict:
    started = time.perf_counter()
    env = dict(os.environ)
    env.update({"PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        item = {
            "name": name,
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "duration_s": time.perf_counter() - started,
            "stdout": completed.stdout[-30000:],
            "stderr": completed.stderr[-30000:],
        }
    except subprocess.TimeoutExpired as exc:
        item = {
            "name": name,
            "ok": False,
            "returncode": 124,
            "duration_s": time.perf_counter() - started,
            "stdout": str(exc.stdout or "")[-30000:],
            "stderr": "TIMEOUT\n" + str(exc.stderr or "")[-30000:],
        }
    report["checks"].append(item)
    report["ok"] = bool(report["ok"] and item["ok"])
    print(f"[{'PASS' if item['ok'] else 'FAIL'}] {name} ({item['duration_s']:.2f}s)", flush=True)
    return item


check(
    "python_compile",
    [
        sys.executable,
        "-c",
        """
from pathlib import Path
excluded={'.git','__pycache__','build','install','log','.pytest_cache','.mypy_cache','.ruff_cache','dist','node_modules'}
files=[]
for p in Path('.').rglob('*.py'):
    if any(part in excluded for part in p.parts):
        continue
    compile(p.read_text(encoding='utf-8'), str(p), 'exec')
    files.append(str(p))
print(f'compiled={len(files)}')
""",
    ],
)

check(
    "unittest_full_suite",
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"],
    timeout=420,
)

shell_files = sorted((ROOT / "scripts").rglob("*.sh")) + sorted((ROOT / "Docker").rglob("*.sh"))
for path in shell_files:
    check(f"bash_syntax:{path.relative_to(ROOT)}", ["bash", "-n", str(path)], timeout=30)

if shutil.which("node"):
    for path in sorted((ROOT / "apps" / "mission_control" / "frontend" / "modules").glob("*.js")):
        check(f"javascript_syntax:{path.name}", ["node", "--check", str(path)], timeout=30)

check(
    "json_yaml_scenario_gate",
    [
        sys.executable,
        "-c",
        """
import json
from pathlib import Path
from netlab.configuration import validate_file
try:
    import yaml
except Exception:
    yaml=None
bad=[]; json_count=0; yaml_count=0; scenarios=0
skip={'.git','__pycache__','.pytest_cache','build','install','log','dist','node_modules'}
for p in Path('.').rglob('*'):
    if not p.is_file() or any(part in skip for part in p.parts):
        continue
    if p.suffix.lower()=='.json':
        try: json.loads(p.read_text(encoding='utf-8')); json_count+=1
        except Exception as exc: bad.append((str(p),str(exc)))
    elif p.suffix.lower() in {'.yaml','.yml'} and yaml:
        try: yaml.safe_load(p.read_text(encoding='utf-8')); yaml_count+=1
        except Exception as exc: bad.append((str(p),str(exc)))
for p in Path('scenarios').rglob('*.json'):
    scenarios+=1
    result=validate_file(p)
    if not result['ok']: bad.append((str(p),result['errors']))
active=validate_file(Path('Docker/workspace/shared/snaas_relay_config.json'))
if not active['ok']: bad.append(('active_configuration',active['errors']))
assert not bad,bad
print(json.dumps({'json':json_count,'yaml':yaml_count,'scenarios':scenarios}))
""",
    ],
    timeout=180,
)

check("embedded_acceptance", [str(ROOT / "scripts" / "netlab"), "target-acceptance", "--embedded"], timeout=180)

report["finished_at"] = time.time()
report["duration_s"] = report["finished_at"] - report["started_at"]
json_path = REPORT_DIR / "v9_test_report.json"
json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
md = [
    "# NETLAB 9 test report",
    "",
    f"Overall: **{'PASS' if report['ok'] else 'FAIL'}**",
    "",
    f"Duration: {report['duration_s']:.2f} s",
    "",
]
for item in report["checks"]:
    md.append(f"- {'PASS' if item['ok'] else 'FAIL'} — `{item['name']}` ({item['duration_s']:.2f} s)")
(REPORT_DIR / "v9_test_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
raise SystemExit(0 if report["ok"] else 1)
