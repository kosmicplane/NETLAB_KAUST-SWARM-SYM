"""Run manifests, evidence indexing, and reproducibility metadata."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

from .config import configuration_hash
from .state import atomic_write_json
from .version import __version__


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_identity(root: Path) -> Dict[str, Any]:
    if not (root / ".git").exists():
        return {"available": False, "commit": None, "branch": None, "dirty": None}
    def command(*args: str) -> str:
        try:
            return subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return ""
    status = command("status", "--porcelain")
    return {
        "available": True,
        "commit": command("rev-parse", "HEAD") or None,
        "branch": command("rev-parse", "--abbrev-ref", "HEAD") or None,
        "dirty": bool(status),
    }


def build_run_manifest(
    *,
    root: Path,
    config: Mapping[str, Any],
    run_id: str,
    experiment_id: str,
    fidelity_profile: str,
    container_images: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    return {
        "manifest_schema": "1.0.0",
        "netlab_version": __version__,
        "experiment_id": experiment_id,
        "run_id": run_id,
        "created_at_unix_s": time.time(),
        "config_hash": configuration_hash(config),
        "fidelity_profile": fidelity_profile,
        "git": git_identity(root),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "container_images": dict(container_images or {}),
        "environment": {
            key: os.environ.get(key)
            for key in ("ROS_DISTRO", "ROS_DOMAIN_ID", "RMW_IMPLEMENTATION", "ISAACSIM_HOST")
            if os.environ.get(key) is not None
        },
    }


def write_run_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    atomic_write_json(path, dict(manifest))


def index_evidence(directory: Path) -> Dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    items = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name == "evidence_index.json":
            continue
        try:
            size = path.stat().st_size
            sha = file_sha256(path) if size <= 128 * 1024 * 1024 else None
            items.append({"path": str(path.relative_to(directory)), "size_bytes": size, "sha256": sha})
        except OSError:
            continue
    payload = {"generated_at": time.time(), "root": str(directory), "item_count": len(items), "items": items}
    atomic_write_json(directory / "evidence_index.json", payload)
    return payload
