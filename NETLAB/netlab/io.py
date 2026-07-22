"""Permission-safe atomic I/O for host/container coordination.

All runtime status, heartbeat, acknowledgement, revision, and evidence files
cross a Docker bind-mount boundary.  This module is the single implementation
used by host and container processes so an atomic replace cannot silently
create a root-only ``0600`` file again.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

DEFAULT_FILE_MODE = 0o664
DEFAULT_DIR_MODE = 0o2775
_APPEND_LOCK = threading.RLock()


class SharedStateError(RuntimeError):
    """Raised when a durable shared-state operation cannot be completed."""


def _mode_from_env(name: str, fallback: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw, 8)
    except ValueError:
        return fallback


def _identity_from_env() -> tuple[int | None, int | None]:
    def parse(name: str) -> int | None:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    return parse("NETLAB_SHARED_UID"), parse("NETLAB_SHARED_GID")


def shared_file_mode() -> int:
    return _mode_from_env("NETLAB_SHARED_FILE_MODE", DEFAULT_FILE_MODE)


def shared_dir_mode() -> int:
    return _mode_from_env("NETLAB_SHARED_DIR_MODE", DEFAULT_DIR_MODE)


def _apply_identity(path: Path, mode: int, uid: int | None, gid: int | None) -> None:
    try:
        os.chmod(path, mode)
    except PermissionError:
        # The existing ownership can prevent chmod from an unprivileged host
        # process.  The diagnostic/repair path reports this explicitly.
        pass
    if uid is not None or gid is not None:
        try:
            os.chown(path, -1 if uid is None else uid, -1 if gid is None else gid)
        except PermissionError:
            pass


def ensure_shared_directory(path: str | Path, mode: int | None = None) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    uid, gid = _identity_from_env()
    _apply_identity(target, shared_dir_mode() if mode is None else mode, uid, gid)
    return target


def atomic_write_bytes(
    path: str | Path,
    payload: bytes,
    *,
    mode: int | None = None,
    uid: int | None = None,
    gid: int | None = None,
) -> Path:
    """Atomically replace *path* and preserve a shared-readable final mode."""

    target = Path(path)
    ensure_shared_directory(target.parent)
    final_mode = shared_file_mode() if mode is None else mode
    env_uid, env_gid = _identity_from_env()
    uid = env_uid if uid is None else uid
    gid = env_gid if gid is None else gid
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _apply_identity(temporary, final_mode, uid, gid)
        os.replace(temporary, target)
        _apply_identity(target, final_mode, uid, gid)
        try:
            directory_fd = os.open(target.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
        return target
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise SharedStateError(f"Failed atomic write to {target}: {exc}") from exc


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    mode: int | None = None,
    uid: int | None = None,
    gid: int | None = None,
) -> Path:
    return atomic_write_bytes(
        path, text.encode("utf-8"), mode=mode, uid=uid, gid=gid
    )


def atomic_write_json(
    path: str | Path,
    value: Any,
    *,
    mode: int | None = None,
    uid: int | None = None,
    gid: int | None = None,
) -> Path:
    encoded = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    return atomic_write_text(path, encoded, mode=mode, uid=uid, gid=gid)


def append_jsonl(path: str | Path, payload: Any, *, mode: int | None = None) -> Path:
    target = Path(path)
    ensure_shared_directory(target.parent)
    final_mode = shared_file_mode() if mode is None else mode
    line = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ) + "\n"
    with _APPEND_LOCK:
        with target.open("a", encoding="utf-8") as stream:
            stream.write(line)
            stream.flush()
            os.fsync(stream.fileno())
        uid, gid = _identity_from_env()
        _apply_identity(target, final_mode, uid, gid)
    return target


def read_json(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    try:
        with target.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return default


def permission_diagnostic(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    result: dict[str, Any] = {
        "path": str(target),
        "exists": target.exists(),
        "readable": False,
        "writable": False,
        "mode": None,
        "uid": None,
        "gid": None,
        "is_directory": False,
    }
    if not target.exists():
        return result
    try:
        information = target.stat()
        result.update(
            readable=os.access(target, os.R_OK),
            writable=os.access(target, os.W_OK),
            mode=oct(stat.S_IMODE(information.st_mode)),
            uid=information.st_uid,
            gid=information.st_gid,
            is_directory=target.is_dir(),
        )
    except OSError as exc:
        result["error"] = str(exc)
    return result


def freshness(
    path: str | Path, *, now: float | None = None, max_age_s: float = 5.0
) -> dict[str, Any]:
    target = Path(path)
    current = time.time() if now is None else now
    diagnostic = permission_diagnostic(target)
    if not diagnostic["exists"]:
        return {
            **diagnostic,
            "fresh": False,
            "age_s": None,
        }
    try:
        age = max(0.0, current - target.stat().st_mtime)
    except OSError:
        age = None
    return {
        **diagnostic,
        "fresh": bool(diagnostic["readable"] and age is not None and age <= max_age_s),
        "age_s": age,
    }


def repair_shared_tree(
    path: str | Path,
    *,
    file_mode: int | None = None,
    dir_mode: int | None = None,
) -> dict[str, Any]:
    final_file_mode = shared_file_mode() if file_mode is None else file_mode
    final_dir_mode = shared_dir_mode() if dir_mode is None else dir_mode
    root = ensure_shared_directory(path, final_dir_mode)
    uid, gid = _identity_from_env()
    counts: dict[str, Any] = {
        "ok": True,
        "path": str(root),
        "directories": 0,
        "files": 0,
        "errors": 0,
        "error_details": [],
    }
    for item in [root, *root.rglob("*")]:
        try:
            if item.is_dir():
                _apply_identity(item, final_dir_mode, uid, gid)
                counts["directories"] += 1
            elif item.is_file():
                _apply_identity(item, final_file_mode, uid, gid)
                counts["files"] += 1
        except OSError as exc:
            counts["errors"] += 1
            counts["error_details"].append({"path": str(item), "message": str(exc)})
    counts["ok"] = counts["errors"] == 0
    return counts
