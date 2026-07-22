"""Deterministic, paper-traceable baseline algorithms for NETLAB.

These implementations are reference baselines, not claims of exact numerical
reproduction. Each plugin manifest documents the deviations and validity
limits. All outputs remain advisory until the NETLAB safety and feasibility
shield accepts them.
"""
from __future__ import annotations

import math
import random
import statistics
from typing import Any, Dict, Iterable, Mapping, Sequence

from .research_tools import rotary_wing_power_w


def active_uavs(snapshot: Mapping[str, Any]) -> list[Dict[str, Any]]:
    value = snapshot.get("uavs", [])
    items = list(value.values()) if isinstance(value, Mapping) else list(value)
    return [dict(item) for item in items if isinstance(item, Mapping) and item.get("active", True) and not item.get("failed", False)]


def position(item: Mapping[str, Any]) -> list[float]:
    for key in ("measured_position", "simulated_position", "position", "desired_position"):
        raw = item.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) and len(raw) >= 3:
            return [float(raw[0]), float(raw[1]), float(raw[2])]
    return [0.0, 0.0, 0.0]


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(float(value) ** 2 for value in vector))


def _unit(vector: Sequence[float]) -> list[float]:
    norm = _norm(vector)
    return [float(value) / norm for value in vector] if norm > 1e-12 else [0.0 for _ in vector]


def _add(*vectors: Sequence[float]) -> list[float]:
    return [sum(float(vector[index]) for vector in vectors) for index in range(3)]


def _scale(vector: Sequence[float], factor: float) -> list[float]:
    return [float(value) * factor for value in vector]


def _sub(first: Sequence[float], second: Sequence[float]) -> list[float]:
    return [float(first[index]) - float(second[index]) for index in range(3)]


def _centroid(points: Sequence[Sequence[float]], weights: Sequence[float] | None = None) -> list[float]:
    if not points:
        return [0.0, 0.0, 0.0]
    w = list(weights or [1.0] * len(points))
    total = sum(w) or 1.0
    return [sum(w[index] * float(points[index][axis]) for index in range(len(points))) / total for axis in range(3)]


def _users(snapshot: Mapping[str, Any]) -> list[Dict[str, Any]]:
    values = snapshot.get("ground_entities", [])
    return [dict(item) for item in values if isinstance(item, Mapping) and item.get("type") not in {"ground_station", "station"}]


def _rng(snapshot: Mapping[str, Any]) -> random.Random:
    return random.Random(int(snapshot.get("seed", 0)))


