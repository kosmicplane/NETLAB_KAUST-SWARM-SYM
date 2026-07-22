"""Typed authoritative models for NETLAB runtime and evidence contracts."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]


class FidelityProfile(str, Enum):
    PREVIEW = "F0_PREVIEW"
    ANALYTICAL = "F1_ANALYTICAL"
    STOCHASTIC = "F2_STOCHASTIC"
    GEOMETRY_AWARE = "F3_GEOMETRY_AWARE"
    PROTOCOL_AWARE = "F4_PROTOCOL_AWARE"
    AUTOPILOT = "F5_AUTOPILOT"
    HARDWARE_ASSISTED = "F6_HARDWARE_ASSISTED"

    # Compatibility aliases retained for legacy v5 experiment files.
    LEGACY_AUTOPILOT = "F4_AUTOPILOT"
    LEGACY_HARDWARE_ASSISTED = "F5_HARDWARE_ASSISTED"


class TopologyMode(str, Enum):
    CHAIN = "chain"
    PARALLEL = "parallel"
    FOREST = "forest"
    MANUAL = "manual"


class RuntimePhase(str, Enum):
    STOPPED = "STOPPED"
    PREFLIGHT = "PREFLIGHT"
    REPAIRING = "REPAIRING"
    BUILDING = "BUILDING"
    STARTING_INFRASTRUCTURE = "STARTING_INFRASTRUCTURE"
    STARTING_SIONNA = "STARTING_SIONNA"
    WAITING_FOR_SIONNA = "WAITING_FOR_SIONNA"
    STARTING_ROS = "STARTING_ROS"
    WAITING_FOR_ROS_CONTAINER = "WAITING_FOR_ROS_CONTAINER"
    WAITING_FOR_ROS_GRAPH = "WAITING_FOR_ROS_GRAPH"
    WAITING_FOR_PACKET_RUNTIME = "WAITING_FOR_PACKET_RUNTIME"
    # Compatibility aggregate retained for older dashboards.
    WAITING_FOR_ROS = "WAITING_FOR_ROS"
    STARTING_ISAAC = "STARTING_ISAAC"
    WAITING_FOR_ISAAC_PROCESS = "WAITING_FOR_ISAAC_PROCESS"
    WAITING_FOR_ISAAC_SCENE = "WAITING_FOR_ISAAC_SCENE"
    WAITING_FOR_ISAAC = "WAITING_FOR_ISAAC"
    SYNCHRONIZING = "SYNCHRONIZING"
    SMOKE_TESTING = "SMOKE_TESTING"
    READY = "READY"
    STARTING_EXPERIMENT = "STARTING_EXPERIMENT"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    OUTAGE = "OUTAGE"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


class TelemetrySource(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    PREVIEW = "PREVIEW"
    OFFLINE = "OFFLINE"
    STALE = "STALE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"




class RevisionPhase(str, Enum):
    DRAFT_SAVED = "DRAFT_SAVED"
    VALIDATED = "VALIDATED"
    PENDING_RUNTIME_APPLY = "PENDING_RUNTIME_APPLY"
    APPLIED_TO_ROS = "APPLIED_TO_ROS"
    APPLIED_TO_SIONNA = "APPLIED_TO_SIONNA"
    APPLIED_TO_ISAAC = "APPLIED_TO_ISAAC"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"


class ParticipantState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPLYING = "APPLYING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    FAILED = "FAILED"
    STALE = "STALE"


class CommandStatus(str, Enum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"
    DISPATCHING = "DISPATCHING"
    WAITING_FOR_ACK = "WAITING_FOR_ACK"
    PARTIALLY_APPLIED = "PARTIALLY_APPLIED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"

class GateReason(str, Enum):
    FEASIBLE = "FEASIBLE"
    SOURCE_FAILED = "SOURCE_FAILED"
    DESTINATION_FAILED = "DESTINATION_FAILED"
    SOURCE_INACTIVE = "SOURCE_INACTIVE"
    DESTINATION_INACTIVE = "DESTINATION_INACTIVE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    HARD_OUTAGE_DISTANCE = "HARD_OUTAGE_DISTANCE"
    SNR_BELOW_THRESHOLD = "SNR_BELOW_THRESHOLD"
    SINR_BELOW_THRESHOLD = "SINR_BELOW_THRESHOLD"
    CAPACITY_BELOW_THRESHOLD = "CAPACITY_BELOW_THRESHOLD"
    NO_ROUTE = "NO_ROUTE"
    STALE_LINK_METRIC = "STALE_LINK_METRIC"
    LINK_SERVICE_UNAVAILABLE = "LINK_SERVICE_UNAVAILABLE"
    ANTENNA_INVALID = "ANTENNA_INVALID"
    WORLD_MODEL_UNAVAILABLE = "WORLD_MODEL_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class PacketStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    WAITING_FOR_LINK = "WAITING_FOR_LINK"
    TRANSMITTING = "TRANSMITTING"
    ADVANCED = "ADVANCED"
    DELIVERED = "DELIVERED"
    PAUSED_OUTAGE = "PAUSED_OUTAGE"
    RETRYING = "RETRYING"
    DROPPED = "DROPPED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass
class ReadinessState:
    docker_ready: bool = False
    gpu_ready: bool = False
    compose_ready: bool = False
    ros_container_ready: bool = False
    ros_graph_ready: bool = False
    packet_runtime_ready: bool = False
    sionna_ready: bool = False
    isaac_process_ready: bool = False
    isaac_scene_ready: bool = False
    isaac_heartbeat_ready: bool = False
    isaac_scenario_acknowledged: bool = False
    telemetry_ready: bool = False
    evidence_ready: bool = False

    @property
    def critical_ready(self) -> bool:
        return all(
            (
                self.docker_ready,
                self.gpu_ready,
                self.compose_ready,
                self.ros_container_ready,
                self.ros_graph_ready,
                self.packet_runtime_ready,
                self.sionna_ready,
                self.isaac_process_ready,
                self.isaac_scene_ready,
                self.isaac_heartbeat_ready,
                self.isaac_scenario_acknowledged,
            )
        )

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["critical_ready"] = self.critical_ready
        return payload


@dataclass
class UAVState:
    uav_id: str
    index: int
    position: Vec3
    velocity: Vec3 = (0.0, 0.0, 0.0)
    acceleration: Vec3 = (0.0, 0.0, 0.0)
    orientation_xyzw: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
    angular_velocity: Vec3 = (0.0, 0.0, 0.0)
    desired_position: Optional[Vec3] = None
    battery_soc_pct: float = 100.0
    role: str = "relay"
    active: bool = True
    failed: bool = False
    integrated: bool = True
    coordinate_frame: str = "ENU"
    timestamp_sim_s: float = 0.0
    timestamp_wall_s: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LinkMetrics:
    link_id: str
    src: str
    dst: str
    distance_m: float
    path_loss_db: float
    rx_power_dbm: float
    snr_db: float
    capacity_mbps: float
    propagation_delay_ms: float
    sinr_db: Optional[float] = None
    queue_delay_ms: float = 0.0
    total_delay_ms: float = 0.0
    los_state: str = "UNKNOWN"
    model: str = "analytical_fspl"
    model_version: str = "1.0"
    fidelity: FidelityProfile = FidelityProfile.ANALYTICAL
    timestamp_wall_s: float = field(default_factory=time.time)
    valid_for_s: float = 2.0
    components_db: Dict[str, float] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    computation_ms: float = 0.0
    cache_status: str = "MISS"

    @property
    def age_s(self) -> float:
        return max(0.0, time.time() - self.timestamp_wall_s)

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["fidelity"] = self.fidelity.value
        payload["age_s"] = self.age_s
        return payload


@dataclass
class GatePredicate:
    name: str
    passed: bool
    value: Any
    threshold: Any
    margin: Optional[float] = None
    unit: str = ""


@dataclass
class FeasibilityDecision:
    feasible: bool
    reason: GateReason
    predicates: List[GatePredicate]
    metric_age_s: Optional[float] = None
    evaluated_at: float = field(default_factory=time.time)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "feasible": self.feasible,
            "reason": self.reason.value,
            "predicates": [asdict(p) for p in self.predicates],
            "metric_age_s": self.metric_age_s,
            "evaluated_at": self.evaluated_at,
        }


@dataclass
class PacketState:
    packet_id: str
    flow_id: str
    branch_id: str
    sequence_number: int
    source: str
    destination: str
    route: List[str]
    current_hop_index: int = 0
    current_node: str = ""
    next_node: str = ""
    status: PacketStatus = PacketStatus.CREATED
    created_at: float = field(default_factory=time.time)
    queued_at: Optional[float] = None
    transmitted_at: Optional[float] = None
    received_at: Optional[float] = None
    dropped_at: Optional[float] = None
    drop_reason: Optional[str] = None
    outage_reason: Optional[str] = None
    ttl_s: float = 60.0
    retries: int = 0
    bytes: int = 512
    priority: int = 0
    last_link_metric_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass
class RuntimeEvent:
    event_type: str
    source_component: str
    payload: Dict[str, Any]
    severity: str = "INFO"
    experiment_id: str = ""
    run_id: str = ""
    affected_entity: str = ""
    correlation_id: str = ""
    command_id: str = ""
    model_version: str = ""
    timestamp_wall: float = field(default_factory=time.time)
    timestamp_sim: Optional[float] = None
    sequence: int = 0
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_vec3(value: Sequence[Any], *, name: str = "vector") -> Vec3:
    if len(value) != 3:
        raise ValueError(f"{name} must contain exactly three values")
    result = tuple(float(v) for v in value)
    if any(v != v or abs(v) == float("inf") for v in result):
        raise ValueError(f"{name} contains non-finite values")
    return result  # type: ignore[return-value]

# NETLAB authoritative contract exports
from .contracts import Phase, CommandStatus, RevisionStatus, TelemetrySource, Command, Revision, ParticipantAck, ServiceState, ReadinessState
