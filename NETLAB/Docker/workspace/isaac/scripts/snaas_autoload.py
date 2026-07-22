# NETLAB Isaac Sim SNaaS autoloader.
# This script is executed by Kit/Isaac from Docker Compose. It waits a few
# frames for the app/stage to settle, then loads the SNaaS digital-twin scene.

from __future__ import annotations

import json
import os
from pathlib import Path
import time
import traceback

import omni.kit.app

from netlab.io import atomic_write_json

ROOT = os.environ.get("NETLAB_ISAAC_SCRIPT_ROOT", "/workspace/isaac/scripts")
SCENE_SCRIPT = os.environ.get("NETLAB_SNAAS_SCENE_SCRIPT", os.path.join(ROOT, "snaas_relay_scene.py"))
FIX_SCRIPT = os.environ.get("NETLAB_SNAAS_FIX_SCRIPT", os.path.join(ROOT, "netlab_fix_drone_usd.py"))
DELAY_FRAMES = max(1, int(os.environ.get("NETLAB_SNAAS_AUTOLOAD_DELAY_FRAMES", "90")))
RUN_FIX = os.environ.get("NETLAB_SNAAS_RUN_ASSET_FIX", "1").strip().lower() not in {"0", "false", "no", "off"}
HEARTBEAT_PATH = os.environ.get("SNAAS_ISAAC_HEARTBEAT", "/workspace/results/snaas_isaac_heartbeat.json")

_state = {"frames": 0, "done": False, "subscription": None}


def _write_boot_status(state: str, message: str, error: str = "") -> None:
    try:
        directory = os.path.dirname(HEARTBEAT_PATH) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {
            "timestamp": time.time(),
            "ready": state == "SCENE_READY",
            "scene_ready": state == "SCENE_READY",
            "state": state,
            "message": message,
            "error": error,
            "pid": os.getpid(),
        }
        atomic_write_json(Path(HEARTBEAT_PATH), payload)
    except Exception:
        pass


def _exec_file(path: str, label: str) -> None:
    if not os.path.exists(path):
        print(f"[NETLAB-SNAAS-AUTOLOAD][WARN] {label} script not found: {path}")
        return
    print(f"[NETLAB-SNAAS-AUTOLOAD] executing {label}: {path}")
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    code = compile(source, path, "exec")
    namespace = globals()
    namespace["__file__"] = path
    exec(code, namespace)


def _start_after_delay(event) -> None:  # noqa: ANN001
    if _state["done"]:
        return
    _state["frames"] += 1
    if _state["frames"] < DELAY_FRAMES:
        return
    _state["done"] = True
    try:
        if RUN_FIX:
            try:
                _exec_file(FIX_SCRIPT, "asset/defaultPrim fixer")
            except Exception:
                print("[NETLAB-SNAAS-AUTOLOAD][WARN] Asset fixer failed; continuing with scene fallback visuals.")
                traceback.print_exc()
        _exec_file(SCENE_SCRIPT, "SNaaS relay scene")
        _write_boot_status("SCENE_READY", "SNaaS scene is active and ready for Mission Control synchronization.")
        print("[NETLAB-SNAAS-AUTOLOAD] SNaaS scene is active. Mission Control can now drive missions without Script Editor reloads.")
    except Exception as exc:
        _write_boot_status("FAILED", "Could not start the SNaaS scene.", str(exc))
        print("[NETLAB-SNAAS-AUTOLOAD][ERROR] Could not start SNaaS scene.")
        traceback.print_exc()
    finally:
        _state["subscription"] = None


try:
    app = omni.kit.app.get_app()
    _state["subscription"] = app.get_update_event_stream().create_subscription_to_pop(
        _start_after_delay,
        name="NETLAB SNaaS Isaac autoload",
    )
    _write_boot_status("STARTING", f"Waiting {DELAY_FRAMES} update frames before loading the SNaaS scene.")
    print(f"[NETLAB-SNAAS-AUTOLOAD] armed; loading scene after {DELAY_FRAMES} update frames.")
except Exception as exc:
    _write_boot_status("FAILED", "Could not register the Isaac update callback.", str(exc))
    print("[NETLAB-SNAAS-AUTOLOAD][ERROR] Could not register update callback.")
    traceback.print_exc()