def common_initialize(_snapshot: Mapping[str, Any], _parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    return {"ok": True, "state": "INITIALIZED"}


def common_validate(_snapshot: Mapping[str, Any], parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    return {"ok": True, "parameters": dict(parameters or {})}


def common_reset(_snapshot: Mapping[str, Any], _parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    return {"ok": True, "state": "RESET"}


def common_on_state_update(snapshot: Mapping[str, Any], parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    return {"ok": True, "sequence": snapshot.get("sequence", 0), "parameters": dict(parameters or {})}


def common_on_failure(snapshot: Mapping[str, Any], parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    standbys = [item for item in active_uavs(snapshot) if item.get("role") == "standby"]
    return {"recovery_action": "promote_standby" if standbys else "recompute_topology", "standby_selection": standbys[0]["id"] if standbys else None}


def common_select_standby(snapshot: Mapping[str, Any], _parameters: Mapping[str, Any] | None = None) -> str | None:
    candidates = [item for item in active_uavs(snapshot) if item.get("role") == "standby"]
    candidates.sort(key=lambda item: (-float(item.get("battery_soc_pct", 100.0)), str(item.get("id"))))
    return str(candidates[0]["id"]) if candidates else None


def common_recompute_topology(snapshot: Mapping[str, Any], _parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    relays = [str(item["id"]) for item in active_uavs(snapshot) if item.get("role") != "standby"]
    return {"topology_candidate": {"mode": "chain", "source": snapshot.get("topology", {}).get("source", "station"), "branches": [relays]}}


def common_compute_metric(snapshot: Mapping[str, Any], _parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    return {"metrics": {"active_uav_count": len(uavs), "mean_battery_soc_pct": statistics.fmean([float(item.get("battery_soc_pct", 100.0)) for item in uavs]) if uavs else 0.0}}


def common_shutdown(_snapshot: Mapping[str, Any], _parameters: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    return {"ok": True, "state": "SHUTDOWN"}


def researcher_chain_spacing(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    spacing = float(parameters.get("spacing_m", 28.0))
    altitude = float(parameters.get("altitude_m", 30.0))
    direction = math.radians(float(parameters.get("direction_deg", 0.0)))
    station = snapshot.get("ground_entities", [{}])[0] if snapshot.get("ground_entities") else {}
    origin = position(station)
    relays = [item for item in active_uavs(snapshot) if item.get("role") != "standby"]
    desired = {
        str(item["id"]): [origin[0] + spacing * (index + 1) * math.cos(direction), origin[1] + spacing * (index + 1) * math.sin(direction), altitude]
        for index, item in enumerate(relays)
    }
    return {"desired_positions": desired, "coordinate_frame": "ENU", "objective_value": 0.0, "termination_reason": "closed_form_chain_spacing", "explanation": {"spacing_m": spacing}}


def connectivity_aware_formation(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    relays = [item for item in active_uavs(snapshot) if item.get("role") != "standby"]
    spacing = float(parameters.get("spacing_m", 28.0))
    altitude = float(parameters.get("altitude_m", 30.0))
    connectivity_weight = float(parameters.get("connectivity_weight", 2.0))
    formation_weight = float(parameters.get("formation_weight", 1.0))
    energy_weight = float(parameters.get("energy_weight", 0.2))
    station = snapshot.get("ground_entities", [{}])[0] if snapshot.get("ground_entities") else {}
    origin = position(station)
    link_margin: Dict[str, float] = {}
    for link in snapshot.get("links", []):
        if isinstance(link, Mapping):
            margin = min(float(link.get("range_margin_m", 1e9)), float(link.get("snr_margin_db", 1e9)), float(link.get("capacity_margin_mbps", 1e9)))
            link_margin[f"{link.get('src')}->{link.get('dst')}"] = margin
    desired: Dict[str, list[float]] = {}
    objective = 0.0
    for index, item in enumerate(relays):
        target = [origin[0] + spacing * (index + 1), origin[1], altitude]
        current = position(item)
        battery = float(item.get("battery_soc_pct", 100.0)) / 100.0
        # Low battery reduces the commanded displacement; the shield remains authoritative.
        responsiveness = max(0.2, 1.0 - energy_weight * (1.0 - battery))
        formation_delta = _sub(target, current)
        correction = _scale(formation_delta, min(1.0, formation_weight * responsiveness))
        # Compress the chain when the adjacent link margin is negative.
        predecessor = "station" if index == 0 else str(relays[index - 1]["id"])
        margin = link_margin.get(f"{predecessor}->{item['id']}", 0.0)
        if margin < 0:
            correction[0] -= connectivity_weight * min(spacing * 0.25, abs(margin) * 0.1)
        desired[str(item["id"])] = _add(current, correction)
        objective += formation_weight * _norm(formation_delta) - connectivity_weight * min(0.0, margin) + energy_weight * (1.0 - battery)
    return {"desired_positions": desired, "coordinate_frame": "ENU", "objective_value": objective, "constraint_residuals": {"minimum_link_margin": min(link_margin.values()) if link_margin else 0.0}, "termination_reason": "single_deterministic_control_step"}


def learn_as_you_fly(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    users = _users(snapshot)
    altitude = float(parameters.get("altitude_m", 45.0))
    learning_rate = max(0.0, min(1.0, float(parameters.get("learning_rate", 0.35))))
    if not users:
        return researcher_chain_spacing(snapshot, {"spacing_m": parameters.get("spacing_m", 30.0), "altitude_m": altitude})
    user_points = [position(item) for item in users]
    assignments: Dict[str, list[Sequence[float]]] = {str(item["id"]): [] for item in uavs}
    for point in user_points:
        owner = min(uavs, key=lambda item: math.dist(position(item), point))
        assignments[str(owner["id"])].append(point)
    desired: Dict[str, list[float]] = {}
    association: Dict[str, str] = {}
    for item in uavs:
        owned = assignments[str(item["id"])]
        target = _centroid(owned) if owned else position(item)
        target[2] = altitude
        current = position(item)
        desired[str(item["id"])] = _add(current, _scale(_sub(target, current), learning_rate))
    for user in users:
        association[str(user.get("id"))] = min(uavs, key=lambda item: math.dist(desired[str(item["id"])], position(user)))["id"]
    return {"desired_positions": desired, "user_association": association, "coordinate_frame": "ENU", "objective_value": sum(math.dist(desired[str(item["id"])], position(item)) for item in uavs), "termination_reason": "distributed_centroid_update"}


def joint_trajectory_communication(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    users = _users(snapshot)
    step = max(0.0, min(1.0, float(parameters.get("step_size", 0.25))))
    altitude = float(parameters.get("altitude_m", 50.0))
    if not users:
        return connectivity_aware_formation(snapshot, parameters)
    throughput = {str(user.get("id")): float(user.get("throughput_mbps", user.get("demand_mbps", 1.0))) for user in users}
    target_user = min(users, key=lambda item: throughput[str(item.get("id"))])
    target = position(target_user)
    desired: Dict[str, list[float]] = {}
    power: Dict[str, float] = {}
    association: Dict[str, str] = {}
    for index, uav in enumerate(uavs):
        current = position(uav)
        offset = [(index - (len(uavs) - 1) / 2.0) * float(parameters.get("spacing_m", 20.0)), 0.0, altitude]
        goal = [target[0] + offset[0], target[1] + offset[1], altitude]
        desired[str(uav["id"])] = _add(current, _scale(_sub(goal, current), step))
        power[str(uav["id"])] = min(float(parameters.get("max_tx_power_dbm", 30.0)), float(parameters.get("base_tx_power_dbm", 23.0)) + max(0.0, float(parameters.get("fairness_gain_db", 2.0))))
    for user in users:
        association[str(user.get("id"))] = min(uavs, key=lambda item: math.dist(desired[str(item["id"])], position(user)))["id"]
    return {"desired_positions": desired, "user_association": association, "transmit_power_commands_dbm": power, "coordinate_frame": "ENU", "objective_value": min(throughput.values()) if throughput else 0.0, "termination_reason": "receding_horizon_fairness_step", "explanation": {"solver_status": "deterministic_reference_heuristic", "paper_method": "BCD/SCA-inspired decomposition"}}


def rotary_wing_energy(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    target_speed = max(0.0, float(parameters.get("target_speed_mps", 8.0)))
    altitude = float(parameters.get("altitude_m", 35.0))
    desired: Dict[str, list[float]] = {}
    energy: Dict[str, float] = {}
    for index, uav in enumerate(uavs):
        current = position(uav)
        direction = _unit([1.0, math.sin(index), 0.0])
        desired[str(uav["id"])] = [current[0] + direction[0] * target_speed * float(snapshot.get("step_s", 0.1)), current[1] + direction[1] * target_speed * float(snapshot.get("step_s", 0.1)), altitude]
        energy[str(uav["id"])] = rotary_wing_power_w(target_speed)
    return {"desired_positions": desired, "metrics": {"predicted_propulsion_power_w": energy, "mean_power_w": statistics.fmean(energy.values()) if energy else 0.0}, "coordinate_frame": "ENU", "objective_value": sum(energy.values()), "termination_reason": "minimum_reference_power_speed_step"}


def graph_connectivity(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    target_distance = float(parameters.get("target_link_distance_m", 45.0))
    gain = float(parameters.get("gain", 0.25))
    desired: Dict[str, list[float]] = {}
    edges = snapshot.get("topology", {}).get("branches", [])
    neighbor_map: Dict[str, set[str]] = {str(item["id"]): set() for item in uavs}
    source = str(snapshot.get("topology", {}).get("source", "station"))
    for branch in edges:
        previous = source
        for node in branch:
            node_id = str(node) if str(node).startswith("drone_") else f"drone_{node}"
            if previous in neighbor_map:
                neighbor_map[previous].add(node_id)
            if node_id in neighbor_map and previous in neighbor_map:
                neighbor_map[node_id].add(previous)
            previous = node_id
    positions = {str(item["id"]): position(item) for item in uavs}
    for uav_id, current in positions.items():
        force = [0.0, 0.0, 0.0]
        for neighbor in neighbor_map.get(uav_id, set()):
            if neighbor not in positions:
                continue
            delta = _sub(positions[neighbor], current)
            distance = _norm(delta)
            force = _add(force, _scale(_unit(delta), gain * (distance - target_distance)))
        desired[uav_id] = _add(current, force)
    return {"desired_positions": desired, "coordinate_frame": "ENU", "objective_value": -sum(_norm(_sub(desired[uav_id], positions[uav_id])) for uav_id in positions), "termination_reason": "weighted_laplacian_gradient_step", "explanation": {"connectivity_surrogate": "distance-weighted Laplacian potential"}}


def voronoi_coverage(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    demand = _users(snapshot)
    if not demand:
        rng = _rng(snapshot)
        region = snapshot.get("constraints", {}).get("service_region", {})
        center = region.get("center", [0, 0, 0])
        length = float(region.get("length_m", 200.0)); width = float(region.get("width_m", 100.0))
        demand = [{"id": f"sample_{i}", "position": [float(center[0]) + rng.uniform(-length / 2, length / 2), float(center[1]) + rng.uniform(-width / 2, width / 2), 0.0], "weight": 1.0} for i in range(int(parameters.get("sample_count", 64)))]
    cells: Dict[str, list[Dict[str, Any]]] = {str(item["id"]): [] for item in uavs}
    for point in demand:
        owner = min(uavs, key=lambda item: math.dist(position(item), position(point)))
        cells[str(owner["id"])].append(point)
    gain = max(0.0, min(1.0, float(parameters.get("lloyd_gain", 0.5))))
    altitude = float(parameters.get("altitude_m", 35.0))
    desired = {}
    cost = 0.0
    for uav in uavs:
        items = cells[str(uav["id"])]
        points = [position(item) for item in items]
        weights = [float(item.get("weight", 1.0)) for item in items]
        centroid = _centroid(points, weights) if points else position(uav)
        centroid[2] = altitude
        current = position(uav)
        desired[str(uav["id"])] = _add(current, _scale(_sub(centroid, current), gain))
        cost += sum(float(item.get("weight", 1.0)) * math.dist(desired[str(uav["id"])], position(item)) ** 2 for item in items)
    return {"desired_positions": desired, "coordinate_frame": "ENU", "objective_value": cost, "termination_reason": "weighted_lloyd_iteration"}


def distributed_flocking(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    positions = {str(item["id"]): position(item) for item in uavs}
    velocities = {str(item["id"]): [float(v) for v in item.get("velocity", [0, 0, 0])] for item in uavs}
    neighbor_radius = float(parameters.get("neighbor_radius_m", 80.0))
    separation = float(parameters.get("separation_m", 8.0))
    cohesion_gain = float(parameters.get("cohesion_gain", 0.1))
    consensus_gain = float(parameters.get("consensus_gain", 0.2))
    separation_gain = float(parameters.get("separation_gain", 1.0))
    dt = float(snapshot.get("step_s", 0.1))
    desired = {}
    for uav_id, current in positions.items():
        neighbors = [other for other in positions if other != uav_id and math.dist(current, positions[other]) <= neighbor_radius]
        cohesion = _sub(_centroid([positions[other] for other in neighbors]), current) if neighbors else [0, 0, 0]
        consensus = _sub(_centroid([velocities[other] for other in neighbors]), velocities[uav_id]) if neighbors else [0, 0, 0]
        repel = [0.0, 0.0, 0.0]
        for other in neighbors:
            delta = _sub(current, positions[other]); distance = _norm(delta)
            if 1e-9 < distance < separation:
                repel = _add(repel, _scale(_unit(delta), separation - distance))
        velocity = _add(velocities[uav_id], _scale(cohesion, cohesion_gain), _scale(consensus, consensus_gain), _scale(repel, separation_gain))
        desired[uav_id] = _add(current, _scale(velocity, dt))
    return {"desired_positions": desired, "coordinate_frame": "ENU", "objective_value": sum(_norm(_sub(desired[key], positions[key])) for key in desired), "termination_reason": "distributed_flocking_step"}


def cbf_filter(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    # This reference projects nominal targets away from pairwise safety boundaries.
    nominal = parameters.get("nominal_desired_positions", {})
    if not nominal:
        nominal = {str(item["id"]): position(item) for item in active_uavs(snapshot)}
    desired = {str(key): [float(v) for v in value] for key, value in nominal.items()}
    safety_distance = float(parameters.get("safety_distance_m", snapshot.get("constraints", {}).get("minimum_separation_m", 4.0)))
    gain = float(parameters.get("barrier_gain", 0.5))
    ids = sorted(desired)
    residuals = {}
    for index, first in enumerate(ids):
        for second in ids[index + 1 :]:
            delta = _sub(desired[first], desired[second]); distance = _norm(delta)
            residual = distance - safety_distance
            residuals[f"separation:{first}:{second}"] = residual
            if distance < safety_distance and distance > 1e-9:
                correction = _scale(_unit(delta), gain * (safety_distance - distance))
                desired[first] = _add(desired[first], correction)
                desired[second] = _add(desired[second], _scale(correction, -1.0))
    return {"desired_positions": desired, "coordinate_frame": "ENU", "constraint_residuals": residuals, "objective_value": sum(max(0.0, -value) ** 2 for value in residuals.values()), "termination_reason": "deterministic_cbf_projection"}


def data_driven_connectivity(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    length_scale = max(1.0, float(parameters.get("length_scale_m", 50.0)))
    threshold = float(parameters.get("minimum_snr_db", 3.0))
    measurements = [item for item in snapshot.get("links", []) if isinstance(item, Mapping) and item.get("snr_db") is not None]
    desired = {str(item["id"]): position(item) for item in uavs}
    uncertainty = {}
    for uav in uavs:
        uav_id = str(uav["id"]); current = position(uav)
        relevant = [item for item in measurements if item.get("src") == uav_id or item.get("dst") == uav_id]
        if not relevant:
            uncertainty[uav_id] = 1.0
            continue
        weights = [math.exp(-float(item.get("distance_m", 0.0)) ** 2 / (2 * length_scale ** 2)) for item in relevant]
        predicted = sum(weight * float(item.get("snr_db", 0.0)) for weight, item in zip(weights, relevant)) / (sum(weights) or 1.0)
        variance = 1.0 / (sum(weights) + 1e-6)
        uncertainty[uav_id] = variance
        if predicted < threshold:
            neighbor_ids = [str(item.get("src")) if item.get("dst") == uav_id else str(item.get("dst")) for item in relevant]
            neighbor_positions = [position(next(candidate for candidate in uavs if str(candidate["id"]) == neighbor)) for neighbor in neighbor_ids if any(str(candidate["id"]) == neighbor for candidate in uavs)]
            if neighbor_positions:
                desired[uav_id] = _add(current, _scale(_sub(_centroid(neighbor_positions), current), 0.25))
    return {"desired_positions": desired, "coordinate_frame": "ENU", "uncertainty": uncertainty, "objective_value": sum(uncertainty.values()), "termination_reason": "kernel_link_quality_update", "explanation": {"model": "RBF-weighted link-quality surrogate", "measurement_count": len(measurements)}}


def spectrum_sharing(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    incumbents = parameters.get("incumbents", [])
    protection_radius = float(parameters.get("protection_radius_m", 100.0))
    max_power = float(parameters.get("max_tx_power_dbm", 30.0))
    min_power = float(parameters.get("min_tx_power_dbm", 5.0))
    desired = {}; powers = {}; residuals = {}
    for uav in uavs:
        uav_id = str(uav["id"]); current = position(uav); correction = [0.0, 0.0, 0.0]
        nearest = float("inf")
        for incumbent in incumbents:
            p = position(incumbent); delta = _sub(current, p); distance = _norm(delta); nearest = min(nearest, distance)
            if 1e-9 < distance < protection_radius:
                correction = _add(correction, _scale(_unit(delta), (protection_radius - distance) * 0.25))
        desired[uav_id] = _add(current, correction)
        margin = nearest - protection_radius if math.isfinite(nearest) else protection_radius
        powers[uav_id] = max(min_power, min(max_power, min_power + max(0.0, margin) * 0.1))
        residuals[f"incumbent_margin:{uav_id}"] = margin
    return {"desired_positions": desired, "transmit_power_commands_dbm": powers, "coordinate_frame": "ENU", "constraint_residuals": residuals, "objective_value": -sum(powers.values()), "termination_reason": "interference_protection_projection"}


def collaborative_beamforming(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    uavs = active_uavs(snapshot)
    target = parameters.get("target_position", [0.0, 0.0, 0.0])
    frequency = float(parameters.get("frequency_hz", 3.5e9)); wavelength = 299_792_458.0 / frequency
    phases = {}; amplitudes = {}; steering = {}
    for uav in uavs:
        uav_id = str(uav["id"]); distance = math.dist(position(uav), target)
        phases[uav_id] = (-2 * math.pi * distance / wavelength) % (2 * math.pi)
        amplitudes[uav_id] = 1.0 / max(1.0, distance)
        direction = _sub(target, position(uav))
        azimuth = math.degrees(math.atan2(direction[1], direction[0])); elevation = math.degrees(math.atan2(direction[2], math.hypot(direction[0], direction[1])))
        steering[uav_id] = {"azimuth_deg": azimuth, "elevation_deg": elevation, "phase_rad": phases[uav_id], "amplitude": amplitudes[uav_id]}
    gain = (sum(amplitudes.values()) ** 2) / (sum(value * value for value in amplitudes.values()) or 1.0)
    return {"antenna_commands": steering, "metrics": {"coherent_array_gain_linear": gain, "element_count": len(uavs)}, "objective_value": -gain, "termination_reason": "geometric_phase_alignment", "explanation": {"fidelity_note": "abstract coherent phase model; requires phase synchronization to realize physically"}}


def aoi_scheduler(snapshot: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
    flows = list(snapshot.get("flows", []))
    now = float(snapshot.get("simulation_time_s", 0.0))
    policy = str(parameters.get("policy", "max_age_deadline"))
    scored = []
    for flow in flows:
        generated = float(flow.get("last_generation_time_s", flow.get("start_time_s", 0.0)))
        received = float(flow.get("last_received_generation_time_s", generated))
        aoi = max(0.0, now - received)
        deadline = max(1e-6, float(flow.get("max_delay_ms", 1000.0)) / 1000.0)
        priority = float(flow.get("priority", 1.0))
        score = aoi / deadline + priority if policy == "max_age_deadline" else aoi
        scored.append((score, str(flow.get("id")), aoi, deadline))
    scored.sort(reverse=True)
    schedule = [{"flow_id": flow_id, "rank": index + 1, "score": score, "age_of_information_s": aoi, "deadline_s": deadline} for index, (score, flow_id, aoi, deadline) in enumerate(scored)]
    return {"traffic_schedule": schedule, "metrics": {"mean_aoi_s": statistics.fmean([item[2] for item in scored]) if scored else 0.0, "peak_aoi_s": max([item[2] for item in scored], default=0.0)}, "objective_value": sum(item[2] for item in scored), "termination_reason": "priority_schedule_computed"}
