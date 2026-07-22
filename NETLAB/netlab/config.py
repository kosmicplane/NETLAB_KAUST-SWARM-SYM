"""Versioned experiment configuration, migration, and validation.

The configuration is the authoritative durable description of an experiment.
Runtime state, telemetry, and Isaac acknowledgements are deliberately stored in
separate files so a configuration can be replayed without stale operational data.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .errors import ValidationError
from .io import atomic_write_json
from .models import FidelityProfile, TopologyMode
from .version import SCHEMA_VERSION

SUPPORTED_COORDINATE_FRAMES = {"ENU", "NED", "ECEF", "WGS84", "ISAAC_STAGE"}
SUPPORTED_PROPAGATION_MODELS = {
    "free_space",
    "log_distance",
    "probabilistic_air_to_ground",
    "stochastic_shadowing",
    "sionna_analytical",
    "sionna_rt",
    "trace_replay",
    "plugin",
}
SUPPORTED_TRAFFIC_MODELS = {
    "constant_packet_rate",
    "constant_bit_rate",
    "poisson",
    "on_off",
    "bursty_on_off",
    "deadline_sensitive",
    "trace_replay",
    "plugin",
}


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _drone(index: int, relay_count: int, spacing_m: float = 28.0, altitude_m: float = 28.0) -> Dict[str, Any]:
    return {
        "id": f"drone_{index}",
        "index": index,
        "type": "quadrotor_reference",
        "role": "relay" if index <= relay_count else "standby",
        "active": True,
        "failed": False,
        "position": [round(index * spacing_m, 6), 0.0, altitude_m + float((index - 1) % 3)],
        "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "velocity": [0.0, 0.0, 0.0],
        "battery_soc_pct": 100.0,
        "antenna_id": "uav_omni_reference",
    }


def default_experiment() -> Dict[str, Any]:
    drone_count = 8
    relay_count = 6
    now = time.time()
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": {
            "id": "first_feasible_relay_chain",
            "name": "First Feasible Relay Chain",
            "description": "Reference SNaaS experiment with communication-gated packet forwarding.",
            "author": "",
            "tags": ["snaas", "relay-chain", "reference"],
            "seed": 20260715,
            "duration_s": 300.0,
            "replications": 1,
            "fidelity_profile": FidelityProfile.ANALYTICAL.value,
            "created_at": now,
            "updated_at": now,
        },
        "clock": {
            "mode": "REAL_TIME",
            "physics_step_s": 1.0 / 60.0,
            "control_step_s": 0.1,
            "link_update_period_s": 0.5,
            "telemetry_period_s": 0.25,
            "use_sim_time": False,
        },
        "world": {
            "template": "open_reference",
            "coordinate_frame": "ENU",
            "stage_units_m": 1.0,
            "origin": [0.0, 0.0, 0.0],
            "terrain": "flat",
            "assets": [],
            "environment": {
                "temperature_c": 25.0,
                "humidity_pct": 40.0,
                "rain_rate_mm_h": 0.0,
                "fog_visibility_m": 10000.0,
                "wind_speed_mps": 1.2,
                "wind_direction_deg": 35.0,
                "gust_speed_mps": 0.8,
                "turbulence_intensity": 0.15,
            },
            "electromagnetic_materials": [],
        },
        "service_region": {
            "shape": "rectangle",
            "center": [120.0, 0.0, 0.0],
            "length_m": 240.0,
            "width_m": 120.0,
            "min_altitude_m": 10.0,
            "max_altitude_m": 120.0,
            "geofence_enabled": True,
            "restricted_regions": [],
        },
        "station": {
            "id": "station",
            "type": "ground_station",
            "position": [0.0, 0.0, 1.5],
            "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
            "antenna_id": "ground_sector_reference",
            "backhaul_capacity_mbps": 1000.0,
            "active": True,
        },
        "swarm": {
            "drone_count": drone_count,
            "relay_count": relay_count,
            "standby_count": drone_count - relay_count,
            "visual_asset_scale": 0.2,
            "physical_collision_dimensions_m": [0.32, 0.32, 0.12],
            "reference_dimensions_m": [0.32, 0.32, 0.12],
            "mass_kg": 1.4,
            "payload_mass_kg": 0.2,
            "minimum_separation_m": 4.0,
            "max_horizontal_speed_mps": 12.0,
            "max_vertical_speed_mps": 4.0,
            "max_acceleration_mps2": 5.0,
            "max_deceleration_mps2": 6.0,
            "max_jerk_mps3": 8.0,
            "max_yaw_rate_deg_s": 90.0,
            "max_climb_rate_mps": 4.0,
            "max_descent_rate_mps": 3.0,
            "controller": {
                "type": "communication_aware_formation",
                "plugin_id": None,
                "update_rate_hz": 10.0,
                "command_timeout_s": 1.0,
                "collision_avoidance": True,
                "safe_fallback": "hold_position",
            },
            "mobility": {
                "model": "hold",
                "formation": "chain",
                "waypoint_smoothing": True,
                "wind_response": True,
                "parameters": {},
            },
            "energy": {
                "model": "simple_power_budget",
                "battery_capacity_wh": 180.0,
                "initial_soc_pct": 100.0,
                "reserve_soc_pct": 20.0,
                "hover_power_w": 180.0,
                "communication_power_w": 8.0,
                "computing_power_w": 15.0,
            },
            "drones": [_drone(i, relay_count) for i in range(1, drone_count + 1)],
        },
        "topology": {
            "mode": TopologyMode.CHAIN.value,
            "source": "station",
            "sinks": [f"drone_{relay_count}"],
            "branch_count": 1,
            "branches": [[i for i in range(1, relay_count + 1)]],
            "manual_edges": [],
            "routing_policy": "ordered_path",
            "forwarding_policy": "store_and_forward",
            "queue_model": "fifo",
            "recompute_on_failure": True,
            "redundancy_target": 1,
            "update_period_s": 0.5,
        },
        "communication": {
            "model": "sionna_analytical",
            "fidelity": FidelityProfile.ANALYTICAL.value,
            "carrier_frequency_hz": 3.5e9,
            "bandwidth_hz": 20e6,
            "tx_power_dbm": 23.0,
            "receiver_noise_figure_db": 7.0,
            "implementation_loss_db": 2.0,
            "operational_range_m": 90.0,
            "hard_outage_distance_m": 220.0,
            "min_snr_db": 3.0,
            "min_sinr_db": 3.0,
            "min_capacity_mbps": 1.0,
            "spectral_efficiency_factor": 0.75,
            "metric_ttl_s": 2.0,
            "shadowing_sigma_db": 0.0,
            "path_loss_exponent": 2.0,
            "rain_enabled": False,
            "foliage_enabled": False,
            "clutter_enabled": False,
            "interference_enabled": False,
            "interference_margin_db": 0.0,
            "allow_fallback": True,
            "fallback_model": "free_space",
        },
        "antennas": {
            "definitions": [
                {
                    "id": "ground_sector_reference",
                    "name": "Ground Sector Reference",
                    "model": "sector",
                    "provenance": "analytical_reference",
                    "center_frequency_hz": 3.5e9,
                    "bandwidth_hz": 20e6,
                    "gain_dbi": 8.0,
                    "efficiency": 0.8,
                    "polarization": "vertical",
                    "beamwidth_azimuth_deg": 110.0,
                    "beamwidth_elevation_deg": 60.0,
                    "front_to_back_ratio_db": 20.0,
                    "cable_loss_db": 1.0,
                    "position_offset_m": [0.0, 0.0, 0.0],
                    "rotation_rpy_deg": [0.0, 0.0, 0.0],
                },
                {
                    "id": "uav_omni_reference",
                    "name": "UAV Omni Reference",
                    "model": "omnidirectional",
                    "provenance": "analytical_reference",
                    "center_frequency_hz": 3.5e9,
                    "bandwidth_hz": 20e6,
                    "gain_dbi": 2.5,
                    "efficiency": 0.75,
                    "polarization": "vertical",
                    "beamwidth_azimuth_deg": 360.0,
                    "beamwidth_elevation_deg": 120.0,
                    "front_to_back_ratio_db": 0.0,
                    "cable_loss_db": 0.5,
                    "position_offset_m": [0.0, 0.0, 0.12],
                    "rotation_rpy_deg": [0.0, 0.0, 0.0],
                },
            ],
            "assignments": {
                "station": "ground_sector_reference",
                **{f"drone_{i}": "uav_omni_reference" for i in range(1, drone_count + 1)},
            },
        },
        "traffic": {
            "flows": [
                {
                    "id": "service_flow_1",
                    "source": "station",
                    "destination": f"drone_{relay_count}",
                    "branch_id": "branch_0",
                    "service_class": "user_data",
                    "generation_model": "constant_packet_rate",
                    "packet_size_bytes": 512,
                    "packet_rate_pps": 2.0,
                    "priority": 1,
                    "max_delay_ms": 150.0,
                    "min_throughput_mbps": 1.0,
                    "reliability_target": 0.99,
                    "queue_capacity_packets": 128,
                    "start_time_s": 0.0,
                    "stop_time_s": 300.0,
                }
            ],
            "scheduler": "round_robin",
            "queue_model": "fifo",
        },
        "failures": {
            "schedule": [],
            "recovery_policy": "communication_aware_standby",
            "failure_detection_s": 1.5,
            "recovery_timeout_s": 20.0,
            "retry_limit": 3,
            "operator_approval_required": False,
        },
        "visualization": {
            "custom_drone_usd": "/workspace/isaac/local_assets/drones/tu_drone.usd",
            "visual_asset_scale": 0.2,
            "show_service_region": True,
            "show_link_lines": True,
            "show_packet_markers": True,
            "show_coverage_preview": True,
            "coverage_opacity": 0.035,
            "status_marker_scale": 0.7,
            "packet_marker_scale": 0.9,
            "camera_preset": "overview",
        },
        "evidence": {
            "output_directory": "/workspace/results",
            "write_jsonl_events": True,
            "write_csv_metrics": True,
            "write_run_manifest": True,
            "record_rosbag": False,
            "capture_screenshots": False,
            "record_video": False,
            "retention_policy": "keep_completed_runs",
        },
        "runtime": {
            "sionna_url": "http://127.0.0.1:8090/link",
            "sionna_health_url": "http://127.0.0.1:8090/health",
            "command_timeout_s": 30.0,
            "startup_timeout_s": 600.0,
            "isaac_heartbeat_timeout_s": 15.0,
            "packet_heartbeat_timeout_s": 5.0,
            "retry_count": 3,
        },
        "compatibility": {
            "legacy_config_version": "v4.1",
            "legacy_fields_emitted": True,
            "generated_reference": True,
        },
    }


def _finite(value: Any) -> bool:
    try:
        v = float(value)
        return math.isfinite(v)
    except Exception:
        return False


def _vec3(value: Any, path: str, errors: List[Dict[str, Any]]) -> List[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 3:
        errors.append({"path": path, "code": "VECTOR_LENGTH", "message": "Expected a three-element numeric vector."})
        return [0.0, 0.0, 0.0]
    result: List[float] = []
    for i, item in enumerate(value):
        if not _finite(item):
            errors.append({"path": f"{path}[{i}]", "code": "NON_FINITE", "message": "Value must be finite."})
            result.append(0.0)
        else:
            result.append(float(item))
    return result


def migrate_legacy_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Migrate legacy flat/v4/v5 configuration into the NETLAB versioned structure.

    The function is intentionally non-destructive and emits legacy aliases later
    so existing ROS and Isaac adapters continue to work during migration.
    """
    if config.get("schema_version") == SCHEMA_VERSION and isinstance(config.get("experiment"), Mapping):
        return deep_merge(default_experiment(), config)
    # Runtime adapters consume a flat compatibility envelope. The authoritative
    # versioned document is retained under `v6`; `v5` remains a read-only migration
    # alias so existing installations can be upgraded without data loss.
    for version_key in ("v6", "v5"):
        if isinstance(config.get(version_key), Mapping):
            nested = config.get(version_key, {})
            if nested.get("schema_version") == SCHEMA_VERSION and isinstance(nested.get("experiment"), Mapping):
                return deep_merge(default_experiment(), nested)

    base = default_experiment()
    source = dict(config)
    exp = base["experiment"]
    exp["id"] = str(source.get("scenario_id", source.get("experiment_name", exp["id"]))).strip() or exp["id"]
    exp["name"] = str(source.get("experiment_name", exp["name"]))
    exp["seed"] = int(source.get("seed", exp["seed"]))
    exp["duration_s"] = float(source.get("duration_s", exp["duration_s"]))

    swarm = base["swarm"]
    total = max(1, int(source.get("drone_count", len(source.get("drones", [])) or swarm["drone_count"])))
    relay = max(1, min(total, int(source.get("relay_count", max(1, total - int(source.get("standby_count", 0)))))))
    standby = max(0, total - relay)
    swarm.update(
        {
            "drone_count": total,
            "relay_count": relay,
            "standby_count": standby,
            "visual_asset_scale": float(source.get("visual", {}).get("drone_scale", source.get("drone_scale", 0.2))),
        }
    )
    legacy_drones = source.get("drones", [])
    if isinstance(legacy_drones, list) and legacy_drones:
        drones = []
        for i in range(1, total + 1):
            item = legacy_drones[i - 1] if i - 1 < len(legacy_drones) and isinstance(legacy_drones[i - 1], Mapping) else {}
            d = _drone(i, relay)
            d.update(copy.deepcopy(dict(item)))
            d["id"] = str(d.get("id") or f"drone_{i}")
            d["index"] = i
            drones.append(d)
        swarm["drones"] = drones
    else:
        swarm["drones"] = [_drone(i, relay) for i in range(1, total + 1)]

    world = base["world"]
    legacy_worlds = source.get("worlds", [])
    if isinstance(legacy_worlds, list):
        world["assets"] = copy.deepcopy(legacy_worlds)
    environment = source.get("environment", {}) if isinstance(source.get("environment"), Mapping) else {}
    world["environment"].update(
        {
            "wind_speed_mps": float(source.get("wind_speed_mps", environment.get("wind_speed_mps", world["environment"]["wind_speed_mps"]))),
            "wind_direction_deg": float(source.get("wind_direction_deg", environment.get("wind_direction_deg", world["environment"]["wind_direction_deg"]))),
            "turbulence_intensity": float(source.get("turbulence_intensity", environment.get("turbulence_intensity", world["environment"]["turbulence_intensity"]))),
            "rain_rate_mm_h": float(environment.get("rain_rate_mm_h", source.get("rain_rate_mm_h", 0.0))),
        }
    )

    service = base["service_region"]
    service["length_m"] = float(source.get("coverage_radius_m", service["length_m"]))
    service["width_m"] = float(source.get("coverage_width_m", service["width_m"]))
    service["min_altitude_m"] = float(source.get("altitude_start_m", service["min_altitude_m"]))
    service["max_altitude_m"] = float(source.get("altitude_end_m", service["max_altitude_m"]))

    station = source.get("station") if isinstance(source.get("station"), Mapping) else {}
    base["station"].update(copy.deepcopy(dict(station)))

    topology_source = source.get("topology", {}) if isinstance(source.get("topology"), Mapping) else {}
    mode = str(topology_source.get("transmission_mode", source.get("transmission_mode", "chain"))).lower()
    if mode not in {m.value for m in TopologyMode}:
        mode = "parallel" if int(source.get("branch_count", 1)) > 1 else "chain"
    branches = topology_source.get("manual_branches", source.get("manual_branches", []))
    if not isinstance(branches, list) or not branches:
        if mode == "chain":
            branches = [[i for i in range(1, relay + 1)]]
        else:
            count = max(1, int(source.get("branch_count", 1)))
            branches = [[] for _ in range(count)]
            for offset, idx in enumerate(range(1, relay + 1)):
                branches[offset % count].append(idx)
    base["topology"].update(
        {
            "mode": mode,
            "branch_count": len(branches),
            "branches": copy.deepcopy(branches),
            "forwarding_policy": str(topology_source.get("forwarding_policy", source.get("forwarding_policy", "store_and_forward"))),
            "queue_model": str(topology_source.get("queue_model", source.get("queue_model", "fifo"))),
        }
    )

    radio = source.get("radio", {}) if isinstance(source.get("radio"), Mapping) else {}
    communication = base["communication"]
    communication.update(
        {
            "carrier_frequency_hz": float(radio.get("frequency_hz", source.get("frequency_hz", communication["carrier_frequency_hz"]))),
            "bandwidth_hz": float(radio.get("bandwidth_hz", source.get("bandwidth_hz", communication["bandwidth_hz"]))),
            "tx_power_dbm": float(radio.get("tx_power_dbm", source.get("tx_power_dbm", communication["tx_power_dbm"]))),
            "operational_range_m": float(source.get("max_single_hop_range_m", communication["operational_range_m"])),
            "hard_outage_distance_m": float(source.get("hard_outage_range_m", communication["hard_outage_distance_m"])),
            "min_snr_db": float(radio.get("min_snr_db", communication["min_snr_db"])),
            "min_capacity_mbps": float(radio.get("required_capacity_mbps", communication["min_capacity_mbps"])),
        }
    )
    noise_floor = radio.get("noise_floor_dbm")
    if noise_floor is not None:
        communication["legacy_noise_floor_dbm"] = float(noise_floor)

    legacy_antennas = source.get("antennas", [])
    if isinstance(legacy_antennas, list) and legacy_antennas:
        defs = []
        assignments: Dict[str, str] = {}
        for idx, item in enumerate(legacy_antennas, start=1):
            if not isinstance(item, Mapping):
                continue
            ant_id = str(item.get("id", f"antenna_{idx}"))
            defs.append(
                {
                    "id": ant_id,
                    "name": str(item.get("name", ant_id)),
                    "model": str(item.get("role", "custom_reference")),
                    "provenance": "legacy_config",
                    "center_frequency_hz": float(item.get("frequency_hz", communication["carrier_frequency_hz"])),
                    "bandwidth_hz": float(item.get("bandwidth_hz", communication["bandwidth_hz"])),
                    "gain_dbi": float(item.get("gain_dbi", 0.0)),
                    "polarization": str(item.get("polarization", "vertical")),
                    "beamwidth_azimuth_deg": float(item.get("beamwidth_deg", 360.0)),
                    "beamwidth_elevation_deg": float(item.get("beamwidth_deg", 120.0)),
                    "position_offset_m": list(item.get("position", [0.0, 0.0, 0.0])),
                    "rotation_rpy_deg": list(item.get("rotation_xyz", [0.0, 0.0, 0.0])),
                    "cable_loss_db": 0.0,
                }
            )
            attached = str(item.get("attached_to", "station" if idx == 1 else ""))
            if attached:
                assignments[attached] = ant_id
        if defs:
            base["antennas"] = {"definitions": defs, "assignments": assignments}

    visual = source.get("visual", {}) if isinstance(source.get("visual"), Mapping) else {}
    base["visualization"].update(
        {
            "custom_drone_usd": str(visual.get("custom_drone_usd", base["visualization"]["custom_drone_usd"])),
            "visual_asset_scale": float(visual.get("drone_scale", 0.2)),
            "show_service_region": bool(visual.get("show_coverage_area", True)),
            "show_coverage_preview": bool(visual.get("show_drone_coverage_rings", True)),
            "coverage_opacity": float(visual.get("drone_coverage_opacity", 0.035)),
        }
    )
    base["compatibility"]["migrated_from_flat_config"] = True
    base["experiment"]["updated_at"] = time.time()
    return base


