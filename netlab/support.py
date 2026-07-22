"""Redacted NETLAB support-bundle generation."""
from __future__ import annotations

import json
import os
import re
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .config import load_experiment, validate_experiment
from .diagnostics import packet_diagnose, system_diagnose
from .docker import ComposeProject, run
from .io import atomic_write_json, atomic_write_text, ensure_shared_directory
from .revisions import RevisionManager
from .state import StateStore, tail_jsonl

_SECRET_PATTERN = re.compile(r"(TOKEN|PASSWORD|PASSWD|SECRET|PRIVATE|CREDENTIAL|API[_-]?KEY)", re.IGNORECASE)


def _redact_mapping(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): ("<redacted>" if _SECRET_PATTERN.search(str(key)) else _redact_mapping(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_mapping(item) for item in value]
    return value


def _redact_env_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if _SECRET_PATTERN.search(key):
                value = "<redacted>"
            line = f"{key}={value}"
        lines.append(line)
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _write_command(directory: Path, name: str, argv: list[str], *, cwd: Optional[Path] = None, timeout: float = 30.0) -> Dict[str, Any]:
    result = run(argv, cwd=cwd, timeout=timeout)
    atomic_write_json(directory / f"{name}.json", _redact_mapping(result.as_dict()))
    return result.as_dict()


def generate_support_bundle(root: Path, compose: Optional[ComposeProject] = None, *, reason: str = "operator_request") -> Dict[str, Any]:
    root = Path(root).resolve()
    compose = compose or ComposeProject(root / "Docker" / "compose")
    store = StateStore(root)
    stamp = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    bundle_root = ensure_shared_directory(store.paths.results / "support" / f"support_{stamp}")

    system = system_diagnose(root, compose)
    packet = packet_diagnose(root, compose)
    revision = RevisionManager(root).status()
    try:
        config_validation = validate_experiment(load_experiment(store.paths.config), strict=False)
    except Exception as exc:
        config_validation = {"ok": False, "errors": [{"code": "CONFIG_LOAD_FAILED", "message": str(exc)}], "warnings": []}

    atomic_write_json(bundle_root / "manifest.json", {
        "generated_at": time.time(),
        "reason": reason,
        "root": str(root),
        "redacted": True,
        "contents": [
            "system_diagnostics.json",
            "packet_diagnostics.json",
            "revision_status.json",
            "configuration_validation.json",
            "compose_rendered.txt",
            "container_state.json",
            "service_logs/*.log",
            "recent_commands.json",
            "recent_events.json",
        ],
    })
    atomic_write_json(bundle_root / "system_diagnostics.json", _redact_mapping(system))
    atomic_write_json(bundle_root / "packet_diagnostics.json", _redact_mapping(packet))
    atomic_write_json(bundle_root / "revision_status.json", _redact_mapping(revision))
    atomic_write_json(bundle_root / "configuration_validation.json", _redact_mapping(config_validation))
    atomic_write_json(bundle_root / "recent_commands.json", tail_jsonl(store.paths.command_log, 200))
    atomic_write_json(bundle_root / "recent_events.json", tail_jsonl(store.paths.event_log, 500))

    if compose.available():
        rendered = compose.command(["config"], timeout=30)
        atomic_write_text(bundle_root / "compose_rendered.txt", _redact_env_text(rendered.stdout + ("\nSTDERR:\n" + rendered.stderr if rendered.stderr else "")))
        ps = compose.ps(all_services=True)
        atomic_write_json(bundle_root / "container_state.json", _redact_mapping(ps))
        log_dir = ensure_shared_directory(bundle_root / "service_logs")
        for service in ("sionna-engine", "ros2-core", "isaac"):
            logs = compose.logs(service, tail=1000)
            atomic_write_text(log_dir / f"{service}.log", logs.stdout + ("\nSTDERR:\n" + logs.stderr if logs.stderr else ""))
    else:
        atomic_write_text(bundle_root / "compose_rendered.txt", "Docker Compose was unavailable.\n")

    env_file = root / "Docker" / "compose" / ".env"
    if env_file.exists():
        atomic_write_text(bundle_root / "compose_env_redacted.txt", _redact_env_text(env_file.read_text(encoding="utf-8", errors="replace")))

    for name, argv in (
        ("docker_info", ["docker", "info"]),
        ("docker_ps", ["docker", "ps", "-a", "--no-trunc"]),
        ("nvidia_smi", ["nvidia-smi"]),
        ("disk_usage", ["df", "-h", str(root)]),
    ):
        _write_command(bundle_root, name, argv, timeout=30)

    archive = store.paths.results / "support" / f"NETLAB_support_{stamp}.zip"
    ensure_shared_directory(archive.parent)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for path in sorted(bundle_root.rglob("*")):
            if path.is_file():
                handle.write(path, path.relative_to(bundle_root.parent))
    return {
        "ok": True,
        "archive": str(archive),
        "directory": str(bundle_root),
        "generated_at": time.time(),
        "redacted": True,
    }
