"""Time-indexed circular-orbit trajectory generator."""
from __future__ import annotations
import math

PLUGIN_MANIFEST = {
    "plugin_id": "circular_orbit",
    "name": "Circular Orbit",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Generates phase-separated circular orbit positions around a configurable center.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "hold_position",
    "parameters": {
        "radius_m": {"type": "number", "default": 40.0, "minimum": 5.0},
        "angular_speed_rad_s": {"type": "number", "default": 0.05, "minimum": 0.001},
        "altitude_m": {"type": "number", "default": 35.0},
    },
}


def plan_positions(context):
    uavs = [u for u in context.get("uavs", []) if u.get("active", True)]
    if not uavs:
        return {}
    p = context.get("parameters", {})
    center = context.get("service_region", {}).get("center", [0.0, 0.0, 0.0])
    radius = float(p.get("radius_m", 40.0))
    omega = float(p.get("angular_speed_rad_s", 0.05))
    altitude = float(p.get("altitude_m", 35.0))
    t = float(context.get("simulation_time_s", 0.0))
    plan = {}
    for i, uav in enumerate(sorted(uavs, key=lambda item: str(item.get("id")))):
        angle = omega * t + 2 * math.pi * i / len(uavs)
        plan[str(uav["id"])] = [float(center[0]) + radius * math.cos(angle), float(center[1]) + radius * math.sin(angle), altitude]
    return plan
