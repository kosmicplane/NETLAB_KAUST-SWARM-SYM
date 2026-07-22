"""Atomic file-backed authoritative state and evidence utilities."""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional

from .config import configuration_hash
from .io import append_jsonl, atomic_write_json, ensure_shared_directory, read_json
from .models import CommandStatus, RuntimeEvent, RuntimePhase, TelemetrySource


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "Docker" / "workspace" / "shared" / "snaas_relay_config.json"

    @property
    def results(self) -> Path:
        return self.root / "Docker" / "workspace" / "results"

    @property
    def state(self) -> Path:
        return self.results / "netlab_runtime_state.json"

    @property
    def legacy_status(self) -> Path:
        return self.results / "snaas_relay_latest_status.json"

    @property
    def event_log(self) -> Path:
        return self.results / "netlab_events.jsonl"

    @property
    def command_log(self) -> Path:
        return self.results / "netlab_commands.jsonl"

    @property
    def isaac_signal(self) -> Path:
        return self.results / "snaas_isaac_sync_signal.json"

    @property
    def isaac_ack(self) -> Path:
        return self.results / "snaas_isaac_sync_ack.json"

    @property
    def isaac_heartbeat(self) -> Path:
        return self.results / "snaas_isaac_heartbeat.json"

    @property
    def packet_heartbeat(self) -> Path:
        return self.results / "snaas_packet_runtime_heartbeat.json"

    @property
    def algorithm_heartbeat(self) -> Path:
        return self.results / "snaas_algorithm_runtime_heartbeat.json"

    @property
    def active_algorithm(self) -> Path:
        return self.results / "snaas_active_algorithm.json"

    @property
    def sionna_heartbeat(self) -> Path:
        return self.results / "snaas_sionna_heartbeat.json"

    @property
    def revisions(self) -> Path:
        return self.results / "revisions"

    @property
    def desired_revision(self) -> Path:
        return self.results / "netlab_desired_revision.json"

    @property
    def committed_revision(self) -> Path:
        return self.results / "netlab_committed_revision.json"

    @property
    def reconciliation(self) -> Path:
        return self.results / "netlab_reconciliation_state.json"

    @property
    def ros_revision_ack(self) -> Path:
        return self.results / "snaas_ros_revision_ack.json"

    @property
    def sionna_revision_ack(self) -> Path:
        return self.results / "snaas_sionna_revision_ack.json"

    @property
    def mission_control(self) -> Path:
        return self.results / "mission_control"


_LOCK = threading.RLock()


def tail_jsonl(path: Path, limit: int = 100) -> list[Dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-max(1, limit):]
    result: list[Dict[str, Any]] = []
    for line in lines:
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                result.append(value)
        except Exception:
            continue
    return result


def file_freshness(path: Path, timeout_s: float) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "fresh": False, "age_s": None, "path": str(path)}
    age = max(0.0, time.time() - path.stat().st_mtime)
    return {"exists": True, "fresh": age <= timeout_s, "age_s": round(age, 3), "path": str(path)}