def _range(errors: List[Dict[str, Any]], path: str, value: Any, lo: float, hi: float) -> float:
    if not _finite(value):
        errors.append({"path": path, "code": "NON_NUMERIC", "message": "Expected a finite number."})
        return lo
    number = float(value)
    if number < lo or number > hi:
        errors.append({"path": path, "code": "OUT_OF_RANGE", "message": f"Expected {lo} <= value <= {hi}.", "value": number})
    return number


def validate_experiment(config: Mapping[str, Any], *, strict: bool = True) -> Dict[str, Any]:
    cfg = migrate_legacy_config(config)
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    if cfg.get("schema_version") != SCHEMA_VERSION:
        errors.append({"path": "schema_version", "code": "SCHEMA_VERSION", "message": f"Expected {SCHEMA_VERSION}."})

    experiment = cfg.get("experiment", {})
    if not str(experiment.get("id", "")).strip():
        errors.append({"path": "experiment.id", "code": "REQUIRED", "message": "Experiment ID is required."})
    _range(errors, "experiment.duration_s", experiment.get("duration_s", 0), 0.1, 864000.0)
    seed = experiment.get("seed")
    try:
        int(seed)
    except Exception:
        errors.append({"path": "experiment.seed", "code": "INTEGER", "message": "Deterministic seed must be an integer."})

    world = cfg.get("world", {})
    frame = str(world.get("coordinate_frame", "ENU")).upper()
    if frame not in SUPPORTED_COORDINATE_FRAMES:
        errors.append({"path": "world.coordinate_frame", "code": "UNSUPPORTED_FRAME", "message": f"Supported frames: {sorted(SUPPORTED_COORDINATE_FRAMES)}."})
    _vec3(world.get("origin", []), "world.origin", errors)

    swarm = cfg.get("swarm", {})
    try:
        total = int(swarm.get("drone_count", 0))
        relay = int(swarm.get("relay_count", 0))
        standby = int(swarm.get("standby_count", 0))
    except Exception:
        total, relay, standby = 0, 0, 0
        errors.append({"path": "swarm", "code": "COUNT_TYPE", "message": "Drone counts must be integers."})
    if total < 1 or total > 512:
        errors.append({"path": "swarm.drone_count", "code": "OUT_OF_RANGE", "message": "Drone count must be between 1 and 512."})
    if relay < 1 or relay > total:
        errors.append({"path": "swarm.relay_count", "code": "COUNT_CONSISTENCY", "message": "Relay count must be between 1 and drone count."})
    if standby < 0 or relay + standby != total:
        errors.append({"path": "swarm.standby_count", "code": "COUNT_CONSISTENCY", "message": "Relay plus standby count must equal drone count."})
    scale = _range(errors, "swarm.visual_asset_scale", swarm.get("visual_asset_scale", 0.2), 0.01, 10.0)
    if abs(scale - 0.2) > 1e-9:
        warnings.append({"path": "swarm.visual_asset_scale", "code": "NON_REFERENCE_SCALE", "message": "The project reference visual scale is 0.2; physical dimensions remain independent."})
    minimum_sep = _range(errors, "swarm.minimum_separation_m", swarm.get("minimum_separation_m", 0), 0.1, 1000.0)

    drones = swarm.get("drones", [])
    if not isinstance(drones, list) or len(drones) != total:
        errors.append({"path": "swarm.drones", "code": "INVENTORY_SIZE", "message": f"Expected exactly {total} drone records."})
        drones = drones if isinstance(drones, list) else []
    ids: set[str] = set()
    positions: List[Tuple[str, List[float]]] = []
    for i, item in enumerate(drones):
        if not isinstance(item, Mapping):
            errors.append({"path": f"swarm.drones[{i}]", "code": "OBJECT", "message": "Drone entry must be an object."})
            continue
        drone_id = str(item.get("id", ""))
        if not drone_id:
            errors.append({"path": f"swarm.drones[{i}].id", "code": "REQUIRED", "message": "Drone ID is required."})
        elif drone_id in ids:
            errors.append({"path": f"swarm.drones[{i}].id", "code": "DUPLICATE", "message": f"Duplicate drone ID {drone_id}."})
        ids.add(drone_id)
        pos = _vec3(item.get("position", []), f"swarm.drones[{i}].position", errors)
        positions.append((drone_id, pos))
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            d = math.dist(positions[i][1], positions[j][1])
            if d < minimum_sep:
                warnings.append({"path": "swarm.drones", "code": "MINIMUM_SEPARATION", "message": f"{positions[i][0]} and {positions[j][0]} are {d:.3f} m apart, below {minimum_sep:.3f} m."})

    topology = cfg.get("topology", {})
    mode = str(topology.get("mode", "chain")).lower()
    if mode not in {m.value for m in TopologyMode}:
        errors.append({"path": "topology.mode", "code": "ENUM", "message": "Topology mode must be chain, parallel, forest, or manual."})
    branches = topology.get("branches", [])
    manual_edges = topology.get("manual_edges", [])
    if mode == "manual":
        if not isinstance(manual_edges, list) or not manual_edges:
            errors.append({"path": "topology.manual_edges", "code": "REQUIRED", "message": "Manual topology requires at least one directed edge."})
        else:
            known_entities = {"station", *ids}
            for edge_index, edge in enumerate(manual_edges):
                if not isinstance(edge, (list, tuple)) or len(edge) != 2:
                    errors.append({"path": f"topology.manual_edges[{edge_index}]", "code": "EDGE_SHAPE", "message": "Manual edges must be [source, destination] pairs."})
                    continue
                source, destination = map(str, edge)
                if source not in known_entities or destination not in known_entities:
                    errors.append({"path": f"topology.manual_edges[{edge_index}]", "code": "UNKNOWN_ENDPOINT", "message": f"Unknown manual-edge endpoint {source}->{destination}."})
                if source == destination:
                    errors.append({"path": f"topology.manual_edges[{edge_index}]", "code": "SELF_LOOP", "message": "Self-loops are not permitted in an operational relay graph."})
    elif not isinstance(branches, list) or not branches:
        errors.append({"path": "topology.branches", "code": "REQUIRED", "message": "At least one branch is required."})
    else:
        used: set[int] = set()
        for bi, branch in enumerate(branches):
            if not isinstance(branch, list) or not branch:
                errors.append({"path": f"topology.branches[{bi}]", "code": "EMPTY_BRANCH", "message": "A branch must contain at least one relay."})
                continue
            local: set[int] = set()
            for raw in branch:
                try:
                    idx = int(raw)
                except Exception:
                    errors.append({"path": f"topology.branches[{bi}]", "code": "INTEGER", "message": "Relay indices must be integers."})
                    continue
                if idx < 1 or idx > relay:
                    errors.append({"path": f"topology.branches[{bi}]", "code": "UNKNOWN_RELAY", "message": f"Relay {idx} is outside active relay inventory 1..{relay}."})
                if idx in local:
                    errors.append({"path": f"topology.branches[{bi}]", "code": "DUPLICATE_NODE", "message": f"Relay {idx} occurs twice in one branch."})
                local.add(idx)
                if mode == "parallel" and idx in used:
                    warnings.append({"path": f"topology.branches[{bi}]", "code": "SHARED_RELAY", "message": f"Relay {idx} is shared between parallel branches; failures may couple branch availability."})
                used.add(idx)

    comm = cfg.get("communication", {})
    model = str(comm.get("model", "free_space"))
    if model not in SUPPORTED_PROPAGATION_MODELS:
        errors.append({"path": "communication.model", "code": "UNSUPPORTED_MODEL", "message": f"Supported models: {sorted(SUPPORTED_PROPAGATION_MODELS)}."})
    frequency = _range(errors, "communication.carrier_frequency_hz", comm.get("carrier_frequency_hz", 0), 1e6, 3e11)
    _range(errors, "communication.bandwidth_hz", comm.get("bandwidth_hz", 0), 1.0, 1e10)
    operational = _range(errors, "communication.operational_range_m", comm.get("operational_range_m", 0), 0.1, 1e7)
    hard = _range(errors, "communication.hard_outage_distance_m", comm.get("hard_outage_distance_m", 0), 0.1, 1e8)
    if hard < operational:
        errors.append({"path": "communication.hard_outage_distance_m", "code": "THRESHOLD_ORDER", "message": "Hard-outage distance must be greater than or equal to operational range."})
    if model == "free_space" and str(world.get("template", "")).lower().startswith("urban"):
        warnings.append({"path": "communication.model", "code": "MODEL_VALIDITY", "message": "Free-space path loss is not a realistic urban propagation model; use it only as a baseline."})
    if model == "sionna_rt" and not world.get("assets"):
        errors.append({"path": "world.assets", "code": "RAY_TRACING_WORLD_REQUIRED", "message": "Sionna RT requires geometry and electromagnetic material mappings."})
    if frequency > 100e9:
        warnings.append({"path": "communication.carrier_frequency_hz", "code": "HIGH_FREQUENCY", "message": "Verify material and atmospheric models for frequencies above 100 GHz."})

    ant = cfg.get("antennas", {})
    defs = ant.get("definitions", []) if isinstance(ant, Mapping) else []
    assignments = ant.get("assignments", {}) if isinstance(ant, Mapping) else {}
    ant_ids: set[str] = set()
    if not isinstance(defs, list):
        errors.append({"path": "antennas.definitions", "code": "ARRAY", "message": "Antenna definitions must be an array."})
        defs = []
    for i, item in enumerate(defs):
        if not isinstance(item, Mapping):
            errors.append({"path": f"antennas.definitions[{i}]", "code": "OBJECT", "message": "Antenna definition must be an object."})
            continue
        ant_id = str(item.get("id", ""))
        if not ant_id or ant_id in ant_ids:
            errors.append({"path": f"antennas.definitions[{i}].id", "code": "DUPLICATE_OR_MISSING", "message": "Antenna IDs must be unique and non-empty."})
        ant_ids.add(ant_id)
        _range(errors, f"antennas.definitions[{i}].gain_dbi", item.get("gain_dbi", 0), -100.0, 100.0)
    if not isinstance(assignments, Mapping):
        errors.append({"path": "antennas.assignments", "code": "OBJECT", "message": "Antenna assignments must be an object."})
    else:
        for entity, ant_id in assignments.items():
            if str(ant_id) not in ant_ids:
                errors.append({"path": f"antennas.assignments.{entity}", "code": "UNKNOWN_ANTENNA", "message": f"Unknown antenna {ant_id}."})

    traffic = cfg.get("traffic", {})
    flows = traffic.get("flows", []) if isinstance(traffic, Mapping) else []
    if not isinstance(flows, list) or not flows:
        errors.append({"path": "traffic.flows", "code": "REQUIRED", "message": "At least one traffic flow is required."})
    else:
        flow_ids: set[str] = set()
        for i, flow in enumerate(flows):
            if not isinstance(flow, Mapping):
                errors.append({"path": f"traffic.flows[{i}]", "code": "OBJECT", "message": "Flow must be an object."})
                continue
            flow_id = str(flow.get("id", ""))
            if not flow_id or flow_id in flow_ids:
                errors.append({"path": f"traffic.flows[{i}].id", "code": "DUPLICATE_OR_MISSING", "message": "Flow IDs must be unique and non-empty."})
            flow_ids.add(flow_id)
            if str(flow.get("generation_model", "")) not in SUPPORTED_TRAFFIC_MODELS:
                errors.append({"path": f"traffic.flows[{i}].generation_model", "code": "UNSUPPORTED_MODEL", "message": f"Supported traffic models: {sorted(SUPPORTED_TRAFFIC_MODELS)}."})
            _range(errors, f"traffic.flows[{i}].packet_size_bytes", flow.get("packet_size_bytes", 0), 1, 10_000_000)
            _range(errors, f"traffic.flows[{i}].packet_rate_pps", flow.get("packet_rate_pps", 0), 0, 1_000_000)

    if errors and strict:
        raise ValidationError(
            code="CONFIG_VALIDATION_FAILED",
            message=f"Experiment configuration contains {len(errors)} validation error(s).",
            component="configuration",
            details={"errors": errors, "warnings": warnings},
            recommendation="Correct the highlighted Mission Designer fields before launching the experiment.",
        )
    return {"ok": not errors, "config": cfg, "errors": errors, "warnings": warnings}


