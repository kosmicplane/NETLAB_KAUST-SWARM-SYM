"""Researcher plugin SDK, discovery, and safe output validation."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence

from .errors import NetlabError, ValidationError

PLUGIN_API_VERSION = "1.0"
RECOGNIZED_HOOKS = {
    "initialize",
    "validate",
    "reset",
    "plan_positions",
    "plan_velocities",
    "plan_trajectories",
    "on_state_update",
    "on_topology_update",
    "on_link_update",
    "on_failure",
    "select_standby",
    "recompute_topology",
    "compute_metric",
    "generate_samples",
    "optimize_parameters",
    "plan_route",
    "shutdown",
}


@dataclass
class PluginManifest:
    plugin_id: str
    name: str
    version: str = "0.1.0"
    api_version: str = PLUGIN_API_VERSION
    author: str = ""
    description: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    execution_mode: str = "isolated_worker"
    timeout_s: float = 0.25
    required_fidelity: str = "F1_ANALYTICAL"
    safety_fallback: str = "hold_position"
    hooks: List[str] = field(default_factory=list)
    sha256: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


def _literal_dict(node: ast.AST) -> Dict[str, Any]:
    try:
        value = ast.literal_eval(node)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def inspect_plugin(path: Path) -> Dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
    except Exception as exc:
        return {"valid": False, "path": str(path), "error": str(exc), "hooks": []}
    hooks = sorted(node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in RECOGNIZED_HOOKS)
    metadata: Dict[str, Any] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"PLUGIN_MANIFEST", "NETLAB_PLUGIN"}:
                    metadata = _literal_dict(node.value)
                    break
    plugin_id = str(metadata.get("plugin_id", path.stem))
    manifest = PluginManifest(
        plugin_id=plugin_id,
        name=str(metadata.get("name", plugin_id.replace("_", " ").title())),
        version=str(metadata.get("version", "0.1.0")),
        api_version=str(metadata.get("api_version", PLUGIN_API_VERSION)),
        author=str(metadata.get("author", "")),
        description=str(metadata.get("description", (ast.get_docstring(tree) or "").strip().split("\n")[0])),
        parameters=dict(metadata.get("parameters", {})) if isinstance(metadata.get("parameters", {}), dict) else {},
        execution_mode=str(metadata.get("execution_mode", "isolated_worker")),
        timeout_s=float(metadata.get("timeout_s", 0.25)),
        required_fidelity=str(metadata.get("required_fidelity", "F1_ANALYTICAL")),
        safety_fallback=str(metadata.get("safety_fallback", "hold_position")),
        hooks=hooks,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    errors = []
    if not hooks:
        errors.append("No recognized plugin hooks were found.")
    if manifest.api_version != PLUGIN_API_VERSION:
        errors.append(f"API version {manifest.api_version} is incompatible with {PLUGIN_API_VERSION}.")
    if manifest.execution_mode not in {"trusted_in_process", "isolated_worker", "external_ros2"}:
        errors.append(f"Unsupported execution mode {manifest.execution_mode}.")
    return {"valid": not errors, "path": str(path), "manifest": manifest.as_dict(), "hooks": hooks, "errors": errors}


def discover(directory: Path) -> List[Dict[str, Any]]:
    directory.mkdir(parents=True, exist_ok=True)
    return [inspect_plugin(path) for path in sorted(directory.glob("*.py")) if not path.name.startswith("_")]


def validate_position_plan(
    plan: Any,
    *,
    known_uav_ids: Iterable[str],
    current_positions: Mapping[str, Sequence[float]],
    max_displacement_m: float,
    altitude_bounds_m: Sequence[float],
    minimum_separation_m: float,
) -> Dict[str, List[float]]:
    if not isinstance(plan, Mapping):
        raise ValidationError(code="PLUGIN_OUTPUT_TYPE", message="Position plan must be an object keyed by UAV ID.", component="plugin_runtime")
    known = set(known_uav_ids)
    normalized: Dict[str, List[float]] = {}
    for raw_id, raw_position in plan.items():
        uav_id = str(raw_id)
        if uav_id not in known:
            raise ValidationError(code="PLUGIN_UNKNOWN_UAV", message=f"Plugin returned unknown UAV {uav_id}.", component="plugin_runtime")
        if not isinstance(raw_position, Sequence) or isinstance(raw_position, (str, bytes)) or len(raw_position) != 3:
            raise ValidationError(code="PLUGIN_POSITION_SHAPE", message=f"Position for {uav_id} must contain three values.", component="plugin_runtime")
        position = [float(v) for v in raw_position]
        if not all(math.isfinite(v) for v in position):
            raise ValidationError(code="PLUGIN_NON_FINITE", message=f"Position for {uav_id} contains a non-finite value.", component="plugin_runtime")
        if not float(altitude_bounds_m[0]) <= position[2] <= float(altitude_bounds_m[1]):
            raise ValidationError(code="PLUGIN_ALTITUDE", message=f"Position for {uav_id} violates altitude bounds.", component="plugin_runtime")
        current = current_positions.get(uav_id)
        if current is not None and math.dist(position, [float(v) for v in current]) > max_displacement_m:
            raise ValidationError(code="PLUGIN_DISPLACEMENT", message=f"Position for {uav_id} exceeds the per-update displacement limit.", component="plugin_runtime")
        normalized[uav_id] = position
    items = list(normalized.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if math.dist(items[i][1], items[j][1]) < minimum_separation_m:
                raise ValidationError(
                    code="PLUGIN_SEPARATION",
                    message=f"Plugin plan violates minimum separation between {items[i][0]} and {items[j][0]}.",
                    component="plugin_runtime",
                )
    return normalized


def invoke_isolated(path: Path, hook: str, context: Mapping[str, Any], *, timeout_s: float = 0.25) -> Dict[str, Any]:
    """Invoke a plugin in a fresh Python subprocess with a hard timeout.

    A subprocess is used instead of ``multiprocessing`` so Mission Control does
    not fork after HTTP/SSE threads exist and so invocation also works from
    notebooks, stdin-driven tools, tests, and packaged CLI entry points.
    """

    if hook not in RECOGNIZED_HOOKS:
        raise ValueError(f"Unsupported hook {hook}")
    resolved = Path(path).expanduser().resolve()
    request = json.dumps(
        {"path": str(resolved), "hook": hook, "context": dict(context), "timeout_s": max(0.001, float(timeout_s))},
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    package_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(package_root) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "netlab.plugin_worker"],
            input=request,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(package_root),
            env=environment,
            # Process startup is bounded separately from plugin execution.
            # The worker enforces ``timeout_s`` with a POSIX timer around module
            # loading and hook execution, while the parent allows a small,
            # configurable interpreter-startup grace period.
            timeout=max(0.05, float(timeout_s)) + max(0.1, float(os.environ.get("NETLAB_PLUGIN_STARTUP_GRACE_S", "2.0"))),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "PLUGIN_TIMEOUT", "duration_s": time.monotonic() - started}
    duration = time.monotonic() - started
    try:
        response = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "PLUGIN_PROTOCOL_ERROR",
            "duration_s": duration,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    if not isinstance(response, dict):
        response = {"ok": False, "error": "PLUGIN_PROTOCOL_ERROR"}
    response["duration_s"] = duration
    response["returncode"] = completed.returncode
    if completed.stderr:
        response["stderr"] = completed.stderr[-2000:]
    return response


def template() -> str:
    return '''"""NETLAB controller plugin example."""
PLUGIN_MANIFEST = {
    "plugin_id": "example_controller",
    "name": "Example Controller",
    "version": "0.1.0",
    "api_version": "1.0",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "hold_position",
    "parameters": {"spacing_m": {"type": "number", "default": 30.0, "minimum": 5.0}},
}


def initialize(context):
    return {"ok": True}


def plan_positions(context):
    """Return {uav_id: [x, y, z]} for UAVs that should move this update."""
    return {}


def on_failure(context):
    return {"action": "recompute_topology"}


def select_standby(context):
    standbys = context.get("standby_uav_ids", [])
    return standbys[0] if standbys else None


def shutdown(context):
    return {"ok": True}
'''
