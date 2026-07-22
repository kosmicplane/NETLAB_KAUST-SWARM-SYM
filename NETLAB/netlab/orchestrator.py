"""Authoritative lifecycle orchestration for the NETLAB simulation stack.

The same implementation is used by the CLI and Mission Control.  Startup is
sequential, bounded, and evidence-producing.  A container being ``running`` is
not considered equivalent to ROS graph, packet runtime, Sionna API, Isaac
scene, or scenario-revision readiness.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .config import configuration_hash, default_experiment, load_experiment, save_experiment, validate_experiment
from .diagnostics import http_json, packet_diagnose, system_diagnose
from .docker import ComposeProject
from .errors import NetlabError, RuntimeUnavailableError
from .evidence import build_run_manifest, write_run_manifest
from .models import ReadinessState, RuntimePhase, TelemetrySource
from .revisions import RevisionManager
from .state import StateStore, file_freshness, read_json
from .support import generate_support_bundle
from .synchronization import RuntimeSynchronizer
from .telemetry import TelemetryReader

ProgressCallback = Callable[[str, Mapping[str, Any]], None]


@dataclass
class OrchestratorSettings:
    compose_file: str = "docker-compose.yml"
    env_file: str = ".env"
    build_on_start: bool = True
    build_timeout_s: float = 1800.0
    poll_interval_s: float = 2.0
    sionna_timeout_s: float = 180.0
    ros_container_timeout_s: float = 180.0
    ros_graph_timeout_s: float = 300.0
    packet_timeout_s: float = 300.0
    isaac_process_timeout_s: float = 180.0
    isaac_scene_timeout_s: float = 900.0
    sync_timeout_s: float = 180.0
    telemetry_timeout_s: float = 60.0


class Orchestrator:
    def __init__(self, root: Path, settings: Optional[OrchestratorSettings] = None) -> None:
        self.root = Path(root).resolve()
        self.settings = settings or OrchestratorSettings()
        self.compose = ComposeProject(self.root / "Docker" / "compose", self.settings.compose_file, self.settings.env_file)
        self.store = StateStore(self.root)
        self.telemetry = TelemetryReader(self.root)
        self.revisions = RevisionManager(self.root)
        self.synchronizer = RuntimeSynchronizer(self.root, self.compose)

    def _progress(self, callback: Optional[ProgressCallback], stage: str, **payload: Any) -> None:
        event = {"stage": stage, "timestamp": time.time(), **payload}
        self.store.append_event("ORCHESTRATION_PROGRESS", event, component="orchestrator")
        if callback:
            callback(stage, event)

    def _set_phase(self, phase: RuntimePhase, callback: Optional[ProgressCallback] = None, **payload: Any) -> None:
        self.store.set_phase(phase)
        self._progress(callback, phase.value.lower(), phase=phase.value, **payload)

    def ensure_configuration(self) -> Dict[str, Any]:
        if self.store.paths.config.exists():
            config = load_experiment(self.store.paths.config)
        else:
            config = default_experiment()
            save_experiment(self.store.paths.config, config, emit_legacy=True)
        return validate_experiment(config, strict=True)["config"]

    def preflight(self, *, repair: bool = False) -> Dict[str, Any]:
        # Local import avoids a module cycle: bootstrap delegates runtime start to
        # this orchestrator after host preparation.
        from .bootstrap import Bootstrapper

        bootstrapper = Bootstrapper(self.root, self.compose)
        repair_result = bootstrapper.repair(repair_invalid_config=True) if repair else None
        result = bootstrapper.preflight()
        if repair_result is not None:
            result["repair"] = repair_result
            result["ok"] = bool(result.get("ok") and repair_result.get("ok"))
        return result

    def _wait(
        self,
        predicate: Callable[[], tuple[bool, Dict[str, Any]]],
        *,
        timeout_s: float,
        stage: str,
        callback: Optional[ProgressCallback] = None,
        recommendation: str = "Run `./scripts/netlab doctor` and inspect the relevant service logs.",
    ) -> Dict[str, Any]:
        started = time.monotonic()
        last: Dict[str, Any] = {}
        while time.monotonic() - started < timeout_s:
            ok, last = predicate()
            self._progress(callback, stage, ready=ok, elapsed_s=round(time.monotonic() - started, 2), timeout_s=timeout_s, observation=last)
            if ok:
                return last
            time.sleep(max(0.2, self.settings.poll_interval_s))
        raise RuntimeUnavailableError(
            code=f"{stage.upper()}_TIMEOUT",
            message=f"Timed out after {timeout_s:.0f} seconds while waiting for {stage}.",
            component="orchestrator",
            details={"last_observation": last, "elapsed_s": round(time.monotonic() - started, 3)},
            recommendation=recommendation,
        )

    def _service_wait(self, service: str, fallback: str) -> tuple[bool, Dict[str, Any]]:
        health = self.compose.service_health(service, fallback)
        ready = bool(
            health.get("running")
            and str(health.get("status", "")).lower() == "running"
            and health.get("health") not in {"unhealthy", "missing", "stopped"}
        )
        return ready, health

    def _clear_stale_artifacts(self, service: str) -> None:
        mapping = {
            "sionna-engine": (self.store.paths.sionna_heartbeat, self.store.paths.sionna_revision_ack),
            "ros2-core": (self.store.paths.packet_heartbeat, self.store.paths.ros_revision_ack),
            "isaac": (self.store.paths.isaac_heartbeat, self.store.paths.isaac_ack),
        }
        for path in mapping.get(service, ()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def _ensure_service_started(
        self,
        service: str,
        fallback: str,
        *,
        command_id: str,
        callback: Optional[ProgressCallback],
        timeout: float = 180.0,
    ) -> Dict[str, Any]:
        """Start or repair one service without retaining a restart-loop container."""
        observed = self.compose.service_health(service, fallback)
        healthy_running = bool(
            observed.get("running")
            and str(observed.get("status", "")).lower() == "running"
            and observed.get("health") not in {"unhealthy", "missing", "stopped"}
            and int(observed.get("restart_count", 0) or 0) == 0
        )
        if healthy_running:
            self._progress(callback, f"reuse_{service}", service=observed, idempotent=True)
            return {"ok": True, "idempotent": True, "service": observed}

        self._clear_stale_artifacts(service)
        if observed.get("exists"):
            removal = self.compose.command(["rm", "-s", "-f", service], timeout=90.0)
            self._progress(callback, f"remove_stale_{service}", command=removal.as_dict(), previous=observed)
        return self._run_compose(
            ["up", "-d", "--force-recreate", service],
            timeout=timeout,
            error_code=f"{service.upper().replace('-', '_')}_START_FAILED",
            message=f"{service} could not be started in a stable container.",
            command_id=command_id,
            callback=callback,
            stage=f"start_{service}",
        )

    def _sionna_wait(self) -> tuple[bool, Dict[str, Any]]:
        service = self.compose.service_health("sionna-engine", "netlab-sionna-engine")
        result = http_json("http://127.0.0.1:8090/ready", timeout_s=2.0)
        if not result.get("ok"):
            result = http_json("http://127.0.0.1:8090/health", timeout_s=2.0)
        heartbeat = file_freshness(self.store.paths.sionna_heartbeat, 12.0)
        ready = bool(service.get("running") and result.get("ok") and heartbeat.get("fresh"))
        return ready, {"service": service, "api": result, "heartbeat": heartbeat}

    def _ros_container_wait(self) -> tuple[bool, Dict[str, Any]]:
        return self._service_wait("ros2-core", "netlab-ros2-core")

    def _ros_graph_wait(self) -> tuple[bool, Dict[str, Any]]:
        health = self.compose.service_health("ros2-core", "netlab-ros2-core")
        if not health.get("running"):
            return False, health
        if str(health.get("status", "")).lower() == "restarting" or health.get("health") == "unhealthy":
            return False, {**health, "error": "ROS container is restarting or unhealthy; inspect the captured service logs."}
        try:
            result = self.compose.exec(
                "ros2-core",
                "set -eo pipefail; source /workspace/ros2/netlab_ros_env.sh; "
                "netlab_source_ros_environment /workspace/ros2/install/setup.bash; "
                "timeout 5 ros2 node list 2>/dev/null | grep -q 'netlab_snaas_relay_chain'",
                timeout=12,
                fallback="netlab-ros2-core",
            )
            return result.ok, {**health, "node_ready": result.ok, "command": result.as_dict()}
        except Exception as exc:
            return False, {**health, "error": str(exc)}

    def _packet_wait(self) -> tuple[bool, Dict[str, Any]]:
        freshness = file_freshness(self.store.paths.packet_heartbeat, 8.0)
        heartbeat = read_json(self.store.paths.packet_heartbeat, {}) or {}
        ready = bool(freshness.get("fresh") and heartbeat.get("ready", True) and heartbeat.get("sequence") is not None)
        return ready, {"freshness": freshness, "heartbeat": heartbeat}

    def _isaac_process_wait(self) -> tuple[bool, Dict[str, Any]]:
        return self._service_wait("isaac", "isaac-sim")

    def _isaac_scene_wait(self) -> tuple[bool, Dict[str, Any]]:
        service = self.compose.service_health("isaac", "isaac-sim")
        freshness = file_freshness(self.store.paths.isaac_heartbeat, 30.0)
        heartbeat = read_json(self.store.paths.isaac_heartbeat, {}) or {}
        scene_ready = bool(heartbeat.get("scene_ready", heartbeat.get("ready", False)))
        ready = bool(service.get("running") and freshness.get("fresh") and scene_ready)
        return ready, {"service": service, "heartbeat": heartbeat, "freshness": freshness, "scene_ready": scene_ready}

    def _telemetry_wait(self) -> tuple[bool, Dict[str, Any]]:
        snapshot = self.telemetry.snapshot()
        source = str(snapshot.get("source", {}).get("source", TelemetrySource.OFFLINE.value))
        rows = snapshot.get("rows", []) if isinstance(snapshot.get("rows"), list) else []
        return source == TelemetrySource.LIVE.value and bool(rows), {"source": source, "sample_count": len(rows), "snapshot_source": snapshot.get("source", {})}

    def _compose_failure_details(self, result: Mapping[str, Any], services: tuple[str, ...] = ("sionna-engine", "ros2-core", "isaac")) -> Dict[str, Any]:
        logs = {}
        for service in services:
            try:
                logs[service] = self.compose.logs(service, tail=250).as_dict()
            except Exception as exc:
                logs[service] = {"ok": False, "error": str(exc)}
        return {"command": dict(result), "service_logs": logs, "container_state": self.compose.ps(all_services=True)}

    def _run_compose(self, args: list[str], *, timeout: float, error_code: str, message: str, command_id: str, callback: Optional[ProgressCallback], stage: str) -> Dict[str, Any]:
        result = self.compose.command(args, timeout=timeout)
        self._progress(callback, stage, command=result.as_dict())
        if not result.ok:
            raise NetlabError(
                code=error_code,
                message=message,
                component="orchestrator",
                details=self._compose_failure_details(result.as_dict()),
                recommendation="Inspect the embedded Compose stderr and service logs or run `./scripts/netlab support-bundle`.",
                command_id=command_id,
            )
        return result.as_dict()

    def _build_images(self, command_id: str, callback: Optional[ProgressCallback]) -> Dict[str, Any]:
        results = {}
        self._set_phase(RuntimePhase.BUILDING, callback)
        for service in ("sionna-engine", "ros2-core", "isaac"):
            results[service] = self._run_compose(
                ["build", service],
                timeout=self.settings.build_timeout_s,
                error_code=f"{service.upper().replace('-', '_')}_BUILD_FAILED",
                message=f"Docker Compose failed to build {service}.",
                command_id=command_id,
                callback=callback,
                stage=f"build_{service}",
            )
        return results

    def _apply_startup_revision(self, config: Mapping[str, Any], command_id: str, callback: Optional[ProgressCallback]) -> Dict[str, Any]:
        record = self.revisions.create(
            config,
            reason="stack_started",
            command_id=command_id,
            initiator="orchestrator",
            required_participants=("ros", "sionna", "isaac"),
            affected_entities=("experiment", "swarm", "topology", "antennas", "world", "traffic", "failures"),
        )
        self.store.update(
            {"desired_revision_id": record["revision_id"], "synchronization_state": "PENDING_RUNTIME_APPLY"},
            event_type="STARTUP_REVISION_CREATED",
            component="orchestrator",
        )
        self._progress(callback, "revision_created", revision=self.revisions.summary(record))
        transaction = self.synchronizer.apply(
            record,
            ros_timeout_s=min(60.0, self.settings.ros_graph_timeout_s),
            sionna_timeout_s=min(30.0, self.settings.sionna_timeout_s),
            isaac_timeout_s=self.settings.sync_timeout_s,
            offline_is_pending=False,
        )
        self._progress(callback, "revision_participant_acknowledgements", transaction=transaction)
        if not transaction.get("committable"):
            raise NetlabError(
                code="STARTUP_REVISION_NOT_COMMITTED",
                message="The stack is alive, but ROS 2, Sionna, and Isaac did not acknowledge one startup revision.",
                component="orchestrator",
                details=transaction,
                recommendation="Run `./scripts/netlab sync-doctor` and inspect the synchronization acknowledgements.",
                command_id=command_id,
            )
        committed = self.revisions.commit(record["revision_id"])
        save_experiment(self.store.paths.config, config, emit_legacy=True)
        return {"transaction": transaction, "revision": committed, "status": self.revisions.status(record["revision_id"])}

    def start_stack(self, *, build: Optional[bool] = None, callback: Optional[ProgressCallback] = None) -> Dict[str, Any]:
        build = self.settings.build_on_start if build is None else bool(build)
        command = self.store.create_command("start_stack", {"build": build}, component="orchestrator")
        command_id = command["command_id"]
        try:
            # Start is intentionally idempotent.  A second UI/CLI request must not
            # create a second packet runtime, experiment run, or startup revision.
            observed = system_diagnose(self.root, self.compose)
            observed_readiness = observed.get("readiness", {}) if isinstance(observed.get("readiness"), Mapping) else {}
            observed_revision = observed.get("revision", {}) if isinstance(observed.get("revision"), Mapping) else {}
            observed_state = observed.get("state", {}) if isinstance(observed.get("state"), Mapping) else {}
            if (
                bool(observed_readiness.get("critical_ready"))
                and bool(observed_revision.get("in_sync"))
                and str(observed_state.get("telemetry_source", "")).upper() == TelemetrySource.LIVE.value
            ):
                acknowledgement = {
                    "idempotent": True,
                    "message": "The complete NETLAB stack is already ready; no duplicate runtime was created.",
                    "state": observed_state,
                    "readiness": observed_readiness,
                    "revision": observed_revision,
                }
                completed = self.store.acknowledge_command(command, status="COMPLETED", acknowledgement=acknowledgement)
                return {"ok": True, "idempotent": True, "command": completed, **acknowledgement}

            self._set_phase(RuntimePhase.PREFLIGHT, callback)
            preflight = self.preflight(repair=True)
            self._progress(callback, "preflight_result", result=preflight)
            if not preflight.get("ok"):
                raise NetlabError(
                    code="PREFLIGHT_FAILED",
                    message="NETLAB preflight found blocking errors.",
                    component="orchestrator",
                    details=preflight,
                    recommendation="Run `./scripts/netlab doctor --repair` and inspect the reported findings.",
                    command_id=command_id,
                )
            config = self.ensure_configuration()
            session_state = self.store.start_run(config)
            build_results = self._build_images(command_id, callback) if build else {}

            self._set_phase(RuntimePhase.STARTING_SIONNA, callback)
            self._ensure_service_started("sionna-engine", "netlab-sionna-engine", command_id=command_id, callback=callback)
            self._set_phase(RuntimePhase.WAITING_FOR_SIONNA, callback)
            sionna = self._wait(self._sionna_wait, timeout_s=self.settings.sionna_timeout_s, stage="sionna", callback=callback)

            self._set_phase(RuntimePhase.STARTING_ROS, callback)
            self._ensure_service_started("ros2-core", "netlab-ros2-core", command_id=command_id, callback=callback)
            self._set_phase(RuntimePhase.WAITING_FOR_ROS_CONTAINER, callback)
            ros_container = self._wait(self._ros_container_wait, timeout_s=self.settings.ros_container_timeout_s, stage="ros_container", callback=callback)
            self._set_phase(RuntimePhase.WAITING_FOR_ROS_GRAPH, callback)
            ros_graph = self._wait(self._ros_graph_wait, timeout_s=self.settings.ros_graph_timeout_s, stage="ros_graph", callback=callback)
            self._set_phase(RuntimePhase.WAITING_FOR_PACKET_RUNTIME, callback)
            packet = self._wait(self._packet_wait, timeout_s=self.settings.packet_timeout_s, stage="packet_runtime", callback=callback)

            self._set_phase(RuntimePhase.STARTING_ISAAC, callback)
            self._ensure_service_started("isaac", "isaac-sim", command_id=command_id, callback=callback)
            self._set_phase(RuntimePhase.WAITING_FOR_ISAAC_PROCESS, callback)
            isaac_process = self._wait(self._isaac_process_wait, timeout_s=self.settings.isaac_process_timeout_s, stage="isaac_process", callback=callback)
            self._set_phase(RuntimePhase.WAITING_FOR_ISAAC_SCENE, callback)
            isaac_scene = self._wait(self._isaac_scene_wait, timeout_s=self.settings.isaac_scene_timeout_s, stage="isaac_scene", callback=callback)

            self._set_phase(RuntimePhase.SYNCHRONIZING, callback)
            synchronization = self._apply_startup_revision(config, command_id, callback)

            self._set_phase(RuntimePhase.SMOKE_TESTING, callback)
            telemetry_observation = self._wait(
                self._telemetry_wait,
                timeout_s=self.settings.telemetry_timeout_s,
                stage="live_telemetry",
                callback=callback,
                recommendation="Inspect the packet runtime metrics and telemetry source classification.",
            )
            telemetry_snapshot = self.telemetry.snapshot()
            telemetry_source = str(telemetry_snapshot.get("source", {}).get("source", TelemetrySource.OFFLINE.value))
            readiness = ReadinessState(
                docker_ready=True,
                gpu_ready=True,
                compose_ready=True,
                ros_container_ready=True,
                ros_graph_ready=True,
                packet_runtime_ready=True,
                sionna_ready=True,
                isaac_process_ready=True,
                isaac_scene_ready=True,
                isaac_heartbeat_ready=True,
                isaac_scenario_acknowledged=True,
                telemetry_ready=telemetry_source == TelemetrySource.LIVE.value,
                evidence_ready=self.store.paths.results.exists(),
            )
            final = self.store.update(
                {
                    "phase": RuntimePhase.READY.value,
                    "telemetry_source": telemetry_source,
                    "readiness": readiness.as_dict(),
                    "services": {
                        "sionna": sionna,
                        "ros_container": ros_container,
                        "ros_graph": ros_graph,
                        "packet": packet,
                        "isaac_process": isaac_process,
                        "isaac_scene": isaac_scene,
                    },
                    "config_hash": configuration_hash(config),
                    "desired_revision_id": synchronization["revision"]["revision_id"],
                    "committed_revision_id": synchronization["revision"]["revision_id"],
                    "synchronization_state": "IN_SYNC",
                },
                event_type="STACK_READY",
                component="orchestrator",
            )
            manifest = build_run_manifest(
                root=self.root,
                config=config,
                run_id=str(final.get("run_id", session_state.get("run_id", ""))),
                experiment_id=str(config["experiment"]["id"]),
                fidelity_profile=str(config["experiment"]["fidelity_profile"]),
            )
            run_dir = self.store.paths.results / "runs" / manifest["run_id"]
            write_run_manifest(run_dir / "run_manifest.json", manifest)
            acknowledgement = {
                "state": final,
                "revision": synchronization,
                "manifest": manifest,
                "build": build_results,
                "telemetry": telemetry_observation,
            }
            completed = self.store.acknowledge_command(command, status="COMPLETED", acknowledgement=acknowledgement)
            return {"ok": True, "command": completed, **acknowledgement}
        except NetlabError as exc:
            self.store.set_phase(RuntimePhase.FAILED, error=exc.as_dict())
            failed = self.store.acknowledge_command(command, status="FAILED", error=exc.as_dict())
            support = generate_support_bundle(self.root, self.compose, reason=exc.code)
            return {"ok": False, "command": failed, "error": exc.as_dict(), "diagnostics": system_diagnose(self.root, self.compose), "support_bundle": support}
        except Exception as exc:
            error = NetlabError(code="UNEXPECTED_STARTUP_ERROR", message=str(exc), component="orchestrator", command_id=command_id)
            self.store.set_phase(RuntimePhase.FAILED, error=error.as_dict())
            failed = self.store.acknowledge_command(command, status="FAILED", error=error.as_dict())
            support = generate_support_bundle(self.root, self.compose, reason="unexpected_startup_error")
            return {"ok": False, "command": failed, "error": error.as_dict(), "support_bundle": support}

    def stop_stack(self) -> Dict[str, Any]:
        command = self.store.create_command("stop_stack", {}, component="orchestrator")
        self.store.set_phase(RuntimePhase.STOPPING)
        result = self.compose.command(["down", "--remove-orphans"], timeout=240)
        if result.ok:
            state = self.store.update(
                {"phase": RuntimePhase.STOPPED.value, "telemetry_source": TelemetrySource.OFFLINE.value, "readiness": {}},
                event_type="STACK_STOPPED",
                component="orchestrator",
            )
            return {"ok": True, "command": self.store.acknowledge_command(command, status="COMPLETED", acknowledgement=state), "result": result.as_dict()}
        error = {"code": "COMPOSE_DOWN_FAILED", "message": result.stderr or result.stdout, "component": "orchestrator", "details": self._compose_failure_details(result.as_dict())}
        return {"ok": False, "command": self.store.acknowledge_command(command, status="FAILED", error=error), "result": result.as_dict(), "error": error}

    def restart_stack(self, *, build: Optional[bool] = None, callback: Optional[ProgressCallback] = None) -> Dict[str, Any]:
        stopped = self.stop_stack()
        if not stopped.get("ok"):
            return stopped
        return self.start_stack(build=build, callback=callback)

    def synchronize(self, reason: str = "operator_request") -> Dict[str, Any]:
        command = self.store.create_command("synchronize", {"reason": reason}, component="orchestrator")
        desired = self.revisions.desired()
        revision_id = str(desired.get("revision_id", ""))
        if revision_id and not self.revisions.status(revision_id).get("in_sync"):
            transaction = self.synchronizer.reconcile(revision_id, isaac_timeout_s=self.settings.sync_timeout_s)
            record = self.revisions.read(revision_id)
            config = record.get("config", {}) if isinstance(record.get("config"), Mapping) else {}
        else:
            config = self.ensure_configuration()
            record = self.revisions.create(
                config,
                reason=reason,
                command_id=command["command_id"],
                initiator="orchestrator",
                required_participants=("ros", "sionna", "isaac"),
                affected_entities=("experiment",),
            )
            revision_id = record["revision_id"]
            transaction = self.synchronizer.apply(record, isaac_timeout_s=self.settings.sync_timeout_s, offline_is_pending=True)
        if transaction.get("committable"):
            committed = self.revisions.commit(revision_id)
            if config:
                save_experiment(self.store.paths.config, config, emit_legacy=True)
            status = self.revisions.status(revision_id)
            self.store.update({"desired_revision_id": revision_id, "committed_revision_id": revision_id, "synchronization_state": "IN_SYNC"}, event_type="RUNTIME_REVISION_COMMITTED", component="orchestrator")
            return {"ok": True, "command": self.store.acknowledge_command(command, status="COMPLETED", acknowledgement=status), "revision": committed, "transaction": transaction, "synchronization": status}
        status = self.revisions.status(revision_id)
        error = transaction.get("error", {"code": "SYNC_PENDING", "message": "Runtime acknowledgements are incomplete."})
        command_status = "PARTIALLY_APPLIED" if transaction.get("pending") else "FAILED"
        return {"ok": False, "pending": bool(transaction.get("pending")), "command": self.store.acknowledge_command(command, status=command_status, error=error), "transaction": transaction, "synchronization": status, "error": error}

    def reconcile(self, revision_id: str = "") -> Dict[str, Any]:
        transaction = self.synchronizer.reconcile(revision_id, isaac_timeout_s=self.settings.sync_timeout_s)
        rid = str(transaction.get("revision_id", revision_id))
        if transaction.get("committable") and rid:
            record = self.revisions.read(rid)
            committed = self.revisions.commit(rid)
            config = record.get("config", {}) if isinstance(record.get("config"), Mapping) else {}
            if config:
                save_experiment(self.store.paths.config, config, emit_legacy=True)
            self.store.update({"desired_revision_id": rid, "committed_revision_id": rid, "synchronization_state": "IN_SYNC"}, event_type="RUNTIME_REVISION_RECONCILED", component="orchestrator")
            return {"ok": True, "revision": committed, "transaction": transaction, "synchronization": self.revisions.status(rid)}
        return {"ok": False, "pending": bool(transaction.get("pending")), "transaction": transaction, "synchronization": self.revisions.status(rid) if rid else self.revisions.status(), "error": transaction.get("error")}

    def status(self) -> Dict[str, Any]:
        return system_diagnose(self.root, self.compose)

    def packet_doctor(self) -> Dict[str, Any]:
        return packet_diagnose(self.root, self.compose)

    def sync_doctor(self) -> Dict[str, Any]:
        return {"ok": self.revisions.status().get("in_sync", False), "synchronization": self.revisions.status(), "system": system_diagnose(self.root, self.compose)}

    def smoke_test(self) -> Dict[str, Any]:
        from .bootstrap import Bootstrapper
        return Bootstrapper(self.root, self.compose).smoke_test()

    def support_bundle(self, reason: str = "operator_request") -> Dict[str, Any]:
        return generate_support_bundle(self.root, self.compose, reason=reason)

    def logs(self, service: str = "", tail: int = 200) -> Dict[str, Any]:
        if service:
            result = self.compose.logs(service, tail=tail)
            return {"ok": result.ok, "service": service, "result": result.as_dict()}
        data = {}
        for name in ("isaac", "ros2-core", "sionna-engine"):
            result = self.compose.logs(name, tail=tail)
            data[name] = result.as_dict()
        return {"ok": all(value["ok"] for value in data.values()), "services": data}
