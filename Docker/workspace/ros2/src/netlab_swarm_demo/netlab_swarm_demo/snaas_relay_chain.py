#!/usr/bin/env python3
"""
NETLAB SNaaS relay-chain / relay-forest controller.

This version supports:
- arbitrary drone counts
- multiple relay branches
- standby drone auto-integration
- runtime reconfiguration through ROS topics
- desired-coverage preservation after failures
- richer Sionna/radio metadata in every hop
- atomic JSON status writes for robust Isaac visualization
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from std_msgs.msg import String
from netlab_interfaces.msg import AlgorithmAction as AlgorithmActionMsg
from netlab_interfaces.msg import AlgorithmObservation as AlgorithmObservationMsg

from netlab.io import atomic_write_json
from netlab.algorithm_contracts import AlgorithmAction
from netlab.algorithm_runtime import AlgorithmRuntime
from netlab.config import load_experiment
from netlab.safety_shield import apply_safety_shield

Vec3 = Tuple[float, float, float]

DEFAULT_CONFIG_PATH = "/workspace/shared/snaas_relay_config.json"
DEFAULT_RESULTS_DIR = "/workspace/results"
DEFAULT_LATEST_STATUS_PATH = "/workspace/results/snaas_relay_latest_status.json"
DEFAULT_PLUGINS_DIR = "/workspace/plugins"
DEFAULT_NETLAB_ROOT = "/workspace/netlab"
DEFAULT_PLUGIN_SELECTION_PATH = "/workspace/results/snaas_active_algorithm.json"
DEFAULT_PACKET_HEARTBEAT_PATH = "/workspace/results/snaas_packet_runtime_heartbeat.json"
DEFAULT_ROS_REVISION_ACK_PATH = "/workspace/results/snaas_ros_revision_ack.json"

VALID_MOVEMENT_PATTERNS = {"hover", "oscillate", "patrol", "figure8", "orbit", "survey", "swarm", "wind", "spiral"}


def _now() -> float:
    return time.time()


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _allowed_motion_patterns() -> set[str]:
    return set(VALID_MOVEMENT_PATTERNS)


def _distance(a: Iterable[float], b: Iterable[float]) -> float:
    av = list(a)
    bv = list(b)
    return math.sqrt(sum((float(av[i]) - float(bv[i])) ** 2 for i in range(3)))


def _pose_to_vec3(msg: PoseStamped) -> Vec3:
    return (float(msg.pose.position.x), float(msg.pose.position.y), float(msg.pose.position.z))


def _default_config() -> Dict[str, Any]:
    drone_count = 8
    relay_count = 6
    return {
        "experiment_name": "snaas_relay_chain_default",
        "drone_count": drone_count,
        "relay_count": relay_count,
        "standby_count": drone_count - relay_count,
        "branch_count": 1,
        "hop_period_s": 0.5,
        "failure_detection_s": 1.5,
        "coverage_radius_m": 140.0,
        "coverage_width_m": 70.0,
        "direction_deg": 0.0,
        "altitude_start_m": 24.0,
        "altitude_end_m": 34.0,
        "movement_pattern": "hover",  # hover | oscillate | patrol | figure8 | orbit | survey | swarm | wind | spiral
        "movement_amplitude_m": 10.0,
        "movement_speed": 1.0,
        "visual_follow_alpha": 0.18,
        "wind_speed_mps": 1.2,
        "wind_direction_deg": 35.0,
        "turbulence_intensity": 0.28,
        "standby_activation_radius_m": 45.0,
        "max_single_hop_range_m": 90.0,
        "hard_outage_range_m": 220.0,
        "allow_degraded_forwarding": False,
        "distance_penalty_db_per_m_after_soft_range": 0.22,
        "station": {"id": "station", "position": [0.0, 0.0, 1.5], "antenna_gain_dbi": 8.0, "antenna_name": "ground_sector_8dBi"},
        "drones": [
            {
                "id": f"drone_{i}",
                "index": i,
                "position": [float(i * 18.0), 0.0, 18.0 + float(i % 3) * 2.0],
                "battery_pct": 100.0 - i,
                "antenna_gain_dbi": 2.5,
                "antenna_name": "dji_mini4pro_like_omni_2p5dBi",
                "role": "relay" if i <= relay_count else "standby",
            }
            for i in range(1, drone_count + 1)
        ],
        "antennas": [
            {
                "id": "ground_sector_1",
                "name": "ground_sector_1",
                "enabled": True,
                "role": "gateway",
                "attached_to": "station",
                "position": [0.0, 0.0, 1.5],
                "rotation_xyz": [0.0, 0.0, 0.0],
                "gain_dbi": 8.0,
                "azimuth_deg": 0.0,
                "elevation_deg": 0.0,
                "beamwidth_deg": 110.0,
                "frequency_hz": 3500000000.0,
                "bandwidth_hz": 20000000.0,
                "tx_power_dbm": 20.0,
                "technology": "SNaaS/5G/NTN research antenna",
            }
        ],
        "antenna_count": 1,
        "worlds": [],
        "world_count": 0,
        "radio": {
            "frequency_hz": 3500000000.0,
            "bandwidth_hz": 20000000.0,
            "tx_power_dbm": 20.0,
            "noise_floor_dbm": -95.0,
            "min_snr_db": 3.0,
            "required_capacity_mbps": 1.0,
            "tx_antenna_name": "omni_uav_array",
            "rx_antenna_name": "omni_uav_array",
            "station_antenna_name": "ground_station_sector",
            "uav_antenna_name": "dji_mini4pro_like_omni_2p5dBi",
            "antenna_model": "dji_mini4pro_like_o4_urban_obstructed_demo_model",
        },
        "message": {
            "payload": "SNaaS service request: maintain relay service, preserve coverage range, append state, return ACK.",
            "payload_bytes": 512,
        },
        "visual": {
            "custom_drone_usd": "/workspace/isaac/local_assets/drones/tu_drone.usd",
            "drone_scale": 0.2,
            "drone_rotation_xyz": [0.0, 0.0, 0.0],
            "show_coverage_area": True,
            "show_drone_coverage_rings": True,
            "show_drone_coverage_spheres": False,
            "drone_coverage_opacity": 0.035,
            "coverage_visual_radius_m": 90.0,
        },
    }


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str) -> Dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return _default_config()
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    # NETLAB stores the authoritative versioned experiment.  The packet
    # runtime keeps one compatibility projection so existing ROS topics and
    # evidence fields continue to work while every researcher edit affects the
    # live controller.
    if isinstance(data, dict) and {"experiment", "swarm", "communication", "topology"}.issubset(data):
        revision_meta = dict(data.get("_netlab_revision") or {})
        try:
            from netlab.config import emit_legacy_config
            data = emit_legacy_config(data)
            if revision_meta:
                data["_netlab_revision"] = revision_meta
        except Exception as exc:
            raise RuntimeError(f"Unable to project the authoritative experiment for ROS: {exc}") from exc
    return _deep_merge(_default_config(), data)


@dataclass
class DroneRuntime:
    index: int
    drone_id: str
    initial_position: Vec3
    current_position: Vec3
    desired_position: Vec3
    battery_pct: float
    role: str = "relay"  # relay | standby
    antenna_gain_dbi: float = 4.0
    antenna_name: str = "uav_omni_4dBi"
    failed: bool = False
    integrated: bool = True
    last_pose_time: float = 0.0
    last_seen_chain_version: int = 0

    def state_summary(self) -> Dict[str, Any]:
        return {
            "id": self.drone_id,
            "index": self.index,
            "position": [round(v, 3) for v in self.current_position],
            "desired_position": [round(v, 3) for v in self.desired_position],
            "battery_pct": round(self.battery_pct, 3),
            "role": self.role,
            "failed": self.failed,
            "integrated": self.integrated,
            "antenna_gain_dbi": round(self.antenna_gain_dbi, 3),
            "antenna_name": self.antenna_name,
            "last_pose_age_s": round(max(0.0, _now() - self.last_pose_time), 3) if self.last_pose_time else None,
        }


@dataclass
class PendingFailure:
    drone_index: int
    requested_at: float
    detection_deadline: float


class EvidenceWriter:
    def __init__(self, results_dir: str, experiment_name: str) -> None:
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in experiment_name)
        timestamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
        self.jsonl_path = self.results_dir / f"{safe_name}_{timestamp}_events.jsonl"
        self.csv_path = self.results_dir / f"{safe_name}_{timestamp}_link_metrics.csv"
        self._csv_header_written = False

    def write_event(self, payload: Dict[str, Any]) -> None:
        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(_json_dumps(payload) + "\n")

    def write_metrics(self, payload: Dict[str, Any]) -> None:
        metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics", {}), dict) else {}
        row = {
            "timestamp": payload.get("timestamp", _now()),
            "sequence": payload.get("sequence"),
            "chain_version": payload.get("chain_version"),
            "branch_id": payload.get("branch_id"),
            "phase": payload.get("phase"),
            "src": payload.get("src"),
            "dst": payload.get("dst"),
            "link_ok": payload.get("link_ok"),
            "status": metrics.get("status"),
            "gate_reason": metrics.get("gate_reason"),
            "model_source": metrics.get("model_source", metrics.get("model")),
            "fidelity_profile": metrics.get("fidelity_profile", metrics.get("fidelity")),
            "distance_m": metrics.get("distance_m"),
            "range_margin_m": metrics.get("range_margin_m"),
            "path_loss_db": metrics.get("path_loss_db"),
            "rx_power_dbm": metrics.get("rx_power_dbm"),
            "snr_db": metrics.get("snr_db"),
            "sinr_db": metrics.get("sinr_db"),
            "snr_margin_db": metrics.get("snr_margin_db"),
            "capacity_mbps": metrics.get("capacity_mbps"),
            "capacity_margin_mbps": metrics.get("capacity_margin_mbps"),
            "propagation_delay_ms": metrics.get("propagation_delay_ms"),
            "total_delay_ms": metrics.get("total_delay_ms", metrics.get("propagation_delay_ms")),
            "tx_antenna": metrics.get("tx_antenna"),
            "rx_antenna": metrics.get("rx_antenna"),
            "antenna_model": metrics.get("antenna_model"),
        }
        with self.csv_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
            if not self._csv_header_written and self.csv_path.stat().st_size == 0:
                writer.writeheader()
                self._csv_header_written = True
            writer.writerow(row)


class SnaasRelayChain(Node):
    def __init__(self) -> None:
        super().__init__("netlab_snaas_relay_chain")

        self.config_path = os.environ.get("SNAAS_CONFIG", DEFAULT_CONFIG_PATH)
        self.results_dir = os.environ.get("SNAAS_RESULTS_DIR", DEFAULT_RESULTS_DIR)
        self.config = load_config(self.config_path)
        initial_revision = self.config.get("_netlab_revision", {}) if isinstance(self.config.get("_netlab_revision", {}), dict) else {}
        self.applied_revision_id = str(initial_revision.get("revision_id", ""))
        self.applied_parent_revision_id = str(initial_revision.get("parent_revision_id", ""))
        self.applied_revision_hashes = {key: value for key, value in initial_revision.items() if key.endswith("_hash")}
        self.applied_revision_command_id = str(initial_revision.get("command_id", ""))

        self.experiment_name = str(self.config.get("experiment_name", "snaas_relay_chain"))
        self.drone_count = max(1, _as_int(self.config.get("drone_count"), 6))
        self.relay_count_hint = max(1, min(self.drone_count, _as_int(self.config.get("relay_count"), self.drone_count)))
        self.standby_count_hint = max(0, _as_int(self.config.get("standby_count"), max(0, self.drone_count - self.relay_count_hint)))
        self.relay_count = max(1, min(self.drone_count, self.relay_count_hint))
        self.standby_count = max(0, self.drone_count - self.relay_count)
        if "standby_count" in self.config and "relay_count" not in self.config:
            self.standby_count = max(0, min(self.drone_count - 1, self.standby_count_hint))
            self.relay_count = max(1, self.drone_count - self.standby_count)
        self.relay_count_hint = self.relay_count
        self.standby_count_hint = self.standby_count
        self.branch_count = max(1, _as_int(self.config.get("branch_count"), 1))
        topology_cfg = self.config.get("topology", {}) if isinstance(self.config.get("topology", {}), dict) else {}
        self.transmission_mode = str(topology_cfg.get("transmission_mode", self.config.get("transmission_mode", "chain" if self.branch_count <= 1 else "parallel"))).lower()
        if self.transmission_mode not in {"chain", "parallel", "forest", "manual"}:
            self.transmission_mode = "parallel" if self.branch_count > 1 else "chain"
        self.manual_branches = self._sanitize_manual_branches(topology_cfg.get("manual_branches", self.config.get("manual_branches", [])), filter_failed=False)
        self.forwarding_policy = str(topology_cfg.get("forwarding_policy", self.config.get("forwarding_policy", "fifo_round_robin")))
        self.queue_model = str(topology_cfg.get("queue_model", self.config.get("queue_model", "priority_mg1_preview")))
        self.hop_period_s = max(0.05, _as_float(self.config.get("hop_period_s"), 0.5))
        self.failure_detection_s = max(0.1, _as_float(self.config.get("failure_detection_s"), 1.5))
        self.coverage_radius_m = max(1.0, _as_float(self.config.get("coverage_radius_m"), 120.0))
        self.coverage_width_m = max(1.0, _as_float(self.config.get("coverage_width_m"), 60.0))
        self.direction_deg = _as_float(self.config.get("direction_deg"), 0.0)
        self.altitude_start_m = _as_float(self.config.get("altitude_start_m"), 22.0)
        self.altitude_end_m = _as_float(self.config.get("altitude_end_m"), 32.0)
        self.movement_pattern = str(self.config.get("movement_pattern", "hover"))
        self.movement_amplitude_m = max(0.0, _as_float(self.config.get("movement_amplitude_m"), 10.0))
        self.movement_speed = max(0.05, _as_float(self.config.get("movement_speed"), 1.0))
        self.visual_follow_alpha = max(0.02, min(1.0, _as_float(self.config.get("visual_follow_alpha"), 0.18)))
        self.wind_speed_mps = max(0.0, _as_float(self.config.get("wind_speed_mps"), 0.0))
        self.wind_direction_deg = _as_float(self.config.get("wind_direction_deg"), 0.0)
        self.turbulence_intensity = max(0.0, _as_float(self.config.get("turbulence_intensity"), 0.0))
        self.standby_activation_radius_m = max(1.0, _as_float(self.config.get("standby_activation_radius_m"), 80.0))
        self.max_single_hop_range_m = max(1.0, _as_float(self.config.get("max_single_hop_range_m"), 90.0))
        self.hard_outage_range_m = max(self.max_single_hop_range_m, _as_float(self.config.get("hard_outage_range_m"), max(220.0, self.max_single_hop_range_m * 2.0)))
        self.allow_degraded_forwarding = _as_bool(self.config.get("allow_degraded_forwarding", False), False)
        self.distance_penalty_db_per_m_after_soft_range = max(0.0, _as_float(self.config.get("distance_penalty_db_per_m_after_soft_range"), 0.22))

        radio = self.config.get("radio", {})
        self.sionna_url = os.environ.get("SIONNA_URL", "http://127.0.0.1:8090/link")
        self.frequency_hz = _as_float(radio.get("frequency_hz"), 3.5e9)
        self.bandwidth_hz = _as_float(radio.get("bandwidth_hz"), 20e6)
        self.tx_power_dbm = _as_float(radio.get("tx_power_dbm"), 23.0)
        self.noise_floor_dbm = _as_float(radio.get("noise_floor_dbm"), -95.0)
        self.min_snr_db = _as_float(radio.get("min_snr_db"), 3.0)
        self.required_capacity_mbps = _as_float(radio.get("required_capacity_mbps"), 1.0)
        self.radio_metadata = {
            "frequency_hz": self.frequency_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "tx_power_dbm": self.tx_power_dbm,
            "noise_floor_dbm": self.noise_floor_dbm,
            "min_snr_db": self.min_snr_db,
            "required_capacity_mbps": self.required_capacity_mbps,
            "station_antenna_name": str(radio.get("station_antenna_name", "ground_station_sector")),
            "uav_antenna_name": str(radio.get("uav_antenna_name", "uav_omni_vertical")),
            "antenna_model": str(radio.get("antenna_model", "abstract_gain_model_for_realtime_demo")),
        }

        station = self.config.get("station", {})
        self.station_position = tuple(float(v) for v in station.get("position", [0.0, 0.0, 1.5]))  # type: ignore[assignment]
        self.station_antenna_name = str(station.get("antenna_name", self.radio_metadata["station_antenna_name"]))
        self.station_antenna_gain_dbi = _as_float(station.get("antenna_gain_dbi"), 8.0)
        self.antennas = self.config.get("antennas", []) if isinstance(self.config.get("antennas", []), list) else []
        self.worlds = self.config.get("worlds", []) if isinstance(self.config.get("worlds", []), list) else []

        self.drones: Dict[int, DroneRuntime] = {}
        self.drone_publishers: Dict[int, Dict[str, Any]] = {}
        self.failed_indices: set[int] = set()
        self.pending_failure: Optional[PendingFailure] = None
        self.last_removed_indices: List[int] = []
        self.chain_version = 1
        self.phase = "forward"
        self.cursor = 0
        self.current_branch_index = 0
        self.packet_id = 0
        self.sequence = 0
        self.last_hop_event: Dict[str, Any] = {}
        self.coverage_feasible = True
        self.coverage_note = "not_evaluated"
        # Protocol safety latch: when a hop is physically unavailable the relay
        # stops transmitting instead of repeatedly faking TX attempts. It resumes
        # only after reset, heal, or runtime config changes recompute a feasible topology.
        self.connectivity_paused = False
        self.connectivity_pause_reason = ""
        self.paused_hop: Dict[str, Any] = {}
        self.operator_paused = False
        self.mission_mode = "RUNNING"
        self.last_mission_command = ""
        self.last_mission_command_id = ""

        self.evidence = EvidenceWriter(self.results_dir, self.experiment_name)
        self.latest_status_path = Path(os.environ.get("SNAAS_LATEST_STATUS", DEFAULT_LATEST_STATUS_PATH))
        self.packet_heartbeat_path = Path(os.environ.get("SNAAS_PACKET_HEARTBEAT", DEFAULT_PACKET_HEARTBEAT_PATH))
        self.ros_revision_ack_path = Path(os.environ.get("SNAAS_ROS_REVISION_ACK", DEFAULT_ROS_REVISION_ACK_PATH))
        self.latest_status_path.parent.mkdir(parents=True, exist_ok=True)
        self.packet_heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self.ros_revision_ack_path.parent.mkdir(parents=True, exist_ok=True)

        self.status_pub = self.create_publisher(String, "/swarm/chain/status", 10)
        self.event_pub = self.create_publisher(String, "/swarm/chain/events", 10)
        self.link_pub = self.create_publisher(String, "/swarm/sionna/link_metrics", 10)
        self.station_outbox_pub = self.create_publisher(String, "/swarm/station/outbox", 10)
        self.station_inbox_pub = self.create_publisher(String, "/swarm/station/inbox", 10)

        self.plugins_dir = Path(os.environ.get("SNAAS_PLUGINS_DIR", DEFAULT_PLUGINS_DIR))
        self.plugin_selection_path = Path(os.environ.get("SNAAS_PLUGIN_SELECTION", DEFAULT_PLUGIN_SELECTION_PATH))
        self.netlab_root = Path(os.environ.get("NETLAB_REPO_ROOT", DEFAULT_NETLAB_ROOT))
        self.algorithm_runtime = AlgorithmRuntime(self.netlab_root)
        self.strategy_module: Any = None
        self.strategy_package: Any = None
        self.strategy_id: Optional[str] = None
        self.strategy_parameters: Dict[str, Any] = {}
        self.strategy_selection_mtime_ns = -1
        self.last_algorithm_decision: Dict[str, Any] = {}
        self.algorithm_status_pub = self.create_publisher(String, "/netlab/algorithm/status", 10)
        self.algorithm_observation_pub = self.create_publisher(AlgorithmObservationMsg, "/netlab/algorithm/observation", 10)
        self.create_subscription(AlgorithmActionMsg, "/netlab/algorithm/action", self._algorithm_action_cb, 10)
        self.algorithm_bridge_mode = str(os.environ.get("NETLAB_ALGORITHM_BRIDGE_MODE", "typed")).lower()
        self.pending_algorithm_observation_hash = ""
        self.pending_algorithm_revision_id = ""
        self._load_active_strategy(force=True)

        self._load_drones_from_config()
        self.home_positions = {idx: tuple(drone.current_position) for idx, drone in self.drones.items()}
        self._recompute_desired_positions(reason="initial_layout", reset_packet=False)

        self.create_subscription(String, "/swarm/control/fail_drone", self._fail_drone_cb, 10)
        self.create_subscription(String, "/swarm/control/heal_drone", self._heal_drone_cb, 10)
        self.create_subscription(String, "/swarm/control/reset_chain", self._reset_chain_cb, 10)
        self.create_subscription(String, "/swarm/control/update_config", self._update_config_cb, 10)
        self.create_subscription(String, "/swarm/control/set_pattern", self._set_pattern_cb, 10)
        self.create_subscription(String, "/swarm/control/standby_drone", self._standby_drone_cb, 10)
        self.create_subscription(String, "/swarm/control/mission_command", self._mission_command_cb, 10)

        self.timer = self.create_timer(self.hop_period_s, self._tick)
        self.status_timer = self.create_timer(0.1, self._publish_status)
        self.current_packet = self._new_packet()
        self.branch_flow_state: Dict[int, Dict[str, Any]] = {}

        self._emit_event(
            "experiment_started",
            {
                "config_path": self.config_path,
                "results_jsonl": str(self.evidence.jsonl_path),
                "results_csv": str(self.evidence.csv_path),
                "drone_count": self.drone_count,
                "relay_count": self.relay_count,
                "standby_count": self.standby_count,
                "branch_count": self.branch_count,
                "active_branches": self._active_branches(),
                "radio": self.radio_metadata,
                "strategy": self.strategy_id,
            },
        )
        self.get_logger().info("SNaaS relay-chain / relay-forest node started")
        self.get_logger().info(f"Config: {self.config_path}")
        self.get_logger().info(f"Sionna URL: {self.sionna_url}")
        self.get_logger().info(f"Active branches: {self._active_branches()}")

    # ---------- setup ----------
    def _load_drones_from_config(self) -> None:
        configured = self.config.get("drones", [])
        if not isinstance(configured, list):
            configured = []
        by_index: Dict[int, Dict[str, Any]] = {}
        for item in configured:
            idx = _as_int(item.get("index"), len(by_index) + 1)
            by_index[idx] = item
        for index in range(1, self.drone_count + 1):
            self._ensure_drone(index, by_index.get(index, {}))
        self._apply_role_counts(self.relay_count, self.standby_count, preserve_explicit_roles=bool(by_index))

    def _resize_swarm(self, new_total: int, relay_count: Optional[int] = None, standby_count: Optional[int] = None) -> Dict[str, Any]:
        new_total = max(1, int(new_total))
        removed = [idx for idx in sorted(self.drones) if idx > new_total]
        added: List[int] = []
        for idx in removed:
            self.failed_indices.discard(idx)
            if self.pending_failure and self.pending_failure.drone_index == idx:
                self.pending_failure = None
            self.drones.pop(idx, None)
            pubs = self.drone_publishers.pop(idx, {})
            for pub in pubs.values():
                try:
                    self.destroy_publisher(pub)
                except Exception:
                    pass
        self.drone_count = new_total
        for idx in range(1, new_total + 1):
            if idx not in self.drones:
                self._ensure_drone(idx)
                added.append(idx)
        self._apply_role_counts(relay_count, standby_count)
        return {"new_total": new_total, "added": added, "removed": removed, "relay_count": self.relay_count, "standby_count": self.standby_count}

    def _apply_role_counts(self, relay_count: Optional[int] = None, standby_count: Optional[int] = None, preserve_explicit_roles: bool = False) -> None:
        total = len(self.drones)
        if total <= 0:
            self.relay_count = 0
            self.standby_count = 0
            return
        if standby_count is not None and relay_count is None:
            relay_count = total - max(0, int(standby_count))
        if relay_count is None:
            relay_count = self.relay_count if self.relay_count else total
        relay_count = max(1, min(total, int(relay_count)))
        self.relay_count = relay_count
        self.standby_count = max(0, total - relay_count)
        if preserve_explicit_roles:
            # Initial config files may explicitly mark standby drones. Respect them,
            # but still keep relay/standby counters internally consistent.
            explicit_standby = [idx for idx, d in sorted(self.drones.items()) if d.role == "standby"]
            if explicit_standby:
                self.standby_count = len(explicit_standby)
                self.relay_count = max(1, total - self.standby_count)
                return
        for idx in sorted(self.drones):
            drone = self.drones[idx]
            if idx <= self.relay_count:
                if idx not in self.failed_indices:
                    drone.role = "relay"
                    drone.integrated = True
            else:
                drone.role = "standby"
                drone.integrated = False


    def _default_position_for_index(self, index: int) -> Vec3:
        theta = math.radians(self.direction_deg)
        dx, dy = math.cos(theta), math.sin(theta)
        px, py = -dy, dx
        spacing = self.coverage_radius_m / max(1, self.drone_count)
        along = spacing * index
        lateral = ((-1.0) ** index) * min(self.coverage_width_m * 0.18, 10.0)
        alpha = (index - 1) / max(1, self.drone_count - 1)
        z = self.altitude_start_m + (self.altitude_end_m - self.altitude_start_m) * alpha
        return (self.station_position[0] + dx * along + px * lateral, self.station_position[1] + dy * along + py * lateral, z)

    def _ensure_drone(self, index: int, item: Optional[Dict[str, Any]] = None) -> None:
        item = item or {}
        if index not in self.drones:
            pos_raw = item.get("position", self._default_position_for_index(index))
            pos = (float(pos_raw[0]), float(pos_raw[1]), float(pos_raw[2]))
            role = str(item.get("role", "relay"))
            self.drones[index] = DroneRuntime(
                index=index,
                drone_id=str(item.get("id", f"drone_{index}")),
                initial_position=pos,
                current_position=pos,
                desired_position=pos,
                battery_pct=_as_float(item.get("battery_pct"), max(10.0, 100.0 - index * 1.5)),
                antenna_gain_dbi=_as_float(item.get("antenna_gain_dbi"), 4.0),
                antenna_name=str(item.get("antenna_name", self.radio_metadata["uav_antenna_name"])),
                role=role,
                integrated=(role != "standby"),
            )
        if index not in self.drone_publishers:
            self.create_subscription(PoseStamped, f"/swarm/drone_{index}/state", self._pose_cb_factory(index), 10)
            self.drone_publishers[index] = {
                "inbox": self.create_publisher(String, f"/swarm/drone_{index}/inbox", 10),
                "outbox": self.create_publisher(String, f"/swarm/drone_{index}/outbox", 10),
                "terminal": self.create_publisher(String, f"/swarm/drone_{index}/terminal", 10),
            }

    # ---------- ROS helpers ----------
    def _pose_cb_factory(self, index: int):
        def _callback(msg: PoseStamped) -> None:
            if index in self.drones:
                self.drones[index].current_position = _pose_to_vec3(msg)
                self.drones[index].last_pose_time = _now()
        return _callback

    def _publish_json(self, publisher: Any, payload: Dict[str, Any]) -> None:
        msg = String()
        msg.data = _json_dumps(payload)
        publisher.publish(msg)

    def _emit_event(self, event_type: str, details: Dict[str, Any]) -> None:
        payload = {
            "timestamp": _now(),
            "event_type": event_type,
            "chain_version": self.chain_version,
            "sequence": self.sequence,
            "details": details,
        }
        self._publish_json(self.event_pub, payload)
        self.evidence.write_event(payload)

    # ---------- strategy plugins ----------
    def _read_json_file(self, path: Path, default: Any) -> Any:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warning(f"Could not read JSON {path}: {exc}")
        return default

    def _parse_drone_index(self, value: Any) -> Optional[int]:
        try:
            if isinstance(value, str):
                value = value.strip().lower().replace("drone_", "")
            idx = int(value)
            return idx if idx in self.drones else None
        except Exception:
            return None

    def _publish_algorithm_status(self, state: str, details: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "timestamp": _now(),
            "state": state,
            "algorithm_id": self.strategy_id,
            "api_version": "2.0",
            "selection_path": str(self.plugin_selection_path),
            "details": details or {},
        }
        self._publish_json(self.algorithm_status_pub, payload)

    def _load_active_strategy(self, *, force: bool = False) -> None:
        try:
            mtime_ns = self.plugin_selection_path.stat().st_mtime_ns if self.plugin_selection_path.exists() else -1
        except OSError:
            mtime_ns = -1
        if not force and mtime_ns == self.strategy_selection_mtime_ns:
            return
        self.strategy_selection_mtime_ns = mtime_ns
        selection = self._read_json_file(self.plugin_selection_path, {"active": None})
        active = None
        if isinstance(selection, dict):
            active = selection.get("algorithm_id", selection.get("active"))
            self.strategy_parameters = dict(selection.get("parameters", {})) if isinstance(selection.get("parameters"), dict) else {}
        if not active:
            previous = self.strategy_id
            self.strategy_module = None
            self.strategy_package = None
            self.strategy_id = None
            if previous:
                self._emit_event("strategy_deactivated", {"strategy": previous})
                self._publish_algorithm_status("INACTIVE")
            return
        try:
            package = self.algorithm_runtime.registry.get(str(active))
            if not package.valid:
                raise RuntimeError("; ".join(package.errors))
            self.strategy_package = package
            self.strategy_module = None
            self.strategy_id = str(active)
            details = {
                "strategy": self.strategy_id,
                "package_dir": str(package.package_dir),
                "version": package.manifest.version,
                "execution_mode": package.manifest.execution_mode,
                "source_hash": package.manifest.source_hash,
            }
            self._emit_event("strategy_loaded", details)
            self._publish_algorithm_status("READY", details)
            return
        except Exception as package_exc:
            candidate = (self.plugins_dir / f"{active}.py").resolve()
            try:
                plugins_root = self.plugins_dir.resolve()
                if plugins_root not in candidate.parents or not candidate.exists():
                    raise FileNotFoundError(f"algorithm package and legacy strategy not found: {active}; package error: {package_exc}")
                spec = importlib.util.spec_from_file_location(f"snaas_strategy_{active}", candidate)
                if spec is None or spec.loader is None:
                    raise ImportError(f"could not create import spec for {candidate}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.strategy_module = module
                self.strategy_package = None
                self.strategy_id = str(active)
                self._emit_event("strategy_loaded_legacy", {"strategy": self.strategy_id, "file": str(candidate)})
                self._publish_algorithm_status("READY_LEGACY", {"file": str(candidate)})
            except Exception as exc:  # noqa: BLE001
                self.strategy_module = None
                self.strategy_package = None
                self.strategy_id = None
                self.get_logger().warning(f"SNaaS strategy load failed: {exc}")
                self._emit_event("strategy_load_failed", {"strategy": str(active), "error": str(exc)})
                self._publish_algorithm_status("FAILED", {"error": str(exc), "requested": str(active)})

    def _strategy_context(self) -> Dict[str, Any]:
        return {
            "experiment_name": self.experiment_name,
            "station": [round(v, 6) for v in self.station_position],
            "relays": list(self._active_chain()),
            "branches": [list(b) for b in self._active_branches()],
            "standby": list(self._standby_indices()),
            "failed": sorted(self.failed_indices),
            "coverage_m": self.coverage_radius_m,
            "coverage_width_m": self.coverage_width_m,
            "altitude_band": (self.altitude_start_m, self.altitude_end_m),
            "range_gate_m": self.max_single_hop_range_m,
            "hard_outage_range_m": self.hard_outage_range_m,
            "radio": dict(self.radio_metadata),
            "transmission_mode": self.transmission_mode,
            "parameters": dict(self.strategy_parameters),
            "drones": {
                idx: {
                    "id": drone.drone_id,
                    "position": [round(v, 6) for v in drone.current_position],
                    "desired_position": [round(v, 6) for v in drone.desired_position],
                    "role": drone.role,
                    "active": bool(drone.integrated),
                    "failed": bool(drone.failed or idx in self.failed_indices),
                    "integrated": bool(drone.integrated),
                    "battery_soc_pct": float(drone.battery_pct),
                }
                for idx, drone in self.drones.items()
            },
        }

    def _canonical_algorithm_observation(self) -> Dict[str, Any]:
        try:
            canonical = load_experiment(Path(self.config_path))
        except Exception as exc:
            self._emit_event("algorithm_config_load_failed", {"error": str(exc)})
            canonical = {}
        uavs: List[Dict[str, Any]] = []
        for idx, drone in sorted(self.drones.items()):
            pos = [float(v) for v in drone.current_position]
            desired = [float(v) for v in drone.desired_position]
            uavs.append({
                "id": drone.drone_id,
                "index": idx,
                "position": pos,
                "desired_position": desired,
                "commanded_position": desired,
                "simulated_position": pos,
                "measured_position": pos,
                "rendered_position": pos,
                "velocity": [0.0, 0.0, 0.0],
                "active": bool(drone.integrated),
                "failed": bool(drone.failed or idx in self.failed_indices),
                "role": drone.role,
                "battery_soc_pct": float(drone.battery_pct),
            })
        topology = dict(canonical.get("topology", {})) if isinstance(canonical.get("topology"), dict) else {
            "mode": self.transmission_mode,
            "branches": [[int(i) for i in branch] for branch in self._active_branches()],
            "source": "station",
        }
        links: List[Dict[str, Any]] = []
        if isinstance(self.last_hop_event, dict) and self.last_hop_event:
            metric = self.last_hop_event.get("metrics", {}) if isinstance(self.last_hop_event.get("metrics"), dict) else {}
            links.append({
                "src": self.last_hop_event.get("src"),
                "dst": self.last_hop_event.get("dst"),
                **metric,
                "timestamp": self.last_hop_event.get("timestamp", _now()),
            })
        state = {
            "experiment_id": str(canonical.get("experiment", {}).get("id", self.experiment_name)) if isinstance(canonical.get("experiment"), dict) else self.experiment_name,
            "run_id": str(getattr(self, "run_id", "")),
            "revision_id": self.applied_revision_id or "runtime-current",
            "seed": int(canonical.get("experiment", {}).get("seed", 0)) if isinstance(canonical.get("experiment"), dict) else 0,
            "wall_time_s": _now(),
            "simulation_time_s": float(self.sequence) * float(self.hop_period_s),
            "step_s": float(self.hop_period_s),
            "real_time_factor": 1.0,
            "uavs": uavs,
            "ground_entities": [dict(canonical.get("station", {}))] if isinstance(canonical.get("station"), dict) else [{"id": "station", "position": list(self.station_position), "active": True}],
            "topology": topology,
            "links": links,
            "packets": dict(self.current_packet) if isinstance(getattr(self, "current_packet", {}), dict) else {},
            "flows": [dict(v) for v in getattr(self, "branch_flow_state", {}).values() if isinstance(v, dict)],
            "world": dict(canonical.get("world", {})) if isinstance(canonical.get("world"), dict) else {},
            "antennas": dict(canonical.get("antennas", {})) if isinstance(canonical.get("antennas"), dict) else {},
            "failures": [{"entity_id": f"drone_{idx}", "type": "uav_failure", "active": True} for idx in sorted(self.failed_indices)],
            "recovery": {"pending_failure": self.pending_failure.drone_index if self.pending_failure else None},
            "service_requirements": {"communication": canonical.get("communication", {}), "traffic": canonical.get("traffic", {})},
            "constraints": {
                "service_region": canonical.get("service_region", {}),
                "minimum_separation_m": canonical.get("swarm", {}).get("minimum_separation_m", 4.0) if isinstance(canonical.get("swarm"), dict) else 4.0,
                "max_horizontal_speed_mps": canonical.get("swarm", {}).get("max_horizontal_speed_mps", 12.0) if isinstance(canonical.get("swarm"), dict) else 12.0,
                "max_vertical_speed_mps": canonical.get("swarm", {}).get("max_vertical_speed_mps", 4.0) if isinstance(canonical.get("swarm"), dict) else 4.0,
                "max_acceleration_mps2": canonical.get("swarm", {}).get("max_acceleration_mps2", 5.0) if isinstance(canonical.get("swarm"), dict) else 5.0,
                "max_jerk_mps3": canonical.get("swarm", {}).get("max_jerk_mps3", 8.0) if isinstance(canonical.get("swarm"), dict) else 8.0,
            },
            "uncertainty": {},
            "source": "LIVE_ROS_RUNTIME",
            "schema_version": "2.0",
            "sequence": int(self.sequence),
        }
        return state

    def _publish_typed_algorithm_observation(self, reason: str) -> bool:
        if self.strategy_package is None or not self.strategy_id:
            return False
        observation = self._canonical_algorithm_observation()
        try:
            from netlab.algorithm_contracts import canonical_json_hash
            payload_json = json.dumps(observation, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            observation_hash = canonical_json_hash(observation)
            msg = AlgorithmObservationMsg()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.schema_version = "2.0"
            msg.experiment_id = str(observation.get("experiment_id", self.experiment_name))
            msg.run_id = str(observation.get("run_id", ""))
            msg.revision_id = str(observation.get("revision_id", "runtime-current"))
            msg.sequence = int(observation.get("sequence", self.sequence))
            msg.seed = int(observation.get("seed", 0))
            msg.simulation_time_s = float(observation.get("simulation_time_s", 0.0))
            msg.step_s = float(observation.get("step_s", self.hop_period_s))
            msg.real_time_factor = float(observation.get("real_time_factor", 1.0))
            msg.fidelity_profile = str(observation.get("service_requirements", {}).get("communication", {}).get("fidelity", "F1_ANALYTICAL"))
            msg.observation_hash = observation_hash
            msg.payload_json = payload_json
            self.pending_algorithm_observation_hash = observation_hash
            self.pending_algorithm_revision_id = msg.revision_id
            self.algorithm_observation_pub.publish(msg)
            self._emit_event("algorithm_observation_published", {"strategy": self.strategy_id, "reason": reason, "observation_hash": observation_hash, "revision_id": msg.revision_id})
            self._publish_algorithm_status("WAITING_FOR_ACTION", {"reason": reason, "observation_hash": observation_hash})
            return True
        except Exception as exc:
            self._emit_event("algorithm_observation_publish_failed", {"strategy": self.strategy_id, "reason": reason, "error": str(exc)})
            return False

    def _algorithm_action_cb(self, msg: AlgorithmActionMsg) -> None:
        if not self.strategy_id or str(msg.algorithm_id) != self.strategy_id:
            return
        if self.pending_algorithm_revision_id and msg.source_revision_id not in {self.pending_algorithm_revision_id, "runtime-current"}:
            self._emit_event("algorithm_action_stale_revision", {"strategy": self.strategy_id, "expected_revision": self.pending_algorithm_revision_id, "received_revision": msg.source_revision_id})
            return
        try:
            payload = json.loads(msg.payload_json or "{}")
            if not isinstance(payload, dict):
                raise TypeError("algorithm action payload must be an object")
            plan = payload.get("desired_positions", {})
            if not isinstance(plan, dict):
                raise TypeError("desired_positions must be an object")
            applied: Dict[str, List[float]] = {}
            active_relays = set(self._active_chain())
            for key, value in plan.items():
                idx = self._parse_drone_index(key)
                if idx is None or idx not in active_relays or idx in self.failed_indices:
                    continue
                vec = list(value)
                if len(vec) != 3:
                    continue
                pos = (float(vec[0]), float(vec[1]), float(vec[2]))
                if not all(math.isfinite(component) for component in pos):
                    continue
                self.drones[idx].desired_position = pos
                applied[f"drone_{idx}"] = [round(v, 3) for v in pos]
            self.last_algorithm_decision = {
                "accepted": not bool(msg.fallback),
                "fallback": bool(msg.fallback),
                "action_id": str(msg.action_id),
                "source_revision_id": str(msg.source_revision_id),
                "objective_value": float(msg.objective_value),
                "termination_reason": str(msg.termination_reason),
                "positions": applied,
            }
            if applied:
                self._emit_event("algorithm_action_applied", {"strategy": self.strategy_id, **self.last_algorithm_decision})
                self._publish_algorithm_status("APPLIED" if not msg.fallback else "FALLBACK_APPLIED", self.last_algorithm_decision)
            elif msg.fallback:
                self._emit_event("algorithm_fallback_hold", {"strategy": self.strategy_id, "action_id": msg.action_id})
                self._publish_algorithm_status("FALLBACK_APPLIED", self.last_algorithm_decision)
        except Exception as exc:
            self._emit_event("algorithm_action_callback_failed", {"strategy": self.strategy_id, "error": str(exc)})
            self._publish_algorithm_status("FAILED", {"error": str(exc)})

    def _strategy_call(self, hook: str, *args: Any) -> Any:
        if self.strategy_package is not None and self.strategy_id:
            observation = self._canonical_algorithm_observation()
            invocation = self.algorithm_runtime.invoke(self.strategy_id, observation, self.strategy_parameters, hook=hook)
            if not invocation.get("ok"):
                self._emit_event("algorithm_invocation_failed", {"strategy": self.strategy_id, "hook": hook, "error": invocation.get("error"), "stderr": invocation.get("stderr", "")})
                self._publish_algorithm_status("FAILED", {"hook": hook, "error": invocation.get("error")})
                return None
            if invocation.get("pending_external_ros2"):
                self._publish_algorithm_status("PENDING_EXTERNAL_ROS2", invocation.get("result", {}))
                return None
            return invocation.get("result")
        module = self.strategy_module
        if module is None or not hasattr(module, hook):
            return None
        try:
            return getattr(module, hook)(*args)
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warning(f"Strategy {self.strategy_id}.{hook} failed: {exc}")
            self._emit_event("strategy_hook_failed", {"strategy": self.strategy_id, "hook": hook, "error": str(exc)})
            return None

    def _apply_strategy_position_plan(self, reason: str) -> bool:
        if self.strategy_package is not None and self.strategy_id:
            if self.algorithm_bridge_mode == "typed":
                return self._publish_typed_algorithm_observation(reason)
            observation = self._canonical_algorithm_observation()
            invocation = self.algorithm_runtime.invoke(self.strategy_id, observation, self.strategy_parameters, hook="step")
            if not invocation.get("ok") or invocation.get("pending_external_ros2"):
                self._emit_event("algorithm_action_unavailable", {"strategy": self.strategy_id, "reason": reason, "invocation": invocation})
                self._publish_algorithm_status("FAILED", {"reason": reason, "invocation": invocation})
                return False
            try:
                raw = invocation.get("result", {})
                if not isinstance(raw, dict):
                    raw = {"metrics": {"result": raw}}
                action = AlgorithmAction.from_mapping(
                    raw,
                    manifest=self.strategy_package.manifest,
                    source_revision_id=str(observation.get("revision_id", "runtime-current")),
                    duration_s=float(invocation.get("duration_s", 0.0)),
                )
                canonical = load_experiment(Path(self.config_path))
                decision = apply_safety_shield(
                    action,
                    observation,
                    canonical,
                    project=True,
                    require_connectivity=bool(canonical.get("swarm", {}).get("controller", {}).get("connectivity_preservation", True)),
                )
                self.last_algorithm_decision = decision.to_dict()
                self._publish_algorithm_status("ACTION_ACCEPTED" if decision.accepted else "ACTION_REJECTED", self.last_algorithm_decision)
                if not decision.accepted:
                    self._emit_event("algorithm_output_rejected", {"strategy": self.strategy_id, "reason": reason, "shield": self.last_algorithm_decision})
                    return False
                plan = decision.action.get("payload", {}).get("desired_positions", {})
            except Exception as exc:
                self._emit_event("algorithm_action_validation_failed", {"strategy": self.strategy_id, "reason": reason, "error": str(exc)})
                self._publish_algorithm_status("FAILED", {"error": str(exc)})
                return False
        else:
            plan = self._strategy_call("plan_positions", self._strategy_context())
        if not isinstance(plan, dict) or not plan:
            return False
        applied: Dict[str, List[float]] = {}
        active_relays = set(self._active_chain())
        for key, value in plan.items():
            idx = self._parse_drone_index(key)
            if idx is None or idx not in active_relays or idx in self.failed_indices:
                continue
            try:
                vec = list(value)
                if len(vec) < 3:
                    continue
                pos = (float(vec[0]), float(vec[1]), float(vec[2]))
                if not all(math.isfinite(v) for v in pos):
                    continue
                self.drones[idx].desired_position = pos
                applied[f"drone_{idx}"] = [round(v, 3) for v in pos]
            except Exception:
                continue
        if applied:
            self._emit_event("strategy_position_plan_applied", {"strategy": self.strategy_id, "reason": reason, "positions": applied, "shield": self.last_algorithm_decision})
            self._publish_algorithm_status("APPLIED", {"reason": reason, "positions": applied})
        return bool(applied)

    def _strategy_selected_standby(self, failed_index: int, standby: List[int]) -> Optional[int]:
        if not standby or (self.strategy_module is None and self.strategy_package is None):
            return None
        context = self._canonical_algorithm_observation() if self.strategy_package is not None else self._strategy_context()
        for hook, args in (("on_failure", (context, failed_index)), ("select_standby", (context,))):
            selected = self._strategy_call(hook, *args)
            if isinstance(selected, dict):
                selected = selected.get("standby_selection", selected.get("replacement_drone", selected.get("selected")))
            idx = self._parse_drone_index(selected)
            if idx in standby:
                self._emit_event("strategy_standby_selected", {"strategy": self.strategy_id, "hook": hook, "failed_drone": failed_index, "replacement_drone": idx})
                return idx
        return None

    # ---------- topology ----------
    def _active_chain(self) -> List[int]:
        # The authoritative mission inventory is [1..drone_count].  Filtering by
        # that range prevents stale UAVs from reappearing after a live reduction.
        return [
            idx
            for idx in sorted(self.drones)
            if 1 <= idx <= self.drone_count
            and idx not in self.failed_indices
            and self.drones[idx].integrated
            and self.drones[idx].role != "standby"
        ]

    def _standby_indices(self) -> List[int]:
        return [
            idx
            for idx in sorted(self.drones)
            if 1 <= idx <= self.drone_count
            and idx not in self.failed_indices
            and (not self.drones[idx].integrated or self.drones[idx].role == "standby")
        ]

    def _sync_drone_inventory(self, requested_count: int, relay_count: Optional[int] = None, drone_specs: Optional[List[Dict[str, Any]]] = None) -> List[int]:
        """Synchronize the runtime inventory with the requested mission size.

        This is intentionally strict: drones with index > requested_count are removed
        from the active runtime state. Isaac then receives a status payload without
        those drones and deletes their visuals. Keeping old drones around was the
        root cause of the UI bug where reducing the swarm size did not actually
        remove UAVs from the experiment.
        """
        requested_count = max(1, int(requested_count))
        relay_limit = max(1, min(requested_count, int(relay_count if relay_count is not None else min(self.relay_count_hint, requested_count))))
        specs_by_index: Dict[int, Dict[str, Any]] = {}
        if isinstance(drone_specs, list):
            for item in drone_specs:
                if not isinstance(item, dict):
                    continue
                idx = _as_int(item.get("index", item.get("id", "0").split("_")[-1] if isinstance(item.get("id"), str) else 0), 0)
                if 1 <= idx <= requested_count:
                    specs_by_index[idx] = item

        removed = [idx for idx in sorted(self.drones) if idx > requested_count]
        for idx in removed:
            self.drones.pop(idx, None)
            self.failed_indices.discard(idx)
            pubs = self.drone_publishers.pop(idx, {})
            for pub in pubs.values():
                try:
                    self.destroy_publisher(pub)
                except Exception:
                    pass
        if self.pending_failure and self.pending_failure.drone_index > requested_count:
            self.pending_failure = None

        self.drone_count = requested_count
        self.relay_count_hint = relay_limit
        self.standby_count_hint = max(0, requested_count - relay_limit)
        self.relay_count = relay_limit
        self.standby_count = max(0, requested_count - relay_limit)
        for index in range(1, requested_count + 1):
            spec = dict(specs_by_index.get(index, {}))
            spec.setdefault("role", "relay" if index <= relay_limit else "standby")
            self._ensure_drone(index, spec)
            drone = self.drones[index]
            if spec.get("id"):
                drone.drone_id = str(spec.get("id"))
            if isinstance(spec.get("position"), list) and len(spec.get("position", [])) >= 3:
                try:
                    pos = tuple(float(v) for v in spec.get("position", [])[:3])  # type: ignore[assignment]
                    drone.initial_position = pos
                    drone.desired_position = pos
                    # When Isaac has not yet published a pose, make the runtime state
                    # match the newly saved mission immediately. Once live poses arrive,
                    # Isaac remains the source of smooth visual motion.
                    if not drone.last_pose_time:
                        drone.current_position = pos
                except Exception:
                    pass
            if "antenna_gain_dbi" in spec:
                drone.antenna_gain_dbi = _as_float(spec.get("antenna_gain_dbi"), drone.antenna_gain_dbi)
            if "antenna_name" in spec:
                drone.antenna_name = str(spec.get("antenna_name"))
            if "battery_pct" in spec:
                drone.battery_pct = max(0.0, min(100.0, _as_float(spec.get("battery_pct"), drone.battery_pct)))
            role = str(spec.get("role", "relay" if index <= relay_limit else "standby")).lower()
            if role not in {"relay", "standby"}:
                role = "relay"
            explicit_failed = _as_bool(spec.get("failed"), index in self.failed_indices)
            if explicit_failed:
                self.failed_indices.add(index)
            else:
                self.failed_indices.discard(index)
            drone.failed = explicit_failed
            drone.role = role
            drone.integrated = bool(spec.get("active", True)) and (role != "standby") and (not drone.failed)
        self.last_removed_indices = removed
        if removed:
            self._emit_event("drone_inventory_pruned", {"removed_indices": removed, "requested_drone_count": requested_count, "relay_count": relay_limit})
        return removed

    def _sanitize_manual_branches(self, branches: Any, filter_failed: bool = True) -> List[List[int]]:
        if not isinstance(branches, list):
            return []
        visible = set(range(1, int(getattr(self, "drone_count", 0)) + 1))
        failed = set(getattr(self, "failed_indices", set())) if filter_failed else set()
        standby = set()
        try:
            standby = set(self._standby_indices()) if filter_failed else set()
        except Exception:
            standby = set()
        seen: set[int] = set()
        clean: List[List[int]] = []
        for branch in branches:
            if not isinstance(branch, list):
                continue
            row: List[int] = []
            for value in branch:
                try:
                    idx = int(value)
                except Exception:
                    continue
                if idx not in visible or idx in failed or idx in standby or idx in seen:
                    continue
                row.append(idx)
                seen.add(idx)
            if row:
                clean.append(row)
        return clean

    def _active_branches(self) -> List[List[int]]:
        active = self._active_chain()
        if not active:
            return []
        active_set = set(active)
        if self.transmission_mode == "manual" and self.manual_branches:
            manual = []
            used: set[int] = set()
            for branch in self._sanitize_manual_branches(self.manual_branches, filter_failed=True):
                row = [idx for idx in branch if idx in active_set and idx not in used]
                if row:
                    manual.append(row)
                    used.update(row)
            leftovers = [idx for idx in active if idx not in used]
            if leftovers:
                if manual:
                    for pos, idx in enumerate(leftovers):
                        manual[pos % len(manual)].append(idx)
                else:
                    manual = [leftovers]
            return manual
        if self.transmission_mode == "chain":
            return [active]
        branch_count = max(1, min(self.branch_count, len(active)))
        branches: List[List[int]] = [[] for _ in range(branch_count)]
        for pos, idx in enumerate(active):
            branches[pos % branch_count].append(idx)
        return [branch for branch in branches if branch]

    def _current_branch(self) -> List[int]:
        branches = self._active_branches()
        if not branches:
            return []
        self.current_branch_index %= len(branches)
        return branches[self.current_branch_index]

    def _chain_nodes(self, phase: str) -> List[str]:
        branch = self._current_branch()
        if phase == "forward":
            return ["station"] + [f"drone_{i}" for i in branch]
        return [f"drone_{i}" for i in reversed(branch)] + ["station"]

    def _branch_nodes(self, branch: List[int], phase: str) -> List[str]:
        if phase == "forward":
            return ["station"] + [f"drone_{i}" for i in branch]
        return [f"drone_{i}" for i in reversed(branch)] + ["station"]

    def _parallel_enabled(self) -> bool:
        return self.transmission_mode in {"parallel", "forest", "manual"} and len(self._active_branches()) > 1

    def _sync_branch_flow_state(self) -> List[Dict[str, Any]]:
        branches = self._active_branches()
        active_ids = set(range(len(branches)))
        for old in list(getattr(self, "branch_flow_state", {})):
            if old not in active_ids:
                self.branch_flow_state.pop(old, None)
        for branch_id, branch in enumerate(branches):
            flow = self.branch_flow_state.get(branch_id)
            if not isinstance(flow, dict):
                previous_branch = []
                flow = {}
            else:
                previous_branch = list(flow.get("active_branch", []))
            if previous_branch != branch or not flow:
                flow.update({
                    "branch_id": branch_id,
                    "active_branch": list(branch),
                    "phase": "forward",
                    "cursor": 0,
                    "packet": self._new_packet(),
                    "paused": False,
                    "pause_reason": "",
                    "paused_hop": {},
                    "last_hop": {},
                    "completed_round_trips": 0,
                })
                flow["packet"]["branch_id"] = branch_id
                self.branch_flow_state[branch_id] = flow
        return [self.branch_flow_state[i] for i in sorted(self.branch_flow_state)]

    def _flow_status(self) -> List[Dict[str, Any]]:
        flows: List[Dict[str, Any]] = []
        for flow in self._sync_branch_flow_state():
            branch = list(flow.get("active_branch", []))
            nodes = self._branch_nodes(branch, str(flow.get("phase", "forward"))) if branch else []
            cursor = int(flow.get("cursor", 0) or 0)
            current_hop = {}
            if nodes and cursor < len(nodes) - 1:
                current_hop = {"src": nodes[cursor], "dst": nodes[cursor + 1]}
            flows.append({
                "branch_id": int(flow.get("branch_id", 0)),
                "branch_label": f"B{int(flow.get('branch_id', 0)) + 1}",
                "transmission_mode": self.transmission_mode,
                "packet_id": flow.get("packet", {}).get("packet_id"),
                "phase": flow.get("phase", "forward"),
                "cursor": cursor,
                "paused": bool(flow.get("paused", False)),
                "pause_reason": flow.get("pause_reason", ""),
                "active_branch": branch,
                "nodes": nodes,
                "current_hop": current_hop,
                "last_hop": flow.get("last_hop", {}),
                "completed_round_trips": int(flow.get("completed_round_trips", 0) or 0),
                "description": "independent branch packet stream",
            })
        return flows

    def _node_position(self, node_id: str) -> Vec3:
        if node_id == "station":
            return self.station_position  # type: ignore[return-value]
        index = int(node_id.split("_")[-1])
        return self.drones[index].current_position

    def _node_antenna(self, node_id: str) -> Tuple[str, float]:
        if node_id == "station":
            return self.station_antenna_name, self.station_antenna_gain_dbi
        drone = self.drones[int(node_id.split("_")[-1])]
        return drone.antenna_name, drone.antenna_gain_dbi

    def _node_failed(self, node_id: str) -> bool:
        if node_id == "station":
            return False
        return int(node_id.split("_")[-1]) in self.failed_indices

    def _clear_connectivity_pause(self, reason: str) -> None:
        if self.connectivity_paused:
            self._emit_event("connectivity_resume", {"reason": reason, "paused_hop": self.paused_hop})
        self.connectivity_paused = False
        self.connectivity_pause_reason = ""
        self.paused_hop = {}
        for flow in getattr(self, "branch_flow_state", {}).values():
            if isinstance(flow, dict):
                flow["paused"] = False
                flow["pause_reason"] = ""
                flow["paused_hop"] = {}

    def _recompute_desired_positions(self, reason: str, reset_packet: bool = True) -> None:
        branches = self._active_branches()
        theta = math.radians(self.direction_deg)
        dx, dy = math.cos(theta), math.sin(theta)
        px, py = -dy, dx
        branch_count = max(1, len(branches))
        feasible = True
        max_spacing = 0.0
        for branch_idx, branch in enumerate(branches):
            if not branch:
                continue
            # Keep the last drone near the requested range when possible.
            spacing = self.coverage_radius_m / max(1, len(branch))
            max_spacing = max(max_spacing, spacing)
            if spacing > self.max_single_hop_range_m:
                feasible = False
            lateral_offset = 0.0 if branch_count == 1 else ((branch_idx - (branch_count - 1) / 2.0) * (self.coverage_width_m / max(1, branch_count - 1)))
            for slot_idx, drone_index in enumerate(branch, start=1):
                along = spacing * slot_idx
                alpha = (slot_idx - 1) / max(1, len(branch) - 1)
                z = self.altitude_start_m + (self.altitude_end_m - self.altitude_start_m) * alpha
                self.drones[drone_index].desired_position = (
                    self.station_position[0] + dx * along + px * lateral_offset,
                    self.station_position[1] + dy * along + py * lateral_offset,
                    z,
                )
                self.drones[drone_index].last_seen_chain_version = self.chain_version
        for failed_index in self.failed_indices:
            if failed_index in self.drones:
                pos = self.drones[failed_index].current_position
                self.drones[failed_index].desired_position = (pos[0], pos[1], max(0.3, pos[2] - 4.0))
        for standby_index in self._standby_indices():
            drone = self.drones[standby_index]
            # Place standby drones near the side of the coverage region until integrated.
            pos = drone.current_position
            if pos == drone.initial_position:
                drone.desired_position = drone.initial_position
        strategy_applied = self._apply_strategy_position_plan(reason)
        self.coverage_feasible = feasible
        self.coverage_note = "coverage_target_preserved" if feasible else f"requested_range_exceeds_hop_capacity:max_spacing={max_spacing:.2f}m,max_hop={self.max_single_hop_range_m:.2f}m"
        if strategy_applied:
            self.coverage_note += f";strategy={self.strategy_id}"
        if reset_packet:
            self._clear_connectivity_pause(reason)
            self.chain_version += 1
            self.phase = "forward"
            self.cursor = 0
            self.current_branch_index = 0
            self.current_packet = self._new_packet()
        standby_indices = self._standby_indices()
        self._emit_event(
            "topology_recomputed",
            {
                "reason": reason,
                "active_branches": branches,
                "standby_indices": standby_indices,
                "coverage_feasible": self.coverage_feasible,
                "coverage_note": self.coverage_note,
                "desired_positions": self._desired_positions_payload(),
            },
        )

    def _integrate_standby_if_possible(self) -> None:
        active = self._active_chain()
        if not active:
            return
        changed = False
        for idx in self._standby_indices():
            drone = self.drones[idx]
            nearest = min(active, key=lambda j: _distance(drone.current_position, self.drones[j].current_position))
            dist = _distance(drone.current_position, self.drones[nearest].current_position)
            if dist <= self.standby_activation_radius_m:
                drone.role = "relay"
                drone.integrated = True
                changed = True
                self._emit_event(
                    "standby_drone_integrated",
                    {"drone": idx, "nearest_active_drone": nearest, "distance_m": round(dist, 3)},
                )
        if changed:
            self._recompute_desired_positions(reason="standby_auto_integration")

    # ---------- radio ----------
    def _query_sionna(self, src: str, dst: str) -> Dict[str, Any]:
        tx = self._node_position(src)
        rx = self._node_position(dst)
        tx_ant, tx_gain = self._node_antenna(src)
        rx_ant, rx_gain = self._node_antenna(dst)
        payload = {
            "tx": list(tx),
            "rx": list(rx),
            "frequency_hz": self.frequency_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "tx_power_dbm": self.tx_power_dbm,
            "noise_floor_dbm": self.noise_floor_dbm,
            "tx_antenna_gain_dbi": tx_gain,
            "rx_antenna_gain_dbi": rx_gain,
            "tx_antenna": tx_ant,
            "rx_antenna": rx_ant,
            "model": str(self.config.get("communication_model", "sionna_analytical")),
            "operational_range_m": self.max_single_hop_range_m,
            "hard_outage_distance_m": self.hard_outage_range_m,
            "min_snr_db": self.min_snr_db,
            "min_sinr_db": self.min_snr_db,
            "min_capacity_mbps": self.required_capacity_mbps,
            "allow_fallback": True,
        }
        encoded = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.sionna_url,
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=0.75) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        if not response_payload.get("ok", False):
            raise RuntimeError(response_payload.get("error", "unknown Sionna error"))
        metrics = dict(response_payload.get("metrics", {}))
        metrics.update(
            {
                "tx_antenna": tx_ant,
                "rx_antenna": rx_ant,
                "tx_antenna_gain_dbi": tx_gain,
                "rx_antenna_gain_dbi": rx_gain,
                "antenna_model": self.radio_metadata["antenna_model"],
                "frequency_hz": self.frequency_hz,
                "bandwidth_hz": self.bandwidth_hz,
                "tx_power_dbm": self.tx_power_dbm,
                "noise_floor_dbm": self.noise_floor_dbm,
                "sionna_service_url": self.sionna_url,
                "link_name": f"{src}->{dst}",
            }
        )
        if "distance_m" not in metrics:
            metrics["distance_m"] = _distance(tx, rx)
        distance_m = float(metrics.get("distance_m", _distance(tx, rx)))
        metrics["max_single_hop_range_m"] = self.max_single_hop_range_m
        metrics["hard_outage_range_m"] = self.hard_outage_range_m
        metrics["range_margin_m"] = round(self.max_single_hop_range_m - distance_m, 3)
        metrics["hard_range_margin_m"] = round(self.hard_outage_range_m - distance_m, 3)

        # Protocol-consistent range model:
        #   - max_single_hop_range_m is the actual coverage/communication radius used
        #     by the relay protocol and by the Isaac coverage rings.
        #   - By default, packets MUST NOT move past this radius. This avoids the
        #     previous inconsistency where the dashboard showed an out-of-range link
        #     while terminal logs still emitted TX/RX events.
        #   - allow_degraded_forwarding is kept as an explicit research toggle, but
        #     it is disabled by default for the paper demo.
        if distance_m > self.max_single_hop_range_m:
            excess_m = distance_m - self.max_single_hop_range_m
            penalty_db = excess_m * self.distance_penalty_db_per_m_after_soft_range
            metrics["distance_penalty_db"] = round(penalty_db, 3)
            try:
                metrics["path_loss_db"] = round(float(metrics.get("path_loss_db", 0.0)) + penalty_db, 3)
            except Exception:
                pass
            try:
                degraded_snr = float(metrics.get("snr_db", -999.0)) - penalty_db
                metrics["snr_db"] = round(degraded_snr, 3)
                snr_linear = max(0.0, 10.0 ** (degraded_snr / 10.0))
                metrics["capacity_mbps"] = round((self.bandwidth_hz * math.log2(1.0 + snr_linear)) / 1e6, 3)
            except Exception:
                pass
            metrics["status"] = "outage_distance_exceeded" if not self.allow_degraded_forwarding else "degraded_distance_exceeds_nominal_range"
            metrics["outage_reason"] = "distance_exceeds_communication_radius"
            metrics["link_budget_ok"] = bool(self.allow_degraded_forwarding)
        else:
            metrics["link_budget_ok"] = True

        if distance_m > self.hard_outage_range_m:
            metrics["status"] = "outage_distance_exceeded"
            metrics["outage_reason"] = "distance_exceeds_hard_outage_range"
            metrics["link_budget_ok"] = False
        return metrics

    def _gate_reason(self, metrics: Dict[str, Any]) -> str:
        """Return the authoritative per-hop gate reason used by packet advancement."""
        try:
            feasibility = metrics.get("feasibility", {}) if isinstance(metrics.get("feasibility", {}), dict) else {}
            service_reason = str(feasibility.get("reason", metrics.get("gate_reason", ""))).strip().upper()
            if service_reason and service_reason not in {"UNKNOWN", "NONE"}:
                return service_reason
            status = str(metrics.get("status", "")).lower()
            if status in {"sionna_unreachable", "link_service_unavailable"}:
                return "LINK_SERVICE_UNAVAILABLE"
            distance_m = float(metrics.get("distance_m", 0.0))
            if distance_m > self.hard_outage_range_m:
                return "HARD_OUTAGE_DISTANCE"
            if distance_m > self.max_single_hop_range_m and not self.allow_degraded_forwarding:
                return "OUT_OF_RANGE"
            sinr = metrics.get("sinr_db")
            if sinr is not None and float(sinr) < self.min_snr_db:
                return "SINR_BELOW_THRESHOLD"
            if float(metrics.get("snr_db", -999.0)) < self.min_snr_db:
                return "SNR_BELOW_THRESHOLD"
            if float(metrics.get("capacity_mbps", 0.0)) < self.required_capacity_mbps:
                return "CAPACITY_BELOW_THRESHOLD"
            return "FEASIBLE"
        except Exception:
            return "UNKNOWN"

    def _annotate_gate(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        reason = self._gate_reason(metrics)
        distance_m = float(metrics.get("distance_m", 0.0) or 0.0)
        snr_db = float(metrics.get("snr_db", -999.0) or -999.0)
        capacity_mbps = float(metrics.get("capacity_mbps", 0.0) or 0.0)
        metrics["gate_reason"] = reason
        metrics["range_margin_m"] = round(self.max_single_hop_range_m - distance_m, 6)
        metrics["hard_range_margin_m"] = round(self.hard_outage_range_m - distance_m, 6)
        metrics["snr_margin_db"] = round(snr_db - self.min_snr_db, 6)
        metrics["capacity_margin_mbps"] = round(capacity_mbps - self.required_capacity_mbps, 6)
        metrics["gate_predicates"] = {
            "range": distance_m <= self.max_single_hop_range_m or self.allow_degraded_forwarding,
            "hard_outage": distance_m <= self.hard_outage_range_m,
            "snr": snr_db >= self.min_snr_db,
            "capacity": capacity_mbps >= self.required_capacity_mbps,
        }
        metrics["link_budget_ok"] = reason == "FEASIBLE"
        return metrics

    def _link_ok(self, metrics: Dict[str, Any]) -> bool:
        self._annotate_gate(metrics)
        return str(metrics.get("gate_reason", "UNKNOWN")) == "FEASIBLE"

    # ---------- packet ----------
    def _new_packet(self) -> Dict[str, Any]:
        self.packet_id += 1
        return {
            "packet_id": self.packet_id,
            "created_at": _now(),
            "origin": "station",
            "mission": "SNaaS relay-chain coverage service",
            "payload": self.config.get("message", {}).get("payload", "Maintain relay service and report local state."),
            "payload_bytes": _as_int(self.config.get("message", {}).get("payload_bytes"), 512),
            "forward_trace": [],
            "reverse_trace": [],
            "states": {},
            "chain_version": self.chain_version,
            "branch_id": self.current_branch_index,
        }

    def _append_local_state(self, packet: Dict[str, Any], node_id: str) -> None:
        if node_id == "station":
            return
        index = int(node_id.split("_")[-1])
        drone = self.drones[index]
        drone.battery_pct = max(0.0, drone.battery_pct - 0.02)
        packet["states"][node_id] = {
            "appended_at": _now(),
            "position": [round(v, 3) for v in drone.current_position],
            "desired_position": [round(v, 3) for v in drone.desired_position],
            "battery_pct": round(drone.battery_pct, 3),
            "role": drone.role,
            "failed": drone.failed,
            "integrated": drone.integrated,
            "antenna_name": drone.antenna_name,
            "antenna_gain_dbi": drone.antenna_gain_dbi,
            "chain_version": self.chain_version,
            "branch_id": self.current_branch_index,
        }

    def _make_hop_event(self, src: str, dst: str, metrics: Dict[str, Any], link_ok: bool, decision: str) -> Dict[str, Any]:
        active_chain = self._active_chain()
        standby_indices = self._standby_indices()
        return {
            "timestamp": _now(),
            "sequence": self.sequence,
            "chain_version": self.chain_version,
            "branch_id": self.current_branch_index,
            "packet_id": self.current_packet["packet_id"],
            "phase": self.phase,
            "direction": self.phase,
            "src": src,
            "dst": dst,
            "active_chain": active_chain,
            "active_branches": self._active_branches(),
            "standby_indices": standby_indices,
            "failed_indices": sorted(self.failed_indices),
            "coverage_radius_m": self.coverage_radius_m,
            "coverage_width_m": self.coverage_width_m,
            "coverage_feasible": self.coverage_feasible,
            "coverage_note": self.coverage_note,
            "connectivity_paused": self.connectivity_paused,
            "connectivity_pause_reason": self.connectivity_pause_reason,
            "paused_hop": self.paused_hop,
            "movement_pattern": self.movement_pattern,
            "src_position": [round(v, 3) for v in self._node_position(src)],
            "dst_position": [round(v, 3) for v in self._node_position(dst)],
            "packet": self.current_packet,
            "metrics": metrics,
            "link_ok": bool(link_ok),
            "link_status": metrics.get("status", "unknown"),
            "decision": decision,
            "hop_period_s": self.hop_period_s,
        }

    def _publish_hop(self, hop_payload: Dict[str, Any]) -> None:
        self._publish_json(self.event_pub, {"event_type": "hop", **hop_payload})
        self._publish_json(self.link_pub, {"event_type": "link_metrics", **hop_payload})
        self.evidence.write_event({"event_type": "hop", **hop_payload})
        self.evidence.write_metrics(hop_payload)

    def _publish_terminal(self, index: int, payload: Dict[str, Any]) -> None:
        if index not in self.drone_publishers:
            return
        self._publish_json(self.drone_publishers[index]["terminal"], payload)
        metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics", {}), dict) else {}
        self.get_logger().info(
            f"[DRONE {index}] {payload.get('terminal_event')} {payload.get('direction', '?').upper()} "
            f"src={payload.get('src')} dst={payload.get('dst')} packet={payload.get('packet_id')} "
            f"branch={payload.get('branch_id')} link={payload.get('link_status')} "
            f"snr={metrics.get('snr_db', 'n/a')} cap={metrics.get('capacity_mbps', 'n/a')} "
            f"txAnt={metrics.get('tx_antenna', 'n/a')} rxAnt={metrics.get('rx_antenna', 'n/a')} "
            f"decision={payload.get('decision')}"
        )

    def _send_to_node_inbox(self, node_id: str, payload: Dict[str, Any]) -> None:
        terminal_payload = dict(payload)
        terminal_payload["terminal_event"] = "RX"
        terminal_payload["local_node"] = node_id
        terminal_payload["peer_node"] = payload.get("src")
        terminal_payload["terminal_message"] = f"RX packet {payload.get('packet_id')} from {payload.get('src')} during {payload.get('phase')}"
        if node_id == "station":
            self._publish_json(self.station_inbox_pub, terminal_payload)
            return
        index = int(node_id.split("_")[-1])
        self._publish_json(self.drone_publishers[index]["inbox"], terminal_payload)
        self._publish_terminal(index, terminal_payload)

    def _send_from_node_outbox(self, node_id: str, payload: Dict[str, Any]) -> None:
        terminal_payload = dict(payload)
        terminal_payload["terminal_event"] = "TX"
        terminal_payload["local_node"] = node_id
        terminal_payload["peer_node"] = payload.get("dst")
        terminal_payload["terminal_message"] = f"TX packet {payload.get('packet_id')} to {payload.get('dst')} during {payload.get('phase')}"
        if node_id == "station":
            self._publish_json(self.station_outbox_pub, terminal_payload)
            return
        index = int(node_id.split("_")[-1])
        self._publish_json(self.drone_publishers[index]["outbox"], terminal_payload)
        self._publish_terminal(index, terminal_payload)

    def _tick_parallel(self) -> None:
        """Advance every active branch as an independent packet stream.

        This is the V4 semantic correction: parallel/forest/manual topologies are
        no longer visualized as one chain packet jumping branch-by-branch. Each
        branch owns its packet, cursor and phase, so Isaac and the dashboard can
        show concurrent branch-level transmissions.
        """
        flows = self._sync_branch_flow_state()
        if not flows:
            self._emit_event("no_active_parallel_relay_path", {"failed_indices": sorted(self.failed_indices), "standby_indices": self._standby_indices()})
            return
        any_blocked = False
        active_unpaused = 0
        for flow in flows:
            branch_id = int(flow.get("branch_id", 0))
            branch = list(flow.get("active_branch", []))
            if not branch:
                continue
            if bool(flow.get("paused", False)):
                any_blocked = True
                continue
            active_unpaused += 1
            phase = str(flow.get("phase", "forward"))
            nodes = self._branch_nodes(branch, phase)
            cursor = int(flow.get("cursor", 0) or 0)
            if cursor >= len(nodes) - 1:
                if phase == "forward":
                    phase = "reverse"
                    cursor = 0
                    nodes = self._branch_nodes(branch, phase)
                    flow["phase"] = phase
                    flow["cursor"] = cursor
                    self._emit_event("parallel_reverse_path_started", {"branch_id": branch_id, "branch": branch, "packet_id": flow.get("packet", {}).get("packet_id")})
                else:
                    self._emit_event("parallel_round_trip_completed", {"branch_id": branch_id, "branch": branch, "packet_id": flow.get("packet", {}).get("packet_id"), "forward_trace": flow.get("packet", {}).get("forward_trace", []), "reverse_trace": flow.get("packet", {}).get("reverse_trace", [])})
                    flow["completed_round_trips"] = int(flow.get("completed_round_trips", 0) or 0) + 1
                    flow["phase"] = "forward"
                    flow["cursor"] = 0
                    flow["packet"] = self._new_packet()
                    flow["packet"]["branch_id"] = branch_id
                    phase = "forward"
                    cursor = 0
                    nodes = self._branch_nodes(branch, phase)
            if len(nodes) < 2:
                continue
            src = nodes[cursor]
            dst = nodes[cursor + 1]
            self.current_branch_index = branch_id
            self.phase = phase
            self.cursor = cursor
            self.current_packet = flow.get("packet") if isinstance(flow.get("packet"), dict) else self._new_packet()
            self.current_packet["branch_id"] = branch_id
            self.sequence += 1
            if self._node_failed(src) or self._node_failed(dst):
                failed_node = src if self._node_failed(src) else dst
                metrics = {"status": "relay_failed", "distance_m": _distance(self._node_position(src), self._node_position(dst)), "tx_antenna": self._node_antenna(src)[0], "rx_antenna": self._node_antenna(dst)[0]}
                hop_payload = self._make_hop_event(src, dst, metrics, False, "blocked_failed_relay")
                hop_payload["parallel_stream"] = True
                flow["last_hop"] = hop_payload
                flow["paused"] = True
                flow["pause_reason"] = "blocked_failed_relay"
                flow["paused_hop"] = hop_payload
                any_blocked = True
                self.last_hop_event = hop_payload
                self._publish_hop(hop_payload)
                self._emit_event("parallel_branch_paused", {"failed_node": failed_node, "branch_id": branch_id, "branch": branch, "src": src, "dst": dst, "packet_id": self.current_packet.get("packet_id"), "protocol_action": "branch_paused_other_branches_continue"})
                continue
            try:
                metrics = self._query_sionna(src, dst)
            except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
                metrics = {"timestamp": _now(), "engine": "netlab-link-service", "status": "sionna_unreachable", "gate_reason": "LINK_SERVICE_UNAVAILABLE", "error": str(exc), "distance_m": _distance(self._node_position(src), self._node_position(dst)), "tx_antenna": self._node_antenna(src)[0], "rx_antenna": self._node_antenna(dst)[0], "antenna_model": self.radio_metadata["antenna_model"]}
            link_ok = self._link_ok(metrics)
            distance_m = float(metrics.get("distance_m", 0.0)) if isinstance(metrics, dict) else 0.0
            if link_ok:
                decision = "forwarded_degraded_distance" if distance_m > self.max_single_hop_range_m else "forwarded"
            elif distance_m > self.hard_outage_range_m:
                decision = "blocked_out_of_hard_range"
            elif distance_m > self.max_single_hop_range_m:
                decision = "blocked_out_of_range"
            else:
                decision = "blocked_link_degraded"
            hop_payload = self._make_hop_event(src, dst, metrics, link_ok, decision)
            hop_payload["parallel_stream"] = True
            hop_payload["branch_packet_id"] = self.current_packet.get("packet_id")
            flow["last_hop"] = hop_payload
            self.last_hop_event = hop_payload
            self._publish_hop(hop_payload)
            if not link_ok:
                flow["paused"] = True
                flow["pause_reason"] = decision
                flow["paused_hop"] = hop_payload
                any_blocked = True
                self._emit_event("parallel_branch_connectivity_lost", {"branch_id": branch_id, "branch": branch, "src": src, "dst": dst, "distance_m": round(distance_m, 3), "decision": decision, "protocol_action": "branch_paused_other_branches_continue"})
                continue
            self._send_from_node_outbox(src, hop_payload)
            self._append_local_state(self.current_packet, src)
            trace_key = "forward_trace" if phase == "forward" else "reverse_trace"
            self.current_packet[trace_key].append({"src": src, "dst": dst, "at": _now(), "branch_id": branch_id})
            self._send_to_node_inbox(dst, hop_payload)
            flow["packet"] = self.current_packet
            flow["cursor"] = cursor + 1
        all_paused = bool(flows) and all(bool(f.get("paused", False)) for f in flows)
        self.connectivity_paused = all_paused
        self.connectivity_pause_reason = "all_parallel_branches_paused" if all_paused else ("one_or_more_parallel_branches_paused" if any_blocked else "")
        self.paused_hop = self.last_hop_event if all_paused else {}

    # ---------- main loop ----------
    def _tick(self) -> None:
        self._load_active_strategy()
        self._process_pending_failure()
        self._integrate_standby_if_possible()

        if self.operator_paused:
            # Operator hold/land/emergency modes pause packet execution explicitly.
            # Status and heartbeat timers continue so Mission Control can observe and acknowledge the state.
            return

        if self._parallel_enabled():
            self._tick_parallel()
            return

        if self.connectivity_paused:
            # Protocol correctness: no TX/RX should occur while the current hop is down.
            # Status continues to publish through the status timer so dashboards stay live.
            return

        nodes = self._chain_nodes(self.phase)
        if len(nodes) < 2:
            self._emit_event("no_active_relay_path", {"failed_indices": sorted(self.failed_indices), "standby_indices": self._standby_indices()})
            return

        if self.cursor >= len(nodes) - 1:
            if self.phase == "forward":
                self.phase = "reverse"
                self.cursor = 0
                nodes = self._chain_nodes(self.phase)
                self._emit_event("reverse_path_started", {"packet_id": self.current_packet["packet_id"], "branch_id": self.current_branch_index, "branch": self._current_branch()})
            else:
                self._emit_event(
                    "round_trip_completed",
                    {
                        "packet_id": self.current_packet["packet_id"],
                        "branch_id": self.current_branch_index,
                        "forward_trace": self.current_packet.get("forward_trace", []),
                        "reverse_trace": self.current_packet.get("reverse_trace", []),
                        "states_seen": sorted(self.current_packet.get("states", {}).keys()),
                    },
                )
                branches = self._active_branches()
                if branches:
                    self.current_branch_index = (self.current_branch_index + 1) % len(branches)
                self.phase = "forward"
                self.cursor = 0
                self.current_packet = self._new_packet()
                nodes = self._chain_nodes(self.phase)

        src = nodes[self.cursor]
        dst = nodes[self.cursor + 1]
        self.sequence += 1

        if self._node_failed(src) or self._node_failed(dst):
            failed_node = src if self._node_failed(src) else dst
            metrics = {"status": "relay_failed", "distance_m": _distance(self._node_position(src), self._node_position(dst)), "tx_antenna": self._node_antenna(src)[0], "rx_antenna": self._node_antenna(dst)[0]}
            self.last_hop_event = self._make_hop_event(src, dst, metrics, False, "blocked_failed_relay")
            self._publish_hop(self.last_hop_event)
            self.connectivity_paused = True
            self.connectivity_pause_reason = "blocked_failed_relay"
            self.paused_hop = self.last_hop_event
            self._emit_event("relay_timeout_observed", {"failed_node": failed_node, "src": src, "dst": dst, "phase": self.phase, "packet_id": self.current_packet["packet_id"], "protocol_action": "relay_paused_no_tx_no_rx"})
            return

        try:
            metrics = self._query_sionna(src, dst)
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
            metrics = {
                "timestamp": _now(),
                "engine": "netlab-link-service",
                "status": "sionna_unreachable",
                "gate_reason": "LINK_SERVICE_UNAVAILABLE",
                "error": str(exc),
                "distance_m": _distance(self._node_position(src), self._node_position(dst)),
                "tx_antenna": self._node_antenna(src)[0],
                "rx_antenna": self._node_antenna(dst)[0],
                "antenna_model": self.radio_metadata["antenna_model"],
            }

        link_ok = self._link_ok(metrics)
        distance_m = float(metrics.get("distance_m", 0.0)) if isinstance(metrics, dict) else 0.0
        if link_ok:
            if distance_m > self.max_single_hop_range_m:
                decision = "forwarded_degraded_distance"
            else:
                decision = "forwarded"
        elif distance_m > self.hard_outage_range_m:
            decision = "blocked_out_of_hard_range"
        elif distance_m > self.max_single_hop_range_m:
            decision = "blocked_out_of_range"
        else:
            decision = "blocked_link_degraded"

        hop_payload = self._make_hop_event(src, dst, metrics, link_ok, decision)
        self.last_hop_event = hop_payload
        self._publish_hop(hop_payload)

        if not link_ok:
            # Do not publish TX/RX terminal events or advance the packet when the link is down.
            # The chain is explicitly paused at the failed hop until the operator changes
            # topology/range or resets/heals the network.
            self.connectivity_paused = True
            self.connectivity_pause_reason = decision
            self.paused_hop = hop_payload
            self._emit_event(
                "connectivity_lost",
                {
                    "src": src,
                    "dst": dst,
                    "distance_m": round(distance_m, 3),
                    "max_single_hop_range_m": self.max_single_hop_range_m,
                    "hard_outage_range_m": self.hard_outage_range_m,
                    "decision": decision,
                    "metrics": metrics,
                    "protocol_action": "relay_paused_no_tx_no_rx",
                },
            )
            return

        self._send_from_node_outbox(src, hop_payload)
        self._append_local_state(self.current_packet, src)
        trace_key = "forward_trace" if self.phase == "forward" else "reverse_trace"
        self.current_packet[trace_key].append({"src": src, "dst": dst, "at": _now(), "branch_id": self.current_branch_index})
        self._send_to_node_inbox(dst, hop_payload)
        self.cursor += 1

    # ---------- controls ----------
    def _fail_drone_cb(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            index = _as_int(payload.get("drone"), -1)
        except Exception:
            index = _as_int(msg.data.strip(), -1)
        if index not in self.drones:
            self._emit_event("invalid_failure_request", {"raw": msg.data, "known_drones": sorted(self.drones)})
            return
        if index in self.failed_indices or (self.pending_failure and self.pending_failure.drone_index == index):
            self._emit_event("duplicate_failure_request", {"drone": index})
            return
        deadline = _now() + self.failure_detection_s
        self.pending_failure = PendingFailure(index, _now(), deadline)
        self._emit_event("failure_injected", {"drone": index, "detection_deadline": deadline, "active_branches_before_detection": self._active_branches()})

    def _heal_drone_cb(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            index = _as_int(payload.get("drone"), -1)
        except Exception:
            index = _as_int(msg.data.strip(), -1)
        if index not in self.drones:
            self._emit_event("invalid_heal_request", {"raw": msg.data, "known_drones": sorted(self.drones)})
            return
        self.failed_indices.discard(index)
        self.drones[index].failed = False
        self.drones[index].integrated = True
        self.drones[index].role = "relay"
        self.pending_failure = None
        self._recompute_desired_positions(reason=f"drone_{index}_healed")

    def _standby_drone_cb(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
            index = _as_int(payload.get("drone"), -1)
        except Exception:
            index = _as_int(msg.data.strip(), -1)
        if index not in self.drones or index < 1 or index > self.drone_count:
            self._emit_event("invalid_standby_request", {"raw": msg.data, "known_visible_drones": self._visible_drone_indices()})
            return
        self.drones[index].role = "standby"
        self.drones[index].integrated = False
        self._recompute_desired_positions(reason=f"drone_{index}_set_standby")

    def _reset_chain_cb(self, msg: String) -> None:  # noqa: ARG002
        self.failed_indices.clear()
        for drone in self.drones.values():
            drone.failed = False
            if drone.role != "standby":
                drone.integrated = True
        self.pending_failure = None
        self._recompute_desired_positions(reason="chain_reset")

    def _mission_command_cb(self, msg: String) -> None:
        raw = msg.data.strip()
        command_id = ""
        try:
            payload = json.loads(raw)
            command = str(payload.get("command", "")).strip().lower()
            command_id = str(payload.get("command_id", ""))
        except Exception:
            command = raw.strip().lower()
            payload = {"command": command}

        aliases = {"pause": "hold", "rtl": "return_home", "stop": "emergency_stop"}
        command = aliases.get(command, command)
        if command not in {"takeoff", "hold", "resume", "land", "return_home", "emergency_stop", "stop_experiment"}:
            self._emit_event("invalid_mission_command", {"raw": raw, "command": command, "command_id": command_id})
            return

        self.last_mission_command = command
        self.last_mission_command_id = command_id
        if command == "resume":
            self.operator_paused = False
            self.mission_mode = "RUNNING"
        elif command == "takeoff":
            minimum_z = max(0.5, self.altitude_start_m)
            for drone in self.drones.values():
                x, y, z = drone.desired_position
                drone.desired_position = (x, y, max(z, minimum_z))
            self.operator_paused = False
            self.mission_mode = "TAKEOFF"
        elif command == "hold":
            for drone in self.drones.values():
                drone.desired_position = tuple(drone.current_position)
            self.operator_paused = True
            self.mission_mode = "HOLD"
        elif command == "land":
            for drone in self.drones.values():
                x, y, _ = drone.current_position
                drone.desired_position = (x, y, 0.3)
            self.operator_paused = True
            self.mission_mode = "LANDING"
        elif command == "return_home":
            for idx, drone in self.drones.items():
                drone.desired_position = tuple(self.home_positions.get(idx, drone.current_position))
            self.operator_paused = True
            self.mission_mode = "RETURN_HOME"
        elif command == "stop_experiment":
            self.operator_paused = True
            self.mission_mode = "COMPLETED"
        else:  # emergency_stop
            for drone in self.drones.values():
                drone.desired_position = tuple(drone.current_position)
            self.operator_paused = True
            self.mission_mode = "EMERGENCY_STOP"

        self._emit_event(
            "mission_command_applied",
            {
                "command": command,
                "command_id": command_id,
                "mission_mode": self.mission_mode,
                "operator_paused": self.operator_paused,
                "payload": payload,
            },
        )

    def _set_pattern_cb(self, msg: String) -> None:
        raw = msg.data.strip()
        amplitude = None
        speed = None
        try:
            payload = json.loads(raw)
            pattern = str(payload.get("movement_pattern", payload.get("pattern", self.movement_pattern))).lower()
            if "movement_amplitude_m" in payload:
                amplitude = max(0.0, _as_float(payload.get("movement_amplitude_m"), self.movement_amplitude_m))
            if "movement_speed" in payload:
                speed = max(0.05, _as_float(payload.get("movement_speed"), self.movement_speed))
        except Exception:
            parts = raw.split()
            pattern = parts[0].lower() if parts else self.movement_pattern
            if len(parts) >= 2:
                amplitude = max(0.0, _as_float(parts[1], self.movement_amplitude_m))
            if len(parts) >= 3:
                speed = max(0.05, _as_float(parts[2], self.movement_speed))
        if pattern not in _allowed_motion_patterns():
            self._emit_event("invalid_movement_pattern", {"requested": pattern, "allowed": sorted(_allowed_motion_patterns())})
            return
        self.movement_pattern = pattern
        if amplitude is not None:
            self.movement_amplitude_m = amplitude
        if speed is not None:
            self.movement_speed = speed
        self._emit_event("movement_pattern_changed", {"movement_pattern": self.movement_pattern, "movement_amplitude_m": self.movement_amplitude_m, "movement_speed": self.movement_speed})

    def _update_config_cb(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except Exception as exc:
            self._emit_event("invalid_update_config", {"raw": msg.data, "error": str(exc)})
            return
        changed: Dict[str, Any] = {}
        revision_meta = payload.get("_netlab_revision", {}) if isinstance(payload.get("_netlab_revision", {}), dict) else {}
        if revision_meta:
            self.applied_revision_id = str(revision_meta.get("revision_id", self.applied_revision_id))
            self.applied_parent_revision_id = str(revision_meta.get("parent_revision_id", self.applied_parent_revision_id))
            self.applied_revision_hashes = {key: value for key, value in revision_meta.items() if key.endswith("_hash")}
            self.applied_revision_command_id = str(revision_meta.get("command_id", self.applied_revision_command_id))
            changed["_netlab_revision"] = revision_meta
        if "experiment_name" in payload:
            self.experiment_name = str(payload.get("experiment_name") or self.experiment_name)
            changed["experiment_name"] = self.experiment_name

        def set_float(attr: str, key: str, minimum: Optional[float] = None) -> None:
            if key in payload:
                val = _as_float(payload.get(key), getattr(self, attr))
                if minimum is not None:
                    val = max(minimum, val)
                setattr(self, attr, val)
                changed[key] = val

        def set_int(attr: str, key: str, minimum: Optional[int] = None) -> None:
            if key in payload:
                val = _as_int(payload.get(key), getattr(self, attr))
                if minimum is not None:
                    val = max(minimum, val)
                setattr(self, attr, val)
                changed[key] = val

        # Swarm size is handled first and strictly. If the requested count is smaller,
        # stale drones are removed from the runtime inventory before topology is recomputed.
        requested_total = self.drone_count
        requested_relay: Optional[int] = None
        requested_standby: Optional[int] = None
        if "relay_count" in payload:
            requested_relay = max(1, _as_int(payload.get("relay_count"), self.relay_count))
        if "standby_count" in payload:
            requested_standby = max(0, _as_int(payload.get("standby_count"), self.standby_count))
        if "drone_count" in payload:
            requested_total = max(1, _as_int(payload.get("drone_count"), self.drone_count))
        elif requested_relay is not None or requested_standby is not None:
            requested_total = max(1, (requested_relay if requested_relay is not None else self.relay_count) + (requested_standby if requested_standby is not None else self.standby_count))
        if requested_relay is None:
            # CLI `drones N` means N active relays unless a standby count is supplied.
            requested_relay = requested_total if requested_standby is None else max(1, requested_total - requested_standby)
        drone_specs = payload.get("drones") if isinstance(payload.get("drones"), list) else None
        removed = self._sync_drone_inventory(requested_total, requested_relay, drone_specs)
        if "failed_indices" in payload:
            requested_failed: set[int] = set()
            raw_failed = payload.get("failed_indices", [])
            if isinstance(raw_failed, list):
                for value in raw_failed:
                    try:
                        idx = int(value)
                    except Exception:
                        continue
                    if 1 <= idx <= self.drone_count:
                        requested_failed.add(idx)
            self.failed_indices = requested_failed
            for idx, drone in self.drones.items():
                drone.failed = idx in self.failed_indices
                drone.integrated = bool(drone.role != "standby" and not drone.failed)
            changed["failed_indices"] = sorted(self.failed_indices)
        if removed or requested_total != self.drone_count or "drone_count" in payload or "relay_count" in payload or "standby_count" in payload:
            changed["swarm_inventory"] = {
                "drone_count": self.drone_count,
                "relay_count": self.relay_count,
                "standby_count": self.standby_count,
                "removed_indices": removed,
                "active_inventory": sorted(self.drones),
            }

        set_int("branch_count", "branch_count", 1)
        self.branch_count = max(1, min(self.branch_count, max(1, self.relay_count)))
        topology_payload = payload.get("topology", {}) if isinstance(payload.get("topology", {}), dict) else {}
        requested_mode = payload.get("transmission_mode", topology_payload.get("transmission_mode"))
        if requested_mode is not None:
            mode = str(requested_mode).lower()
            if mode in {"chain", "parallel", "forest", "manual"}:
                self.transmission_mode = mode
        if "manual_branches" in payload or "manual_branches" in topology_payload:
            self.manual_branches = self._sanitize_manual_branches(payload.get("manual_branches", topology_payload.get("manual_branches", [])), filter_failed=False)
        if "forwarding_policy" in payload or "forwarding_policy" in topology_payload:
            self.forwarding_policy = str(payload.get("forwarding_policy", topology_payload.get("forwarding_policy", self.forwarding_policy)))
        if "queue_model" in payload or "queue_model" in topology_payload:
            self.queue_model = str(payload.get("queue_model", topology_payload.get("queue_model", self.queue_model)))
        changed["topology"] = {
            "transmission_mode": self.transmission_mode,
            "branch_count": self.branch_count,
            "manual_branches": self.manual_branches,
            "active_branches": self._active_branches(),
            "forwarding_policy": self.forwarding_policy,
            "queue_model": self.queue_model,
        }
        set_float("coverage_radius_m", "coverage_radius_m", 1.0)
        set_float("coverage_width_m", "coverage_width_m", 1.0)
        set_float("direction_deg", "direction_deg")
        set_float("altitude_start_m", "altitude_start_m")
        set_float("altitude_end_m", "altitude_end_m")
        set_float("max_single_hop_range_m", "max_single_hop_range_m", 1.0)
        set_float("hard_outage_range_m", "hard_outage_range_m", self.max_single_hop_range_m)
        if self.hard_outage_range_m < self.max_single_hop_range_m:
            self.hard_outage_range_m = self.max_single_hop_range_m
        if "allow_degraded_forwarding" in payload:
            self.allow_degraded_forwarding = _as_bool(payload.get("allow_degraded_forwarding"), self.allow_degraded_forwarding)
            changed["allow_degraded_forwarding"] = self.allow_degraded_forwarding
        set_float("distance_penalty_db_per_m_after_soft_range", "distance_penalty_db_per_m_after_soft_range", 0.0)
        set_float("standby_activation_radius_m", "standby_activation_radius_m", 1.0)
        set_float("movement_amplitude_m", "movement_amplitude_m", 0.0)
        set_float("movement_speed", "movement_speed", 0.05)
        set_float("visual_follow_alpha", "visual_follow_alpha", 0.02)
        set_float("wind_speed_mps", "wind_speed_mps", 0.0)
        set_float("wind_direction_deg", "wind_direction_deg")
        set_float("turbulence_intensity", "turbulence_intensity", 0.0)
        if "hop_period_s" in payload:
            self.hop_period_s = max(0.05, _as_float(payload.get("hop_period_s"), self.hop_period_s))
            try:
                self.timer.cancel()
            except Exception:
                pass
            self.timer = self.create_timer(self.hop_period_s, self._tick)
            changed["hop_period_s"] = self.hop_period_s
        if "movement_pattern" in payload:
            pattern = str(payload.get("movement_pattern", self.movement_pattern)).lower()
            if pattern in _allowed_motion_patterns():
                self.movement_pattern = pattern
                changed["movement_pattern"] = pattern
            else:
                self._emit_event("invalid_movement_pattern", {"requested": pattern, "allowed": sorted(_allowed_motion_patterns())})
        if "radio" in payload and isinstance(payload["radio"], dict):
            radio = payload["radio"]
            for key, attr in [("frequency_hz", "frequency_hz"), ("bandwidth_hz", "bandwidth_hz"), ("tx_power_dbm", "tx_power_dbm"), ("noise_floor_dbm", "noise_floor_dbm"), ("min_snr_db", "min_snr_db"), ("required_capacity_mbps", "required_capacity_mbps")]:
                if key in radio:
                    setattr(self, attr, _as_float(radio[key], getattr(self, attr)))
                    changed[f"radio.{key}"] = getattr(self, attr)
            self.radio_metadata.update({
                "frequency_hz": self.frequency_hz,
                "bandwidth_hz": self.bandwidth_hz,
                "tx_power_dbm": self.tx_power_dbm,
                "noise_floor_dbm": self.noise_floor_dbm,
                "min_snr_db": self.min_snr_db,
                "required_capacity_mbps": self.required_capacity_mbps,
                "station_antenna_name": str(radio.get("station_antenna_name", self.radio_metadata.get("station_antenna_name", self.station_antenna_name))),
                "uav_antenna_name": str(radio.get("uav_antenna_name", self.radio_metadata.get("uav_antenna_name", "uav_omni"))),
                "antenna_model": str(radio.get("antenna_model", self.radio_metadata.get("antenna_model", "abstract_gain_model_for_realtime_demo"))),
            })
        if "station" in payload and isinstance(payload["station"], dict):
            station = payload["station"]
            if isinstance(station.get("position"), list) and len(station.get("position", [])) >= 3:
                try:
                    self.station_position = tuple(float(v) for v in station.get("position", [])[:3])  # type: ignore[assignment]
                    changed["station.position"] = [round(v, 3) for v in self.station_position]
                except Exception:
                    pass
            if "antenna_name" in station:
                self.station_antenna_name = str(station.get("antenna_name"))
                changed["station.antenna_name"] = self.station_antenna_name
            if "antenna_gain_dbi" in station:
                self.station_antenna_gain_dbi = _as_float(station.get("antenna_gain_dbi"), self.station_antenna_gain_dbi)
                changed["station.antenna_gain_dbi"] = self.station_antenna_gain_dbi
        if "antennas" in payload and isinstance(payload.get("antennas"), list):
            self.antennas = payload.get("antennas", [])
            changed["antennas"] = len(self.antennas)
        if "worlds" in payload and isinstance(payload.get("worlds"), list):
            self.worlds = payload.get("worlds", [])
            changed["worlds"] = len(self.worlds)

        self._recompute_desired_positions(reason="runtime_update_config")
        self._emit_event("runtime_config_updated", changed)
        if revision_meta:
            try:
                atomic_write_json(self.ros_revision_ack_path, {
                    "timestamp": _now(),
                    "ready": True,
                    "component": "ros2_packet_runtime",
                    "revision": self.applied_revision_id,
                    "revision_id": self.applied_revision_id,
                    "parent_revision_id": self.applied_parent_revision_id,
                    "command_id": self.applied_revision_command_id,
                    "applied_config_hash": self.applied_revision_hashes.get("config_hash", ""),
                    "applied_hashes": self.applied_revision_hashes,
                    "chain_version": self.chain_version,
                    "node_name": self.get_name(),
                })
            except Exception as exc:
                self.get_logger().warn(f"Could not write ROS revision acknowledgement {self.ros_revision_ack_path}: {exc}")

    def _activate_best_standby_for_failure(self, failed_index: int) -> Optional[int]:
        standby = self._standby_indices()
        if not standby:
            self._emit_event("no_standby_available_for_failure", {"failed_drone": failed_index})
            return None
        if failed_index not in self.drones:
            self._emit_event("failed_drone_missing_for_replacement", {"failed_drone": failed_index, "known_visible_drones": self._visible_drone_indices()})
            return None
        failed_pos = self.drones[failed_index].desired_position
        replacement = self._strategy_selected_standby(failed_index, standby)
        if replacement is None:
            replacement = min(standby, key=lambda idx: _distance(self.drones[idx].current_position, failed_pos))
        repl = self.drones[replacement]
        repl.role = "relay"
        repl.integrated = True
        repl.failed = False
        # Pull the standby drone toward the failed drone's logical slot immediately.
        repl.desired_position = failed_pos
        self._emit_event(
            "standby_drone_promoted_for_failure",
            {
                "failed_drone": failed_index,
                "replacement_drone": replacement,
                "replacement_previous_position": [round(v, 3) for v in repl.current_position],
                "replacement_target_position": [round(v, 3) for v in failed_pos],
            },
        )
        return replacement

    def _process_pending_failure(self) -> None:
        if self.pending_failure is None or _now() < self.pending_failure.detection_deadline:
            return
        failed_index = self.pending_failure.drone_index
        if failed_index not in self.drones or failed_index > self.drone_count:
            self._emit_event("pending_failure_dropped", {"drone": failed_index, "reason": "drone_not_in_current_inventory"})
            self.pending_failure = None
            return
        self.failed_indices.add(failed_index)
        self.drones[failed_index].failed = True
        self.pending_failure = None
        replacement = self._activate_best_standby_for_failure(failed_index)
        self._emit_event("failure_detected", {"drone": failed_index, "replacement_drone": replacement, "detection_timeout_s": self.failure_detection_s})
        self._recompute_desired_positions(reason=f"drone_{failed_index}_failure")

    # ---------- status ----------
    def _desired_positions_payload(self) -> Dict[str, List[float]]:
        return {
            f"drone_{idx}": [round(v, 3) for v in d.desired_position]
            for idx, d in sorted(self.drones.items())
            if 1 <= idx <= self.drone_count
        }

    def _visible_drone_indices(self) -> List[int]:
        return [idx for idx in sorted(self.drones) if 1 <= idx <= self.drone_count]

    def _service_state(self) -> str:
        if self.connectivity_paused:
            return "outage"
        if self.failed_indices:
            return "degraded"
        if not self.coverage_feasible:
            return "coverage_warning"
        return "nominal"

    def _last_link_summary(self) -> Dict[str, Any]:
        hop = self.last_hop_event or {}
        metrics = hop.get("metrics", {}) if isinstance(hop.get("metrics", {}), dict) else {}
        return {
            "src": hop.get("src"),
            "dst": hop.get("dst"),
            "decision": hop.get("decision"),
            "link_ok": hop.get("link_ok"),
            "status": hop.get("link_status") or metrics.get("status"),
            "gate_reason": metrics.get("gate_reason", hop.get("decision")),
            "model_source": metrics.get("model_source", metrics.get("model")),
            "fidelity_profile": metrics.get("fidelity_profile", metrics.get("fidelity")),
            "distance_m": metrics.get("distance_m"),
            "range_margin_m": metrics.get("range_margin_m"),
            "rx_power_dbm": metrics.get("rx_power_dbm"),
            "snr_db": metrics.get("snr_db"),
            "sinr_db": metrics.get("sinr_db"),
            "snr_margin_db": metrics.get("snr_margin_db"),
            "capacity_mbps": metrics.get("capacity_mbps"),
            "capacity_margin_mbps": metrics.get("capacity_margin_mbps"),
            "propagation_delay_ms": metrics.get("propagation_delay_ms"),
        }

    def _publish_status(self) -> None:
        active_chain = self._active_chain()
        standby_indices = self._standby_indices()
        payload = {
            "timestamp": _now(),
            "experiment_name": self.experiment_name,
            "chain_version": self.chain_version,
            "applied_revision_id": self.applied_revision_id,
            "applied_parent_revision_id": self.applied_parent_revision_id,
            "applied_revision_hashes": self.applied_revision_hashes,
            "applied_revision_command_id": self.applied_revision_command_id,
            "controller_state": "paused_by_operator" if self.operator_paused else "running",
            "mission_mode": self.mission_mode,
            "operator_paused": self.operator_paused,
            "last_mission_command": self.last_mission_command,
            "last_mission_command_id": self.last_mission_command_id,
            "service_state": self._service_state(),
            "drone_count": self.drone_count,
            "visible_drone_indices": self._visible_drone_indices(),
            "relay_count": self.relay_count,
            "standby_count": self.standby_count,
            "active_drone_count": len(active_chain),
            "active_count": len(active_chain),
            "removed_indices": list(self.last_removed_indices),
            "phase": self.phase,
            "cursor": self.cursor,
            "packet_id": self.current_packet.get("packet_id"),
            "sequence": self.sequence,
            "connectivity_paused": self.connectivity_paused,
            "connectivity_pause_reason": self.connectivity_pause_reason,
            "paused_hop": self.paused_hop,
            "active_chain": active_chain,
            "active_branches": self._active_branches(),
            "branch_flows": self._flow_status(),
            "parallel_independent_streams": bool(self._parallel_enabled()),
            "manual_branches": self.manual_branches,
            "transmission_mode": self.transmission_mode,
            "topology": {
                "transmission_mode": self.transmission_mode,
                "branch_count": self.branch_count,
                "active_branches": self._active_branches(),
                "branch_flows": self._flow_status(),
                "parallel_independent_streams": bool(self._parallel_enabled()),
                "manual_branches": self.manual_branches,
                "forwarding_policy": self.forwarding_policy,
                "queue_model": self.queue_model,
            },
            "current_branch_index": self.current_branch_index,
            "branch_count": self.branch_count,
            "failed_indices": sorted(self.failed_indices),
            "standby_indices": standby_indices,
            "pending_failure": None if self.pending_failure is None else {"drone": self.pending_failure.drone_index, "detection_deadline": self.pending_failure.detection_deadline, "remaining_s": round(max(0.0, self.pending_failure.detection_deadline - _now()), 3)},
            "station_position": [round(v, 3) for v in self.station_position],
            "desired_positions": self._desired_positions_payload(),
            "coverage_radius_m": self.coverage_radius_m,
            "coverage_width_m": self.coverage_width_m,
            "direction_deg": self.direction_deg,
            "altitude_start_m": self.altitude_start_m,
            "altitude_end_m": self.altitude_end_m,
            "max_single_hop_range_m": self.max_single_hop_range_m,
            "hard_outage_range_m": self.hard_outage_range_m,
            "allow_degraded_forwarding": self.allow_degraded_forwarding,
            "communication_radius_m": self.max_single_hop_range_m,
            "distance_penalty_db_per_m_after_soft_range": self.distance_penalty_db_per_m_after_soft_range,
            "standby_activation_radius_m": self.standby_activation_radius_m,
            "coverage_feasible": self.coverage_feasible,
            "coverage_note": self.coverage_note,
            "system_health": "outage" if self.connectivity_paused else ("degraded" if not self.coverage_feasible else "nominal"),
            "movement_pattern": self.movement_pattern,
            "movement_amplitude_m": self.movement_amplitude_m,
            "movement_speed": self.movement_speed,
            "visual_follow_alpha": self.visual_follow_alpha,
            "wind_speed_mps": self.wind_speed_mps,
            "wind_direction_deg": self.wind_direction_deg,
            "turbulence_intensity": self.turbulence_intensity,
            "radio": self.radio_metadata,
            "strategy": {"active": self.strategy_id, "plugins_dir": str(self.plugins_dir), "api_version": "2.0", "parameters": self.strategy_parameters, "last_decision": self.last_algorithm_decision},
            "antennas": self.antennas,
            "antenna_count": len(self.antennas),
            "worlds": self.worlds,
            "world_count": len(self.worlds),
            "drones": {f"drone_{i}": d.state_summary() for i, d in sorted(self.drones.items()) if 1 <= i <= self.drone_count},
            "last_link_summary": self._last_link_summary(),
            "last_hop": self.last_hop_event,
            "hop_period_s": self.hop_period_s,
        }
        self._publish_json(self.status_pub, payload)
        try:
            self.latest_status_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self.latest_status_path, payload)
        except Exception as exc:
            self.get_logger().warn(f"Could not write latest status file {self.latest_status_path}: {exc}")
        try:
            last_metrics = self.last_hop_event.get("metrics", {}) if isinstance(self.last_hop_event.get("metrics", {}), dict) else {}
            heartbeat = {
                "timestamp": _now(),
                "ready": True,
                "state": "RUNNING",
                "node_name": self.get_name(),
                "pid": os.getpid(),
                "experiment_name": self.experiment_name,
                "revision": self.applied_revision_id,
                "revision_id": self.applied_revision_id,
                "applied_config_hash": self.applied_revision_hashes.get("config_hash", ""),
                "applied_hashes": self.applied_revision_hashes,
                "sequence": self.sequence,
                "packet_id": self.current_packet.get("packet_id"),
                "phase": self.phase,
                "cursor": self.cursor,
                "mission_mode": self.mission_mode,
                "operator_paused": self.operator_paused,
                "last_mission_command": self.last_mission_command,
                "last_mission_command_id": self.last_mission_command_id,
                "packet_advancing": bool(self.last_hop_event.get("link_ok", False)) and not self.connectivity_paused and not self.operator_paused,
                "connectivity_paused": self.connectivity_paused,
                "gate_reason": last_metrics.get("gate_reason", self.connectivity_pause_reason or "NO_LINK_SAMPLE"),
                "last_hop": {
                    "src": self.last_hop_event.get("src"),
                    "dst": self.last_hop_event.get("dst"),
                    "link_ok": self.last_hop_event.get("link_ok"),
                    "decision": self.last_hop_event.get("decision"),
                },
            }
            atomic_write_json(self.packet_heartbeat_path, heartbeat)
        except Exception as exc:
            self.get_logger().warn(f"Could not write packet-runtime heartbeat {self.packet_heartbeat_path}: {exc}")


def main(args: Optional[List[str]] = None) -> None:
    rclpy.init(args=args)
    node = SnaasRelayChain()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
