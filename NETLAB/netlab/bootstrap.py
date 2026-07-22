"""Near-automatic NETLAB host bootstrap and safe generated-state repair."""
from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

from .config import default_experiment, load_experiment, save_experiment, validate_experiment
from .diagnostics import packet_diagnose, system_diagnose
from .docker import ComposeProject, docker_daemon_status, gpu_status, run
from .io import atomic_write_json, atomic_write_text, ensure_shared_directory, repair_shared_tree
from .state import StateStore
from .support import generate_support_bundle


class Bootstrapper:
    """Prepare a clean host without modifying researcher-owned inputs silently."""

    def __init__(self, root: Path, compose: Optional[ComposeProject] = None) -> None:
        self.root = Path(root).resolve()
        self.compose = compose or ComposeProject(self.root / "Docker" / "compose")
        self.store = StateStore(self.root)

    @staticmethod
    def _parse_env(text: str) -> Dict[str, str]:
        values: Dict[str, str] = {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    @staticmethod
    def _format_env(values: Mapping[str, str], preferred_order: Iterable[str]) -> str:
        emitted = set()
        lines = []
        for key in preferred_order:
            if key in values:
                lines.append(f"{key}={values[key]}")
                emitted.add(key)
        for key in sorted(set(values) - emitted):
            lines.append(f"{key}={values[key]}")
        return "\n".join(lines) + "\n"

    def detect_host_address(self) -> str:
        configured = os.environ.get("ISAACSIM_HOST", "").strip()
        if configured and configured not in {"0.0.0.0", "127.0.0.1", "localhost", "YOUR_BREV_PUBLIC_IP"}:
            return configured
        tailscale = run(["tailscale", "ip", "-4"], timeout=5)
        if tailscale.ok:
            for line in tailscale.stdout.splitlines():
                value = line.strip()
                if value and not value.startswith("127."):
                    return value
        hostname = run(["hostname", "-I"], timeout=5)
        if hostname.ok:
            for value in hostname.stdout.split():
                if value and not value.startswith("127."):
                    return value
        return "127.0.0.1"

    def prepare_env(self) -> Dict[str, Any]:
        target = self.compose.compose_dir / self.compose.env_file
        example = self.compose.compose_dir / f"{self.compose.env_file}.example"
        values: Dict[str, str] = {}
        if example.exists():
            values.update(self._parse_env(example.read_text(encoding="utf-8", errors="replace")))
        if target.exists():
            values.update(self._parse_env(target.read_text(encoding="utf-8", errors="replace")))
        values.update(
            {
                "ROS_DISTRO": values.get("ROS_DISTRO", "jazzy"),
                "ROS_DOMAIN_ID": values.get("ROS_DOMAIN_ID", "42"),
                "RMW_IMPLEMENTATION": values.get("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp"),
                "ISAACSIM_HOST": self.detect_host_address(),
                "ISAACSIM_SIGNAL_PORT": values.get("ISAACSIM_SIGNAL_PORT", "49100"),
                "ISAACSIM_STREAM_PORT": values.get("ISAACSIM_STREAM_PORT", "47998"),
                "ISAACSIM_TAG": values.get("ISAACSIM_TAG", "5.1.0"),
                "NETLAB_SHARED_FILE_MODE": values.get("NETLAB_SHARED_FILE_MODE", "0664"),
                "NETLAB_SHARED_DIR_MODE": values.get("NETLAB_SHARED_DIR_MODE", "2775"),
                "NETLAB_SHARED_UID": str(os.getuid()),
                "NETLAB_SHARED_GID": str(os.getgid()),
            }
        )
        order = (
            "ROS_DISTRO",
            "ROS_DOMAIN_ID",
            "RMW_IMPLEMENTATION",
            "ISAACSIM_HOST",
            "ISAACSIM_SIGNAL_PORT",
            "ISAACSIM_STREAM_PORT",
            "ISAACSIM_TAG",
            "NETLAB_SHARED_FILE_MODE",
            "NETLAB_SHARED_DIR_MODE",
            "NETLAB_SHARED_UID",
            "NETLAB_SHARED_GID",
        )
        atomic_write_text(target, self._format_env(values, order), mode=0o664)
        return {"ok": True, "path": str(target), "values": {key: values[key] for key in order}}

    @staticmethod
    def _authoritative_config_view(raw: Any) -> Mapping[str, Any]:
        """Return the versioned experiment object from a legacy compatibility envelope."""

        if not isinstance(raw, Mapping):
            return {}
        for key in ("v6", "v5"):
            candidate = raw.get(key)
            if isinstance(candidate, Mapping):
                return candidate
        return raw

    @classmethod
    def _is_generated_reference_config(cls, raw: Any) -> bool:
        """Identify the packaged reference experiment without guessing about user files.

        New releases carry an explicit marker.  The conservative legacy signature is
        retained only for the historical packaged default that triggered the V5 P0
        preflight defect.  Any other invalid experiment remains untouched.
        """

        config = cls._authoritative_config_view(raw)
        compatibility = config.get("compatibility", {}) if isinstance(config, Mapping) else {}
        if isinstance(compatibility, Mapping) and compatibility.get("generated_reference") is True:
            return True
        experiment = config.get("experiment", {}) if isinstance(config, Mapping) else {}
        tags = experiment.get("tags", []) if isinstance(experiment, Mapping) else []
        return bool(
            isinstance(experiment, Mapping)
            and experiment.get("id") == "first_feasible_relay_chain"
            and not str(experiment.get("author", "")).strip()
            and isinstance(tags, list)
            and "reference" in tags
        )

    def _repair_executables(self) -> list[str]:
        repaired = []
        candidates = [
            self.root / "scripts" / "netlab",
            *sorted((self.root / "scripts").glob("*.sh")),
            *sorted((self.root / "scripts" / "diagnostics").glob("*.sh")),
            *sorted((self.root / "scripts" / "migration").glob("*.sh")),
            *sorted((self.root / "scripts" / "release").glob("*.sh")),
            *sorted((self.root / "Docker" / "scripts").glob("*.sh")),
            self.root / "Docker" / "docker" / "isaacsim" / "entrypoint.sh",
            self.root / "Docker" / "workspace" / "ros2" / "runtime_entrypoint.sh",
            self.root / "Docker" / "workspace" / "ros2" / "netlab_ros_env.sh",
        ]
        for path in candidates:
            if not path.exists() or not path.is_file():
                continue
            mode = stat.S_IMODE(path.stat().st_mode)
            if not mode & stat.S_IXUSR:
                path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP)
                repaired.append(str(path))
        return repaired

    def validate_packaged_scenarios(self) -> Dict[str, Any]:
        results = []
        for path in sorted((self.root / "scenarios").rglob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                validation = validate_experiment(raw, strict=False)
                results.append({"path": str(path.relative_to(self.root)), "ok": bool(validation.get("ok")), "errors": validation.get("errors", []), "warnings": validation.get("warnings", [])})
            except Exception as exc:
                results.append({"path": str(path.relative_to(self.root)), "ok": False, "errors": [{"code": "SCENARIO_LOAD_FAILED", "message": str(exc)}], "warnings": []})
        return {"ok": all(item["ok"] for item in results), "scenarios": results}

    def repair(self, *, repair_invalid_config: bool = True) -> Dict[str, Any]:
        actions: list[Dict[str, Any]] = []
        for directory in (
            self.root / "Docker" / "workspace" / "results",
            self.root / "Docker" / "workspace" / "shared",
            self.root / "Docker" / "workspace" / "plugins",
            self.root / "Docker" / "data" / "isaac" / "cache" / "main",
            self.root / "Docker" / "data" / "isaac" / "cache" / "computecache",
            self.root / "Docker" / "data" / "isaac" / "logs",
            self.root / "Docker" / "data" / "isaac" / "config",
            self.root / "Docker" / "data" / "isaac" / "local-data",
            self.root / "Docker" / "data" / "isaac" / "pkg",
        ):
            ensure_shared_directory(directory)
        actions.append({"action": "ENSURE_RUNTIME_DIRECTORIES", "ok": True})
        actions.append({"action": "REPAIR_RESULTS_PERMISSIONS", **repair_shared_tree(self.root / "Docker" / "workspace" / "results")})
        actions.append({"action": "REPAIR_SHARED_PERMISSIONS", **repair_shared_tree(self.root / "Docker" / "workspace" / "shared")})
        repaired_executables = self._repair_executables()
        actions.append({"action": "RESTORE_EXECUTABLE_BITS", "ok": True, "paths": repaired_executables})
        env = self.prepare_env()
        actions.append({"action": "PREPARE_COMPOSE_ENV", **env})

        config_action: Dict[str, Any]
        raw_config: Any = None
        config_exists = self.store.paths.config.exists()
        if config_exists:
            try:
                raw_config = json.loads(self.store.paths.config.read_text(encoding="utf-8"))
                config = load_experiment(self.store.paths.config)
                validation = validate_experiment(config, strict=False)
            except Exception as exc:
                validation = {
                    "ok": False,
                    "errors": [{"code": "CONFIG_LOAD_FAILED", "message": str(exc)}],
                    "warnings": [],
                }
        else:
            validation = {"ok": False, "errors": [{"code": "CONFIG_MISSING", "message": "No active experiment configuration exists."}], "warnings": []}

        if validation.get("ok"):
            config_action = {"action": "VALIDATE_ACTIVE_CONFIG", "ok": True, "preserved": True}
        elif repair_invalid_config and (not config_exists or self._is_generated_reference_config(raw_config)):
            backup = self.store.paths.config.with_name(f"{self.store.paths.config.stem}.invalid_{int(time.time())}.json")
            if config_exists:
                shutil.copy2(self.store.paths.config, backup)
            config = default_experiment()
            save_experiment(self.store.paths.config, config, emit_legacy=True)
            config_action = {
                "action": "CREATE_VALID_REFERENCE_CONFIG" if not config_exists else "REPLACE_INVALID_GENERATED_DEFAULT",
                "ok": True,
                "preserved_user_configuration": True,
                "backup": str(backup) if backup.exists() else None,
                "errors": validation.get("errors", []),
                "replacement_experiment": config["experiment"]["id"],
            }
        else:
            config_action = {
                "action": "PRESERVE_INVALID_USER_CONFIGURATION",
                "ok": False,
                "preserved": True,
                "requires_operator_action": True,
                "path": str(self.store.paths.config),
                "errors": validation.get("errors", []),
                "recommendation": "Correct or explicitly migrate the researcher experiment; bootstrap did not overwrite it.",
            }
        actions.append(config_action)

        stale = []
        for path in (self.store.paths.results / "mission_control" / "mission_control.pid",):
            if path.exists():
                try:
                    pid = int(path.read_text().strip())
                    os.kill(pid, 0)
                except Exception:
                    path.unlink(missing_ok=True)
                    stale.append(str(path))
        actions.append({"action": "REMOVE_STALE_PID_FILES", "ok": True, "paths": stale})
        return {"ok": all(item.get("ok", True) for item in actions), "actions": actions}

    @staticmethod
    def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
        try:
            with socket.create_connection((host, int(port)), timeout=0.2):
                return True
        except OSError:
            return False

    def host_requirements(self) -> Dict[str, Any]:
        """Collect bounded host prerequisites without mutating managed components."""

        commands = {name: bool(shutil.which(name)) for name in ("python3", "docker", "curl", "jq", "unzip", "rsync")}
        disk = shutil.disk_usage(self.root)
        memory_total = 0
        meminfo = Path("/proc/meminfo")
        if meminfo.exists():
            for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        memory_total = int(parts[1]) * 1024
                    break
        return {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "commands": commands,
            "disk": {"total_bytes": disk.total, "free_bytes": disk.free},
            "memory": {"total_bytes": memory_total},
            "ports": {
                "mission_control_8765_listening": self._port_listening(8765),
                "sionna_8090_listening": self._port_listening(8090),
                "isaac_signal_49100_listening": self._port_listening(49100),
            },
        }

    def preflight(self) -> Dict[str, Any]:
        compose_validation = self.compose.validate().as_dict() if self.compose.available() else {"ok": False, "stderr": "Docker Compose unavailable."}
        scenarios = self.validate_packaged_scenarios()
        try:
            config = validate_experiment(load_experiment(self.store.paths.config), strict=False)
        except Exception as exc:
            config = {"ok": False, "errors": [{"code": "CONFIG_LOAD_FAILED", "message": str(exc)}]}
        docker = docker_daemon_status()
        gpu = gpu_status()
        host = self.host_requirements()
        findings = []
        if not docker.get("reachable"):
            findings.append({"severity": "ERROR", "code": "DOCKER_UNAVAILABLE", "message": docker.get("error")})
        if not gpu.get("available"):
            findings.append({"severity": "ERROR", "code": "GPU_UNAVAILABLE", "message": gpu.get("error")})
        if not compose_validation.get("ok"):
            findings.append({"severity": "ERROR", "code": "COMPOSE_INVALID", "message": compose_validation.get("stderr")})
        if not config.get("ok"):
            findings.append({"severity": "ERROR", "code": "CONFIG_INVALID", "details": config.get("errors", [])})
        if not scenarios.get("ok"):
            findings.append({"severity": "ERROR", "code": "PACKAGED_SCENARIO_INVALID", "details": [item for item in scenarios["scenarios"] if not item["ok"]]})

        missing_utilities = [name for name, available in host["commands"].items() if name not in {"docker", "python3"} and not available]
        if missing_utilities:
            findings.append({
                "severity": "WARNING",
                "code": "HOST_OPERATOR_UTILITIES_MISSING",
                "details": missing_utilities,
                "message": "Optional operator utilities are missing; use scripts/bootstrap_host.sh --install-packages.",
            })
        free_bytes = int(host["disk"]["free_bytes"])
        if free_bytes < 10 * 1024**3:
            findings.append({"severity": "ERROR", "code": "DISK_SPACE_CRITICAL", "message": "Less than 10 GiB is free; container build/start is unsafe.", "details": host["disk"]})
        elif free_bytes < 40 * 1024**3:
            findings.append({"severity": "WARNING", "code": "DISK_SPACE_LOW", "message": "Less than 40 GiB is free; first-time Isaac/CUDA builds may exhaust storage.", "details": host["disk"]})
        memory_bytes = int(host["memory"].get("total_bytes", 0) or 0)
        if memory_bytes and memory_bytes < 8 * 1024**3:
            findings.append({"severity": "ERROR", "code": "HOST_MEMORY_CRITICAL", "message": "Less than 8 GiB of host memory is available to the system.", "details": host["memory"]})
        elif memory_bytes and memory_bytes < 16 * 1024**3:
            findings.append({"severity": "WARNING", "code": "HOST_MEMORY_LOW", "message": "Less than 16 GiB of host memory may constrain Isaac and analysis workloads.", "details": host["memory"]})
        return {
            "ok": not any(item["severity"] == "ERROR" for item in findings),
            "host": host,
            "docker": docker,
            "gpu": gpu,
            "compose": compose_validation,
            "configuration": config,
            "scenarios": scenarios,
            "findings": findings,
        }

    def smoke_test(self) -> Dict[str, Any]:
        system = system_diagnose(self.root, self.compose)
        packet = packet_diagnose(self.root, self.compose)
        heartbeat = packet.get("heartbeat", {}) if isinstance(packet.get("heartbeat"), Mapping) else {}
        gate = packet.get("latest_gate", {}) if isinstance(packet.get("latest_gate"), Mapping) else {}
        source = str(system.get("state", {}).get("telemetry_source", "OFFLINE")).upper()
        raw_sequence = heartbeat.get("sequence")
        try:
            sequence = int(raw_sequence)
        except (TypeError, ValueError):
            sequence = -1
        gate_reason = str(
            gate.get("reason")
            or gate.get("gate_reason")
            or heartbeat.get("gate_reason")
            or heartbeat.get("last_gate")
            or ""
        ).upper()
        packet_not_paused = not bool(heartbeat.get("connectivity_paused")) and not bool(heartbeat.get("operator_paused"))
        checks = {
            "critical_readiness": bool(system.get("readiness", {}).get("critical_ready")),
            "packet_runtime": bool(packet.get("heartbeat_freshness", {}).get("fresh")) and bool(heartbeat.get("ready", True)),
            "packet_sequence_advanced": sequence > 0,
            "reference_gate_feasible": gate_reason == "FEASIBLE",
            "packet_flow_not_paused": packet_not_paused,
            "telemetry_live": source == "LIVE",
        }
        return {
            "ok": all(checks.values()),
            "checks": checks,
            "observed": {
                "packet_sequence": sequence,
                "packet_advancing": bool(heartbeat.get("packet_advancing")),
                "gate_reason": gate_reason or "UNAVAILABLE",
                "telemetry_source": source,
            },
            "system": system,
            "packet": packet,
        }

    def _start_mission_control(self) -> Dict[str, Any]:
        """Start the operator console through the canonical compatibility wrapper.

        Mission Control remains available when stack startup fails so the operator can
        inspect the generated support bundle and retry from the same control plane.
        """

        script = self.root / "scripts" / "netlab_mission_control.sh"
        if not script.exists():
            return {
                "ok": False,
                "returncode": 127,
                "stdout": "",
                "stderr": f"Missing Mission Control launcher: {script}",
            }
        completed = subprocess.run(
            [str(script), "start"],
            cwd=str(self.root),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "url": "http://127.0.0.1:8765",
        }

    def bootstrap(self, *, build: bool = True, start: bool = True, non_interactive: bool = False) -> Dict[str, Any]:
        started = time.time()
        repair = self.repair(repair_invalid_config=True)
        preflight = self.preflight()
        report: Dict[str, Any] = {
            "ok": False,
            "started_at": started,
            "repair": repair,
            "preflight": preflight,
            "non_interactive": non_interactive,
        }
        if not repair.get("ok") or not preflight.get("ok"):
            report["support_bundle"] = generate_support_bundle(self.root, self.compose, reason="bootstrap_preflight_failure")
            report["completed_at"] = time.time()
            return report
        if not start:
            report.update({"ok": True, "completed_at": time.time(), "message": "Host preparation completed; stack startup was not requested."})
            atomic_write_json(self.store.paths.results / "bootstrap_report.json", report)
            return report
        mission_control = self._start_mission_control()
        report["mission_control"] = mission_control
        if not mission_control.get("ok"):
            report["support_bundle"] = generate_support_bundle(self.root, self.compose, reason="bootstrap_mission_control_failure")
            report["completed_at"] = time.time()
            atomic_write_json(self.store.paths.results / "bootstrap_report.json", report)
            return report

        # Local import avoids an import cycle with the orchestrator's repair path.
        from .orchestrator import Orchestrator

        stack = Orchestrator(self.root).start_stack(build=build)
        report["stack"] = stack
        report["smoke_test"] = self.smoke_test() if stack.get("ok") else None
        report["ok"] = bool(
            mission_control.get("ok")
            and stack.get("ok")
            and report["smoke_test"]
            and report["smoke_test"].get("ok")
        )
        if not report["ok"]:
            report["support_bundle"] = generate_support_bundle(self.root, self.compose, reason="bootstrap_runtime_failure")
        report["completed_at"] = time.time()
        atomic_write_json(self.store.paths.results / "bootstrap_report.json", report)
        return report
