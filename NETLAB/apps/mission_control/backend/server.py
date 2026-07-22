"""NETLAB Mission Control HTTP API and static-file server.

The server exposes acknowledged commands rather than optimistic UI actions. Long
operations execute as jobs and retain structured status for the operator.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import mimetypes
import os
import threading
import time
import traceback
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional
import sys

# Make direct execution and service launch resolve the repository package identically.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from netlab.config import (
    configuration_hash,
    default_experiment,
    emit_legacy_config,
    load_experiment,
    migrate_legacy_config,
    save_experiment,
    validate_experiment,
)
from netlab.diagnostics import packet_diagnose, system_diagnose
from netlab.evidence import index_evidence
from netlab.link import LinkRequest, compute_analytical_link, evaluate_feasibility
from netlab.models import RuntimePhase
from netlab.orchestrator import Orchestrator
from netlab.plugins import discover, inspect_plugin, invoke_isolated, template, validate_position_plan
from netlab.algorithm_runtime import AlgorithmRuntime
from netlab.algorithm_contracts import ALGORITHM_API_VERSION
from netlab.state import StateStore, atomic_write_json, read_json, tail_jsonl
from netlab.support import generate_support_bundle
from netlab.telemetry import TelemetryReader
from netlab.topology import build_edges, graph_metrics, normalize_branches, validate_config_topology
from netlab.version import API_VERSION, __version__
from netlab.revisions import RevisionManager
from netlab.synchronization import RuntimeSynchronizer
from netlab.research_tools import (
    probabilistic_a2g_path_loss,
    ntn_slant_range_delay,
    edge_offloading,
    inverse_distance_radio_map,
    calibrate_log_distance,
)
from netlab.security import validate_asset


@dataclass
class Job:
    job_id: str
    name: str
    status: str = "QUEUED"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress: list[Dict[str, Any]] = field(default_factory=list)
    result: Any = None
    error: Any = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "progress": self.progress[-200:],
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="netlab-job")

    def submit(self, name: str, function: Callable[[Callable[[str, Mapping[str, Any]], None]], Any]) -> Job:
        job = Job(job_id=str(uuid.uuid4()), name=name)
        with self._lock:
            self._jobs[job.job_id] = job

        def run() -> None:
            job.status = "RUNNING"
            job.started_at = time.time()
            def progress(stage: str, payload: Mapping[str, Any]) -> None:
                with self._lock:
                    job.progress.append({"stage": stage, "timestamp": time.time(), **dict(payload)})
            try:
                job.result = function(progress)
                job.status = "COMPLETED" if isinstance(job.result, Mapping) and job.result.get("ok", True) else "FAILED"
                if job.status == "FAILED":
                    job.error = job.result.get("error") if isinstance(job.result, Mapping) else "operation failed"
            except Exception as exc:
                job.status = "FAILED"
                job.error = {"code": "JOB_EXCEPTION", "message": str(exc), "traceback": traceback.format_exc(limit=20)}
            finally:
                job.completed_at = time.time()

        self._executor.submit(run)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Dict[str, Any]]:
        with self._lock:
            return [job.as_dict() for job in sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)[:100]]


class MissionControlApplication:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.orchestrator = Orchestrator(self.root)
        self.store = StateStore(self.root)
        self.jobs = JobManager()
        self.static_root = self.root / "apps" / "mission_control" / "frontend"
        self.plugin_root = self.root / "plugins" / "controllers"
        self.plugin_root.mkdir(parents=True, exist_ok=True)
        self._config_lock = threading.RLock()
        self.telemetry = TelemetryReader(self.root)
        self.revisions = RevisionManager(self.root)
        self.synchronizer = RuntimeSynchronizer(self.root, self.orchestrator.compose)
        self.algorithms = AlgorithmRuntime(self.root)

    def load_config(self) -> Dict[str, Any]:
        with self._config_lock:
            return load_experiment(self.store.paths.config)

    def save_config(self, value: Mapping[str, Any], *, sync: bool = True, command_id: str = "") -> Dict[str, Any]:
        """Persist a validated draft and, when live, apply one revision transaction.

        Durable persistence is never confused with runtime commitment.  An
        offline ROS/Sionna/Isaac participant leaves the revision explicitly
        pending and the UI can retry through the Synchronization module.
        """
        with self._config_lock:
            validation = validate_experiment(value, strict=True)
            if not validation.get("ok"):
                return {
                    "ok": False,
                    "durable_saved": False,
                    "committed": False,
                    "validation": validation,
                    "error": {
                        "code": "CONFIG_VALIDATION_FAILED",
                        "message": "Experiment configuration is invalid.",
                        "details": validation.get("errors", []),
                    },
                }
            config = validation["config"]
            payload = save_experiment(self.store.paths.config, config, emit_legacy=True)
            config_hash = configuration_hash(config)
            record = self.revisions.create(
                config,
                reason="configuration_saved",
                command_id=command_id,
                initiator="mission_control",
                required_participants=("ros", "sionna", "isaac"),
                affected_entities=("experiment", "swarm", "topology", "antennas", "world", "traffic", "failures"),
            )
            self.store.update(
                {
                    "experiment_id": config["experiment"]["id"],
                    "config_hash": config_hash,
                    "topology": config["topology"],
                    "desired_revision_id": record["revision_id"],
                    "synchronization_state": "PENDING_RUNTIME_APPLY" if sync else "DRAFT_SAVED",
                },
                event_type="CONFIGURATION_SAVED",
                component="mission_control",
            )

            transaction: Dict[str, Any] = {
                "revision_id": record["revision_id"],
                "committable": False,
                "pending": ["ros", "sionna", "isaac"],
                "participants": {},
            }
            committed = False
            if sync:
                observed = self.orchestrator.status()
                readiness = observed.get("readiness", {}) if isinstance(observed, Mapping) else {}
                participants_live = bool(
                    readiness.get("ros_container_ready")
                    and readiness.get("sionna_ready")
                    and readiness.get("isaac_process_ready")
                )
                if participants_live:
                    transaction = self.synchronizer.apply(
                        record,
                        ros_timeout_s=20.0,
                        sionna_timeout_s=10.0,
                        isaac_timeout_s=45.0,
                        offline_is_pending=True,
                    )
                    if transaction.get("committable"):
                        self.revisions.commit(record["revision_id"])
                        committed = True
                        self.store.update(
                            {
                                "committed_revision_id": record["revision_id"],
                                "synchronization_state": "IN_SYNC",
                            },
                            event_type="RUNTIME_REVISION_COMMITTED",
                            component="mission_control",
                        )
            synchronization = self.revisions.status(record["revision_id"])
            command_status = "COMPLETED" if committed else ("PARTIALLY_APPLIED" if sync else "COMPLETED")
            return {
                "ok": True,
                "durable_saved": True,
                "runtime_applied": committed,
                "runtime_application_status": "COMMITTED" if committed else ("PENDING_RUNTIME_APPLY" if sync else "DRAFT_SAVED"),
                "committed": committed,
                "config": config,
                "legacy_payload": payload,
                "config_hash": config_hash,
                "validation": validation,
                "revision": self.revisions.read(record["revision_id"]),
                "transaction": transaction,
                "synchronization": synchronization,
                "command_status": command_status,
            }

    def publish_ros_string(self, topic: str, payload: Any) -> Dict[str, Any]:
        container = self.orchestrator.compose.service_container_name("ros2-core", "netlab-ros2-core")
        if not container:
            return {"ok": False, "status": "OFFLINE", "error": {"code": "ROS_CONTAINER_NOT_FOUND", "message": "ROS runtime is not available; the durable configuration was still saved."}}
        text = payload if isinstance(payload, str) else json.dumps(payload, separators=(",", ":"))
        escaped = text.replace("'", "'\"'\"'")
        command = (
            "source /opt/ros/jazzy/setup.bash >/dev/null 2>&1; "
            "cd /workspace/ros2; [ -f install/setup.bash ] && source install/setup.bash; "
            f"timeout 12 ros2 topic pub --once {topic} std_msgs/msg/String \"{{data: '{escaped}'}}\""
        )
        try:
            result = self.orchestrator.compose.exec("ros2-core", command, timeout=20, fallback="netlab-ros2-core")
            return {"ok": result.ok, "status": "ACKNOWLEDGED" if result.ok else "FAILED", "result": result.as_dict()}
        except Exception as exc:
            return {"ok": False, "status": "FAILED", "error": {"code": "ROS_PUBLISH_FAILED", "message": str(exc)}}

    def publish_runtime_config(self, legacy_payload: Mapping[str, Any]) -> Dict[str, Any]:
        return self.publish_ros_string("/swarm/control/update_config", legacy_payload)

    def wait_runtime_status(self, predicate: Callable[[Mapping[str, Any]], bool], *, timeout_s: float = 8.0, description: str = "runtime acknowledgement") -> Dict[str, Any]:
        started = time.monotonic()
        last: Dict[str, Any] = {}
        while time.monotonic() - started < max(0.1, timeout_s):
            last = read_json(self.store.paths.legacy_status, {}) or {}
            try:
                if last and predicate(last):
                    return {"ok": True, "status": "ACKNOWLEDGED", "description": description, "elapsed_s": round(time.monotonic() - started, 3), "latest_status": last}
            except Exception:
                pass
            time.sleep(0.1)
        return {
            "ok": False,
            "status": "TIMEOUT",
            "description": description,
            "elapsed_s": round(time.monotonic() - started, 3),
            "latest_status": last,
            "error": {"code": "RUNTIME_ACK_TIMEOUT", "message": f"Timed out while waiting for {description}."},
        }

    def _start_experiment_job(self, progress: Callable[[str, Mapping[str, Any]], None]) -> Dict[str, Any]:
        command = self.store.create_command("start_experiment", {}, component="mission_control")
        config = self.load_config()
        validation = validate_experiment(config, strict=False)
        progress("configuration_validation", {"ok": validation.get("ok"), "errors": validation.get("errors", [])})
        if not validation["ok"]:
            error = {"code": "CONFIG_INVALID", "message": "Experiment validation failed.", "details": validation}
            return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error}
        readiness = self.orchestrator.status()
        packet_ready = bool(readiness.get("readiness", {}).get("packet_runtime_ready"))
        if not packet_ready:
            error = {
                "code": "PACKET_RUNTIME_NOT_READY",
                "message": "The experiment cannot enter RUNNING because the authoritative packet runtime is not ready.",
                "details": readiness,
                "recommendation": "Start the complete stack and run Packet Doctor before starting the experiment.",
            }
            return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error}
        state = self.store.start_run(config)
        ros = self.publish_runtime_config(emit_legacy_config(config))
        progress("ros_configuration", ros)
        if not ros.get("ok"):
            error = {
                "code": "ROS_CONFIGURATION_NOT_ACKNOWLEDGED",
                "message": "The experiment configuration was not acknowledged by the ROS 2 transport.",
                "details": ros,
                "recommendation": "Inspect the ROS container, graph, and packet runtime before retrying.",
            }
            self.store.set_phase(RuntimePhase.DEGRADED, error=error)
            return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error, "state": state}
        sync = self.orchestrator.synchronize("experiment_started")
        progress("isaac_synchronization", sync)
        if not sync.get("ok"):
            error = sync.get("error", {"code": "ISAAC_SYNC_FAILED", "message": "Isaac did not acknowledge the experiment revision."})
            self.store.set_phase(RuntimePhase.DEGRADED, error=error)
            return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error, "state": state, "ros": ros, "sync": sync}
        state = self.store.update({"phase": RuntimePhase.RUNNING.value}, event_type="EXPERIMENT_STARTED", component="mission_control", command_id=command["command_id"])
        completed = self.store.acknowledge_command(command, status="COMPLETED", acknowledgement={"ros": ros, "sync": sync, "state": state})
        return {"ok": True, "command": completed, "state": state, "ros": ros, "sync": sync}

    def command(self, name: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        if name in {"start_stack", "restart_stack"}:
            operation = self.orchestrator.start_stack if name == "start_stack" else self.orchestrator.restart_stack
            job = self.jobs.submit(name, lambda progress: operation(build=bool(payload.get("build", True)), callback=progress))
            return {"ok": True, "accepted": True, "job": job.as_dict()}
        if name == "stop_stack":
            job = self.jobs.submit(name, lambda _progress: self.orchestrator.stop_stack())
            return {"ok": True, "accepted": True, "job": job.as_dict()}
        if name == "sync_isaac":
            job = self.jobs.submit(name, lambda _progress: self.orchestrator.synchronize(str(payload.get("reason", "operator_request"))))
            return {"ok": True, "accepted": True, "job": job.as_dict()}
        if name in {"fail_uav", "heal_uav", "standby_uav", "reset_chain"}:
            topic_map = {
                "fail_uav": "/swarm/control/fail_drone",
                "heal_uav": "/swarm/control/heal_drone",
                "standby_uav": "/swarm/control/standby_drone",
                "reset_chain": "/swarm/control/reset_chain",
            }
            index = int(payload.get("index", payload.get("uav_id", 0)) or 0)
            value = str(index) if name != "reset_chain" else "reset"
            command = self.store.create_command(name, payload)
            ros = self.publish_ros_string(topic_map[name], value)
            if not ros["ok"]:
                status = self.store.acknowledge_command(command, status="FAILED", error=ros.get("error", ros))
                return {"ok": False, "command": status, "error": ros.get("error", ros)}

            if name == "fail_uav":
                predicate = lambda st: index in [int(v) for v in st.get("failed_indices", [])]
                timeout_s = 12.0
                description = f"UAV {index} failure state"
            elif name == "heal_uav":
                predicate = lambda st: index not in [int(v) for v in st.get("failed_indices", [])] and index in [int(v) for v in st.get("visible_drone_indices", [])]
                timeout_s = 8.0
                description = f"UAV {index} healed state"
            elif name == "standby_uav":
                predicate = lambda st: index in [int(v) for v in st.get("standby_indices", [])]
                timeout_s = 8.0
                description = f"UAV {index} standby state"
            else:
                predicate = lambda st: not st.get("failed_indices") and not bool(st.get("connectivity_paused"))
                timeout_s = 10.0
                description = "chain reset state"
            runtime_ack = self.wait_runtime_status(predicate, timeout_s=timeout_s, description=description)
            if runtime_ack["ok"]:
                self.store.write_sync_signal(name, command_id=command["command_id"])
                status = self.store.acknowledge_command(command, status="COMPLETED", acknowledgement={"transport": ros, "runtime": runtime_ack})
                return {"ok": True, "command": status, "ros": ros, "runtime_ack": runtime_ack}
            status = self.store.acknowledge_command(command, status="FAILED", error=runtime_ack.get("error"))
            return {"ok": False, "command": status, "ros": ros, "runtime_ack": runtime_ack, "error": runtime_ack.get("error")}
        if name == "promote_standby":
            index = int(payload.get("index", 0))
            command = self.store.create_command(name, payload)
            config = self.load_config()
            found = False
            for drone in config["swarm"]["drones"]:
                if int(drone["index"]) == index:
                    drone["role"] = "relay"
                    drone["active"] = True
                    found = True
            if not found:
                error = {"code": "UAV_NOT_FOUND", "message": f"No UAV has index {index}."}
                return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error}
            config["swarm"]["relay_count"] = sum(1 for d in config["swarm"]["drones"] if d.get("role") != "standby")
            config["swarm"]["standby_count"] = config["swarm"]["drone_count"] - config["swarm"]["relay_count"]
            saved = self.save_config(config, sync=True, command_id=command["command_id"])
            if not saved.get("runtime_applied"):
                error = saved.get("ros", {}).get("error", {"code": "PROMOTION_NOT_APPLIED", "message": "The promotion was saved but not applied to ROS 2."})
                return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error, "save": saved}
            runtime_ack = self.wait_runtime_status(
                lambda st: index not in [int(v) for v in st.get("standby_indices", [])] and index in [int(v) for v in st.get("visible_drone_indices", [])],
                timeout_s=10.0,
                description=f"UAV {index} standby promotion",
            )
            if not runtime_ack["ok"]:
                return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=runtime_ack.get("error")), "error": runtime_ack.get("error"), "save": saved, "runtime_ack": runtime_ack}
            completed = self.store.acknowledge_command(command, status="COMPLETED", acknowledgement={"runtime": runtime_ack, "config_hash": saved["config_hash"]})
            return {"ok": True, "command": completed, "save": saved, "runtime_ack": runtime_ack}
        if name in {"hold", "resume", "takeoff", "land", "emergency_stop", "return_home", "stop_experiment"}:
            command = self.store.create_command(name, payload)
            ros = self.publish_ros_string("/swarm/control/mission_command", {"command": name, "command_id": command["command_id"], **dict(payload)})
            if not ros["ok"]:
                acknowledged = self.store.acknowledge_command(command, status="FAILED", error=ros)
                return {"ok": False, "command": acknowledged, "ros": ros, "error": ros.get("error", ros)}
            runtime_ack = self.wait_runtime_status(
                lambda st: str(st.get("last_mission_command_id", "")) == command["command_id"],
                timeout_s=8.0,
                description=f"mission command {name}",
            )
            if not runtime_ack["ok"]:
                acknowledged = self.store.acknowledge_command(command, status="FAILED", error=runtime_ack.get("error"))
                return {"ok": False, "command": acknowledged, "ros": ros, "runtime_ack": runtime_ack, "error": runtime_ack.get("error")}
            if name == "stop_experiment":
                self.store.set_phase(RuntimePhase.COMPLETED)
            acknowledged = self.store.acknowledge_command(command, status="COMPLETED", acknowledgement={"transport": ros, "runtime": runtime_ack})
            return {"ok": True, "command": acknowledged, "ros": ros, "runtime_ack": runtime_ack}
        if name == "start_experiment":
            job = self.jobs.submit(name, self._start_experiment_job)
            return {"ok": True, "accepted": True, "job": job.as_dict()}
        if name == "recompute_topology":
            command = self.store.create_command(name, payload)
            config = self.load_config()
            validation = validate_config_topology(config)
            if not validation["structurally_valid"]:
                error = {"code": "TOPOLOGY_INVALID", "message": "Topology cannot be recomputed until structural errors are fixed.", "details": validation}
                return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error}
            before = read_json(self.store.paths.legacy_status, {}) or {}
            before_version = int(before.get("chain_version", 0) or 0)
            ros = self.publish_runtime_config(emit_legacy_config(config))
            if not ros.get("ok"):
                error = ros.get("error", {"code": "TOPOLOGY_RUNTIME_UNAVAILABLE", "message": "ROS 2 did not accept the topology update."})
                return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "error": error, "ros": ros}
            runtime_ack = self.wait_runtime_status(
                lambda st: int(st.get("chain_version", 0) or 0) > before_version,
                timeout_s=10.0,
                description="topology recomputation",
            )
            if not runtime_ack["ok"]:
                return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=runtime_ack.get("error")), "error": runtime_ack.get("error"), "ros": ros, "runtime_ack": runtime_ack}
            self.store.write_sync_signal("topology_recomputed", command_id=command["command_id"])
            completed = self.store.acknowledge_command(command, status="COMPLETED", acknowledgement={"runtime": runtime_ack, "transport": ros})
            return {"ok": True, "command": completed, "topology": validation, "ros": ros, "runtime_ack": runtime_ack}
        return {"ok": False, "error": {"code": "UNKNOWN_COMMAND", "message": name}}

    def update_swarm(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        config = self.load_config()
        drones = config["swarm"]["drones"]
        updates = payload.get("drones") if isinstance(payload.get("drones"), list) else []
        by_id = {str(item["id"]): item for item in drones}
        for update in updates:
            if not isinstance(update, Mapping):
                continue
            drone_id = str(update.get("id", ""))
            if drone_id not in by_id:
                return {"ok": False, "error": {"code": "UNKNOWN_UAV", "message": drone_id}}
            target = by_id[drone_id]
            for key in ("position", "orientation_xyzw", "role", "active", "battery_soc_pct", "antenna_id"):
                if key in update:
                    target[key] = update[key]
        return self.save_config(config, sync=True)

    def update_topology(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """Atomically update graph structure and the embodied node inventory."""
        config = self.load_config()
        proposed = payload.get("topology", payload)
        if isinstance(proposed, Mapping):
            config["topology"].update(dict(proposed))

        if isinstance(payload.get("drones"), list):
            incoming = [dict(item) for item in payload["drones"] if isinstance(item, Mapping)]
            if payload.get("replace_inventory"):
                config["swarm"]["drones"] = incoming
            else:
                existing = {str(item.get("id")): item for item in config["swarm"].get("drones", [])}
                for item in incoming:
                    existing[str(item.get("id"))] = item
                config["swarm"]["drones"] = list(existing.values())
        if isinstance(payload.get("station"), Mapping):
            config["station"] = dict(payload["station"])

        drones = config["swarm"].get("drones", [])
        config["swarm"]["drone_count"] = len(drones)
        config["swarm"]["relay_count"] = sum(1 for drone in drones if drone.get("role") != "standby")
        config["swarm"]["standby_count"] = sum(1 for drone in drones if drone.get("role") == "standby")
        if "branches" in config["topology"]:
            config["topology"]["branches"] = normalize_branches(config["topology"]["branches"])
            config["topology"]["branch_count"] = len(config["topology"]["branches"])

        validation = validate_config_topology(config)
        if not validation["structurally_valid"] or not validation["physically_valid"]:
            return {
                "ok": False,
                "committed": False,
                "error": {
                    "code": "TOPOLOGY_VALIDATION_FAILED",
                    "message": "The proposed topology is not structurally and physically valid.",
                    "details": validation,
                },
                "topology_validation": validation,
            }
        saved = self.save_config(config, sync=bool(payload.get("sync", True)))
        saved["topology_validation"] = validation
        return saved

    def evaluate_link_preview(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        config = self.load_config()
        request = LinkRequest.from_mapping(payload)
        metrics = compute_analytical_link(request)
        comm = config["communication"]
        decision = evaluate_feasibility(
            metrics,
            source_active=bool(payload.get("source_active", True)),
            destination_active=bool(payload.get("destination_active", True)),
            source_failed=bool(payload.get("source_failed", False)),
            destination_failed=bool(payload.get("destination_failed", False)),
            operational_range_m=float(comm["operational_range_m"]),
            hard_outage_distance_m=float(comm["hard_outage_distance_m"]),
            min_snr_db=float(comm["min_snr_db"]),
            min_sinr_db=float(comm.get("min_sinr_db", comm["min_snr_db"])),
            min_capacity_mbps=float(comm["min_capacity_mbps"]),
            metric_ttl_s=float(comm["metric_ttl_s"]),
        )
        return {"ok": True, "source": "PREVIEW", "metrics": metrics.as_dict(), "gate": decision.as_dict(), "decision": decision.as_dict()}

    def guided_demo(self, step: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        def preflight_step() -> Dict[str, Any]:
            result = self.orchestrator.preflight()
            return {
                "ok": bool(result.get("ok")),
                "preflight": result,
                "error": None if result.get("ok") else {
                    "code": "PREFLIGHT_FAILED",
                    "message": "Preflight reported blocking findings.",
                    "details": result,
                },
            }

        def require_config_application(config: Mapping[str, Any], reason: str) -> Dict[str, Any]:
            saved = self.save_config(config, sync=True)
            if not saved.get("runtime_applied"):
                return {
                    "ok": False,
                    "error": {
                        "code": "DEMO_CONFIG_NOT_APPLIED",
                        "message": "The demonstration configuration was saved durably but ROS 2 did not acknowledge it.",
                        "details": saved.get("ros"),
                    },
                    "save": saved,
                }
            sync = self.orchestrator.synchronize(reason)
            if not sync.get("ok"):
                return {"ok": False, "error": sync.get("error"), "save": saved, "sync": sync}
            return {"ok": True, "save": saved, "sync": sync}

        def load_reference_step() -> Dict[str, Any]:
            return require_config_application(default_experiment(), "guided_demo_reference_loaded")

        def verify_isaac_step() -> Dict[str, Any]:
            status = self.store.sync_status(timeout_s=20.0)
            ok = bool(status.get("acknowledged") and status.get("heartbeat_freshness", {}).get("fresh"))
            return {
                "ok": ok,
                "sync": status,
                "error": None if ok else {
                    "code": "ISAAC_NOT_ACKNOWLEDGED",
                    "message": "Isaac heartbeat or scenario acknowledgement is not current.",
                    "details": status,
                },
            }

        def wait_packet(*, advancing: Optional[bool] = None, paused: Optional[bool] = None, timeout_s: float = 20.0) -> Dict[str, Any]:
            started = time.monotonic()
            last: Dict[str, Any] = {}
            while time.monotonic() - started < timeout_s:
                last = packet_diagnose(self.root, self.orchestrator.compose)
                heartbeat = last.get("heartbeat", {}) if isinstance(last.get("heartbeat"), Mapping) else {}
                conditions = [bool(last.get("ok"))]
                if advancing is not None:
                    conditions.append(bool(heartbeat.get("packet_advancing")) is advancing)
                if paused is not None:
                    conditions.append(bool(heartbeat.get("connectivity_paused")) is paused)
                if all(conditions):
                    return {"ok": True, "diagnostics": last, "elapsed_s": round(time.monotonic() - started, 3)}
                time.sleep(0.5)
            return {
                "ok": False,
                "diagnostics": last,
                "error": {
                    "code": "PACKET_CONDITION_TIMEOUT",
                    "message": "The authoritative packet runtime did not reach the expected demonstration state.",
                    "details": {"advancing": advancing, "paused": paused, "last": last},
                },
            }

        def switch_topology_step() -> Dict[str, Any]:
            config = self.load_config()
            config["topology"].update({
                "mode": "parallel",
                "branch_count": 2,
                "branches": [[1, 2, 3], [4, 5, 6]],
                "sinks": ["drone_3", "drone_6"],
                "manual_edges": [],
            })
            base_flow = dict(config["traffic"]["flows"][0])
            flow_a = {**base_flow, "id": "guided_branch_a", "destination": "drone_3", "branch_id": "branch_0"}
            flow_b = {**base_flow, "id": "guided_branch_b", "destination": "drone_6", "branch_id": "branch_1"}
            config["traffic"]["flows"] = [flow_a, flow_b]
            return require_config_application(config, "guided_demo_parallel_topology")

        def move_uav_step() -> Dict[str, Any]:
            config = self.load_config()
            drone = next(item for item in config["swarm"]["drones"] if int(item["index"]) == 2)
            x, y, z = [float(value) for value in drone["position"]]
            drone["position"] = [x, y + 6.0, z]
            return require_config_application(config, "guided_demo_uav_coordinate_change")

        def antenna_step() -> Dict[str, Any]:
            config = self.load_config()
            antenna = next(item for item in config["antennas"]["definitions"] if item["id"] == "uav_omni_reference")
            antenna["gain_dbi"] = round(float(antenna.get("gain_dbi", 0.0)) + 0.5, 3)
            return require_config_application(config, "guided_demo_antenna_change")

        def world_step() -> Dict[str, Any]:
            config = self.load_config()
            environment = config["world"]["environment"]
            environment["wind_speed_mps"] = round(float(environment.get("wind_speed_mps", 0.0)) + 0.5, 3)
            return require_config_application(config, "guided_demo_world_change")

        algorithm_id = str(payload.get("algorithm_id", "connectivity_aware_formation"))
        algorithm_parameters = payload.get("parameters", {}) if isinstance(payload.get("parameters", {}), Mapping) else {}

        def inspect_algorithm_step() -> Dict[str, Any]:
            package = self.algorithms.registry.get(algorithm_id)
            return {"ok": package.valid, "algorithm": package.to_dict(), "api_version": ALGORITHM_API_VERSION}

        def validate_algorithm_step() -> Dict[str, Any]:
            package = self.algorithms.registry.get(algorithm_id)
            return {"ok": package.valid, "algorithm": package.to_dict(), "errors": list(package.errors)}

        def dry_run_algorithm_step(*, negative: bool = False) -> Dict[str, Any]:
            return self.algorithms.dry_run(
                algorithm_id,
                parameters=algorithm_parameters,
                negative_test=negative,
            )

        def activate_algorithm_step() -> Dict[str, Any]:
            activation = self.algorithms.activate(algorithm_id, algorithm_parameters)
            if not activation.get("ok"):
                return activation
            config = self.load_config()
            config.setdefault("swarm", {}).setdefault("controller", {})
            config["swarm"]["controller"].update({
                "type": "plugin",
                "plugin_id": algorithm_id,
                "algorithm_api_version": ALGORITHM_API_VERSION,
                "parameters": dict(algorithm_parameters),
                "safe_fallback": activation["selection"].get("safety_fallback", "hold_position"),
            })
            config["algorithm"] = {
                "algorithm_id": algorithm_id,
                "version": activation["selection"].get("version"),
                "source_hash": activation["selection"].get("source_hash"),
                "parameters": dict(algorithm_parameters),
                "selection_id": activation["selection"].get("selection_id"),
            }
            applied = require_config_application(config, "guided_demo_algorithm_activation")
            return {"ok": bool(applied.get("ok")), "activation": activation, "application": applied}

        def compare_algorithm_step() -> Dict[str, Any]:
            return self.algorithms.compare(
                [algorithm_id, "researcher_chain_spacing"],
                parameters={algorithm_id: dict(algorithm_parameters)},
                replications=int(payload.get("replications", 3)),
                seed=int(payload["seed"]) if payload.get("seed") is not None else None,
            )

        actions = {
            "preflight": preflight_step,
            "verify_environment": lambda: system_diagnose(self.root, self.orchestrator.compose),
            "start_stack": lambda: self.command("start_stack", payload),
            "verify_services": lambda: system_diagnose(self.root, self.orchestrator.compose),
            "load_example": load_reference_step,
            "sync_mission": lambda: self.command("sync_isaac", {"reason": "guided_demo_explicit_sync"}),
            "verify_isaac": verify_isaac_step,
            "start_experiment": lambda: self.command("start_experiment", payload),
            "verify_packet": lambda: wait_packet(advancing=True, paused=False, timeout_s=30.0),
            "inspect_algorithm": inspect_algorithm_step,
            "validate_algorithm": validate_algorithm_step,
            "dry_run_algorithm": lambda: dry_run_algorithm_step(negative=False),
            "reject_invalid_algorithm_output": lambda: dry_run_algorithm_step(negative=True),
            "activate_algorithm": activate_algorithm_step,
            "compare_algorithm": compare_algorithm_step,
            "inject_failure": lambda: self.command("fail_uav", {"index": int(payload.get("index", 3))}),
            "observe_outage": lambda: wait_packet(paused=True, timeout_s=20.0),
            "recompute": lambda: self.command("recompute_topology", payload),
            "promote_standby": lambda: self.command("promote_standby", {"index": int(payload.get("index", 7))}),
            "verify_recovery": lambda: wait_packet(advancing=True, paused=False, timeout_s=30.0),
            "switch_topology": switch_topology_step,
            "move_uav": move_uav_step,
            "modify_antenna": antenna_step,
            "modify_world": world_step,
            "export_evidence": lambda: {"ok": True, "index": index_evidence(self.store.paths.results)},
            "stop_experiment": lambda: self.command("stop_experiment", payload),
            "stop_stack": lambda: self.command("stop_stack", payload),
        }
        if step not in actions:
            return {"ok": False, "error": {"code": "UNKNOWN_OR_MANUAL_DEMO_STEP", "message": step}}
        return actions[step]()


class Handler(BaseHTTPRequestHandler):
    server_version = "NETLABMissionControl/5"

    @property
    def app(self) -> MissionControlApplication:
        return self.server.app  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        self.app.store.append_event("HTTP_ACCESS", {"client": self.client_address[0], "request": format % args}, component="mission_control", severity="DEBUG")

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > 16 * 1024 * 1024:
            raise ValueError("request body exceeds 16 MiB")
        raw = self.rfile.read(length) if length else b"{}"
        value = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(value, dict):
            raise ValueError("JSON request root must be an object")
        return value

    def _serve_static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        if relative == "": relative = "index.html"
        requested = (self.app.static_root / relative).resolve()
        try:
            requested.relative_to(self.app.static_root.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if requested.is_dir():
            requested = requested / "index.html"
        if not requested.exists() or not requested.is_file():
            # SPA route fallback.
            requested = self.app.static_root / "index.html"
        data = requested.read_bytes()
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        if requested.suffix.lower() == ".js":
            content_type = "text/javascript"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") or "javascript" in content_type else content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _sse_telemetry(self, *, once: bool = False) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close" if once else "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        if once:
            self.close_connection = True
        sequence = 0
        while True:
            try:
                sequence += 1
                payload = self.app.telemetry.snapshot()
                encoded = json.dumps(payload, separators=(",", ":"), default=str)
                frame = f"id: {sequence}\nevent: telemetry\ndata: {encoded}\n\n".encode("utf-8")
                self.wfile.write(frame)
                self.wfile.flush()
                if once:
                    break
                time.sleep(1.0)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                break
            except Exception as exc:
                try:
                    error = json.dumps({"ok": False, "error": {"code": "TELEMETRY_STREAM_ERROR", "message": str(exc)}})
                    self.wfile.write(f"event: error\ndata: {error}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    pass
                break

    def do_HEAD(self) -> None:  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/"):
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "GET, POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        relative = path.lstrip("/") or "index.html"
        requested = (self.app.static_root / relative).resolve()
        try:
            requested.relative_to(self.app.static_root.resolve())
        except ValueError:
            self.send_response(HTTPStatus.FORBIDDEN)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if not requested.is_file():
            requested = self.app.static_root / "index.html"
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        if requested.suffix.lower() == ".js":
            content_type = "text/javascript"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") or "javascript" in content_type else content_type)
        self.send_header("Content-Length", str(requested.stat().st_size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/telemetry/stream":
                self._sse_telemetry(once=query.get("once", ["0"])[0] in {"1", "true", "yes"})
                return
            if path == "/api/health":
                self._json({"ok": True, "service": "NETLAB Mission Control", "version": __version__, "api_version": API_VERSION, "time": time.time()})
            elif path == "/api/readiness":
                self._json(self.app.orchestrator.status())
            elif path == "/api/status":
                self._json(self.app.store.read())
            elif path == "/api/config":
                config = self.app.load_config()
                self._json({"ok": True, "config": config, "hash": configuration_hash(config), "validation": validate_experiment(config, strict=False)})
            elif path == "/api/topology":
                config = self.app.load_config()
                validation = validate_config_topology(config)
                self._json({"ok": True, "topology": config["topology"], "drones": config["swarm"]["drones"], "validation": validation, "metrics": validation.get("metrics", {})})
            elif path == "/api/telemetry":
                self._json(self.app.telemetry.snapshot())
            elif path == "/api/events":
                self._json({"ok": True, "events": tail_jsonl(self.app.store.paths.event_log, int(query.get("limit", [100])[0]))})
            elif path == "/api/jobs":
                self._json({"ok": True, "jobs": self.app.jobs.list()})
            elif path.startswith("/api/jobs/"):
                job = self.app.jobs.get(path.rsplit("/", 1)[-1])
                self._json({"ok": bool(job), "job": job.as_dict() if job else None}, 200 if job else 404)
            elif path == "/api/diagnostics":
                self._json(system_diagnose(self.app.root, self.app.orchestrator.compose))
            elif path == "/api/packet-doctor":
                self._json(packet_diagnose(self.app.root, self.app.orchestrator.compose))
            elif path == "/api/plugins":
                # Legacy flat-controller registry remains available for compatibility.
                self._json({"ok": True, "plugins": discover(self.app.plugin_root), "api_version": "1.0"})
            elif path == "/api/actions":
                registry = read_json(self.app.root / "apps" / "mission_control" / "action_registry.json", {}) or {}
                self._json({"ok": True, **registry})
            elif path == "/api/algorithms":
                self._json(self.app.algorithms.registry.summary())
            elif path == "/api/algorithm/source":
                algorithm_id = str(query.get("algorithm_id", [""])[0])
                try:
                    package = self.app.algorithms.registry.get(algorithm_id)
                    self._json({"ok": True, "algorithm_id": algorithm_id, "entrypoint": package.manifest.entrypoint, "source": package.entrypoint.read_text(encoding="utf-8"), "source_hash": package.manifest.source_hash})
                except KeyError:
                    self._json({"ok": False, "error": {"code": "ALGORITHM_NOT_FOUND", "message": algorithm_id}}, 404)
            elif path.startswith("/api/algorithms/"):
                algorithm_id = path.rsplit("/", 1)[-1]
                try:
                    package = self.app.algorithms.registry.get(algorithm_id)
                    self._json({"ok": True, "algorithm": package.to_dict()})
                except KeyError:
                    self._json({"ok": False, "error": {"code": "ALGORITHM_NOT_FOUND", "message": algorithm_id}}, 404)
            elif path == "/api/algorithm/selection":
                self._json({"ok": True, "selection": read_json(self.app.algorithms.selection_path, {}) or {}})
            elif path == "/api/algorithm/runs":
                records = []
                for item in sorted(self.app.algorithms.results_dir.iterdir(), key=lambda value: value.stat().st_mtime, reverse=True) if self.app.algorithms.results_dir.exists() else []:
                    if item.is_dir():
                        result = read_json(item / "result.json", {}) or {}
                        records.append({"run_id": item.name, "result": result, "mtime": item.stat().st_mtime})
                    elif item.suffix == ".json":
                        records.append({"run_id": item.stem, "result": read_json(item, {}) or {}, "mtime": item.stat().st_mtime})
                self._json({"ok": True, "runs": records[:100]})
            elif path == "/api/evidence":
                self._json({"ok": True, "index": index_evidence(self.app.store.paths.results)})
            elif path in {"/api/guide", "/api/guided-demo"}:
                self._json({"ok": True, "steps": guided_demo_steps()})
            elif path == "/api/synchronization":
                self._json({
                    "ok": True,
                    "synchronization": self.app.revisions.status(),
                    "desired": self.app.revisions.desired(),
                    "committed": self.app.revisions.committed(),
                    "isaac_ack": read_json(self.app.store.paths.isaac_ack, {}) or {},
                    "ros_ack": read_json(self.app.store.paths.ros_revision_ack, {}) or {},
                    "sionna_ack": read_json(self.app.store.paths.sionna_revision_ack, {}) or {},
                })
            elif path == "/api/revisions":
                self._json({"ok": True, "revisions": self.app.revisions.list()})
            elif path == "/api/smoke-test":
                diagnostics = system_diagnose(self.app.root, self.app.orchestrator.compose)
                packet = packet_diagnose(self.app.root, self.app.orchestrator.compose)
                self._json({"ok": bool(diagnostics.get("ok") and packet.get("ok")), "diagnostics": diagnostics, "packet": packet})
            elif path == "/api/support-bundle":
                self._json({"ok": True, "available": True, "method": "POST", "description": "Generate a redacted support bundle."})
            elif path == "/api/ros/topics":
                diag = packet_diagnose(self.app.root, self.app.orchestrator.compose)
                self._json({"ok": bool(diag.get("container")), "topics": diag.get("ros", {}).get("topic_list", []), "nodes": diag.get("ros", {}).get("node_list", [])})
            elif path.startswith("/api/logs/"):
                service = path.rsplit("/", 1)[-1]
                self._json(self.app.orchestrator.logs(service, int(query.get("tail", [200])[0])))
            else:
                self._serve_static(path)
        except Exception as exc:
            self._json({"ok": False, "error": {"code": "GET_FAILED", "message": str(exc), "traceback": traceback.format_exc(limit=8)}}, 500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            body = self._body()
            if path == "/api/command":
                result = self.app.command(str(body.get("name", body.get("operation", body.get("action", "")))), body.get("payload", body))
            elif path == "/api/config/validate":
                result = validate_experiment(body.get("config", body), strict=False)
            elif path == "/api/config":
                command = self.app.store.create_command("save_config", {})
                try:
                    result = self.app.save_config(body.get("config", body), sync=bool(body.get("sync", True)), command_id=command["command_id"])
                    status = result.get("command_status", "COMPLETED" if result.get("committed") else "PARTIALLY_APPLIED")
                    result["command"] = self.app.store.acknowledge_command(
                        command,
                        status=status,
                        acknowledgement={
                            "hash": result.get("config_hash"),
                            "revision_id": (result.get("revision") or {}).get("revision_id"),
                            "committed": bool(result.get("committed")),
                            "synchronization": result.get("synchronization"),
                        },
                    )
                except Exception as exc:
                    result = {"ok": False, "error": {"code": "CONFIG_SAVE_FAILED", "message": str(exc)}}
                    result["command"] = self.app.store.acknowledge_command(command, status="FAILED", error=result["error"])
            elif path in {"/api/swarm", "/api/swarm/apply"}:
                result = self.app.update_swarm(body)
            elif path in {"/api/topology", "/api/topology/apply"}:
                result = self.app.update_topology(body)
            elif path in {"/api/antennas", "/api/antennas/apply"}:
                config = self.app.load_config(); config["antennas"] = dict(body.get("antennas", body)); result = self.app.save_config(config, sync=bool(body.get("sync", True)))
            elif path in {"/api/world", "/api/world/apply"}:
                config = self.app.load_config(); config["world"] = dict(body.get("world", body)); result = self.app.save_config(config, sync=bool(body.get("sync", True)))
            elif path in {"/api/failures", "/api/failures/apply"}:
                config = self.app.load_config(); config["failures"] = dict(body.get("failures", body)); result = self.app.save_config(config, sync=bool(body.get("sync", True)))
            elif path in {"/api/traffic", "/api/traffic/apply"}:
                config = self.app.load_config(); config["traffic"] = dict(body.get("traffic", body)); result = self.app.save_config(config, sync=bool(body.get("sync", True)))
            elif path == "/api/topology/validate":
                config = self.app.load_config()
                config["topology"].update(dict(body.get("topology", body)))
                result = {"ok": True, "validation": validate_config_topology(config)}
            elif path == "/api/link/preview":
                result = self.app.evaluate_link_preview(body)
            elif path == "/api/guided-demo":
                result = self.app.guided_demo(str(body.get("step", "")), body.get("payload", {}))
            elif path == "/api/research/a2g":
                result = {"ok": True, "result": probabilistic_a2g_path_loss(float(body["distance_2d_m"]), float(body["altitude_m"]), float(body["frequency_hz"]), str(body.get("environment", "urban"))).to_dict()}
            elif path == "/api/research/ntn":
                result = {"ok": True, "result": ntn_slant_range_delay(float(body["altitude_m"]), float(body["elevation_deg"])).to_dict()}
            elif path == "/api/research/offload":
                result = {"ok": True, "result": edge_offloading(**body).to_dict()}
            elif path == "/api/research/radio-map":
                result = {"ok": True, "points": inverse_distance_radio_map([tuple(item) for item in body["samples"]], [tuple(item) for item in body["points"]], float(body.get("power", 2.0)))}
            elif path == "/api/research/calibrate":
                result = {"ok": True, "result": calibrate_log_distance([tuple(item) for item in body["samples"]], float(body["frequency_hz"]))}
            elif path == "/api/algorithm/create":
                package = self.app.algorithms.registry.create_project(
                    str(body.get("algorithm_id", "research_algorithm")),
                    name=str(body.get("name", "")),
                    category=str(body.get("category", "controller")),
                )
                result = {"ok": package.valid, "algorithm": package.to_dict()}
            elif path == "/api/algorithm/validate":
                algorithm_id = str(body.get("algorithm_id", ""))
                package = self.app.algorithms.registry.get(algorithm_id)
                result = {"ok": package.valid, "algorithm": package.to_dict(), "api_version": ALGORITHM_API_VERSION}
            elif path == "/api/algorithm/source":
                algorithm_id = str(body.get("algorithm_id", ""))
                package = self.app.algorithms.registry.get(algorithm_id)
                source = str(body.get("source", ""))
                if len(source.encode("utf-8")) > 1024 * 1024:
                    result = {"ok": False, "error": {"code": "ALGORITHM_SOURCE_TOO_LARGE", "message": "Algorithm source exceeds 1 MiB."}}
                else:
                    compile(source, str(package.entrypoint), "exec")
                    package.entrypoint.write_text(source, encoding="utf-8")
                    refreshed = self.app.algorithms.registry.get(algorithm_id)
                    result = {"ok": refreshed.valid, "algorithm": refreshed.to_dict(), "source_hash": refreshed.manifest.source_hash}
            elif path == "/api/algorithm/dry-run":
                result = self.app.algorithms.dry_run(
                    str(body.get("algorithm_id", "")),
                    parameters=body.get("parameters", {}),
                    observation=body.get("observation") if isinstance(body.get("observation"), Mapping) else None,
                    negative_test=bool(body.get("negative_test", False)),
                )
            elif path == "/api/algorithm/activate":
                algorithm_id = str(body.get("algorithm_id", ""))
                parameters = body.get("parameters", {}) if isinstance(body.get("parameters", {}), Mapping) else {}
                activation = self.app.algorithms.activate(algorithm_id, parameters)
                if not activation.get("ok"):
                    result = activation
                else:
                    config = self.app.load_config()
                    config.setdefault("swarm", {}).setdefault("controller", {})
                    config["swarm"]["controller"].update({
                        "type": "plugin",
                        "plugin_id": algorithm_id,
                        "algorithm_api_version": ALGORITHM_API_VERSION,
                        "parameters": dict(parameters),
                        "safe_fallback": activation["selection"].get("safety_fallback", "hold_position"),
                    })
                    config["algorithm"] = {
                        "algorithm_id": algorithm_id,
                        "version": activation["selection"].get("version"),
                        "source_hash": activation["selection"].get("source_hash"),
                        "parameters": dict(parameters),
                        "selection_id": activation["selection"].get("selection_id"),
                    }
                    saved = self.app.save_config(config, sync=bool(body.get("sync", True)))
                    result = {"ok": bool(saved.get("ok")), "activation": activation, "configuration": saved, "committed": bool(saved.get("committed"))}
            elif path == "/api/algorithm/compare":
                ids = [str(item) for item in body.get("algorithm_ids", [])]
                result = self.app.algorithms.compare(
                    ids,
                    parameters=body.get("parameters", {}) if isinstance(body.get("parameters", {}), Mapping) else {},
                    replications=int(body.get("replications", 3)),
                    seed=int(body["seed"]) if body.get("seed") is not None else None,
                )
            elif path == "/api/algorithm/export":
                result = self.app.algorithms.export_bundle(str(body.get("run_id", "")))
            elif path == "/api/algorithm/deactivate":
                atomic_write_json(self.app.algorithms.selection_path, {"schema_version": "2.0", "active": None, "timestamp": time.time()})
                config = self.app.load_config()
                config.setdefault("swarm", {}).setdefault("controller", {}).update({"type": "hold_position", "plugin_id": None, "parameters": {}})
                result = self.app.save_config(config, sync=bool(body.get("sync", True)))
            elif path == "/api/smoke-test":
                diagnostics = system_diagnose(self.app.root, self.app.orchestrator.compose)
                packet = packet_diagnose(self.app.root, self.app.orchestrator.compose)
                result = {"ok": bool(diagnostics.get("ok") and packet.get("ok")), "diagnostics": diagnostics, "packet": packet}
            elif path == "/api/support-bundle":
                result = generate_support_bundle(self.app.root, self.app.orchestrator.compose, reason=str(body.get("reason", "mission_control")))
            elif path == "/api/reconcile":
                current = self.app.revisions.status()
                revision_id = str(body.get("revision_id") or current.get("revision_id") or "")
                if not revision_id:
                    result = {"ok": False, "error": {"code": "NO_REVISION", "message": "No desired revision is available for reconciliation."}}
                else:
                    transaction = self.app.synchronizer.reconcile(revision_id, timeout_s=float(body.get("timeout_s", 30.0)))
                    result = {"ok": bool(transaction.get("committed")), "committed": bool(transaction.get("committed")), "synchronization": transaction}
            elif path == "/api/revisions/rollback":
                revision_id = str(body.get("revision_id", ""))
                if not revision_id:
                    result = {"ok": False, "error": {"code": "REVISION_ID_REQUIRED", "message": "revision_id is required."}}
                else:
                    rolled = self.app.revisions.rollback(revision_id, reason=str(body.get("reason", "operator_rollback")))
                    result = {"ok": True, "committed": False, "revision": rolled, "synchronization": self.app.revisions.status(rolled["revision_id"])}
            elif path == "/api/diagnostics/repair":
                result = self.app.orchestrator.preflight(repair=True)
            elif path == "/api/plugin/invoke":
                plugin_path = (self.app.plugin_root / str(body.get("plugin", ""))).resolve()
                plugin_path.relative_to(self.app.plugin_root.resolve())
                inspection = inspect_plugin(plugin_path)
                if not inspection.get("valid"):
                    result = {"ok": False, "error": {"code": "PLUGIN_INVALID", "details": inspection}}
                else:
                    invocation = invoke_isolated(plugin_path, str(body.get("hook", "plan_positions")), body.get("context", {}), timeout_s=float(body.get("timeout_s", 0.25)))
                    result = {"ok": bool(invocation.get("ok")), "inspection": inspection, "invocation": invocation}
            elif path == "/api/plugin/template":
                filename = str(body.get("filename", "new_controller.py"))
                target = (self.app.plugin_root / filename).resolve()
                target.relative_to(self.app.plugin_root.resolve())
                if target.suffix != ".py":
                    raise ValueError("plugin template filename must end in .py")
                target.write_text(template(), encoding="utf-8")
                result = {"ok": True, "path": str(target.relative_to(self.app.root))}
            elif path == "/api/evidence/export":
                result = {"ok": True, "index": index_evidence(self.app.store.paths.results)}
            else:
                self._json({"ok": False, "error": {"code": "NOT_FOUND", "message": path}}, 404)
                return
            self._json(result, 200 if result.get("ok", False) else 400)
        except Exception as exc:
            self._json({"ok": False, "error": {"code": "POST_FAILED", "message": str(exc), "traceback": traceback.format_exc(limit=8)}}, 500)


class MissionControlServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], app: MissionControlApplication) -> None:
        self.app = app
        super().__init__(address, Handler)


def guided_demo_steps() -> list[Dict[str, Any]]:
    return [
        {"id": "welcome", "title": "Understand the SNaaS experiment", "description": "Review how embodied UAV motion, ROS 2 coordination, communication evaluation, packet execution, failures, recovery, and evidence form one closed loop.", "automatic": False},
        {"id": "preflight", "title": "Run system preflight", "description": "Validate Docker, Compose, NVIDIA access, configuration, disk capacity, and required service definitions.", "automatic": True},
        {"id": "verify_environment", "title": "Verify the execution environment", "description": "Inspect Docker, GPU, ports, storage, and current service state before starting the simulation.", "automatic": True},
        {"id": "start_stack", "title": "Start the complete stack", "description": "Launch Sionna, ROS 2, the packet runtime, and Isaac Sim through one authoritative orchestration path.", "automatic": True},
        {"id": "verify_services", "title": "Wait for service readiness", "description": "Confirm Sionna health, the ROS graph, packet heartbeat, Isaac heartbeat, and bounded startup state.", "automatic": True},
        {"id": "load_example", "title": "Load the reference experiment", "description": "Apply a deterministic feasible chain with eight UAVs, two standbys, and a 0.2 visual asset scale.", "automatic": True},
        {"id": "inspect_service_region", "title": "Inspect the service region", "description": "Open Mission Designer and review the coordinate frame, geofence, altitude limits, world, and service-region dimensions.", "automatic": False},
        {"id": "inspect_fleet", "title": "Inspect active and standby UAVs", "description": "Open Swarm Control and identify relay roles, standby reserve, exact coordinates, separation constraints, and antenna assignments.", "automatic": False},
        {"id": "sync_mission", "title": "Synchronize the mission with Isaac", "description": "Create a scenario revision and wait for the always-running Isaac integration to acknowledge it.", "automatic": True},
        {"id": "verify_isaac", "title": "Verify Isaac scene acknowledgement", "description": "Require a fresh scene heartbeat and a matching scenario-revision acknowledgement; opening the WebRTC viewer is optional.", "automatic": True},
        {"id": "start_experiment", "title": "Start the experiment", "description": "Apply the configuration to ROS 2, synchronize Isaac, and enter RUNNING only after acknowledgements.", "automatic": True},
        {"id": "verify_packet", "title": "Verify packet advancement", "description": "Require a fresh packet heartbeat and authoritative cursor advancement on feasible active hops.", "automatic": True},
        {"id": "inspect_gate", "title": "Inspect the link feasibility gate", "description": "Review endpoint, operational-range, hard-outage, SNR or SINR, capacity, and metric-freshness predicates.", "automatic": False},
        {"id": "observe_packet", "title": "Observe the packet in Isaac", "description": "Use the WebRTC viewer only as visual evidence; verify that the marker follows authoritative packet events rather than an independent animation.", "automatic": False},
        {"id": "inspect_telemetry", "title": "Inspect live telemetry", "description": "Confirm the LIVE source badge, timestamps, sample freshness, packet statistics, link metrics, and branch availability.", "automatic": False},
        {"id": "inspect_link_metrics", "title": "Interpret link and SLA metrics", "description": "Inspect distance, path loss, received power, SNR or SINR, capacity, delay, margins, and explicit gate reason.", "automatic": False},
        {"id": "inspect_algorithm", "title": "Inspect a researcher algorithm", "description": "Open Algorithm Lab and inspect the connectivity-aware formation manifest, parameters, assumptions, source hash, execution budget, and safety fallback.", "automatic": True},
        {"id": "validate_algorithm", "title": "Validate the algorithm package", "description": "Validate the API version, source, manifest, schemas, resource budget, dependencies, and supported fidelity profiles.", "automatic": True},
        {"id": "dry_run_algorithm", "title": "Run a deterministic algorithm dry run", "description": "Execute the algorithm in an isolated worker against a typed authoritative snapshot and pass its output through the Safety and Feasibility Shield.", "automatic": True},
        {"id": "reject_invalid_algorithm_output", "title": "Verify invalid-output rejection", "description": "Run the automated negative test and confirm that an unsafe or unknown target is rejected with a deterministic fallback.", "automatic": True},
        {"id": "activate_algorithm", "title": "Activate and synchronize the algorithm", "description": "Create one revision and require matching ROS 2, Sionna, and Isaac acknowledgements before the algorithm is committed.", "automatic": True},
        {"id": "compare_algorithm", "title": "Compare with a deterministic baseline", "description": "Run paired-seed comparisons against researcher_chain_spacing and preserve execution time, acceptance rate, fallback rate, and objective evidence.", "automatic": True},
        {"id": "inject_failure", "title": "Inject a UAV failure", "description": "Fail relay UAV 3 and wait for the ROS runtime to acknowledge the failed endpoint after detection latency.", "automatic": True},
        {"id": "observe_outage", "title": "Observe the outage", "description": "Require the affected packet stream to pause without cursor advancement and expose the precise failure or route reason.", "automatic": True},
        {"id": "recompute", "title": "Recompute topology", "description": "Recompute the relay graph and acknowledge a new topology version without treating visual connectivity as recovery.", "automatic": True},
        {"id": "promote_standby", "title": "Promote a standby UAV", "description": "Promote UAV 7, apply the new runtime inventory, and preserve the normal communication feasibility gate.", "automatic": True},
        {"id": "verify_recovery", "title": "Verify service recovery", "description": "Confirm a feasible restored route and authoritative packet resumption; a drawn path alone is insufficient.", "automatic": True},
        {"id": "switch_topology", "title": "Switch to parallel topology", "description": "Create two independent branch streams and synchronize the topology with ROS 2 and Isaac.", "automatic": True},
        {"id": "move_uav", "title": "Edit one UAV coordinate", "description": "Move UAV 2 through the authoritative configuration path and trigger topology, link, telemetry, and Isaac updates.", "automatic": True},
        {"id": "modify_antenna", "title": "Modify an antenna parameter", "description": "Change the reference UAV antenna gain, invalidate affected communication state, and synchronize the scene.", "automatic": True},
        {"id": "modify_world", "title": "Modify the world environment", "description": "Change wind state through World Lab and synchronize the authoritative environment configuration.", "automatic": True},
        {"id": "inspect_updated_metrics", "title": "Inspect updated metrics", "description": "Confirm that topology, coordinate, antenna, and world revisions are reflected in current telemetry and evidence.", "automatic": False},
        {"id": "export_evidence", "title": "Export the evidence index", "description": "Hash and index configuration, metrics, events, command records, logs, and run manifests.", "automatic": True},
        {"id": "stop_experiment", "title": "Stop the experiment", "description": "Pause packet execution, acknowledge the COMPLETED mission mode, and preserve evidence for the run.", "automatic": True},
        {"id": "stop_stack", "title": "Shut down the stack", "description": "Stop Compose services and remove orphan resources through the authoritative lifecycle manager.", "automatic": True},
        {"id": "complete", "title": "Complete the first-run review", "description": "Review the command history, evidence, remaining warnings, model fidelity, and known limitations before designing a new experiment.", "automatic": False},
    ]


def serve(*, root: Path, host: str = "0.0.0.0", port: int = 8765) -> None:
    app = MissionControlApplication(root)
    server = MissionControlServer((host, int(port)), app)
    print(f"NETLAB Mission Control {__version__} listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NETLAB Mission Control")
    parser.add_argument("--host", default=os.environ.get("NETLAB_MISSION_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("NETLAB_MISSION_PORT", "8765")))
    parser.add_argument("--root", default=os.environ.get("NETLAB_ROOT", str(Path(__file__).resolve().parents[3])))
    arguments = parser.parse_args()
    serve(root=Path(arguments.root), host=arguments.host, port=arguments.port)
