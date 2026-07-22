"""Isolated process entry point for researcher algorithm hooks."""
from __future__ import annotations

import importlib.util
import json
import os
import resource
import signal
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping


class _Deadline(Exception):
    pass


def _timeout(_signum: int, _frame: Any) -> None:
    raise _Deadline("algorithm execution deadline exceeded")


def _apply_limits(request: Mapping[str, Any]) -> None:
    memory_mb = max(1024, int(request.get("memory_mb", 256)))
    output_kb = max(8, int(request.get("output_kb", 256)))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (output_kb * 1024, output_kb * 1024))
    except Exception:
        pass
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    except Exception:
        pass


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(f"netlab_algorithm_{path.stem}_{os.getpid()}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load algorithm entry point {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(request: Mapping[str, Any]) -> dict[str, Any]:
    entrypoint = Path(str(request.get("entrypoint", ""))).resolve()
    package_root = Path(str(request.get("package_root", entrypoint.parent))).resolve()
    entrypoint.relative_to(package_root)
    if not entrypoint.is_file():
        raise FileNotFoundError(entrypoint)
    hook = str(request.get("hook", "step"))
    observation = request.get("observation", {})
    parameters = request.get("parameters", {})
    if not isinstance(observation, Mapping) or not isinstance(parameters, Mapping):
        raise TypeError("observation and parameters must be JSON objects")
    _apply_limits(request)
    timeout_s = max(0.001, float(request.get("timeout_s", 0.25)))
    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_s)
    try:
        module = _load(entrypoint)
        if not hasattr(module, hook):
            if hook == "step" and hasattr(module, "plan_positions"):
                result = {"desired_positions": module.plan_positions(dict(observation))}
            else:
                raise AttributeError(f"Algorithm has no hook {hook!r}")
        else:
            function = getattr(module, hook)
            try:
                result = function(dict(observation), dict(parameters))
            except TypeError:
                # Backwards-compatible single-argument hook.
                context = dict(observation)
                context.setdefault("parameters", dict(parameters))
                result = function(context)
        json.dumps(result, allow_nan=False)
        return {"ok": True, "result": result}
    except _Deadline:
        return {"ok": False, "error": {"code": "ALGORITHM_TIMEOUT", "message": "Algorithm exceeded its execution budget."}}
    except BaseException as exc:  # isolated trust boundary
        return {
            "ok": False,
            "error": {
                "code": "ALGORITHM_EXCEPTION",
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=30),
            },
        }
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


def main() -> int:
    try:
        request = json.loads(sys.stdin.read() or "{}")
        if not isinstance(request, Mapping):
            raise TypeError("request must be a JSON object")
        response = run(request)
    except BaseException as exc:
        response = {"ok": False, "error": {"code": "ALGORITHM_WORKER_PROTOCOL", "message": str(exc)}}
    sys.stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    sys.stdout.flush()
    return 0 if response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
