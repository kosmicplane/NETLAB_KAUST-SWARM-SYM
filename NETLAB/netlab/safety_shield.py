"""Safety and communication-feasibility shield for researcher actions.

The shield is deliberately deterministic. It validates and, where configured,
projects advisory algorithm outputs before they enter the authoritative ROS 2,
Sionna, and Isaac synchronization pipeline.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence

from .algorithm_contracts import AlgorithmAction, AlgorithmContractError, normalize_vec3_map
from .link import LinkRequest, compute_analytical_link, evaluate_feasibility
from .topology import branches_to_edges, normalize_manual_edges


@dataclass
class ShieldIssue:
    code: str
    severity: str
    message: str
    entity: str = ""
    measured: Any = None
    limit: Any = None
    correction: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ShieldDecision:
    accepted: bool
    action: Dict[str, Any]
    issues: list[ShieldIssue] = field(default_factory=list)
    projected: bool = False
    fallback_applied: bool = False
    fallback: str = ""
    link_preview: list[Dict[str, Any]] = field(default_factory=list)
    computation_s: float = 0.0
    source_revision_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "action": self.action,
            "issues": [issue.to_dict() for issue in self.issues],
            "projected": self.projected,
            "fallback_applied": self.fallback_applied,
            "fallback": self.fallback,
            "link_preview": self.link_preview,
            "computation_s": self.computation_s,
            "source_revision_id": self.source_revision_id,
        }


def _uav_map(snapshot: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    value = snapshot.get("uavs", [])
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items() if isinstance(item, Mapping)}
    return {str(item.get("id")): item for item in value if isinstance(item, Mapping) and item.get("id")}


def _enu(vector: Sequence[float], frame: str) -> list[float]:
    x, y, z = (float(vector[0]), float(vector[1]), float(vector[2]))
    if frame == "ENU" or frame == "ISAAC_STAGE":
        return [x, y, z]
    if frame == "NED":
        return [y, x, -z]
    raise AlgorithmContractError(f"The safety shield cannot project frame {frame!r} into ENU without a configured transform.")


def _service_bounds(config: Mapping[str, Any]) -> tuple[float, float, float, float, float, float]:
    region = config.get("service_region", {}) if isinstance(config.get("service_region"), Mapping) else {}
    center = region.get("center", [0.0, 0.0, 0.0])
    cx, cy = float(center[0]), float(center[1])
    length = max(1.0, float(region.get("length_m", 1000.0)))
    width = max(1.0, float(region.get("width_m", 1000.0)))
    min_alt = float(region.get("min_altitude_m", -1e6))
    max_alt = float(region.get("max_altitude_m", 1e6))
    return cx - length / 2.0, cx + length / 2.0, cy - width / 2.0, cy + width / 2.0, min_alt, max_alt


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _current_position(item: Mapping[str, Any]) -> list[float]:
    for key in ("measured_position", "simulated_position", "position", "commanded_position", "desired_position"):
        raw = item.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) >= 3:
            return [float(raw[0]), float(raw[1]), float(raw[2])]
    return [0.0, 0.0, 0.0]


def _project_step(current: Sequence[float], target: Sequence[float], max_distance: float) -> list[float]:
    delta = [float(target[i]) - float(current[i]) for i in range(3)]
    distance = math.sqrt(sum(component * component for component in delta))
    if distance <= max_distance or distance <= 1e-12:
        return [float(v) for v in target]
    scale = max_distance / distance
    return [float(current[i]) + delta[i] * scale for i in range(3)]


def _fallback_positions(uavs: Mapping[str, Mapping[str, Any]], fallback: str) -> Dict[str, list[float]]:
    # All implemented fallbacks are conservative at this layer. A future
    # autopilot adapter may translate safe_land/return_home into actions.
    return {uav_id: _current_position(item) for uav_id, item in uavs.items() if item.get("active", True) and not item.get("failed", False)}


def _antenna_gain(config: Mapping[str, Any], entity_id: str) -> tuple[float, float]:
    antennas = config.get("antennas", {}) if isinstance(config.get("antennas"), Mapping) else {}
    assignments = antennas.get("assignments", {}) if isinstance(antennas.get("assignments"), Mapping) else {}
    definitions = {
        str(item.get("id")): item
        for item in antennas.get("definitions", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    definition = definitions.get(str(assignments.get(entity_id, "")), {})
    return float(definition.get("gain_dbi", 0.0)), float(definition.get("cable_loss_db", 0.0))


def _topology_edges(config: Mapping[str, Any]) -> list[tuple[str, str]]:
    topology = config.get("topology", {}) if isinstance(config.get("topology"), Mapping) else {}
    if str(topology.get("mode", "chain")) == "manual" and topology.get("manual_edges"):
        return normalize_manual_edges(topology.get("manual_edges"))
    return branches_to_edges(topology.get("branches", []), str(topology.get("source", "station")))


def _connectivity_preview(
    positions: Mapping[str, Sequence[float]],
    config: Mapping[str, Any],
    uavs: Mapping[str, Mapping[str, Any]],
) -> tuple[list[Dict[str, Any]], bool]:
    communication = config.get("communication", {}) if isinstance(config.get("communication"), Mapping) else {}
    station = config.get("station", {}) if isinstance(config.get("station"), Mapping) else {}
    station_id = str(station.get("id", "station"))
    station_position = station.get("position", [0.0, 0.0, 0.0])
    entity_positions: Dict[str, Sequence[float]] = {station_id: station_position, **positions}
    results: list[Dict[str, Any]] = []
    all_feasible = True
    for src, dst in _topology_edges(config):
        if src not in entity_positions or dst not in entity_positions:
            results.append({"src": src, "dst": dst, "feasible": False, "reason": "MISSING_ENDPOINT"})
            all_feasible = False
            continue
        src_item = station if src == station_id else uavs.get(src, {})
        dst_item = station if dst == station_id else uavs.get(dst, {})
        tx_gain, tx_cable = _antenna_gain(config, src)
        rx_gain, rx_cable = _antenna_gain(config, dst)
        request = LinkRequest(
            src=src,
            dst=dst,
            tx_position=entity_positions[src],
            rx_position=entity_positions[dst],
            frequency_hz=float(communication.get("carrier_frequency_hz", 3.5e9)),
            bandwidth_hz=float(communication.get("bandwidth_hz", 20e6)),
            tx_power_dbm=float(communication.get("tx_power_dbm", 23.0)),
            receiver_noise_figure_db=float(communication.get("receiver_noise_figure_db", 7.0)),
            implementation_loss_db=float(communication.get("implementation_loss_db", 2.0)),
            tx_gain_dbi=tx_gain,
            rx_gain_dbi=rx_gain,
            tx_cable_loss_db=tx_cable,
            rx_cable_loss_db=rx_cable,
            path_loss_exponent=float(communication.get("path_loss_exponent", 2.0)),
            shadowing_sigma_db=float(communication.get("shadowing_sigma_db", 0.0)),
            interference_margin_db=float(communication.get("interference_margin_db", 0.0)),
            model=str(communication.get("fallback_model", "free_space")),
            spectral_efficiency_factor=float(communication.get("spectral_efficiency_factor", 0.75)),
            seed=int(config.get("experiment", {}).get("seed", 0)),
        )
        metrics = compute_analytical_link(request)
        decision = evaluate_feasibility(
            metrics,
            source_active=bool(src_item.get("active", True)),
            destination_active=bool(dst_item.get("active", True)),
            source_failed=bool(src_item.get("failed", False)),
            destination_failed=bool(dst_item.get("failed", False)),
            operational_range_m=float(communication.get("operational_range_m", 90.0)),
            hard_outage_distance_m=float(communication.get("hard_outage_distance_m", 220.0)),
            min_snr_db=float(communication.get("min_snr_db", 3.0)),
            min_sinr_db=float(communication.get("min_sinr_db", communication.get("min_snr_db", 3.0))),
            min_capacity_mbps=float(communication.get("min_capacity_mbps", 1.0)),
            metric_ttl_s=float(communication.get("metric_ttl_s", 2.0)),
        )
        result = {
            "src": src,
            "dst": dst,
            "feasible": decision.feasible,
            "reason": decision.reason.value,
            "distance_m": metrics.distance_m,
            "snr_db": metrics.snr_db,
            "sinr_db": metrics.sinr_db,
            "capacity_mbps": metrics.capacity_mbps,
            "predicates": [asdict(predicate) for predicate in decision.predicates],
            "source": "SAFETY_SHIELD_ANALYTICAL_PREVIEW",
        }
        results.append(result)
        all_feasible = all_feasible and decision.feasible
    return results, all_feasible


def apply_safety_shield(
    action: AlgorithmAction,
    snapshot: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    project: bool = True,
    require_connectivity: bool = True,
) -> ShieldDecision:
    started = time.perf_counter()
    issues: list[ShieldIssue] = []
    action_errors = action.validate()
    if action_errors:
        return ShieldDecision(
            accepted=False,
            action={},
            issues=[ShieldIssue("ALGORITHM_ACTION_INVALID", "ERROR", message) for message in action_errors],
            fallback_applied=True,
            fallback=str(config.get("swarm", {}).get("controller", {}).get("safe_fallback", "hold_position")),
            computation_s=time.perf_counter() - started,
            source_revision_id=action.source_revision_id,
        )

    uavs = _uav_map(snapshot)
    known = set(uavs)
    payload = dict(action.payload)
    desired_raw = payload.get("desired_positions")
    if desired_raw is None:
        return ShieldDecision(
            accepted=True,
            action=action.to_dict(),
            issues=[],
            computation_s=time.perf_counter() - started,
            source_revision_id=action.source_revision_id,
        )

    try:
        desired = normalize_vec3_map(desired_raw, field_name="desired_positions")
    except AlgorithmContractError as exc:
        return ShieldDecision(
            accepted=False,
            action={},
            issues=[ShieldIssue("ALGORITHM_OUTPUT_REJECTED", "ERROR", str(exc))],
            fallback_applied=True,
            fallback=str(config.get("swarm", {}).get("controller", {}).get("safe_fallback", "hold_position")),
            computation_s=time.perf_counter() - started,
            source_revision_id=action.source_revision_id,
        )

    unknown = sorted(set(desired) - known)
    for entity_id in unknown:
        issues.append(ShieldIssue("UNKNOWN_ENTITY", "ERROR", "Algorithm targeted an unknown UAV.", entity=entity_id))
        desired.pop(entity_id, None)

    swarm = config.get("swarm", {}) if isinstance(config.get("swarm"), Mapping) else {}
    update_rate_hz = max(0.1, float(swarm.get("controller", {}).get("update_rate_hz", 10.0)))
    max_speed = max(0.01, float(swarm.get("max_horizontal_speed_mps", 12.0)))
    max_vertical = max(0.01, float(swarm.get("max_vertical_speed_mps", 4.0)))
    max_distance = max_speed / update_rate_hz
    min_separation = max(0.0, float(swarm.get("minimum_separation_m", 4.0)))
    min_x, max_x, min_y, max_y, min_alt, max_alt = _service_bounds(config)
    geofence_enabled = bool(config.get("service_region", {}).get("geofence_enabled", False))
    projected = False
    normalized: Dict[str, list[float]] = {}

    for uav_id, target in desired.items():
        item = uavs[uav_id]
        if not item.get("active", True) or item.get("failed", False):
            issues.append(ShieldIssue("INACTIVE_OR_FAILED_ENTITY", "ERROR", "Algorithm targeted an inactive or failed UAV.", entity=uav_id))
            continue
        current = _current_position(item)
        try:
            target_enu = _enu(target, action.coordinate_frame)
        except AlgorithmContractError as exc:
            issues.append(ShieldIssue("COORDINATE_FRAME", "ERROR", str(exc), entity=uav_id))
            continue
        corrected = list(target_enu)
        if geofence_enabled:
            clipped = [
                _clamp(corrected[0], min_x, max_x),
                _clamp(corrected[1], min_y, max_y),
                _clamp(corrected[2], min_alt, max_alt),
            ]
            if clipped != corrected:
                issues.append(ShieldIssue("GEOFENCE_PROJECTED", "WARNING", "Target was projected into the configured service region.", entity=uav_id, measured=corrected, limit=[min_x, max_x, min_y, max_y, min_alt, max_alt], correction=clipped))
                corrected = clipped
                projected = True
        else:
            clipped_alt = _clamp(corrected[2], min_alt, max_alt)
            if clipped_alt != corrected[2]:
                issues.append(ShieldIssue("ALTITUDE_PROJECTED", "WARNING", "Target altitude was projected into bounds.", entity=uav_id, measured=corrected[2], limit=[min_alt, max_alt], correction=clipped_alt))
                corrected[2] = clipped_alt
                projected = True

        stepped = _project_step(current, corrected, max_distance)
        vertical_delta = stepped[2] - current[2]
        max_vertical_step = max_vertical / update_rate_hz
        if abs(vertical_delta) > max_vertical_step:
            stepped[2] = current[2] + math.copysign(max_vertical_step, vertical_delta)
        if math.dist(stepped, corrected) > 1e-9:
            issues.append(ShieldIssue("MOTION_PROJECTED", "WARNING", "Target was projected to the per-update motion envelope.", entity=uav_id, measured=corrected, limit=max_distance, correction=stepped))
            projected = True
        normalized[uav_id] = stepped

    # Include current positions for UAVs not commanded so separation and links
    # are evaluated against the complete active swarm.
    complete_positions = {
        uav_id: normalized.get(uav_id, _current_position(item))
        for uav_id, item in uavs.items()
        if item.get("active", True) and not item.get("failed", False)
    }
    ids = sorted(complete_positions)
    separation_violation = False
    for index, first in enumerate(ids):
        for second in ids[index + 1 :]:
            distance = math.dist(complete_positions[first], complete_positions[second])
            if distance + 1e-9 < min_separation:
                separation_violation = True
                issues.append(ShieldIssue("MINIMUM_SEPARATION", "ERROR", "Proposed positions violate minimum separation.", entity=f"{first},{second}", measured=distance, limit=min_separation))

    reserve = float(swarm.get("energy", {}).get("reserve_soc_pct", 20.0))
    for uav_id in normalized:
        soc = float(uavs[uav_id].get("battery_soc_pct", 100.0))
        if soc <= reserve:
            issues.append(ShieldIssue("BATTERY_RESERVE", "ERROR", "UAV battery is at or below reserve state.", entity=uav_id, measured=soc, limit=reserve))

    link_preview, connectivity_ok = _connectivity_preview(complete_positions, config, uavs)
    if require_connectivity and not connectivity_ok:
        failed_links = [f"{item['src']}->{item['dst']}:{item['reason']}" for item in link_preview if not item.get("feasible")]
        issues.append(ShieldIssue("COMMUNICATION_FEASIBILITY", "ERROR", "Proposed state does not preserve every required active hop.", measured=failed_links, limit="all required hops feasible"))

    hard_errors = [issue for issue in issues if issue.severity == "ERROR"]
    fallback_name = str(swarm.get("controller", {}).get("safe_fallback", "hold_position"))
    if hard_errors:
        fallback_positions = _fallback_positions(uavs, fallback_name)
        fallback_action = action.to_dict()
        fallback_action["payload"] = {"desired_positions": fallback_positions}
        fallback_action["fallback"] = True
        fallback_action["termination_reason"] = "safety_shield_rejection"
        fallback_action.setdefault("explanation", {})["shield_issues"] = [issue.to_dict() for issue in issues]
        return ShieldDecision(
            accepted=False,
            action=fallback_action,
            issues=issues,
            projected=projected,
            fallback_applied=True,
            fallback=fallback_name,
            link_preview=link_preview,
            computation_s=time.perf_counter() - started,
            source_revision_id=action.source_revision_id,
        )

    accepted_action = action.to_dict()
    accepted_action["coordinate_frame"] = "ENU"
    accepted_action["payload"] = {**payload, "desired_positions": normalized}
    accepted_action.setdefault("explanation", {})["safety_shield"] = {
        "projected": projected,
        "issues": [issue.to_dict() for issue in issues],
        "link_preview_source": "SAFETY_SHIELD_ANALYTICAL_PREVIEW",
    }
    return ShieldDecision(
        accepted=True,
        action=accepted_action,
        issues=issues,
        projected=projected,
        fallback_applied=False,
        fallback="",
        link_preview=link_preview,
        computation_s=time.perf_counter() - started,
        source_revision_id=action.source_revision_id,
    )
