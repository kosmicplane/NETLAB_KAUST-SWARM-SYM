"""Bounded energy-aware repositioning heuristic for reference experiments."""
from __future__ import annotations
import math

PLUGIN_MANIFEST = {
    "plugin_id": "energy_aware_trajectory",
    "name": "Energy-Aware Repositioning",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Moves lower-state-of-charge UAVs toward a configured reserve point using bounded steps.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "hold_position",
    "parameters": {
        "reserve_soc_pct": {"type": "number", "default": 30.0, "minimum": 0.0, "maximum": 100.0},
        "step_m": {"type": "number", "default": 2.0, "minimum": 0.1, "maximum": 10.0},
        "reserve_x_m": {"type": "number", "default": 20.0},
        "reserve_y_m": {"type": "number", "default": -30.0},
        "reserve_altitude_m": {"type": "number", "default": 20.0},
    },
}


def plan_positions(context):
    parameters = context.get("parameters", {})
    threshold = float(parameters.get("reserve_soc_pct", 30.0))
    step = max(0.1, float(parameters.get("step_m", 2.0)))
    target = [float(parameters.get("reserve_x_m", 20.0)), float(parameters.get("reserve_y_m", -30.0)), float(parameters.get("reserve_altitude_m", 20.0))]
    result = {}
    for uav in context.get("uavs", []):
        if not uav.get("active", True) or uav.get("failed", False):
            continue
        soc = float(uav.get("battery_soc_pct", uav.get("battery_pct", 100.0)))
        if soc >= threshold:
            continue
        position = [float(value) for value in uav.get("position", [0.0, 0.0, 0.0])]
        delta = [target[index] - position[index] for index in range(3)]
        length = math.sqrt(sum(value * value for value in delta)) or 1.0
        scale = min(1.0, step / length)
        result[str(uav["id"])] = [position[index] + delta[index] * scale for index in range(3)]
    return result
