#!/usr/bin/env python3
"""Typed ROS 2 bridge for isolated researcher algorithms.

The bridge consumes authoritative observation snapshots, runs the selected
algorithm in an isolated worker, applies the NETLAB safety/feasibility shield,
and publishes a typed action. Researcher code never mutates the ROS graph,
Isaac stage, or packet cursor directly.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Mapping

import rclpy
from rclpy.node import Node

from netlab.algorithm_contracts import AlgorithmAction, canonical_json_hash
from netlab.algorithm_runtime import AlgorithmRuntime
from netlab.config import load_experiment
from netlab.io import atomic_write_json
from netlab_interfaces.msg import AlgorithmAction as AlgorithmActionMsg
from netlab_interfaces.msg import AlgorithmObservation as AlgorithmObservationMsg
from netlab_interfaces.msg import AlgorithmStatus
from netlab_interfaces.srv import ValidateAlgorithm


class ResearcherAlgorithmBridge(Node):
    """Execute selected algorithms behind one typed, supervised ROS boundary."""

    def __init__(self) -> None:
        super().__init__("netlab_researcher_algorithm_bridge")
        root = Path(os.environ.get("NETLAB_REPO_ROOT", "/workspace/netlab"))
        self.runtime = AlgorithmRuntime(root)
        self.selection_path = Path(os.environ.get("SNAAS_PLUGIN_SELECTION", "/workspace/results/snaas_active_algorithm.json"))
        self.config_path = Path(os.environ.get("SNAAS_CONFIG", "/workspace/shared/snaas_relay_config.json"))
        self.heartbeat_path = Path(os.environ.get("SNAAS_ALGORITHM_HEARTBEAT", "/workspace/results/snaas_algorithm_runtime_heartbeat.json"))
        self.action_pub = self.create_publisher(AlgorithmActionMsg, "/netlab/algorithm/action", 10)
        self.status_pub = self.create_publisher(AlgorithmStatus, "/netlab/algorithm/status_typed", 10)
        self.create_subscription(AlgorithmObservationMsg, "/netlab/algorithm/observation", self._observation_cb, 10)
        self.create_service(ValidateAlgorithm, "/netlab/algorithm/validate", self._validate_cb)
        self.timer = self.create_timer(1.0, self._heartbeat)
        self.deadline_misses = 0
        self.rejection_count = 0
        self.last_state = "IDLE"
        self.last_algorithm_id = ""
        self.last_execution_ms = 0.0
        self.last_error: Dict[str, Any] = {}
        self.get_logger().info("NETLAB researcher algorithm bridge is ready")

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value
        except Exception:
            return default

    def _selection(self) -> Dict[str, Any]:
        value = self._read_json(self.selection_path, {})
        return dict(value) if isinstance(value, Mapping) else {}

    def _publish_status(self, state: str, *, algorithm_id: str = "", revision_id: str = "", accepted: bool = False, fallback: bool = False, details: Mapping[str, Any] | None = None) -> None:
        self.last_state = state
        self.last_algorithm_id = algorithm_id or self.last_algorithm_id
        msg = AlgorithmStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.algorithm_id = self.last_algorithm_id
        msg.algorithm_version = str((details or {}).get("algorithm_version", ""))
        msg.state = state
        msg.run_id = str((details or {}).get("run_id", ""))
        msg.revision_id = revision_id
        msg.worker_healthy = state not in {"FAILED", "TIMEOUT"}
        msg.action_accepted = bool(accepted)
        msg.fallback_active = bool(fallback)
        msg.last_execution_ms = float(self.last_execution_ms)
        msg.deadline_misses = int(self.deadline_misses)
        msg.rejection_count = int(self.rejection_count)
        msg.details_json = json.dumps(dict(details or {}), separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        self.status_pub.publish(msg)

    def _heartbeat(self) -> None:
        selection = self._selection()
        payload = {
            "timestamp": time.time(),
            "ready": True,
            "state": self.last_state,
            "node": self.get_name(),
            "pid": os.getpid(),
            "algorithm_id": selection.get("algorithm_id", selection.get("active", self.last_algorithm_id)),
            "selection_id": selection.get("selection_id", ""),
            "last_execution_ms": self.last_execution_ms,
            "deadline_misses": self.deadline_misses,
            "rejection_count": self.rejection_count,
            "last_error": self.last_error,
        }
        atomic_write_json(self.heartbeat_path, payload)

    def _validate_cb(self, request: ValidateAlgorithm.Request, response: ValidateAlgorithm.Response) -> ValidateAlgorithm.Response:
        try:
            package = self.runtime.registry.get(str(request.algorithm_id))
            response.valid = bool(package.valid)
            response.errors = list(package.errors)
            response.warnings = list(package.warnings)
            response.normalized_manifest_json = json.dumps(package.manifest.to_dict(), separators=(",", ":"), ensure_ascii=False)
        except Exception as exc:
            response.valid = False
            response.errors = [str(exc)]
            response.warnings = []
            response.normalized_manifest_json = "{}"
        return response

    def _observation_cb(self, msg: AlgorithmObservationMsg) -> None:
        selection = self._selection()
        algorithm_id = str(selection.get("algorithm_id", selection.get("active", "")))
        if not algorithm_id:
            self._publish_status("IDLE", revision_id=msg.revision_id)
            return
        try:
            observation = json.loads(msg.payload_json or "{}")
            if not isinstance(observation, Mapping):
                raise TypeError("Algorithm observation payload must be an object")
            observed_hash = canonical_json_hash(observation)
            if msg.observation_hash and observed_hash != msg.observation_hash:
                raise ValueError("Algorithm observation hash mismatch")
            parameters = selection.get("parameters", {}) if isinstance(selection.get("parameters"), Mapping) else {}
            started = time.perf_counter()
            invocation = self.runtime.invoke(algorithm_id, observation, parameters, hook="step")
            self.last_execution_ms = 1000.0 * (time.perf_counter() - started)
            if not invocation.get("ok"):
                error = dict(invocation.get("error", {}))
                if error.get("code") in {"ALGORITHM_TIMEOUT", "ALGORITHM_WORKER_TIMEOUT"}:
                    self.deadline_misses += 1
                    state = "TIMEOUT"
                else:
                    state = "FAILED"
                self.last_error = error
                self._publish_status(state, algorithm_id=algorithm_id, revision_id=msg.revision_id, details={"error": error, "stderr": invocation.get("stderr", "")})
                return
            if invocation.get("pending_external_ros2"):
                self._publish_status("PENDING_EXTERNAL_ROS2", algorithm_id=algorithm_id, revision_id=msg.revision_id, details=invocation.get("result", {}))
                return
            package = self.runtime.registry.get(algorithm_id)
            raw = invocation.get("result", {})
            if not isinstance(raw, Mapping):
                raw = {"metrics": {"result": raw}}
            action = AlgorithmAction.from_mapping(
                raw,
                manifest=package.manifest,
                source_revision_id=str(msg.revision_id or observation.get("revision_id", "runtime-current")),
                duration_s=float(invocation.get("duration_s", 0.0)),
            )
            config = load_experiment(self.config_path)
            shield = __import__("netlab.safety_shield", fromlist=["apply_safety_shield"]).apply_safety_shield(
                action,
                observation,
                config,
                project=True,
                require_connectivity=bool(config.get("swarm", {}).get("controller", {}).get("connectivity_preservation", True)),
            )
            if not shield.accepted:
                self.rejection_count += 1
            outgoing = shield.action if shield.action else action.to_dict()
            action_msg = AlgorithmActionMsg()
            action_msg.header.stamp = self.get_clock().now().to_msg()
            action_msg.schema_version = str(outgoing.get("schema_version", "2.0"))
            action_msg.algorithm_id = algorithm_id
            action_msg.algorithm_version = str(package.manifest.version)
            action_msg.source_revision_id = str(outgoing.get("source_revision_id", msg.revision_id))
            action_msg.action_id = canonical_json_hash(outgoing)[:24]
            action_msg.coordinate_frame = str(outgoing.get("coordinate_frame", "ENU"))
            action_msg.validity_horizon_s = float(outgoing.get("validity_horizon_s", 1.0))
            action_msg.computation_duration_s = float(outgoing.get("computation_duration_s", invocation.get("duration_s", 0.0)))
            action_msg.objective_value = float(outgoing.get("objective_value") or 0.0)
            action_msg.termination_reason = str(outgoing.get("termination_reason", "completed"))
            action_msg.fallback = bool(outgoing.get("fallback", shield.fallback_applied))
            action_msg.payload_json = json.dumps(outgoing.get("payload", {}), separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            action_msg.constraint_residuals_json = json.dumps(outgoing.get("constraint_residuals", {}), separators=(",", ":"), ensure_ascii=False, allow_nan=False)
            self.action_pub.publish(action_msg)
            details = {
                "algorithm_version": package.manifest.version,
                "action_id": action_msg.action_id,
                "shield": shield.to_dict(),
                "observation_hash": observed_hash,
            }
            self._publish_status(
                "ACTION_ACCEPTED" if shield.accepted else "ACTION_REJECTED_FALLBACK",
                algorithm_id=algorithm_id,
                revision_id=msg.revision_id,
                accepted=shield.accepted,
                fallback=shield.fallback_applied,
                details=details,
            )
            self.last_error = {}
        except Exception as exc:
            self.last_error = {"code": "ALGORITHM_BRIDGE_EXCEPTION", "type": type(exc).__name__, "message": str(exc)}
            self._publish_status("FAILED", algorithm_id=algorithm_id, revision_id=msg.revision_id, details={"error": self.last_error})
            self.get_logger().error(f"Algorithm bridge failed: {exc}")


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = ResearcherAlgorithmBridge()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