def canonical_json(config: Mapping[str, Any]) -> str:
    return json.dumps(config, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def configuration_hash(config: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(config).encode("utf-8")).hexdigest()


def emit_legacy_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Emit v4-compatible aliases consumed by the existing ROS and Isaac adapters."""
    cfg = migrate_legacy_config(config)
    swarm = cfg["swarm"]
    topology = cfg["topology"]
    comm = cfg["communication"]
    world = cfg["world"]
    visualization = cfg["visualization"]
    station = copy.deepcopy(cfg["station"])
    antennas = cfg["antennas"]

    legacy_drones = []
    for item in swarm["drones"]:
        ant_id = antennas.get("assignments", {}).get(item["id"], item.get("antenna_id", "uav_omni_reference"))
        ant_def = next((x for x in antennas.get("definitions", []) if x.get("id") == ant_id), {})
        legacy_drones.append(
            {
                "id": item["id"],
                "index": item["index"],
                "position": list(item["position"]),
                "role": item.get("role", "relay"),
                "active": bool(item.get("active", True)),
                "failed": bool(item.get("failed", False)),
                "battery_pct": item.get("battery_soc_pct", 100.0),
                "antenna_name": ant_id,
                "antenna_gain_dbi": ant_def.get("gain_dbi", 0.0),
            }
        )

    legacy_antennas = []
    for item in antennas.get("definitions", []):
        legacy_antennas.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "enabled": True,
                "role": item.get("model", "custom"),
                "attached_to": next((entity for entity, aid in antennas.get("assignments", {}).items() if aid == item.get("id")), "world"),
                "position": item.get("position_offset_m", [0.0, 0.0, 0.0]),
                "rotation_xyz": item.get("rotation_rpy_deg", [0.0, 0.0, 0.0]),
                "gain_dbi": item.get("gain_dbi", 0.0),
                "azimuth_deg": item.get("rotation_rpy_deg", [0.0, 0.0, 0.0])[2] if len(item.get("rotation_rpy_deg", [])) == 3 else 0.0,
                "elevation_deg": item.get("rotation_rpy_deg", [0.0, 0.0, 0.0])[1] if len(item.get("rotation_rpy_deg", [])) == 3 else 0.0,
                "beamwidth_deg": item.get("beamwidth_azimuth_deg", 360.0),
                "frequency_hz": item.get("center_frequency_hz", comm["carrier_frequency_hz"]),
                "bandwidth_hz": item.get("bandwidth_hz", comm["bandwidth_hz"]),
                "tx_power_dbm": comm["tx_power_dbm"],
                "polarization": item.get("polarization", "vertical"),
                "technology": "SNaaS research antenna",
                "provenance": item.get("provenance", "unknown"),
            }
        )

    legacy = {
        "schema_version": cfg["schema_version"],
        "experiment_name": cfg["experiment"]["name"],
        "scenario_id": cfg["experiment"]["id"],
        "seed": cfg["experiment"]["seed"],
        "duration_s": cfg["experiment"]["duration_s"],
        "fidelity_profile": cfg["experiment"]["fidelity_profile"],
        "drone_count": swarm["drone_count"],
        "relay_count": swarm["relay_count"],
        "standby_count": swarm["standby_count"],
        "failed_indices": [int(item["index"]) for item in swarm["drones"] if bool(item.get("failed", False))],
        "branch_count": len(topology["branches"]),
        "transmission_mode": topology["mode"],
        "manual_branches": copy.deepcopy(topology["branches"]),
        "topology": {
            "transmission_mode": topology["mode"],
            "manual_branches": copy.deepcopy(topology["branches"]),
            "forwarding_policy": topology["forwarding_policy"],
            "queue_model": topology["queue_model"],
            "routing_policy": topology["routing_policy"],
        },
        "hop_period_s": cfg["clock"]["link_update_period_s"],
        "failure_detection_s": cfg["failures"]["failure_detection_s"],
        "coverage_radius_m": cfg["service_region"]["length_m"],
        "coverage_width_m": cfg["service_region"]["width_m"],
        "altitude_start_m": cfg["service_region"]["min_altitude_m"],
        "altitude_end_m": cfg["service_region"]["max_altitude_m"],
        "direction_deg": 0.0,
        "movement_pattern": cfg["swarm"]["mobility"]["model"],
        "movement_amplitude_m": float(cfg["swarm"]["mobility"].get("parameters", {}).get("amplitude_m", 0.0)),
        "movement_speed": float(cfg["swarm"]["mobility"].get("parameters", {}).get("speed_multiplier", 1.0)),
        "visual_follow_alpha": 0.18,
        "wind_speed_mps": world["environment"]["wind_speed_mps"],
        "wind_direction_deg": world["environment"]["wind_direction_deg"],
        "turbulence_intensity": world["environment"]["turbulence_intensity"],
        "standby_activation_radius_m": max(5.0, swarm["minimum_separation_m"] * 8.0),
        "max_single_hop_range_m": comm["operational_range_m"],
        "hard_outage_range_m": comm["hard_outage_distance_m"],
        "allow_degraded_forwarding": False,
        "distance_penalty_db_per_m_after_soft_range": 0.22,
        "station": station,
        "drones": legacy_drones,
        "antennas": legacy_antennas,
        "antenna_count": len(legacy_antennas),
        "worlds": copy.deepcopy(world.get("assets", [])),
        "world_count": len(world.get("assets", [])),
        "radio": {
            "frequency_hz": comm["carrier_frequency_hz"],
            "bandwidth_hz": comm["bandwidth_hz"],
            "tx_power_dbm": comm["tx_power_dbm"],
            "noise_floor_dbm": comm.get("legacy_noise_floor_dbm", -174.0 + 10.0 * math.log10(comm["bandwidth_hz"]) + comm["receiver_noise_figure_db"]),
            "receiver_noise_figure_db": comm["receiver_noise_figure_db"],
            "implementation_loss_db": comm["implementation_loss_db"],
            "min_snr_db": comm["min_snr_db"],
            "required_capacity_mbps": comm["min_capacity_mbps"],
            "model": comm["model"],
            "fidelity": comm["fidelity"],
            "spectral_efficiency_factor": comm["spectral_efficiency_factor"],
            "antenna_model": "versioned_antenna_registry",
        },
        "message": {
            "payload": "SNaaS service request: preserve service continuity, append UAV state, and return acknowledgement.",
            "payload_bytes": cfg["traffic"]["flows"][0]["packet_size_bytes"] if cfg["traffic"]["flows"] else 512,
        },
        "traffic": copy.deepcopy(cfg["traffic"]),
        "environment": copy.deepcopy(world["environment"]),
        "energy": copy.deepcopy(swarm["energy"]),
        "visual": {
            "custom_drone_usd": visualization["custom_drone_usd"],
            "drone_scale": 0.2,
            "visual_asset_scale": 0.2,
            "physical_collision_dimensions_m": swarm["physical_collision_dimensions_m"],
            "show_coverage_area": visualization["show_service_region"],
            "show_drone_coverage_rings": visualization["show_coverage_preview"],
            "show_drone_coverage_spheres": False,
            "drone_coverage_opacity": visualization["coverage_opacity"],
            "coverage_visual_radius_m": comm["operational_range_m"],
        },
        "v6": cfg,
        "v5": cfg,  # compatibility alias; remove only after all v5 adapters are retired
    }
    return legacy


def load_experiment(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return default_experiment()
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValidationError(code="CONFIG_ROOT_TYPE", message="Experiment configuration root must be an object.", component="configuration")
    return validate_experiment(value, strict=False)["config"]


def save_experiment(path: Path, config: Mapping[str, Any], *, emit_legacy: bool = True) -> Dict[str, Any]:
    validated = validate_experiment(config, strict=True)["config"]
    payload = emit_legacy_config(validated) if emit_legacy else validated
    atomic_write_json(path, payload)
    return payload
