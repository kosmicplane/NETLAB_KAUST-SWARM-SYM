"""Deterministic rectangular coverage-grid controller."""
from __future__ import annotations
import math

PLUGIN_MANIFEST = {
    "plugin_id": "coverage_grid",
    "name": "Coverage Grid",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Assigns UAVs to a deterministic grid inside the configured service region.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "hold_position",
    "parameters": {"altitude_m": {"type": "number", "default": 35.0}, "margin_m": {"type": "number", "default": 8.0}},
}


def plan_positions(context):
    uavs = [u for u in context.get("uavs", []) if u.get("active", True)]
    region = context.get("service_region", {})
    parameters = context.get("parameters", {})
    center = region.get("center", [0.0, 0.0, 0.0])
    length = max(1.0, float(region.get("length_m", 100.0)) - 2 * float(parameters.get("margin_m", 8.0)))
    width = max(1.0, float(region.get("width_m", 100.0)) - 2 * float(parameters.get("margin_m", 8.0)))
    columns = max(1, math.ceil(math.sqrt(len(uavs) * length / max(width, 1e-9))))
    rows = max(1, math.ceil(len(uavs) / columns))
    altitude = float(parameters.get("altitude_m", 35.0))
    plan = {}
    for i, uav in enumerate(sorted(uavs, key=lambda item: str(item.get("id")))):
        row, col = divmod(i, columns)
        x = float(center[0]) - length / 2 + (col + 0.5) * length / columns
        y = float(center[1]) - width / 2 + (row + 0.5) * width / rows
        plan[str(uav["id"])] = [x, y, altitude]
    return plan
