"""Connectivity-preserving formation planner for relay branches.

The plugin spaces relays below a configurable fraction of the operational
communication range. It is an analytical planning aid, not a collision-free
flight controller; NETLAB validates displacement, geofence, altitude, and
minimum-separation constraints before applying the output.
"""
from __future__ import annotations

PLUGIN_MANIFEST = {
    "plugin_id": "connectivity_preserving_formation",
    "name": "Connectivity-Preserving Formation",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Places ordered branch relays with a configurable communication-range margin.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.35,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "hold_position",
    "parameters": {
        "range_fraction": {"type": "number", "default": 0.72, "minimum": 0.2, "maximum": 0.95},
        "altitude_m": {"type": "number", "default": 32.0, "minimum": 5.0},
        "lateral_branch_spacing_m": {"type": "number", "default": 24.0, "minimum": 4.0},
    },
}


def plan_positions(context):
    uavs = {str(item["id"]): item for item in context.get("uavs", []) if item.get("active", True)}
    topology = context.get("topology", {})
    branches = topology.get("branches", []) or []
    parameters = context.get("parameters", {})
    communication = context.get("communication", {})
    range_fraction = max(0.2, min(0.95, float(parameters.get("range_fraction", 0.72))))
    spacing = max(1.0, float(communication.get("operational_range_m", 90.0)) * range_fraction)
    altitude = float(parameters.get("altitude_m", 32.0))
    lateral = float(parameters.get("lateral_branch_spacing_m", 24.0))
    station = context.get("station", {}).get("position", [0.0, 0.0, 0.0])
    result = {}
    for branch_index, branch in enumerate(branches):
        y = (branch_index - (len(branches) - 1) / 2.0) * lateral
        for order, raw_index in enumerate(branch, start=1):
            uav_id = f"drone_{int(raw_index)}"
            if uav_id in uavs:
                result[uav_id] = [float(station[0]) + spacing * order, float(station[1]) + y, altitude]
    return result
