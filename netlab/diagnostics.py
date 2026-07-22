"""System, synchronization, and packet-runtime diagnostics.

Diagnostics never infer readiness from a single running container.  The same
readiness object is consumed by the CLI, Mission Control header, topology
transactions, and Guided Demo so operator messages cannot contradict each
other without a timestamped state transition.
"""
from __future__ import annotations

import csv
import json
import shutil
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .config import load_experiment, validate_experiment
from .docker import ComposeProject, docker_daemon_status, gpu_status
from .io import permission_diagnostic
from .models import ReadinessState
from .revisions import RevisionManager
from .state import StateStore, file_freshness, read_json, tail_jsonl


def http_json(url: str, timeout_s: float = 3.0) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(body) if body else {}
            return {"ok": 200 <= response.status < 300, "status": response.status, "data": parsed, "error": None}
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return {"ok": False, "status": None, "data": None, "error": str(exc)}


def port_available(host: str, port: int) -> Dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        result = sock.connect_ex((host, int(port)))
        return {"host": host, "port": int(port), "listening": result == 0}
    finally:
        sock.close()


def _last_csv_row(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows[-1] if rows else {}
    except Exception:
        return {}


def _service_ready(service: Mapping[str, Any]) -> bool:
    return bool(service.get("running") and service.get("health") not in {"unhealthy", "missing", "stopped", "unavailable"})


def _permission_findings(paths: Mapping[str, Path]) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    diagnostics: Dict[str, Any] = {}
    findings: list[Dict[str, Any]] = []
    for name, path in paths.items():
        value = permission_diagnostic(path)
        diagnostics[name] = value
        if value.get("exists") and not value.get("readable"):
            findings.append(
                {
                    "severity": "ERROR",
                    "code": "SHARED_FILE_UNREADABLE",
                    "message": f"Shared runtime artifact {name} is not readable by Mission Control.",
                    "details": value,
                    "action": "Run `./scripts/netlab doctor --repair` to normalize generated runtime permissions.",
                }
            )
    return diagnostics, findings


def system_diagnose(root: Path, compose: Optional[ComposeProject] = None) -> Dict[str, Any]:
    root = root.resolve()
    compose = compose or ComposeProject(root / "Docker" / "compose")
    store = StateStore(root)
    revision_manager = RevisionManager(root)
    paths = store.paths
    docker = docker_daemon_status()
    gpu = gpu_status()
    config_exists = paths.config.exists()
    compose_validation = compose.validate().as_dict() if compose.available() else {
        "ok": False,
        "returncode": 127,
        "stderr": "Docker Compose or the Compose file is unavailable.",
    }
    services: Dict[str, Any] = {}
    for service, fallback in (("isaac", "isaac-sim"), ("ros2-core", "netlab-ros2-core"), ("sionna-engine", "netlab-sionna-engine")):
        services[service] = compose.service_health(service, fallback) if compose.available() else {
            "service": service,
            "exists": False,
            "running": False,
            "health": "unavailable",
            "restart_count": 0,
        }

    packet_freshness = file_freshness(paths.packet_heartbeat, 5.0)
    packet_heartbeat = read_json(paths.packet_heartbeat, {}) or {}
    algorithm_freshness = file_freshness(paths.algorithm_heartbeat, 5.0)
    algorithm_heartbeat = read_json(paths.algorithm_heartbeat, {}) or {}
    sionna_freshness = file_freshness(paths.sionna_heartbeat, 10.0)
    sionna_heartbeat = read_json(paths.sionna_heartbeat, {}) or {}
    sionna_api = http_json("http://127.0.0.1:8090/health", timeout_s=2.0)
    sync = store.sync_status()
    revision = revision_manager.status()
    state = store.read()
    config_validation: Dict[str, Any]
    if config_exists:
        try:
            config_validation = validate_experiment(load_experiment(paths.config), strict=False)
        except Exception as exc:
            config_validation = {"ok": False, "errors": [{"code": "CONFIG_LOAD_FAILED", "message": str(exc)}], "warnings": []}
    else:
        config_validation = {"ok": False, "errors": [{"code": "CONFIG_MISSING", "message": str(paths.config)}], "warnings": []}

    permission_map, permission_findings = _permission_findings(
        {
            "authoritative_state": paths.state,
            "configuration": paths.config,
            "packet_heartbeat": paths.packet_heartbeat,
            "algorithm_heartbeat": paths.algorithm_heartbeat,
            "sionna_heartbeat": paths.sionna_heartbeat,
            "isaac_heartbeat": paths.isaac_heartbeat,
            "isaac_ack": paths.isaac_ack,
            "ros_revision_ack": paths.ros_revision_ack,
            "sionna_revision_ack": paths.sionna_revision_ack,
        }
    )

    readiness = ReadinessState(
        docker_ready=bool(docker.get("reachable")),
        gpu_ready=bool(gpu.get("available")),
        compose_ready=bool(compose_validation.get("ok")),
        ros_container_ready=_service_ready(services["ros2-core"]),
        ros_graph_ready=bool(_service_ready(services["ros2-core"]) and packet_freshness.get("fresh") and packet_heartbeat.get("ready", True) and algorithm_freshness.get("fresh") and algorithm_heartbeat.get("ready", True)),
        packet_runtime_ready=bool(packet_freshness.get("fresh") and packet_heartbeat.get("ready", True)),
        sionna_ready=bool(_service_ready(services["sionna-engine"]) and sionna_api.get("ok") and sionna_freshness.get("fresh")),
        isaac_process_ready=_service_ready(services["isaac"]),
        isaac_scene_ready=bool(sync.get("heartbeat_freshness", {}).get("fresh") and sync.get("heartbeat", {}).get("scene_ready", sync.get("heartbeat", {}).get("ready", False))),
        isaac_heartbeat_ready=bool(sync.get("heartbeat_freshness", {}).get("fresh")),
        isaac_scenario_acknowledged=bool(sync.get("acknowledged") and revision.get("in_sync", False)),
        telemetry_ready=str(state.get("telemetry_source", "OFFLINE")) == "LIVE" or bool(packet_freshness.get("fresh")),
        evidence_ready=paths.results.exists() and permission_diagnostic(paths.results).get("writable", False),
    ).as_dict()

    findings: list[Dict[str, Any]] = [*permission_findings]
    if not config_exists:
        findings.append({"severity": "ERROR", "code": "CONFIG_MISSING", "message": "The authoritative experiment configuration is missing.", "action": "Run `./scripts/netlab bootstrap` or `./scripts/netlab init`."})
    elif not config_validation.get("ok"):
        findings.append({"severity": "ERROR", "code": "CONFIG_INVALID", "message": "The active experiment configuration is invalid.", "details": config_validation, "action": "Open Mission Designer or run `./scripts/netlab doctor --repair`."})
    if not compose_validation.get("ok"):
        findings.append({"severity": "ERROR", "code": "COMPOSE_INVALID", "message": "Docker Compose validation failed.", "details": compose_validation, "action": "Inspect Docker/compose/docker-compose.yml and the rendered configuration."})
    if services["ros2-core"].get("restart_count", 0):
        findings.append({"severity": "ERROR", "code": "ROS_RESTART_LOOP", "message": "The ROS 2 service has restarted.", "details": services["ros2-core"], "action": "Run `./scripts/netlab packet-doctor` and inspect ROS logs."})
    if services["ros2-core"].get("running") and not packet_freshness.get("fresh"):
        findings.append({"severity": "ERROR", "code": "PACKET_RUNTIME_STALE", "message": "ROS 2 is running but the packet-runtime heartbeat is stale or absent.", "action": "Run `./scripts/netlab packet-doctor`."})
    if services["ros2-core"].get("running") and not algorithm_freshness.get("fresh"):
        findings.append({"severity": "ERROR", "code": "ALGORITHM_RUNTIME_STALE", "message": "ROS 2 is running but the researcher-algorithm bridge heartbeat is stale or absent.", "action": "Inspect ROS logs and the Algorithm Lab runtime status."})
    if services["isaac"].get("running") and not sync.get("heartbeat_freshness", {}).get("fresh"):
        findings.append({"severity": "WARNING", "code": "ISAAC_HEARTBEAT_STALE", "message": "Isaac is running but the scene heartbeat is stale or absent.", "action": "Inspect Isaac logs and run `./scripts/netlab sync-doctor`."})
    if services["sionna-engine"].get("running") and not sionna_api.get("ok"):
        findings.append({"severity": "ERROR", "code": "SIONNA_API_UNAVAILABLE", "message": "Sionna is running but the link-service health endpoint is unavailable.", "action": "Inspect Sionna logs and TCP port 8090."})
    if revision.get("state") in {"FAILED", "DRIFT_DETECTED"}:
        findings.append({"severity": "ERROR", "code": "RUNTIME_REVISION_DIVERGENCE", "message": "Desired and observed runtime revisions are not coherent.", "details": revision, "action": "Run `./scripts/netlab sync-doctor` and reconcile or roll back the revision."})
    elif str(revision.get("state", "")).startswith("PENDING_"):
        findings.append({"severity": "WARNING", "code": "RUNTIME_REVISION_PENDING", "message": "A validated draft is waiting for runtime acknowledgements.", "details": revision, "action": "Use the Synchronization Inspector or run `./scripts/netlab sync-doctor`."})

    # A state saved by an older process must not override current observed readiness.
    readiness_consistent = True
    stored = state.get("readiness", {}) if isinstance(state.get("readiness"), Mapping) else {}
    contradictions = []
    for key, observed in readiness.items():
        if key == "critical_ready" or key not in stored:
            continue
        if bool(stored.get(key)) != bool(observed):
            contradictions.append({"field": key, "stored": bool(stored.get(key)), "observed": bool(observed)})
    if contradictions:
        readiness_consistent = False
        findings.append({"severity": "WARNING", "code": "STALE_STORED_READINESS", "message": "Stored readiness differs from current observations; the UI uses current observations.", "details": contradictions})

    return {
        "generated_at": time.time(),
        "root": str(root),
        "docker": docker,
        "gpu": gpu,
        "compose": compose_validation,
        "services": services,
        "configuration": {"exists": config_exists, "path": str(paths.config), "validation": config_validation},
        "readiness": readiness,
        "readiness_consistent": readiness_consistent,
        "readiness_contradictions": contradictions,
        "revision": revision,
        "isaac_sync": sync,
        "packet_heartbeat": {**packet_freshness, "data": packet_heartbeat},
        "algorithm_heartbeat": {**algorithm_freshness, "data": algorithm_heartbeat},
        "active_algorithm": read_json(paths.active_algorithm, {}) or {},
        "sionna_heartbeat": {**sionna_freshness, "data": sionna_heartbeat},
        "sionna_api": sionna_api,
        "permissions": permission_map,
        "ports": {
            "mission_control": port_available("127.0.0.1", 8765),
            "sionna": port_available("127.0.0.1", 8090),
            "isaac_signal": port_available("127.0.0.1", 49100),
        },
        "disk_free_bytes": shutil.disk_usage(root).free,
        "state": state,
        "findings": findings,
        "ok": not any(item["severity"] == "ERROR" for item in findings),
    }


def packet_diagnose(root: Path, compose: Optional[ComposeProject] = None) -> Dict[str, Any]:
    root = root.resolve()
    compose = compose or ComposeProject(root / "Docker" / "compose")
    store = StateStore(root)
    paths = store.paths
    container = compose.service_container_name("ros2-core", "netlab-ros2-core") if compose.available() else None
    ros: Dict[str, Any] = {"container": container, "node_list": [], "topic_list": [], "runtime_processes": [], "errors": []}
    if container:
        try:
            command = (
                "set -eo pipefail; source /workspace/ros2/netlab_ros_env.sh; "
                "netlab_source_ros_environment /workspace/ros2/install/setup.bash; "
                "printf '%s\\n' '---NODES---'; timeout 5 ros2 node list 2>&1 || true; "
                "printf '%s\\n' '---TOPICS---'; timeout 5 ros2 topic list 2>&1 || true; "
                "printf '%s\\n' '---PROCESSES---'; pgrep -af 'snaas_relay_chain|netlab_packet_runtime' || true"
            )
            result = compose.exec("ros2-core", command, timeout=20, fallback="netlab-ros2-core")
            sections = {"nodes": [], "topics": [], "processes": []}
            current: Optional[str] = None
            for line in result.stdout.splitlines():
                if line == "---NODES---":
                    current = "nodes"
                elif line == "---TOPICS---":
                    current = "topics"
                elif line == "---PROCESSES---":
                    current = "processes"
                elif current and line.strip():
                    sections[current].append(line.strip())
            ros.update({"node_list": sections["nodes"], "topic_list": sections["topics"], "runtime_processes": sections["processes"], "command": result.as_dict()})
        except Exception as exc:
            ros["errors"].append(str(exc))

    heartbeat = read_json(paths.packet_heartbeat, {}) or {}
    latest_status = read_json(paths.legacy_status, {}) or {}
    metric_candidates = sorted(paths.results.glob("*_link_metrics.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
    metrics_path = (paths.results / "snaas_link_metrics.csv") if (paths.results / "snaas_link_metrics.csv").exists() else (metric_candidates[0] if metric_candidates else paths.results / "snaas_link_metrics.csv")
    event_candidates = sorted(paths.results.glob("*_events.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    event_path = event_candidates[0] if event_candidates else paths.results / "snaas_relay_events.jsonl"
    events = tail_jsonl(event_path, 20)
    packet_freshness = file_freshness(paths.packet_heartbeat, 5.0)
    status_freshness = file_freshness(paths.legacy_status, 5.0)
    expected_topics = ["/swarm/chain/status", "/swarm/chain/events", "/swarm/sionna/link_metrics"]
    topics = set(ros["topic_list"])
    missing_topics = [topic for topic in expected_topics if topic not in topics]
    findings: list[Dict[str, Any]] = []
    service = compose.service_health("ros2-core", "netlab-ros2-core") if compose.available() else {}
    if not container:
        findings.append({"severity": "ERROR", "code": "ROS_CONTAINER_NOT_FOUND", "action": "Start the stack and verify Compose service ros2-core."})
    if service.get("restart_count", 0):
        findings.append({"severity": "ERROR", "code": "ROS_RESTART_LOOP", "details": service, "action": "Inspect ROS logs and the environment bootstrap."})
    if container and not ros["runtime_processes"]:
        findings.append({"severity": "ERROR", "code": "PACKET_PROCESS_NOT_RUNNING", "action": "Run `./scripts/netlab restart --no-build` and inspect ROS logs."})
    if not packet_freshness.get("fresh"):
        findings.append({"severity": "ERROR", "code": "PACKET_HEARTBEAT_STALE", "action": "Inspect /workspace/results/snaas_relay_chain.log."})
    permission = permission_diagnostic(paths.packet_heartbeat)
    if permission.get("exists") and not permission.get("readable"):
        findings.append({"severity": "ERROR", "code": "PACKET_HEARTBEAT_UNREADABLE", "details": permission, "action": "Run `./scripts/netlab doctor --repair`."})
    if missing_topics and ros["node_list"]:
        findings.append({"severity": "WARNING", "code": "EXPECTED_TOPICS_MISSING", "details": missing_topics, "action": "Inspect ROS topic remapping and controller startup."})

    packet_summary = latest_status.get("packet") or latest_status.get("runtime") or {
        "packet_id": latest_status.get("packet_id"),
        "sequence": latest_status.get("sequence"),
        "phase": latest_status.get("phase"),
        "cursor": latest_status.get("cursor"),
        "connectivity_paused": latest_status.get("connectivity_paused"),
    }
    gate = latest_status.get("gate") or latest_status.get("last_gate") or latest_status.get("link") or latest_status.get("last_link_summary") or {}
    return {
        "generated_at": time.time(),
        "container": container,
        "service": service,
        "ros": ros,
        "heartbeat": heartbeat,
        "heartbeat_permission": permission,
        "heartbeat_freshness": packet_freshness,
        "status_freshness": status_freshness,
        "latest_status": latest_status,
        "latest_packet": packet_summary,
        "latest_gate": gate,
        "latest_metric": _last_csv_row(metrics_path),
        "recent_events": events,
        "metrics_file": {"path": str(metrics_path), "exists": metrics_path.exists(), "size_bytes": metrics_path.stat().st_size if metrics_path.exists() else 0},
        "events_file": {"path": str(event_path), "exists": event_path.exists(), "size_bytes": event_path.stat().st_size if event_path.exists() else 0},
        "isaac": store.sync_status(),
        "revision": RevisionManager(root).status(),
        "findings": findings,
        "ok": not any(item["severity"] == "ERROR" for item in findings),
    }
