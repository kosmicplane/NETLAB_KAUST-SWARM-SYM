"""Persistent NETLAB desired/observed-state bridge for Isaac Sim.

This module is intentionally usable both from a Kit extension and from the
headless autoload path. It consumes revisioned desired state, applies embodied
UAV transforms idempotently, and publishes permission-safe heartbeat and
acknowledgement files. Rendering never advances authoritative packet state.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

CONFIG_PATH = Path(os.environ.get("SNAAS_CONFIG", "/workspace/shared/snaas_relay_config.json"))
RESULTS_DIR = Path(os.environ.get("SNAAS_RESULTS_DIR", "/workspace/results"))
SHARED_DIR = Path(os.environ.get("SNAAS_SHARED_DIR", "/workspace/shared"))
SIGNAL_CANDIDATES = (
    Path(os.environ.get("SNAAS_ISAAC_SYNC_SIGNAL", str(RESULTS_DIR / "snaas_isaac_sync_signal.json"))),
    SHARED_DIR / "snaas_isaac_sync_signal.json",
    SHARED_DIR / "revision_isaac_request.json",
)
HEARTBEAT_PATH = Path(os.environ.get("SNAAS_ISAAC_HEARTBEAT", str(RESULTS_DIR / "snaas_isaac_heartbeat.json")))
ACK_PATH = Path(os.environ.get("SNAAS_ISAAC_SYNC_ACK", str(RESULTS_DIR / "snaas_isaac_sync_ack.json")))
DEMO_ROOT = os.environ.get("SNAAS_DEMO_ROOT", "/World/NETLAB_SNAAS_Relay_Chain_Demo")
FILE_MODE = 0o664
DIR_MODE = 0o2775


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, json.JSONDecodeError):
        return default


def _atomic_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, DIR_MODE)
    except OSError:
        pass
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, FILE_MODE)
        os.replace(tmp, path)
        os.chmod(path, FILE_MODE)  # 0o664 is a required host/container contract.
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _desired_config(signal: Dict[str, Any]) -> Dict[str, Any]:
    candidate = signal.get("configuration") or signal.get("config") or signal.get("candidate")
    if isinstance(candidate, dict):
        return candidate
    path_value = signal.get("configuration_path") or signal.get("config_path")
    if path_value:
        loaded = _read_json(Path(path_value), {})
        if isinstance(loaded, dict):
            return loaded
    loaded = _read_json(CONFIG_PATH, {})
    return loaded if isinstance(loaded, dict) else {}


def _revision(signal: Dict[str, Any]) -> str:
    return str(signal.get("revision_id") or signal.get("revision") or "")


def _iter_drones(config: Dict[str, Any]) -> Iterable[tuple[int, str, list[float]]]:
    swarm = config.get("swarm", {}) if isinstance(config.get("swarm"), dict) else {}
    drones = swarm.get("drones", [])
    if isinstance(drones, dict):
        drones = list(drones.values())
    for offset, drone in enumerate(drones if isinstance(drones, list) else [], start=1):
        if not isinstance(drone, dict):
            continue
        drone_id = str(drone.get("id", f"drone_{offset}"))
        index = int(drone.get("index", offset))
        raw = drone.get("position", [index * 18.0, 0.0, 20.0])
        try:
            position = [float(raw[0]), float(raw[1]), float(raw[2])]
        except Exception:
            position = [index * 18.0, 0.0, 20.0]
        yield index, drone_id, position


def _get_stage():
    try:
        import omni.usd  # type: ignore
        return omni.usd.get_context().get_stage()
    except Exception:
        return None


def _set_translation(path: str, position: list[float]) -> bool:
    stage = _get_stage()
    if stage is None:
        return False
    try:
        from pxr import Gf, UsdGeom  # type: ignore
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            return False
        xform = UsdGeom.Xformable(prim)
        translate = None
        for operation in xform.GetOrderedXformOps():
            if operation.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                translate = operation
                break
        if translate is None:
            translate = xform.AddTranslateOp()
        translate.Set(Gf.Vec3d(*position))
        return True
    except Exception:
        return False


def _observe_position(path: str) -> Optional[list[float]]:
    stage = _get_stage()
    if stage is None:
        return None
    try:
        from pxr import UsdGeom  # type: ignore
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsValid():
            return None
        matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0.0)
        value = matrix.ExtractTranslation()
        return [float(value[0]), float(value[1]), float(value[2])]
    except Exception:
        return None


class NetlabSnaasBridge:
    """Idempotent persistent bridge driven by revision IDs and hashes."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self.last_revision_id = ""
        self.last_signal_mtime_ns = -1
        self.last_error = ""
        self.scene_ready = False
        self.observed_positions: Dict[str, list[float]] = {}
        self.scene_checksum = ""
        self.sequence = 0

    def _latest_signal(self) -> tuple[Path, Dict[str, Any]]:
        candidates: list[tuple[int, Path]] = []
        for path in SIGNAL_CANDIDATES:
            try:
                candidates.append((path.stat().st_mtime_ns, path))
            except OSError:
                continue
        if not candidates:
            return SIGNAL_CANDIDATES[0], {}
        _, path = max(candidates, key=lambda item: item[0])
        value = _read_json(path, {})
        return path, value if isinstance(value, dict) else {}

    def _apply(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        config = _desired_config(signal)
        observed: Dict[str, list[float]] = {}
        apply_failures: list[str] = []
        applied_count = 0
        maximum_error_m = 0.0
        desired_drones = list(_iter_drones(config))
        for index, drone_id, desired in desired_drones:
            path = f"{DEMO_ROOT}/Drone_{index}"
            applied = _set_translation(path, desired)
            applied_count += int(applied)
            actual = _observe_position(path)
            if not applied or actual is None:
                apply_failures.append(drone_id)
                continue
            observed[drone_id] = actual
            error = sum((actual[i] - desired[i]) ** 2 for i in range(3)) ** 0.5
            maximum_error_m = max(maximum_error_m, error)
        topology = config.get("topology", {}) if isinstance(config.get("topology"), dict) else {}
        checksum_payload = {"observed_positions": observed, "topology": topology}
        self.observed_positions = observed
        self.scene_checksum = _canonical_hash(checksum_payload)
        tolerance_m = float(os.environ.get("NETLAB_ISAAC_POSITION_TOLERANCE_M", "0.05"))
        expected_count = len(desired_drones)
        self.scene_ready = bool(
            expected_count > 0
            and applied_count == expected_count
            and len(observed) == expected_count
            and maximum_error_m <= tolerance_m
        )
        revision_id = _revision(signal)
        hashes = signal.get("hashes") if isinstance(signal.get("hashes"), dict) else {}
        acknowledgement = {
            "ok": self.scene_ready,
            "accepted": self.scene_ready,
            "participant": "isaac",
            "revision": revision_id,
            "revision_id": revision_id,
            "parent_revision_id": str(signal.get("parent_revision_id", "")),
            "command_id": str(signal.get("command_id", "")),
            "scene_ready": self.scene_ready,
            "state": "SCENE_READY" if self.scene_ready else "APPLY_FAILED",
            "observed_hashes": hashes if self.scene_ready else {},
            "observed_positions": observed,
            "maximum_position_error_m": maximum_error_m,
            "scene_checksum": self.scene_checksum,
            "expected_entity_count": expected_count,
            "applied_entity_count": applied_count,
            "failed_entities": apply_failures,
            "position_tolerance_m": tolerance_m,
            "timestamp": time.time(),
            "error": "" if self.scene_ready else "One or more desired UAV transforms were not applied or verified.",
        }
        _atomic_json(ACK_PATH, acknowledgement)
        if self.scene_ready:
            self.last_revision_id = revision_id
        return acknowledgement

    def tick(self) -> None:
        self.sequence += 1
        try:
            signal_path, signal = self._latest_signal()
            try:
                mtime_ns = signal_path.stat().st_mtime_ns
            except OSError:
                mtime_ns = -1
            revision_id = _revision(signal)
            if signal and (mtime_ns != self.last_signal_mtime_ns or revision_id != self.last_revision_id):
                self._apply(signal)
                self.last_signal_mtime_ns = mtime_ns
            heartbeat = {
                "service": "netlab.snaas.bridge",
                "ready": True,
                "scene_ready": self.scene_ready,
                "state": "SCENE_READY" if self.scene_ready else "BRIDGE_READY",
                "revision": self.last_revision_id,
                "revision_id": self.last_revision_id,
                "scene_checksum": self.scene_checksum,
                "observed_positions": self.observed_positions,
                "sequence": self.sequence,
                "timestamp": time.time(),
                "uptime_s": time.time() - self.started_at,
                "error": self.last_error,
            }
            _atomic_json(HEARTBEAT_PATH, heartbeat)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            _atomic_json(HEARTBEAT_PATH, {
                "service": "netlab.snaas.bridge",
                "ready": False,
                "scene_ready": False,
                "state": "DEGRADED",
                "revision_id": self.last_revision_id,
                "scene_checksum": self.scene_checksum,
                "observed_positions": self.observed_positions,
                "sequence": self.sequence,
                "timestamp": time.time(),
                "error": self.last_error,
            })


_bridge: Optional[NetlabSnaasBridge] = None


def get_bridge() -> NetlabSnaasBridge:
    global _bridge
    if _bridge is None:
        _bridge = NetlabSnaasBridge()
    return _bridge


def tick() -> None:
    get_bridge().tick()
