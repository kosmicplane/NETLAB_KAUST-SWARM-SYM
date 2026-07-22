"""Docker Compose discovery and command execution helpers.

Container names are never assumed. Services are resolved through Compose first,
then Docker labels, with an optional stable-name fallback for legacy deployments.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from .errors import RuntimeUnavailableError


@dataclass
class CommandResult:
    argv: List[str]
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "argv": self.argv,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_s": self.duration_s,
            "timed_out": self.timed_out,
            "ok": self.ok,
        }


def run(argv: Sequence[str], *, cwd: Optional[Path] = None, timeout: float = 30.0, env: Optional[Mapping[str, str]] = None) -> CommandResult:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **dict(env or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(list(argv), proc.returncode, proc.stdout, proc.stderr, time.monotonic() - started)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            list(argv),
            124,
            exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            time.monotonic() - started,
            timed_out=True,
        )
    except FileNotFoundError as exc:
        return CommandResult(list(argv), 127, "", str(exc), time.monotonic() - started)


class ComposeProject:
    def __init__(self, compose_dir: Path, compose_file: str = "docker-compose.yml", env_file: str = ".env") -> None:
        self.compose_dir = compose_dir.resolve()
        self.compose_file = compose_file
        self.env_file = env_file

    @property
    def compose_path(self) -> Path:
        return self.compose_dir / self.compose_file

    def available(self) -> bool:
        return shutil.which("docker") is not None and self.compose_path.exists()

    def ensure_env_file(self) -> Path:
        """Create a safe local Compose environment from the example when absent.

        The generated file contains no credentials. Remote operators can update
        ``ISAACSIM_HOST`` through ``setup-brev`` or edit the file explicitly.
        """
        target = self.compose_dir / self.env_file
        if target.exists():
            return target
        example = self.compose_dir / f"{self.env_file}.example"
        target.parent.mkdir(parents=True, exist_ok=True)
        if example.exists():
            text = example.read_text(encoding="utf-8")
            text = text.replace("YOUR_BREV_PUBLIC_IP", "127.0.0.1")
        else:
            text = (
                "ROS_DISTRO=jazzy\n"
                "ROS_DOMAIN_ID=42\n"
                "RMW_IMPLEMENTATION=rmw_fastrtps_cpp\n"
                "ISAACSIM_HOST=127.0.0.1\n"
                "ISAACSIM_SIGNAL_PORT=49100\n"
                "ISAACSIM_STREAM_PORT=47998\n"
                "ISAACSIM_TAG=5.1.0\n"
            )
        target.write_text(text.rstrip() + "\n", encoding="utf-8")
        return target

    def base_argv(self) -> List[str]:
        self.ensure_env_file()
        return ["docker", "compose", "--env-file", self.env_file, "-f", self.compose_file]

    def command(self, args: Sequence[str], *, timeout: float = 60.0) -> CommandResult:
        return run([*self.base_argv(), *args], cwd=self.compose_dir, timeout=timeout)

    def services(self) -> List[str]:
        result = self.command(["config", "--services"], timeout=20)
        if not result.ok:
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def validate(self) -> CommandResult:
        return self.command(["config", "--quiet"], timeout=30)

    def ps(self, *, all_services: bool = True) -> Dict[str, Any]:
        args = ["ps", "--format", "json"]
        if all_services:
            args.insert(1, "--all")
        result = self.command(args, timeout=30)
        if not result.ok:
            return {"ok": False, "result": result.as_dict(), "containers": []}
        containers = []
        text = result.stdout.strip()
        if text:
            try:
                parsed = json.loads(text)
                containers = parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                for line in text.splitlines():
                    try:
                        containers.append(json.loads(line))
                    except Exception:
                        continue
        return {"ok": True, "result": result.as_dict(), "containers": containers}

    def service_container_id(self, service: str) -> Optional[str]:
        result = self.command(["ps", "-q", service], timeout=20)
        container_id = result.stdout.strip().splitlines()[0] if result.ok and result.stdout.strip() else ""
        if container_id:
            return container_id
        label_result = run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=com.docker.compose.service={service}",
                "--format",
                "{{.ID}}",
            ],
            timeout=20,
        )
        return label_result.stdout.strip().splitlines()[0] if label_result.ok and label_result.stdout.strip() else None

    def service_container_name(self, service: str, fallback: str = "") -> Optional[str]:
        container_id = self.service_container_id(service)
        if container_id:
            inspect = run(["docker", "inspect", "--format", "{{.Name}}", container_id], timeout=15)
            if inspect.ok and inspect.stdout.strip():
                return inspect.stdout.strip().lstrip("/")
        if fallback:
            inspect = run(["docker", "inspect", fallback], timeout=15)
            if inspect.ok:
                return fallback
        return None

    def service_running(self, service: str, fallback: str = "") -> bool:
        name = self.service_container_name(service, fallback)
        if not name:
            return False
        result = run(["docker", "inspect", "--format", "{{.State.Running}}", name], timeout=15)
        return result.ok and result.stdout.strip().lower() == "true"

    def service_health(self, service: str, fallback: str = "") -> Dict[str, Any]:
        name = self.service_container_name(service, fallback)
        if not name:
            return {"service": service, "container": None, "exists": False, "running": False, "health": "missing", "restart_count": 0}
        result = run(["docker", "inspect", "--format", "{{json .}}", name], timeout=15)
        inspected: Dict[str, Any] = {}
        if result.ok:
            try:
                parsed = json.loads(result.stdout)
                inspected = parsed if isinstance(parsed, dict) else {}
            except Exception:
                inspected = {}
        state = inspected.get("State") if isinstance(inspected.get("State"), dict) else {}
        health = state.get("Health", {}).get("Status") if isinstance(state.get("Health"), dict) else None
        labels = inspected.get("Config", {}).get("Labels", {}) if isinstance(inspected.get("Config"), dict) else {}
        return {
            "service": service,
            "container": str(inspected.get("Name") or name).lstrip("/"),
            "container_id": inspected.get("Id"),
            "compose_service": labels.get("com.docker.compose.service") if isinstance(labels, dict) else None,
            "exists": bool(inspected),
            "running": bool(state.get("Running", False)),
            "status": state.get("Status"),
            "health": health or ("running" if state.get("Running") else "stopped"),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "exit_code": state.get("ExitCode"),
            "restart_count": int(inspected.get("RestartCount", 0) or 0),
            "oom_killed": bool(state.get("OOMKilled", False)),
            "dead": bool(state.get("Dead", False)),
            "error": state.get("Error") or (result.stderr.strip() if not result.ok else ""),
        }

    def exec(self, service: str, command: str, *, timeout: float = 30.0, fallback: str = "") -> CommandResult:
        name = self.service_container_name(service, fallback)
        if not name:
            raise RuntimeUnavailableError(
                code="CONTAINER_NOT_FOUND",
                message=f"No container could be resolved for Compose service {service}.",
                component="docker",
                details={"service": service, "fallback": fallback},
                recommendation="Start the stack and inspect `scripts/netlab status`.",
            )
        return run(["docker", "exec", name, "bash", "-lc", command], timeout=timeout)

    def logs(self, service: str, *, tail: int = 200) -> CommandResult:
        return self.command(["logs", "--no-color", f"--tail={max(1, tail)}", service], timeout=30)


def docker_daemon_status() -> Dict[str, Any]:
    if shutil.which("docker") is None:
        return {"available": False, "reachable": False, "error": "docker command not found"}
    result = run(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=15)
    return {
        "available": True,
        "reachable": result.ok,
        "server_version": result.stdout.strip().strip('"') if result.ok else None,
        "error": result.stderr.strip() if not result.ok else None,
    }


def gpu_status() -> Dict[str, Any]:
    if shutil.which("nvidia-smi") is None:
        return {"available": False, "error": "nvidia-smi not found"}
    result = run(
        [
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=15,
    )
    rows = []
    if result.ok:
        for line in result.stdout.splitlines():
            parts = [x.strip() for x in line.split(",")]
            if len(parts) >= 5:
                rows.append(
                    {
                        "name": parts[0],
                        "driver_version": parts[1],
                        "memory_total_mib": parts[2],
                        "memory_used_mib": parts[3],
                        "utilization_gpu_pct": parts[4],
                    }
                )
    return {"available": result.ok, "gpus": rows, "error": result.stderr.strip() if not result.ok else None}
