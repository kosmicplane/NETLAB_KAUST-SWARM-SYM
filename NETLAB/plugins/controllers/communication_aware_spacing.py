"""Position relay UAVs along a route while preserving a configurable link margin."""
from __future__ import annotations

import math

PLUGIN_MANIFEST = {
    "plugin_id": "communication_aware_spacing",
    "name": "Communication-Aware Relay Spacing",
    "version": "1.0.0",
    "api_version": "1.0",
    "author": "NETLAB",
    "description": "Places active relays on a source-to-sink segment with spacing bounded by the operational radio range.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "hold_position",
    "parameters": {
        "target_range_utilization": {"type": "number", "default": 0.75, "minimum": 0.2, "maximum": 0.95},
        "altitude_m": {"type": "number", "default": 30.0, "minimum": 5.0, "maximum": 500.0},
    },
}


def validate(configuration):
    utilization = float(configuration.get("parameters", {}).get("target_range_utilization", 0.75))
    return {"ok": 0.2 <= utilization <= 0.95, "message": "target_range_utilization must be within [0.2, 0.95]"}


def plan_positions(context):
    # ``uavs`` is the v1 SDK collection. ``uav_states`` is accepted as a
    # compatibility input for existing researchers that used the pre-SDK
    # mapping contract.
    raw_uavs = context.get("uavs", [])
    if not raw_uavs and isinstance(context.get("uav_states"), dict):
        raw_uavs = [
            {
                "id": str(uav_id),
                "index": order,
                "position": state.get("position", [0.0, 0.0, 30.0]),
                "active": state.get("active", True),
                "role": state.get("role", "relay"),
            }
            for order, (uav_id, state) in enumerate(sorted(context["uav_states"].items()), start=1)
        ]
    uavs = [u for u in raw_uavs if u.get("active", True) and u.get("role") != "standby"]
    if not uavs:
        return {}
    station = context.get("station", {}).get("position", [0.0, 0.0, 0.0])
    service = context.get("service_region", {})
    parameters = context.get("parameters", {})
    radio = context.get("communication", {})
    utilization = float(parameters.get("target_range_utilization", 0.75))
    range_m = float(radio.get("operational_range_m", 90.0))
    # The historical controller exposed an absolute target spacing. Preserve
    # it as an explicit compatibility alias while keeping utilization as the
    # canonical v1 parameter.
    if "target_spacing_m" in parameters:
        max_step = max(1.0, min(range_m * 0.95, float(parameters["target_spacing_m"])))
    else:
        max_step = max(1.0, range_m * utilization)
    target = [
        float(station[0]) + float(service.get("length_m", max_step * len(uavs))),
        float(station[1]),
        float(parameters.get("altitude_m", 30.0)),
    ]
    dx, dy = target[0] - float(station[0]), target[1] - float(station[1])
    length = max(1e-9, math.hypot(dx, dy))
    required = max(1, math.ceil(length / max_step))
    denominator = max(required, len(uavs))
    plan = {}
    for order, uav in enumerate(sorted(uavs, key=lambda item: int(item.get("index", 0))), start=1):
        alpha = min(1.0, order / denominator)
        plan[str(uav["id"])] = [
            float(station[0]) + dx * alpha,
            float(station[1]) + dy * alpha,
            target[2],
        ]
    return plan


def on_failure(context):
    return {"action": "recompute_topology", "failed_uav": context.get("failed_uav")}


def select_standby(context):
    failed_position = context.get("failed_position", [0.0, 0.0, 0.0])
    candidates = context.get("standbys", [])
    if not candidates:
        return None
    return min(candidates, key=lambda item: math.dist(item.get("position", [0, 0, 0]), failed_position)).get("id")
