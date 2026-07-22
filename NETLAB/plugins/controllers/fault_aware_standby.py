"""Fault-aware standby selection based on geometric route-repair cost."""
from __future__ import annotations
import math

PLUGIN_MANIFEST = {
    "plugin_id": "fault_aware_standby",
    "name": "Fault-Aware Standby Selection",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Selects the standby with minimum distance to the failed relay and its neighboring route nodes.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "no_automatic_promotion",
    "parameters": {"battery_weight": {"type": "number", "default": 0.2, "minimum": 0.0, "maximum": 10.0}},
}


def select_standby(context):
    candidates = context.get("standbys", [])
    if not candidates:
        return None
    target = context.get("failed_position", [0.0, 0.0, 0.0])
    neighbors = context.get("neighbor_positions", [])
    battery_weight = float(context.get("parameters", {}).get("battery_weight", 0.2))
    def score(item):
        position = item.get("position", [0.0, 0.0, 0.0])
        geometric = math.dist(position, target) + sum(math.dist(position, neighbor) for neighbor in neighbors)
        battery = float(item.get("battery_soc_pct", 100.0))
        return geometric + battery_weight * (100.0 - battery)
    return min(candidates, key=score).get("id")


def on_failure(context):
    return {"action": "evaluate_standby_candidates", "failed_uav": context.get("failed_uav")}
