"""Isolated subprocess entry point for researcher plugins.

The parent process sends one JSON request through standard input.  The worker
loads exactly one plugin file, invokes one recognized hook, emits one JSON
response, and exits.  This avoids forking Mission Control after HTTP/SSE worker
threads have started and gives the parent a hard OS-level timeout boundary.
"""
from __future__ import annotations

import importlib.util
import json
import signal
import sys
from pathlib import Path
from typing import Any, Mapping


class PluginDeadlineExceeded(TimeoutError):
    """Raised inside the isolated worker when the plugin deadline expires."""


def _deadline_handler(_signum: int, _frame: Any) -> None:
    raise PluginDeadlineExceeded("Plugin execution exceeded its configured deadline.")


def invoke(path: Path, hook: str, context: Mapping[str, Any], timeout_s: float) -> dict[str, Any]:
    previous_handler = None
    timer_enabled = hasattr(signal, "setitimer") and timeout_s > 0
    try:
        if timer_enabled:
            previous_handler = signal.signal(signal.SIGALRM, _deadline_handler)
            signal.setitimer(signal.ITIMER_REAL, float(timeout_s))
        resolved = path.expanduser().resolve(strict=True)
        if resolved.suffix.lower() != ".py":
            raise ValueError("Plugin path must reference a Python source file.")
        spec = importlib.util.spec_from_file_location("netlab_user_plugin", str(resolved))
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not construct plugin module specification.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        function = getattr(module, hook, None)
        if not callable(function):
            raise AttributeError(f"Plugin does not define {hook}.")
        result = function(dict(context))
        # Validate JSON serializability inside the worker so the parent always
        # receives one deterministic protocol response.
        json.dumps(result, ensure_ascii=False, allow_nan=False)
        return {"ok": True, "result": result}
    except PluginDeadlineExceeded as exc:
        return {"ok": False, "error": "PLUGIN_TIMEOUT", "details": str(exc)}
    except BaseException as exc:  # isolated process boundary
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        if timer_enabled:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            if previous_handler is not None:
                signal.signal(signal.SIGALRM, previous_handler)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            raise ValueError("Worker request must be a JSON object.")
        path = Path(str(payload.get("path", "")))
        hook = str(payload.get("hook", ""))
        context = payload.get("context", {})
        if not isinstance(context, dict):
            raise ValueError("Plugin context must be a JSON object.")
        timeout_s = max(0.001, float(payload.get("timeout_s", 0.25)))
        response = invoke(path, hook, context, timeout_s)
    except BaseException as exc:
        response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    sys.stdout.write(json.dumps(response, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    sys.stdout.flush()
    return 0 if response.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
