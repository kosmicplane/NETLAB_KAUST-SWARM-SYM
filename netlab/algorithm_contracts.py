"""Typed contracts for researcher-defined algorithms.

The contracts intentionally separate observations, proposed actions, safety
validation, runtime acknowledgements, and evidence. Researcher code never
mutates authoritative NETLAB state directly.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

ALGORITHM_API_VERSION = "2.0"
ALGORITHM_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
EXECUTION_MODES = {
    "isolated_python",
    "external_ros2",
    "oci_container",
    "pettingzoo_parallel",
    "replay",
}
ALGORITHM_CATEGORIES = {
    "controller",
    "trajectory_planner",
    "formation_controller",
    "topology_generator",
    "routing_policy",
    "recovery_policy",
    "standby_selector",
    "propagation_model",
    "antenna_model",
    "traffic_generator",
    "scheduler",
    "energy_model",
    "metric",
    "optimizer",
    "safety_filter",
    "marl_policy",
    "import_export_adapter",
}
ACTION_FIELDS = {
    "desired_positions",
    "desired_velocities",
    "desired_accelerations",
    "desired_jerks",
    "desired_yaws_deg",
    "desired_trajectories",
    "formation_targets",
    "topology_candidate",
    "route_candidate",
    "branch_candidates",
    "user_association",
    "traffic_schedule",
    "standby_selection",
    "recovery_action",
    "antenna_commands",
    "transmit_power_commands_dbm",
    "channel_allocation",
    "metrics",
    "optimization_result",
}


class AlgorithmContractError(ValueError):
    """Raised when an algorithm package or action violates the public contract."""


@dataclass(frozen=True)
class ResourceBudget:
    timeout_s: float = 0.25
    memory_mb: int = 256
    cpu_cores: float = 1.0
    output_kb: int = 256
    gpu_required: bool = False
    network_policy: str = "deny"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not 0.001 <= float(self.timeout_s) <= 300.0:
            errors.append("resource_budget.timeout_s must be within [0.001, 300].")
        if not 16 <= int(self.memory_mb) <= 131072:
            errors.append("resource_budget.memory_mb must be within [16, 131072].")
        if not 0.05 <= float(self.cpu_cores) <= 128.0:
            errors.append("resource_budget.cpu_cores must be within [0.05, 128].")
        if not 8 <= int(self.output_kb) <= 1048576:
            errors.append("resource_budget.output_kb must be within [8, 1048576].")
        if self.network_policy not in {"deny", "loopback", "experiment_network"}:
            errors.append("resource_budget.network_policy is unsupported.")
        return errors


@dataclass(frozen=True)
class AlgorithmManifest:
    algorithm_id: str
    name: str
    version: str
    api_version: str
    category: str
    entrypoint: str
    execution_mode: str = "isolated_python"
    author: str = ""
    organization: str = ""
    license: str = ""
    description: str = ""
    citations: tuple[Mapping[str, Any], ...] = ()
    supported_fidelity_profiles: tuple[str, ...] = ("F1_ANALYTICAL",)
    required_state_fields: tuple[str, ...] = ()
    required_ros_interfaces: tuple[str, ...] = ()
    observation_schema: Mapping[str, Any] = field(default_factory=dict)
    action_schema: Mapping[str, Any] = field(default_factory=dict)
    parameter_schema: Mapping[str, Any] = field(default_factory=dict)
    resource_budget: ResourceBudget = field(default_factory=ResourceBudget)
    deterministic_seed: bool = True
    checkpoint_contract: Mapping[str, Any] = field(default_factory=dict)
    safety_fallback: str = "hold_position"
    assumptions: tuple[str, ...] = ()
    validity_domain: str = ""
    known_limitations: tuple[str, ...] = ()
    source_hash: str = ""
    dependency_lock_hash: str = ""
    package_path: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, package_path: str = "") -> "AlgorithmManifest":
        budget_value = value.get("resource_budget", {})
        if not isinstance(budget_value, Mapping):
            budget_value = {}
        budget = ResourceBudget(
            timeout_s=float(budget_value.get("timeout_s", value.get("timeout_s", 0.25))),
            memory_mb=int(budget_value.get("memory_mb", 256)),
            cpu_cores=float(budget_value.get("cpu_cores", 1.0)),
            output_kb=int(budget_value.get("output_kb", 256)),
            gpu_required=bool(budget_value.get("gpu_required", False)),
            network_policy=str(budget_value.get("network_policy", "deny")),
        )
        citations_value = value.get("citations", [])
        citations: tuple[Mapping[str, Any], ...] = tuple(
            item for item in citations_value if isinstance(item, Mapping)
        ) if isinstance(citations_value, Sequence) and not isinstance(citations_value, (str, bytes)) else ()
        category_aliases = {
            "trajectory": "trajectory_planner",
            "routing": "routing_policy",
            "recovery": "recovery_policy",
            "antenna": "antenna_model",
            "experiment": "optimizer",
            "formation": "formation_controller",
        }
        execution_aliases = {
            "isolated_worker": "isolated_python",
            "isolated_python_worker": "isolated_python",
            "trusted_in_process": "isolated_python",
            "container": "oci_container",
        }
        category = category_aliases.get(str(value.get("category", "controller")).strip(), str(value.get("category", "controller")).strip())
        execution_mode = execution_aliases.get(str(value.get("execution_mode", "isolated_python")).strip(), str(value.get("execution_mode", "isolated_python")).strip())
        return cls(
            algorithm_id=str(value.get("algorithm_id", value.get("plugin_id", ""))).strip(),
            name=str(value.get("name", "")).strip(),
            version=str(value.get("version", "0.0.0")).strip(),
            api_version=str(value.get("api_version", "")).strip(),
            category=category,
            entrypoint=str(value.get("entrypoint", "algorithm.py")).strip(),
            execution_mode=execution_mode,
            author=str(value.get("author", "")).strip(),
            organization=str(value.get("organization", "")).strip(),
            license=str(value.get("license", "")).strip(),
            description=str(value.get("description", "")).strip(),
            citations=citations,
            supported_fidelity_profiles=tuple(str(item) for item in value.get("supported_fidelity_profiles", value.get("supported_fidelity", [value.get("required_fidelity", "F1_ANALYTICAL")]))),
            required_state_fields=tuple(str(item) for item in value.get("required_state_fields", [])),
            required_ros_interfaces=tuple(str(item) for item in value.get("required_ros_interfaces", [])),
            observation_schema=dict(value.get("observation_schema", {})) if isinstance(value.get("observation_schema", {}), Mapping) else {},
            action_schema=dict(value.get("action_schema", {})) if isinstance(value.get("action_schema", {}), Mapping) else {},
            parameter_schema=dict(value.get("parameter_schema", value.get("parameters", {}))) if isinstance(value.get("parameter_schema", value.get("parameters", {})), Mapping) else {},
            resource_budget=budget,
            deterministic_seed=bool(value.get("deterministic_seed", True)),
            checkpoint_contract=dict(value.get("checkpoint_contract", {})) if isinstance(value.get("checkpoint_contract", {}), Mapping) else {},
            safety_fallback=str(value.get("safety_fallback", value.get("safe_fallback", "hold_position"))),
            assumptions=tuple(str(item) for item in value.get("assumptions", [])),
            validity_domain=str(value.get("validity_domain", "")),
            known_limitations=tuple(str(item) for item in value.get("known_limitations", [])),
            source_hash=str(value.get("source_hash", "")),
            dependency_lock_hash=str(value.get("dependency_lock_hash", "")),
            package_path=package_path,
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not ALGORITHM_ID_PATTERN.fullmatch(self.algorithm_id):
            errors.append("algorithm_id must match ^[a-z][a-z0-9_]{2,63}$.")
        if not self.name:
            errors.append("name is required.")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", self.version):
            errors.append("version must be semantic version syntax.")
        if self.api_version != ALGORITHM_API_VERSION:
            errors.append(f"api_version must be {ALGORITHM_API_VERSION}.")
        if self.category not in ALGORITHM_CATEGORIES:
            errors.append(f"category {self.category!r} is unsupported.")
        if self.execution_mode not in EXECUTION_MODES:
            errors.append(f"execution_mode {self.execution_mode!r} is unsupported.")
        if not self.entrypoint or Path(self.entrypoint).is_absolute() or ".." in Path(self.entrypoint).parts:
            errors.append("entrypoint must be a safe package-relative path.")
        if not self.supported_fidelity_profiles:
            errors.append("supported_fidelity_profiles must not be empty.")
        errors.extend(self.resource_budget.validate())
        return errors

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["citations"] = [dict(item) for item in self.citations]
        value["supported_fidelity_profiles"] = list(self.supported_fidelity_profiles)
        value["required_state_fields"] = list(self.required_state_fields)
        value["required_ros_interfaces"] = list(self.required_ros_interfaces)
        value["assumptions"] = list(self.assumptions)
        value["known_limitations"] = list(self.known_limitations)
        return value


@dataclass
class AlgorithmObservation:
    experiment_id: str
    run_id: str
    revision_id: str
    seed: int
    wall_time_s: float
    simulation_time_s: float
    step_s: float
    real_time_factor: float
    uavs: list[Dict[str, Any]]
    ground_entities: list[Dict[str, Any]]
    topology: Dict[str, Any]
    links: list[Dict[str, Any]]
    packets: Dict[str, Any]
    flows: list[Dict[str, Any]]
    world: Dict[str, Any]
    antennas: Dict[str, Any]
    failures: list[Dict[str, Any]]
    recovery: Dict[str, Any]
    service_requirements: Dict[str, Any]
    constraints: Dict[str, Any]
    uncertainty: Dict[str, Any]
    source: str = "AUTHORITATIVE_SNAPSHOT"
    schema_version: str = "2.0"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AlgorithmAction:
    algorithm_id: str
    algorithm_version: str
    source_revision_id: str
    timestamp_s: float
    validity_horizon_s: float
    coordinate_frame: str
    units: Mapping[str, str]
    payload: Dict[str, Any]
    confidence: Optional[float] = None
    uncertainty: Mapping[str, Any] = field(default_factory=dict)
    objective_value: Optional[float] = None
    constraint_residuals: Mapping[str, float] = field(default_factory=dict)
    computation_duration_s: float = 0.0
    termination_reason: str = "completed"
    fallback: bool = False
    explanation: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "2.0"

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        manifest: AlgorithmManifest,
        source_revision_id: str,
        duration_s: float,
    ) -> "AlgorithmAction":
        payload: Dict[str, Any]
        if isinstance(value.get("payload"), Mapping):
            payload = dict(value["payload"])
        else:
            payload = {key: value[key] for key in ACTION_FIELDS if key in value}
        return cls(
            algorithm_id=str(value.get("algorithm_id", manifest.algorithm_id)),
            algorithm_version=str(value.get("algorithm_version", manifest.version)),
            source_revision_id=str(value.get("source_revision_id", source_revision_id)),
            timestamp_s=float(value.get("timestamp_s", time.time())),
            validity_horizon_s=float(value.get("validity_horizon_s", max(0.01, manifest.resource_budget.timeout_s * 4.0))),
            coordinate_frame=str(value.get("coordinate_frame", "ENU")),
            units=dict(value.get("units", {"position": "m", "velocity": "m/s", "acceleration": "m/s^2", "jerk": "m/s^3"})),
            payload=payload,
            confidence=float(value["confidence"]) if value.get("confidence") is not None else None,
            uncertainty=dict(value.get("uncertainty", {})) if isinstance(value.get("uncertainty", {}), Mapping) else {},
            objective_value=float(value["objective_value"]) if value.get("objective_value") is not None else None,
            constraint_residuals={str(k): float(v) for k, v in dict(value.get("constraint_residuals", {})).items()},
            computation_duration_s=float(value.get("computation_duration_s", duration_s)),
            termination_reason=str(value.get("termination_reason", "completed")),
            fallback=bool(value.get("fallback", False)),
            explanation=dict(value.get("explanation", {})) if isinstance(value.get("explanation", {}), Mapping) else {},
        )

    def validate(self, *, now_s: Optional[float] = None) -> list[str]:
        errors: list[str] = []
        if not ALGORITHM_ID_PATTERN.fullmatch(self.algorithm_id):
            errors.append("algorithm_id is invalid.")
        if not self.source_revision_id:
            errors.append("source_revision_id is required.")
        if self.coordinate_frame not in {"ENU", "NED", "ECEF", "WGS84", "ISAAC_STAGE"}:
            errors.append("coordinate_frame is unsupported.")
        if self.validity_horizon_s <= 0:
            errors.append("validity_horizon_s must be positive.")
        check_time = time.time() if now_s is None else float(now_s)
        if check_time - self.timestamp_s > self.validity_horizon_s:
            errors.append("algorithm action is stale.")
        unknown = sorted(set(self.payload) - ACTION_FIELDS)
        if unknown:
            errors.append(f"unsupported action payload fields: {unknown}.")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be within [0, 1].")
        for key, value in self.constraint_residuals.items():
            if not math.isfinite(value):
                errors.append(f"constraint residual {key} is not finite.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def canonical_json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def package_hash(package_dir: Path, *, exclude: Iterable[str] = ("__pycache__", ".pytest_cache")) -> str:
    excluded = set(exclude)
    digest = hashlib.sha256()
    for path in sorted(p for p in package_dir.rglob("*") if p.is_file() and not any(part in excluded for part in p.parts)):
        digest.update(str(path.relative_to(package_dir)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_manifest(path: Path) -> AlgorithmManifest:
    manifest_path = path / "manifest.json" if path.is_dir() else path
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AlgorithmContractError(f"Could not read algorithm manifest {manifest_path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise AlgorithmContractError("Algorithm manifest must be a JSON object.")
    package_dir = manifest_path.parent
    manifest = AlgorithmManifest.from_mapping(value, package_path=str(package_dir))
    source_hash = package_hash(package_dir)
    if manifest.source_hash and manifest.source_hash != source_hash:
        raise AlgorithmContractError("Manifest source_hash does not match the package contents.")
    return AlgorithmManifest(**{**manifest.__dict__, "source_hash": source_hash})


def normalize_vec3_map(value: Any, *, field_name: str) -> Dict[str, list[float]]:
    if not isinstance(value, Mapping):
        raise AlgorithmContractError(f"{field_name} must be an object keyed by entity ID.")
    normalized: Dict[str, list[float]] = {}
    for entity_id, raw in value.items():
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 3:
            raise AlgorithmContractError(f"{field_name}.{entity_id} must contain three numeric values.")
        vector = [float(component) for component in raw]
        if not all(math.isfinite(component) for component in vector):
            raise AlgorithmContractError(f"{field_name}.{entity_id} contains a non-finite value.")
        normalized[str(entity_id)] = vector
    return normalized


def observation_hash(observation: Mapping[str, Any]) -> str:
    return canonical_json_hash(observation)