class StateStore:
    def __init__(self, root: Path) -> None:
        self.paths = RuntimePaths(root.resolve())
        ensure_shared_directory(self.paths.results)
        ensure_shared_directory(self.paths.mission_control)
        ensure_shared_directory(self.paths.revisions)

    def default_state(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "sequence": 0,
            "updated_at": time.time(),
            "phase": RuntimePhase.STOPPED.value,
            "experiment_id": "",
            "run_id": "",
            "config_hash": "",
            "telemetry_source": TelemetrySource.OFFLINE.value,
            "readiness": {},
            "services": {},
            "packet": {},
            "topology": {},
            "failures": [],
            "last_error": None,
            "last_command_id": None,
            "desired_revision_id": "",
            "committed_revision_id": "",
            "synchronization_state": "NO_REVISION",
        }

    def read(self) -> Dict[str, Any]:
        state = read_json(self.paths.state, self.default_state())
        if not isinstance(state, dict):
            state = self.default_state()
        return state

    def update(self, patch: Mapping[str, Any], *, event_type: str = "STATE_UPDATED", component: str = "state_store") -> Dict[str, Any]:
        with _LOCK:
            state = self.read()
            state.update(dict(patch))
            state["sequence"] = int(state.get("sequence", 0)) + 1
            state["updated_at"] = time.time()
            atomic_write_json(self.paths.state, state)
            self.append_event(event_type, {"patch": dict(patch), "state_sequence": state["sequence"]}, component=component)
            return state

    def set_phase(self, phase: RuntimePhase, *, error: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        patch: Dict[str, Any] = {"phase": phase.value}
        if error is not None:
            patch["last_error"] = dict(error)
        return self.update(patch, event_type="RUNTIME_PHASE_CHANGED", component="orchestrator")

    def start_run(self, experiment: Mapping[str, Any]) -> Dict[str, Any]:
        run_id = str(uuid.uuid4())
        experiment_meta = experiment.get("experiment", {}) if isinstance(experiment.get("experiment"), Mapping) else {}
        return self.update(
            {
                "experiment_id": str(experiment_meta.get("id", "experiment")),
                "run_id": run_id,
                "config_hash": configuration_hash(experiment),
                "phase": RuntimePhase.STARTING_EXPERIMENT.value,
                "failures": [],
            },
            event_type="RUN_CREATED",
            component="experiment_manager",
        )

    def append_event(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        component: str,
        severity: str = "INFO",
        entity: str = "",
        command_id: str = "",
        correlation_id: str = "",
    ) -> Dict[str, Any]:
        state = self.read()
        event = RuntimeEvent(
            event_type=event_type,
            source_component=component,
            payload=dict(payload),
            severity=severity,
            experiment_id=str(state.get("experiment_id", "")),
            run_id=str(state.get("run_id", "")),
            affected_entity=entity,
            command_id=command_id,
            correlation_id=correlation_id,
            sequence=int(state.get("sequence", 0)),
        ).as_dict()
        append_jsonl(self.paths.event_log, event)
        return event

    def create_command(self, name: str, payload: Mapping[str, Any], *, component: str = "mission_control") -> Dict[str, Any]:
        command_id = str(uuid.uuid4())
        command = {
            "command_id": command_id,
            "idempotency_key": str(payload.get("idempotency_key", "")) if isinstance(payload, Mapping) else "",
            "name": name,
            "payload": dict(payload),
            "component": component,
            "status": CommandStatus.ACCEPTED.value,
            "created_at": time.time(),
            "updated_at": time.time(),
            "acknowledgement": None,
            "participant_acknowledgements": {},
            "resulting_revision_id": "",
            "error": None,
        }
        append_jsonl(self.paths.command_log, command)
        self.update({"last_command_id": command_id}, event_type="COMMAND_ACCEPTED", component=component)
        return command

    def acknowledge_command(self, command: Mapping[str, Any], *, status: str, acknowledgement: Any = None, error: Any = None) -> Dict[str, Any]:
        updated = dict(command)
        updated.update({"status": status, "updated_at": time.time(), "acknowledgement": acknowledgement, "error": error})
        append_jsonl(self.paths.command_log, updated)
        self.append_event(
            "COMMAND_ACKNOWLEDGED" if status in {"ACKNOWLEDGED", "COMPLETED"} else "COMMAND_FAILED",
            updated,
            component=str(command.get("component", "mission_control")),
            severity="INFO" if status in {"ACKNOWLEDGED", "COMPLETED"} else "ERROR",
            command_id=str(command.get("command_id", "")),
        )
        return updated

    def write_sync_signal(
        self,
        reason: str,
        *,
        config_hash: str = "",
        command_id: str = "",
        revision_id: str = "",
        parent_revision_id: str = "",
        hashes: Optional[Mapping[str, Any]] = None,
        config_path: str = "",
    ) -> Dict[str, Any]:
        signal = {
            "revision": revision_id or str(uuid.uuid4()),
            "revision_id": revision_id or "",
            "parent_revision_id": parent_revision_id,
            "timestamp": time.time(),
            "reason": reason,
            "config_hash": config_hash,
            "hashes": dict(hashes or {}),
            "config_path": config_path,
            "command_id": command_id,
        }
        atomic_write_json(self.paths.isaac_signal, signal)
        self.append_event("ISAAC_SYNC_REQUESTED", signal, component="mission_control", command_id=command_id)
        return signal

    def sync_status(self, timeout_s: float = 15.0) -> Dict[str, Any]:
        signal = read_json(self.paths.isaac_signal, {}) or {}
        ack = read_json(self.paths.isaac_ack, {}) or {}
        heartbeat = read_json(self.paths.isaac_heartbeat, {}) or {}
        signal_revision = str(signal.get("revision_id") or signal.get("revision", ""))
        ack_revision = str(ack.get("revision_id") or ack.get("revision", ""))
        hb_freshness = file_freshness(self.paths.isaac_heartbeat, timeout_s)
        requested_hash = str(signal.get("config_hash", ""))
        applied_hash = str(ack.get("applied_config_hash", ""))
        hash_matches = not requested_hash or requested_hash == applied_hash
        acknowledged = bool(signal_revision and ack_revision == signal_revision and hash_matches and ack.get("scene_ready", True))
        state = "SYNCED" if acknowledged else ("ISAAC_ALIVE_ACK_PENDING" if hb_freshness["fresh"] else "WAITING_FOR_ISAAC")
        return {
            "state": state,
            "acknowledged": acknowledged,
            "signal": signal,
            "ack": ack,
            "heartbeat": heartbeat,
            "heartbeat_freshness": hb_freshness,
            "hash_matches": hash_matches,
        }

    def iter_events(self, limit: int = 100) -> Iterator[Dict[str, Any]]:
        yield from tail_jsonl(self.paths.event_log, limit)
