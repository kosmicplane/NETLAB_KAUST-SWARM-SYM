"""Analytical antenna boresight suggestion based on active link geometry."""
from __future__ import annotations
import math

PLUGIN_MANIFEST = {
    "plugin_id": "antenna_orientation_optimizer",
    "name": "Antenna Orientation Optimizer",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Suggests yaw and pitch angles that point directional antennas at the active peer.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.2,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "retain_orientation",
    "parameters": {"maximum_pitch_deg": {"type": "number", "default": 80.0, "minimum": 0.0, "maximum": 90.0}},
}


def optimize_parameters(context):
    maximum_pitch = abs(float(context.get("parameters", {}).get("maximum_pitch_deg", 80.0)))
    suggestions = {}
    for link in context.get("links", []):
        src = link.get("src_position")
        dst = link.get("dst_position")
        if not isinstance(src, (list, tuple)) or not isinstance(dst, (list, tuple)) or len(src) != 3 or len(dst) != 3:
            continue
        dx, dy, dz = (float(dst[i]) - float(src[i]) for i in range(3))
        horizontal = math.hypot(dx, dy)
        yaw = math.degrees(math.atan2(dy, dx))
        pitch = max(-maximum_pitch, min(maximum_pitch, math.degrees(math.atan2(dz, horizontal))))
        suggestions[str(link.get("src"))] = {"rotation_rpy_deg": [0.0, -pitch, yaw], "peer": str(link.get("dst"))}
    return {"suggestions": suggestions, "status": "CANDIDATE_ONLY"}


def on_link_update(context):
    return optimize_parameters(context)
