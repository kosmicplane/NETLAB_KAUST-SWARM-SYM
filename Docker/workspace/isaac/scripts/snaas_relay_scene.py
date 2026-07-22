
# NETLAB SNaaS - SNaaS relay-chain / relay-forest Isaac Sim scene.
# Usage in Isaac Sim Script Editor:
#   exec(open("/workspace/isaac/scripts/snaas_relay_scene.py").read())

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import omni.kit.app
import omni.usd
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade

from netlab.io import atomic_write_json

try:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from std_msgs.msg import String
    ROS_AVAILABLE = True
except Exception as exc:
    ROS_AVAILABLE = False
    ROS_IMPORT_ERROR = str(exc)

CONFIG_PATH = os.environ.get("SNAAS_CONFIG", "/workspace/shared/snaas_relay_config.json")
LATEST_STATUS_PATH = os.environ.get("SNAAS_LATEST_STATUS", "/workspace/results/snaas_relay_latest_status.json")
ISAAC_SYNC_SIGNAL_PATH = os.environ.get("SNAAS_ISAAC_SYNC_SIGNAL", "/workspace/results/snaas_isaac_sync_signal.json")
ISAAC_SYNC_ACK_PATH = os.environ.get("SNAAS_ISAAC_SYNC_ACK", "/workspace/results/snaas_isaac_sync_ack.json")
ISAAC_HEARTBEAT_PATH = os.environ.get("SNAAS_ISAAC_HEARTBEAT", "/workspace/results/snaas_isaac_heartbeat.json")

VISUAL_CONFIG_PATH = "/workspace/results/snaas_relay_visual_config.json"


def _load_runtime_visual_config() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "show_coverage_indicators": True,
        "status_ball_scale": 0.70,
        "packet_marker_scale": 0.90,
    }
    try:
        if os.path.exists(VISUAL_CONFIG_PATH) and os.path.getsize(VISUAL_CONFIG_PATH) > 0:
            with open(VISUAL_CONFIG_PATH, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                cfg.update(loaded)
    except Exception:
        pass

    def _bool(value: Any, default: bool = True) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _scale(value: Any, default: float) -> float:
        try:
            return max(0.05, min(float(value), 5.0))
        except Exception:
            return default

    cfg["show_coverage_indicators"] = _bool(cfg.get("show_coverage_indicators"), True)
    cfg["status_ball_scale"] = _scale(cfg.get("status_ball_scale"), 0.70)
    cfg["packet_marker_scale"] = _scale(cfg.get("packet_marker_scale"), 0.90)
    return cfg

WORLD_PATH = "/World"
DEMO_ROOT = "/World/NETLAB_SNAAS_Relay_Chain_Demo"
COVERAGE_PATH = f"{DEMO_ROOT}/CoverageArea"

BLACK = (0.02, 0.02, 0.02)
GREEN = (0.0, 1.0, 0.15)
BLUE = (0.1, 0.55, 1.0)
YELLOW = (1.0, 0.82, 0.0)
RED = (1.0, 0.05, 0.02)
GREY = (0.45, 0.45, 0.45)
CYAN = (0.05, 0.9, 1.0)
PURPLE = (0.7, 0.35, 1.0)
STATION_COLOR = (0.85, 0.25, 0.05)
COVERAGE_COLOR = (0.1, 0.75, 1.0)
WORLD_COLOR = (0.20, 0.42, 0.82)
ANTENNA_COLOR = (1.0, 0.78, 0.08)


def _safe_name(value: Any, fallback: str = "item") -> str:
    text = str(value or fallback)
    cleaned = "".join(c if c.isalnum() or c in "_-" else "_" for c in text)
    return cleaned or fallback


def _stage():
    return omni.usd.get_context().get_stage()


def _load_config(path: str = CONFIG_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        print(f"[NETLAB-SNAAS][WARN] Config not found: {path}. Using defaults.")
        return {
            "experiment_name": "snaas_relay_chain_default",
            "drone_count": 6,
            "branch_count": 1,
            "hop_period_s": 0.5,
            "coverage_radius_m": 140.0,
            "coverage_width_m": 70.0,
            "direction_deg": 0.0,
            "movement_pattern": "hover",
            "movement_amplitude_m": 10.0,
            "movement_speed": 1.0,
            "visual_follow_alpha": 0.18,
            "wind_speed_mps": 1.2,
            "wind_direction_deg": 35.0,
            "turbulence_intensity": 0.28,
            "station": {"position": [0.0, 0.0, 1.5]},
            "drones": [{"index": i, "id": f"drone_{i}", "position": [i * 18.0, 0.0, 18.0 + (i % 3) * 2.0]} for i in range(1, 7)],
            "visual": {"custom_drone_usd": "/workspace/isaac/local_assets/drones/tu_drone.usd", "drone_scale": 0.2, "show_drone_coverage_rings": True, "show_drone_coverage_spheres": False, "drone_coverage_opacity": 0.035, "coverage_visual_radius_m": 35.0, "coverage_ring_width": 0.004},
        }
    with open(path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if isinstance(loaded, dict) and {"experiment", "swarm", "communication", "topology"}.issubset(loaded):
        revision_meta = dict(loaded.get("_netlab_revision") or {})
        try:
            from netlab.config import emit_legacy_config
            loaded = emit_legacy_config(loaded)
            if revision_meta:
                loaded["_netlab_revision"] = revision_meta
        except Exception as exc:
            raise RuntimeError(f"Unable to project the authoritative experiment for Isaac: {exc}") from exc
    return loaded


def _ensure_world() -> None:
    if not _stage().GetPrimAtPath(Sdf.Path(WORLD_PATH)).IsValid():
        UsdGeom.Xform.Define(_stage(), WORLD_PATH)


def _remove_if_exists(path: str) -> None:
    if _stage().GetPrimAtPath(path).IsValid():
        _stage().RemovePrim(path)


def _clear_xform(path: str) -> UsdGeom.Xformable:
    prim = _stage().GetPrimAtPath(path)
    xform = UsdGeom.Xformable(prim)
    xform.ClearXformOpOrder()
    return xform


def _set_transform(path: str, translation=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)) -> None:
    xform = _clear_xform(path)
    xform.AddTranslateOp().Set(Gf.Vec3d(*translation))
    xform.AddRotateXYZOp().Set(Gf.Vec3f(*rotation))
    xform.AddScaleOp().Set(Gf.Vec3f(*scale))


def _display_color(path: str, color: Tuple[float, float, float]) -> None:
    prim = _stage().GetPrimAtPath(path)
    if prim and prim.IsValid() and prim.IsA(UsdGeom.Gprim):
        UsdGeom.Gprim(prim).CreateDisplayColorAttr([Gf.Vec3f(*color)])


def _make_material(path: str, color: Tuple[float, float, float], opacity: float = 1.0) -> UsdShade.Material:
    stage = _stage()
    if stage.GetPrimAtPath(path).IsValid():
        return UsdShade.Material(stage.GetPrimAtPath(path))
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, f"{path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.55)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(opacity))
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def _bind_material(path: str, material: UsdShade.Material) -> None:
    prim = _stage().GetPrimAtPath(path)
    if prim.IsValid():
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)


def _cube(path: str, translation, scale, color) -> None:
    UsdGeom.Cube.Define(_stage(), path)
    _set_transform(path, translation=translation, scale=scale)
    _display_color(path, color)


def _sphere(path: str, translation, scale, color, material: Optional[UsdShade.Material] = None) -> None:
    sphere = UsdGeom.Sphere.Define(_stage(), path)
    sphere.CreateRadiusAttr(1.0)
    _set_transform(path, translation=translation, scale=scale)
    _display_color(path, color)
    if material is not None:
        _bind_material(path, material)


def _cylinder(path: str, translation, radius, height, color, rotation=(0.0, 0.0, 0.0)) -> None:
    cylinder = UsdGeom.Cylinder.Define(_stage(), path)
    cylinder.CreateRadiusAttr(float(radius))
    cylinder.CreateHeightAttr(float(height))
    _set_transform(path, translation=translation, rotation=rotation)
    _display_color(path, color)


def _curve(path: str, points: List[Tuple[float, float, float]], color, width=0.08) -> None:
    curve = UsdGeom.BasisCurves.Define(_stage(), path)
    curve.CreateTypeAttr("linear")
    curve.CreateCurveVertexCountsAttr([len(points)])
    curve.CreatePointsAttr([Gf.Vec3f(*p) for p in points])
    curve.CreateWidthsAttr([float(width)] * len(points))
    curve.CreateDisplayColorAttr([Gf.Vec3f(*color)])


def _circle_points(plane: str, segments: int = 128) -> List[Tuple[float, float, float]]:
    pts: List[Tuple[float, float, float]] = []
    for i in range(segments + 1):
        a = 2.0 * math.pi * i / segments
        c, ss = math.cos(a), math.sin(a)
        if plane == "xy":
            pts.append((c, ss, 0.0))
        elif plane == "xz":
            pts.append((c, 0.0, ss))
        else:
            pts.append((0.0, c, ss))
    return pts


def _coverage_rings(root: str) -> None:
    rings_root = f"{root}/CoverageRings"
    UsdGeom.Xform.Define(_stage(), rings_root)
    # Thin rings, not a solid sphere: visible coverage without hiding the drone model.
    _curve(f"{rings_root}/Range_XY", _circle_points("xy"), (0.12, 0.75, 0.9), width=0.003)
    _curve(f"{rings_root}/Range_XZ", _circle_points("xz"), (0.10, 0.45, 0.75), width=0.002)
    _curve(f"{rings_root}/Range_YZ", _circle_points("yz"), (0.10, 0.45, 0.75), width=0.002)


def _prepare_usd_reference(asset_path: str) -> Tuple[bool, str]:
    if not asset_path or not os.path.exists(asset_path):
        return False, f"asset_not_found:{asset_path}"
    try:
        asset_stage = Usd.Stage.Open(asset_path)
        if asset_stage is None:
            return False, f"could_not_open:{asset_path}"
        default_prim = asset_stage.GetDefaultPrim()
        if default_prim and default_prim.IsValid():
            return True, f"defaultPrim:{default_prim.GetPath()}"
        chosen = None
        for prim in asset_stage.GetPseudoRoot().GetChildren():
            has_mesh = any(child.IsA(UsdGeom.Mesh) for child in Usd.PrimRange(prim))
            if has_mesh:
                chosen = prim
                break
        if chosen is None:
            children = list(asset_stage.GetPseudoRoot().GetChildren())
            if not children:
                return False, "empty_usd"
            chosen = children[0]
        asset_stage.SetDefaultPrim(chosen)
        asset_stage.GetRootLayer().Save()
        return True, f"defaultPrim_set:{chosen.GetPath()}"
    except Exception as exc:
        return False, f"usd_fix_failed:{exc}"


def _make_station(position: Tuple[float, float, float]) -> None:
    root = f"{DEMO_ROOT}/GroundStation"
    UsdGeom.Xform.Define(_stage(), root)
    _set_transform(root, translation=position)
    _cylinder(f"{root}/Tower", (0.0, 0.0, 2.0), 0.25, 4.0, STATION_COLOR)
    _sphere(f"{root}/Antenna", (0.0, 0.0, 4.3), (0.55, 0.55, 0.55), STATION_COLOR)
    _sphere(f"{root}/Beacon", (0.0, 0.0, 5.3), (0.35, 0.35, 0.35), BLACK)


def _make_fallback_drone(root: str, base_color: Tuple[float, float, float]) -> None:
    UsdGeom.Xform.Define(_stage(), f"{root}/DefaultVisual")
    _cube(f"{root}/DefaultVisual/Body", (0.0, 0.0, 0.0), (0.55, 0.32, 0.13), base_color)
    _cube(f"{root}/DefaultVisual/Nose", (0.66, 0.0, 0.02), (0.12, 0.18, 0.08), (0.95, 0.95, 0.95))
    _cube(f"{root}/DefaultVisual/Arm_X", (0.0, 0.0, 0.02), (1.05, 0.045, 0.035), (0.08, 0.08, 0.08))
    _cube(f"{root}/DefaultVisual/Arm_Y", (0.0, 0.0, 0.025), (0.045, 1.05, 0.035), (0.08, 0.08, 0.08))
    for i, (x, y) in enumerate([(0.95, 0.95), (0.95, -0.95), (-0.95, 0.95), (-0.95, -0.95)], start=1):
        _sphere(f"{root}/DefaultVisual/Motor_{i}", (x, y, 0.055), (0.095, 0.095, 0.055), base_color)
        _cube(f"{root}/DefaultVisual/RotorBlade_{i}_A", (x, y, 0.12), (0.34, 0.028, 0.006), BLACK)
        _cube(f"{root}/DefaultVisual/RotorBlade_{i}_B", (x, y, 0.121), (0.028, 0.34, 0.006), BLACK)


def _make_drone(index: int, position: Tuple[float, float, float], config: Dict[str, Any]) -> None:
    root = f"{DEMO_ROOT}/Drone_{index}"
    if _stage().GetPrimAtPath(root).IsValid():
        return
    UsdGeom.Xform.Define(_stage(), root)
    _set_transform(root, translation=position)
    base_color = (1.0, 0.7, 0.1) if index % 2 else (0.05, 0.85, 1.0)
    custom_usd = str(config.get("visual", {}).get("custom_drone_usd", "")).strip()
    loaded_custom = False
    if custom_usd and os.path.exists(custom_usd):
        ok, info = _prepare_usd_reference(custom_usd)
        if ok:
            visual = f"{root}/CustomDroneVisual"
            UsdGeom.Xform.Define(_stage(), visual)
            _stage().GetPrimAtPath(visual).GetReferences().AddReference(custom_usd)
            scale = float(config.get("visual", {}).get("drone_scale", 0.2))
            rot = config.get("visual", {}).get("drone_rotation_xyz", [0.0, 0.0, 0.0])
            _set_transform(visual, rotation=(float(rot[0]), float(rot[1]), float(rot[2])), scale=(scale, scale, scale))
            loaded_custom = True
            print(f"[NETLAB-SNAAS] Drone {index} custom USD loaded: {custom_usd} ({info})")
        else:
            print(f"[NETLAB-SNAAS][WARN] Drone {index} custom USD not used: {info}")
    elif custom_usd and index == 1:
        print(f"[NETLAB-SNAAS][INFO] Custom drone asset not found ({custom_usd}); using built-in procedural UAV visuals.")
    if not loaded_custom:
        _make_fallback_drone(root, base_color)

    _sphere(f"{root}/MessageBeacon", (0.0, 0.0, 1.45), (0.70, 0.70, 0.70), BLACK)
    _cylinder(f"{root}/Antenna", (0.0, 0.0, 0.75), 0.03, 1.0, CYAN)
    # Coverage is intentionally rendered as thin rings instead of a translucent solid sphere.
    # Solid transparent spheres hid the drone model in RTX/WebRTC, which is bad for the demo.
    _coverage_rings(root)
    # Keep old path absent/invisible for compatibility with older configs.


def _make_coverage_area(config: Dict[str, Any]) -> None:
    station = tuple(float(v) for v in config.get("station", {}).get("position", [0.0, 0.0, 1.5]))
    radius = float(config.get("coverage_radius_m", 120.0))
    width = float(config.get("coverage_width_m", 60.0))
    direction_deg = float(config.get("direction_deg", 0.0))
    theta = math.radians(direction_deg)
    dx, dy = math.cos(theta), math.sin(theta)
    px, py = -dy, dx
    center = (station[0] + dx * radius * 0.5, station[1] + dy * radius * 0.5, 0.05)
    corners = []
    for along, side in [(0, -1), (radius, -1), (radius, 1), (0, 1), (0, -1)]:
        corners.append((station[0] + dx * along + px * side * width * 0.5, station[1] + dy * along + py * side * width * 0.5, 0.08))
    _curve(COVERAGE_PATH, corners, COVERAGE_COLOR, width=0.12)
    _sphere(f"{DEMO_ROOT}/CoverageCenter", center, (0.30, 0.30, 0.04), COVERAGE_COLOR)


def _make_antenna_visual(antenna: Dict[str, Any], index: int) -> None:
    if not bool(antenna.get("enabled", True)):
        return
    ant_id = _safe_name(antenna.get("id", f"antenna_{index}"), f"antenna_{index}")
    root = f"{DEMO_ROOT}/Antennas/{ant_id}"
    UsdGeom.Xform.Define(_stage(), root)
    pos = tuple(float(v) for v in antenna.get("position", [0.0, 0.0, 3.0]))
    rot = antenna.get("rotation_xyz", [0.0, 0.0, float(antenna.get("azimuth_deg", 0.0) or 0.0)])
    while len(rot) < 3:
        rot.append(0.0)
    _set_transform(root, translation=pos, rotation=(float(rot[0]), float(rot[1]), float(rot[2])))
    gain = float(antenna.get("gain_dbi", 8.0) or 8.0)
    beam = float(antenna.get("beamwidth_deg", 120.0) or 120.0)
    height = max(1.0, min(7.0, 1.7 + gain * 0.18))
    _cylinder(f"{root}/Mast", (0.0, 0.0, height * 0.5), 0.055, height, ANTENNA_COLOR)
    _sphere(f"{root}/Head", (0.0, 0.0, height + 0.15), (0.22, 0.22, 0.22), ANTENNA_COLOR)
    # Sector fan as three beam rays in local coordinates.  It is intentionally
    # lightweight and updates through full scene reload on config changes.
    radius = max(4.0, min(45.0, gain * 2.2))
    half = math.radians(max(5.0, min(360.0, beam)) * 0.5)
    z = height + 0.15
    rays = [0.0, -half, half] if beam < 350 else [0, math.pi * 0.5, math.pi, math.pi * 1.5]
    for i, angle in enumerate(rays):
        end = (radius * math.cos(angle), radius * math.sin(angle), z + 0.12 * math.sin(angle))
        _curve(f"{root}/Beam_{i}", [(0.0, 0.0, z), end], ANTENNA_COLOR, width=0.025)


def _make_antennas(config: Dict[str, Any]) -> None:
    UsdGeom.Xform.Define(_stage(), f"{DEMO_ROOT}/Antennas")
    antennas = config.get("antennas", config.get("visual", {}).get("antennas", []))
    if not isinstance(antennas, list):
        return
    for idx, ant in enumerate(antennas, start=1):
        if isinstance(ant, dict):
            _make_antenna_visual(ant, idx)


def _make_world_layer(world: Dict[str, Any], index: int) -> None:
    if not bool(world.get("enabled", True)):
        return
    world_id = _safe_name(world.get("id", f"world_{index}"), f"world_{index}")
    root = f"{DEMO_ROOT}/WorldLayers/{world_id}"
    UsdGeom.Xform.Define(_stage(), root)
    pos = tuple(float(v) for v in world.get("position", [0.0, 0.0, 0.0]))
    rot = world.get("rotation_xyz", [0.0, 0.0, 0.0])
    scale = world.get("scale", [1.0, 1.0, 1.0])
    while len(rot) < 3:
        rot.append(0.0)
    while len(scale) < 3:
        scale.append(1.0)
    _set_transform(root, translation=pos, rotation=(float(rot[0]), float(rot[1]), float(rot[2])), scale=(float(scale[0]), float(scale[1]), float(scale[2])))
    asset_path = str(world.get("asset_path", "")).strip()
    if asset_path and os.path.exists(asset_path):
        visual = f"{root}/AssetReference"
        UsdGeom.Xform.Define(_stage(), visual)
        _stage().GetPrimAtPath(visual).GetReferences().AddReference(asset_path)
        print(f"[NETLAB-SNAAS] Loaded world layer {world_id}: {asset_path}")
    else:
        # Procedural proxy keeps the researcher aware that a world layer exists even
        # before a USD asset is mounted into the container.
        _cube(f"{root}/ProxyBase", (0.0, 0.0, 0.02), (12.0, 12.0, 0.025), WORLD_COLOR)
        _cube(f"{root}/ProxyBlock_A", (2.2, -1.8, 1.0), (1.2, 1.8, 1.0), (0.18, 0.30, 0.46))
        _cube(f"{root}/ProxyBlock_B", (-2.5, 2.2, 1.5), (1.7, 1.0, 1.5), (0.16, 0.26, 0.42))
        if asset_path:
            print(f"[NETLAB-SNAAS][WARN] World asset not found for {world_id}: {asset_path}; using proxy layer.")


def _make_world_layers(config: Dict[str, Any]) -> None:
    UsdGeom.Xform.Define(_stage(), f"{DEMO_ROOT}/WorldLayers")
    worlds = config.get("worlds", config.get("visual", {}).get("worlds", []))
    if not isinstance(worlds, list):
        return
    for idx, world in enumerate(worlds, start=1):
        if isinstance(world, dict):
            _make_world_layer(world, idx)


def _make_scene(config: Dict[str, Any]) -> None:
    _ensure_world()
    _remove_if_exists(DEMO_ROOT)
    UsdGeom.Xform.Define(_stage(), DEMO_ROOT)
    _make_world_layers(config)
    _make_antennas(config)

    if not _stage().GetPrimAtPath("/World/NETLAB_Sun").IsValid():
        sun = UsdLux.DistantLight.Define(_stage(), "/World/NETLAB_Sun")
        sun.CreateIntensityAttr(4500)
        UsdGeom.Xformable(sun.GetPrim()).AddRotateXYZOp().Set(Gf.Vec3f(-52.0, 0.0, -35.0))
    if not _stage().GetPrimAtPath("/World/NETLAB_Sky").IsValid():
        UsdLux.DomeLight.Define(_stage(), "/World/NETLAB_Sky").CreateIntensityAttr(350)

    station_position = tuple(float(v) for v in config.get("station", {}).get("position", [0.0, 0.0, 1.5]))
    _make_station(station_position)
    if config.get("visual", {}).get("show_coverage_area", True):
        _make_coverage_area(config)

    for item in config.get("drones", []):
        index = int(item.get("index", 1))
        pos = tuple(float(v) for v in item.get("position", [index * 18.0, 0.0, 20.0]))
        _make_drone(index, pos, config)

    _sphere(f"{DEMO_ROOT}/PacketMarker", station_position, (0.18, 0.18, 0.18), GREEN)

    camera = UsdGeom.Camera.Define(_stage(), f"{DEMO_ROOT}/Overview_Camera")
    _set_transform(f"{DEMO_ROOT}/Overview_Camera", translation=(station_position[0] + 50.0, station_position[1] - 95.0, 70.0), rotation=(60.0, 0.0, 32.0))
    camera.CreateFocalLengthAttr(24)


def _vec_lerp(a: Tuple[float, float, float], b: Tuple[float, float, float], alpha: float) -> Tuple[float, float, float]:
    return tuple(float(a[i]) + (float(b[i]) - float(a[i])) * alpha for i in range(3))  # type: ignore[return-value]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


class SnaasRelayScene:
    def __init__(self) -> None:
        self.config = _load_config()
        self.start_time = time.time()
        self.last_publish_time = 0.0
        self.publish_period_s = 0.1
        self.ros_ready = False
        self.ros_node = None
        self.pose_publishers: Dict[int, Any] = {}
        self.last_status: Dict[str, Any] = {}
        self._last_status_file_mtime = 0.0
        self._last_config_file_mtime = os.path.getmtime(CONFIG_PATH) if os.path.exists(CONFIG_PATH) else 0.0
        # Start at zero so a sync request written before Isaac finished loading is
        # consumed and acknowledged on the first update.
        self._last_sync_signal_mtime = 0.0
        self._last_heartbeat_time = 0.0
        self.current_revision_id = ""
        self.current_parent_revision_id = ""
        self.current_revision_hashes: Dict[str, Any] = {}
        self.pending_revision_id = ""
        self.pending_parent_revision_id = ""
        self.pending_revision_hashes: Dict[str, Any] = {}
        self.current_config_source = CONFIG_PATH
        self.scene_ready = False
        self.last_event_time = time.time()
        self.target_positions: Dict[int, Tuple[float, float, float]] = {}
        self.current_positions: Dict[int, Tuple[float, float, float]] = {}
        self.motion_velocity: Dict[int, Tuple[float, float, float]] = {}
        self.motion_yaw: Dict[int, float] = {}
        self._last_visual_update = time.time()
        self.branch_link_paths: List[str] = []
        self.branch_packet_paths: List[str] = []

        for item in self.config.get("drones", []):
            index = int(item.get("index", 1))
            pos = tuple(float(v) for v in item.get("position", [index * 18.0, 0.0, 20.0]))
            self.target_positions[index] = pos
            self.current_positions[index] = pos

        _make_scene(self.config)
        self.scene_ready = True
        self._setup_ros()
        self.subscription = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(self._on_update, name="NETLAB SNaaS relay-chain scene update")
        print("[NETLAB-SNAAS] Relay-chain Isaac scene started.")
        print(f"[NETLAB-SNAAS] Config: {CONFIG_PATH}")
        if self.ros_ready:
            print("[NETLAB-SNAAS] ROS 2 pose publishers and chain-status subscriber are active.")
        else:
            print("[NETLAB-SNAAS] ROS 2 not active in Isaac context; JSON fallback visual mode active.")

    def shutdown(self) -> None:
        try:
            self.subscription = None
            if self.ros_node is not None:
                self.ros_node.destroy_node()
        except Exception:
            traceback.print_exc()

    def _setup_ros(self) -> None:
        if not ROS_AVAILABLE:
            print(f"[NETLAB-SNAAS] rclpy unavailable in Isaac context: {ROS_IMPORT_ERROR}")
            return
        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self.ros_node = rclpy.create_node("isaac_snaas_relay_scene")
            for index in sorted(self.current_positions):
                self.pose_publishers[index] = self.ros_node.create_publisher(PoseStamped, f"/swarm/drone_{index}/state", 10)
            self.ros_node.create_subscription(String, "/swarm/chain/status", self._status_cb, 10)
            self.ros_ready = True
        except Exception as exc:
            print(f"[NETLAB-SNAAS] ROS setup failed: {exc}")
            traceback.print_exc()

    def _config_drone_positions(self, config: Optional[Dict[str, Any]] = None) -> Dict[int, Tuple[float, float, float]]:
        cfg = config if config is not None else self.config
        positions: Dict[int, Tuple[float, float, float]] = {}
        for item in cfg.get("drones", []):
            try:
                index = int(item.get("index", len(positions) + 1))
                vec = item.get("position", [index * 18.0, 0.0, 20.0])
                positions[index] = (float(vec[0]), float(vec[1]), float(vec[2]))
            except Exception:
                continue
        return positions

    def _reload_scene_from_config(
        self,
        reason: str = "config_file_changed",
        config_path: Optional[str] = None,
        *,
        snap_to_targets: bool = False,
    ) -> None:
        source_path = config_path or CONFIG_PATH
        new_config = _load_config(source_path)
        new_positions = self._config_drone_positions(new_config)
        if not new_positions:
            print("[NETLAB-SNAAS][WARN] Config has no drones; keeping current scene.")
            return
        previous_positions = dict(self.current_positions)
        self.config = new_config
        self.current_config_source = source_path
        revision_meta = new_config.get("_netlab_revision", {}) if isinstance(new_config.get("_netlab_revision", {}), dict) else {}
        if revision_meta:
            self.pending_revision_id = str(revision_meta.get("revision_id", self.pending_revision_id))
            self.pending_parent_revision_id = str(revision_meta.get("parent_revision_id", self.pending_parent_revision_id))
            self.pending_revision_hashes = {key: value for key, value in revision_meta.items() if key.endswith("_hash")}
        _make_scene(self.config)
        self.target_positions = dict(new_positions)
        station = tuple(float(v) for v in self.config.get("station", {}).get("position", [0.0, 0.0, 1.5]))
        def _spawn_position(idx: int, pos: Tuple[float, float, float]) -> Tuple[float, float, float]:
            if idx in previous_positions:
                return previous_positions[idx]
            # New UAVs enter organically from near the station/below their target.
            return (station[0] + 1.2 * idx, station[1] - 0.8 * idx, max(0.7, min(pos[2] - 14.0, station[2] + 2.0)))
        self.current_positions = (
            dict(new_positions)
            if snap_to_targets
            else {idx: _spawn_position(idx, pos) for idx, pos in new_positions.items()}
        )
        if snap_to_targets:
            for idx, pos in new_positions.items():
                _set_transform(f"{DEMO_ROOT}/Drone_{idx}", translation=pos)
        self.motion_velocity = {idx: self.motion_velocity.get(idx, (0.0, 0.0, 0.0)) for idx in new_positions}
        for idx in list(self.pose_publishers):
            if idx not in new_positions:
                self.pose_publishers.pop(idx, None)
        if self.ros_ready and self.ros_node is not None:
            for idx in sorted(new_positions):
                if idx not in self.pose_publishers:
                    self.pose_publishers[idx] = self.ros_node.create_publisher(PoseStamped, f"/swarm/drone_{idx}/state", 10)
        self.last_status = {}
        self.last_event_time = time.time()
        print(f"[NETLAB-SNAAS] Scene automatically reloaded from {source_path} ({reason}). Visible drones: {sorted(new_positions)}")

    def _poll_config_file(self) -> None:
        try:
            if not os.path.exists(CONFIG_PATH) or os.path.getsize(CONFIG_PATH) == 0:
                return
            mtime = os.path.getmtime(CONFIG_PATH)
            if mtime <= self._last_config_file_mtime:
                return
            self._last_config_file_mtime = mtime
            self._reload_scene_from_config("config_file_changed")
            # If the latest-status file is older than the new config, do not replay stale
            # status that would recreate old drones. Mission Control writes a fresh preview
            # status on save, and ROS writes fresh live status after start/apply-live.
            if os.path.exists(LATEST_STATUS_PATH):
                status_mtime = os.path.getmtime(LATEST_STATUS_PATH)
                if status_mtime < mtime:
                    self._last_status_file_mtime = status_mtime
        except Exception as exc:
            print(f"[NETLAB-SNAAS] Could not reload config file {CONFIG_PATH}: {exc}")
            traceback.print_exc()

    def _ensure_drone_visual(self, index: int, position: Tuple[float, float, float]) -> None:
        if index not in self.current_positions:
            station = tuple(float(v) for v in self.config.get("station", {}).get("position", [0.0, 0.0, 1.5]))
            spawn = (station[0] + 1.1 * index, station[1] - 0.7 * index, max(0.7, min(position[2] - 14.0, station[2] + 2.0)))
            self.current_positions[index] = spawn
            self.target_positions[index] = position
            self.motion_velocity[index] = (0.0, 0.0, 0.0)
            self.motion_yaw[index] = 0.0
            if self.ros_ready and self.ros_node is not None and index not in self.pose_publishers:
                self.pose_publishers[index] = self.ros_node.create_publisher(PoseStamped, f"/swarm/drone_{index}/state", 10)
        _make_drone(index, self.current_positions[index], self.config)

    def _apply_status_payload(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        self.last_status = payload
        self.last_event_time = time.time()
        desired = payload.get("desired_positions", {}) if isinstance(payload.get("desired_positions", {}), dict) else {}
        drones_payload = payload.get("drones", {}) if isinstance(payload.get("drones", {}), dict) else {}
        live_indices = set()
        for name, vec in desired.items():
            if name.startswith("drone_"):
                try:
                    index = int(name.split("_")[-1])
                    pos = (float(vec[0]), float(vec[1]), float(vec[2]))
                except Exception:
                    continue
                live_indices.add(index)
                self._ensure_drone_visual(index, pos)
                self.target_positions[index] = pos
        for name, drone_state in drones_payload.items():
            if name.startswith("drone_"):
                try:
                    index = int(name.split("_")[-1])
                except Exception:
                    continue
                live_indices.add(index)
                if name not in desired:
                    vec = drone_state.get("position", [index * 18.0, 0.0, 20.0]) if isinstance(drone_state, dict) else [index * 18.0, 0.0, 20.0]
                    try:
                        pos = (float(vec[0]), float(vec[1]), float(vec[2]))
                    except Exception:
                        pos = (index * 18.0, 0.0, 20.0)
                    self._ensure_drone_visual(index, pos)
        if live_indices:
            self._remove_stale_drones(live_indices)

    def _remove_stale_drones(self, live_indices: set[int]) -> None:
        stale = [idx for idx in sorted(self.current_positions) if idx not in live_indices]
        if not stale:
            return
        for idx in stale:
            _remove_if_exists(f"{DEMO_ROOT}/Drone_{idx}")
            self.current_positions.pop(idx, None)
            self.target_positions.pop(idx, None)
            self.motion_velocity.pop(idx, None)
            self.motion_yaw.pop(idx, None)
            self.pose_publishers.pop(idx, None)
        print(f"[NETLAB-SNAAS] Removed stale drone visuals: {stale}")

    def _configuration_hash(self) -> str:
        try:
            return hashlib.sha256(json.dumps(self.config, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def _atomic_json(self, path: str, payload: Dict[str, Any]) -> None:
        atomic_write_json(Path(path), payload)

    def _observe_scene_application(self, tolerance_m: float = 0.02) -> Dict[str, Any]:
        """Verify desired entities against the actual USD stage before acknowledging.

        The acknowledgement is based on observed prims and transforms, not on the
        mere presence of a synchronization request file.  This prevents Mission
        Control from committing a revision that Isaac did not embody.
        """
        desired_positions = {int(idx): tuple(float(v) for v in pos) for idx, pos in self.target_positions.items()}
        observed_positions: Dict[str, List[float]] = {}
        position_errors_m: Dict[str, float] = {}
        missing_entities: List[str] = []
        stage = _stage()
        root_ready = bool(stage.GetPrimAtPath(DEMO_ROOT).IsValid())
        for idx, target in sorted(desired_positions.items()):
            entity_id = f"drone_{idx}"
            path = f"{DEMO_ROOT}/Drone_{idx}"
            prim = stage.GetPrimAtPath(path)
            if not prim.IsValid():
                missing_entities.append(entity_id)
                continue
            try:
                matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                translation = matrix.ExtractTranslation()
                observed = (float(translation[0]), float(translation[1]), float(translation[2]))
                observed_positions[entity_id] = [round(v, 6) for v in observed]
                position_errors_m[entity_id] = float(_distance(observed, target))
            except Exception as exc:
                missing_entities.append(entity_id)
                position_errors_m[entity_id] = float("inf")
                print(f"[NETLAB-SNAAS][WARN] Could not observe {entity_id}: {exc}")

        expected_antennas = [
            item for item in self.config.get("antennas", [])
            if isinstance(item, dict) and bool(item.get("enabled", True))
        ]
        applied_antennas = sum(
            1 for idx, item in enumerate(expected_antennas, start=1)
            if stage.GetPrimAtPath(f"{DEMO_ROOT}/Antennas/{_safe_name(item.get('id', f'antenna_{idx}'), f'antenna_{idx}')}").IsValid()
        )
        expected_worlds = [
            item for item in self.config.get("worlds", [])
            if isinstance(item, dict) and bool(item.get("enabled", True))
        ]
        applied_worlds = sum(
            1 for idx, item in enumerate(expected_worlds, start=1)
            if stage.GetPrimAtPath(f"{DEMO_ROOT}/WorldLayers/{_safe_name(item.get('id', f'world_{idx}'), f'world_{idx}')}").IsValid()
        )
        maximum_error_m = max(position_errors_m.values(), default=0.0)
        expected_count = len(desired_positions)
        applied_count = len(observed_positions)
        station_ready = stage.GetPrimAtPath(f"{DEMO_ROOT}/GroundStation").IsValid()
        all_entities_applied = applied_count == expected_count and not missing_entities
        accepted = bool(
            self.scene_ready
            and root_ready
            and station_ready
            and all_entities_applied
            and maximum_error_m <= tolerance_m
            and applied_antennas == len(expected_antennas)
            and applied_worlds == len(expected_worlds)
        )
        checksum_payload = {
            "revision_id": self.pending_revision_id,
            "observed_positions": observed_positions,
            "antennas": applied_antennas,
            "worlds": applied_worlds,
            "root": DEMO_ROOT,
        }
        scene_checksum = hashlib.sha256(
            json.dumps(checksum_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "accepted": accepted,
            "scene_ready": bool(self.scene_ready),
            "root_ready": root_ready,
            "station_ready": bool(station_ready),
            "expected_count": expected_count,
            "applied_count": applied_count,
            "missing_entities": missing_entities,
            "desired_positions": {f"drone_{idx}": [round(v, 6) for v in pos] for idx, pos in desired_positions.items()},
            "observed_positions": observed_positions,
            "position_errors_m": position_errors_m,
            "maximum_error_m": maximum_error_m,
            "tolerance_m": tolerance_m,
            "expected_antennas": len(expected_antennas),
            "applied_antennas": applied_antennas,
            "expected_worlds": len(expected_worlds),
            "applied_worlds": applied_worlds,
            "scene_checksum": scene_checksum,
        }

    def _write_sync_ack(self, signal: Dict[str, Any], reason: str) -> None:
        try:
            revision_id = str(signal.get("revision_id") or signal.get("revision", ""))
            requested_hashes = dict(signal.get("hashes") or {})
            evidence = self._observe_scene_application(
                tolerance_m=float(signal.get("position_tolerance_m", 0.02) or 0.02)
            )
            accepted = bool(revision_id and evidence["accepted"])
            if accepted:
                self.current_revision_id = revision_id
                self.current_parent_revision_id = str(signal.get("parent_revision_id", ""))
                self.current_revision_hashes = requested_hashes or dict(self.pending_revision_hashes)
            ack = {
                "timestamp": time.time(),
                "iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "participant": "isaac",
                "accepted": accepted,
                "ok": accepted,
                "ready": accepted,
                "revision": revision_id,
                "revision_id": revision_id,
                "observed_revision": revision_id if accepted else "",
                "parent_revision_id": signal.get("parent_revision_id", ""),
                "command_id": signal.get("command_id", ""),
                "requested_config_hash": signal.get("config_hash", "") or requested_hashes.get("config_hash", ""),
                "applied_config_hash": (requested_hashes.get("config_hash", "") if accepted else ""),
                "requested_hashes": requested_hashes,
                "observed_hashes": (dict(self.current_revision_hashes) if accepted else {}),
                "applied_hashes": (dict(self.current_revision_hashes) if accepted else {}),
                "config_source": self.current_config_source,
                "reason": reason,
                "consumed_signal_reason": signal.get("reason", ""),
                "scene_ready": bool(evidence["scene_ready"]),
                "scene_checksum": evidence["scene_checksum"],
                "expected_count": evidence["expected_count"],
                "applied_count": evidence["applied_count"],
                "missing_entities": evidence["missing_entities"],
                "desired_positions": evidence["desired_positions"],
                "observed_positions": evidence["observed_positions"],
                "position_errors_m": evidence["position_errors_m"],
                "maximum_error_m": evidence["maximum_error_m"],
                "tolerance_m": evidence["tolerance_m"],
                "expected_antennas": evidence["expected_antennas"],
                "applied_antennas": evidence["applied_antennas"],
                "expected_worlds": evidence["expected_worlds"],
                "applied_worlds": evidence["applied_worlds"],
                "visible_drones": sorted(self.current_positions),
                "transmission_mode": self.last_status.get("transmission_mode", self.config.get("transmission_mode", "chain")),
                "active_branches": self.last_status.get("active_branches", []),
                "branch_flows": self.last_status.get("branch_flows", []),
                "error": None if accepted else {
                    "code": "ISAAC_SCENE_APPLICATION_INCOMPLETE",
                    "message": "Isaac did not observe every requested entity and transform within tolerance.",
                    "details": {
                        "missing_entities": evidence["missing_entities"],
                        "maximum_error_m": evidence["maximum_error_m"],
                        "expected_count": evidence["expected_count"],
                        "applied_count": evidence["applied_count"],
                    },
                },
                "message": (
                    "Isaac applied and verified the requested NETLAB revision."
                    if accepted
                    else "Isaac received the revision but did not verify complete scene application."
                ),
            }
            self._atomic_json(ISAAC_SYNC_ACK_PATH, ack)
        except Exception as exc:
            failure = {
                "timestamp": time.time(),
                "participant": "isaac",
                "accepted": False,
                "ok": False,
                "ready": False,
                "revision_id": str(signal.get("revision_id") or signal.get("revision", "")),
                "observed_hashes": {},
                "scene_ready": False,
                "error": {"code": "ISAAC_ACK_EXCEPTION", "message": f"{type(exc).__name__}: {exc}"},
            }
            try:
                self._atomic_json(ISAAC_SYNC_ACK_PATH, failure)
            except Exception:
                pass
            print(f"[NETLAB-SNAAS][WARN] Could not write sync ack {ISAAC_SYNC_ACK_PATH}: {exc}")

    def _write_heartbeat(self) -> None:
        now = time.time()
        if now - self._last_heartbeat_time < 1.0:
            return
        self._last_heartbeat_time = now
        try:
            status_timestamp = float(self.last_status.get("timestamp", 0.0) or 0.0)
            payload = {
                "timestamp": now,
                "ready": bool(self.scene_ready),
                "scene_ready": bool(self.scene_ready),
                "pid": os.getpid(),
                "ros_bridge_available": bool(self.ros_ready),
                "controller_status_age_s": None if status_timestamp <= 0 else max(0.0, now - status_timestamp),
                "visible_drones": sorted(self.current_positions),
                "config_hash": self.current_revision_hashes.get("config_hash", "") or self._configuration_hash(),
                "current_revision_id": self.current_revision_id or self._read_sync_revision(),
                "current_hashes": self.current_revision_hashes,
                "last_sync_revision": (self._read_sync_revision()),
                "config_source": self.current_config_source,
                "stage_path": DEMO_ROOT,
                "streaming_process_ready": True,
                "message": "NETLAB Isaac integration heartbeat",
            }
            self._atomic_json(ISAAC_HEARTBEAT_PATH, payload)
        except Exception as exc:
            print(f"[NETLAB-SNAAS][WARN] Could not write Isaac heartbeat {ISAAC_HEARTBEAT_PATH}: {exc}")

    def _read_sync_revision(self) -> str:
        try:
            with open(ISAAC_SYNC_ACK_PATH, "r", encoding="utf-8") as handle:
                value = json.load(handle)
            return str(value.get("revision_id") or value.get("revision", "")) if isinstance(value, dict) else ""
        except Exception:
            return ""

    def _ensure_branch_packet_marker(self, branch_id: int) -> str:
        path = f"{DEMO_ROOT}/BranchPacket_{branch_id}"
        if not _stage().GetPrimAtPath(path).IsValid():
            _sphere(path, (0, 0, -1000), (0.16, 0.16, 0.16), GREEN)
        if path not in self.branch_packet_paths:
            self.branch_packet_paths.append(path)
        return path

    def _hide_unused_branch_packets(self, used_count: int) -> None:
        for idx in range(used_count, used_count + 64):
            path = f"{DEMO_ROOT}/BranchPacket_{idx}"
            if _stage().GetPrimAtPath(path).IsValid():
                _set_transform(path, translation=(0, 0, -1000), scale=(0.001, 0.001, 0.001))

    def _render_branch_packets(self, status: Dict[str, Any], default_progress: float, packet_marker_scale: float) -> bool:
        flows = status.get("branch_flows", [])
        if not isinstance(flows, list) or not flows:
            return False
        independent = bool(status.get("parallel_independent_streams", False)) or str(status.get("transmission_mode", "")).lower() in {"parallel", "forest", "manual"}
        if not independent or len(flows) <= 1:
            return False
        used = 0
        for flow in flows:
            if not isinstance(flow, dict):
                continue
            branch_id = int(flow.get("branch_id", used) or used)
            hop = flow.get("current_hop", {}) if isinstance(flow.get("current_hop", {}), dict) else {}
            last = flow.get("last_hop", {}) if isinstance(flow.get("last_hop", {}), dict) else {}
            src = hop.get("src") or last.get("src")
            dst = hop.get("dst") or last.get("dst")
            path = self._ensure_branch_packet_marker(branch_id)
            if not src or not dst:
                _set_transform(path, translation=(0, 0, -1000), scale=(0.001, 0.001, 0.001))
                used += 1
                continue
            try:
                p_src = self._node_position(str(src))
                p_dst = self._node_position(str(dst))
            except Exception:
                _set_transform(path, translation=(0, 0, -1000), scale=(0.001, 0.001, 0.001))
                used += 1
                continue
            if bool(flow.get("paused", False)):
                packet_position = p_src
                _set_transform(path, translation=packet_position, scale=(packet_marker_scale * 0.85, packet_marker_scale * 0.85, packet_marker_scale * 0.85))
                _display_color(path, RED)
            else:
                ts = float(last.get("timestamp", 0.0) or 0.0)
                period = float(last.get("hop_period_s", status.get("hop_period_s", 0.5)) or 0.5)
                if ts <= 0:
                    _set_transform(path, translation=(0, 0, -1000), scale=(0.001, 0.001, 0.001))
                    used += 1
                    continue
                progress = max(0.0, min(1.0, (time.time() - ts) / max(0.05, period)))
                packet_position = _vec_lerp(p_src, p_dst, progress)
                _set_transform(path, translation=packet_position, scale=(packet_marker_scale * 0.78, packet_marker_scale * 0.78, packet_marker_scale * 0.78))
                _display_color(path, GREEN if str(flow.get("phase", "forward")) == "forward" else BLUE)
            used += 1
        self._hide_unused_branch_packets(used)
        return True

    def _poll_sync_signal(self) -> None:
        """Mission Control writes this file whenever a GUI action must be reflected in Isaac.

        Config and status mtimes are normally enough, but this explicit signal makes
        visual synchronization deterministic for operator actions such as fail/heal,
        topology edits, antenna/world updates, and forced visual refreshes.
        """
        try:
            if not os.path.exists(ISAAC_SYNC_SIGNAL_PATH) or os.path.getsize(ISAAC_SYNC_SIGNAL_PATH) == 0:
                return
            mtime = os.path.getmtime(ISAAC_SYNC_SIGNAL_PATH)
            if mtime <= self._last_sync_signal_mtime:
                return
            self._last_sync_signal_mtime = mtime
            reason = "mission_control_sync"
            signal: Dict[str, Any] = {}
            try:
                with open(ISAAC_SYNC_SIGNAL_PATH, "r", encoding="utf-8") as handle:
                    loaded_signal = json.load(handle)
                if isinstance(loaded_signal, dict):
                    signal = loaded_signal
                    reason = str(signal.get("reason", reason))
            except Exception:
                pass
            # A transaction may point to an immutable candidate configuration.
            candidate_path = str(signal.get("config_path", "") or "")
            if candidate_path and os.path.exists(candidate_path):
                self._reload_scene_from_config(reason, candidate_path, snap_to_targets=True)
            else:
                self._last_config_file_mtime = 0.0
                self._poll_config_file()
            self.pending_revision_id = str(signal.get("revision_id") or signal.get("revision", self.pending_revision_id))
            self.pending_parent_revision_id = str(signal.get("parent_revision_id", self.pending_parent_revision_id))
            if isinstance(signal.get("hashes"), dict):
                self.pending_revision_hashes = dict(signal.get("hashes", {}))
            self._last_status_file_mtime = 0.0
            self._poll_status_file()
            self._write_sync_ack(signal, reason)
            print(f"[NETLAB-SNAAS] Mission Control sync signal consumed by Isaac ({reason}).")
        except Exception as exc:
            print(f"[NETLAB-SNAAS] Could not process Isaac sync signal {ISAAC_SYNC_SIGNAL_PATH}: {exc}")

    def _poll_status_file(self) -> None:
        try:
            if not os.path.exists(LATEST_STATUS_PATH) or os.path.getsize(LATEST_STATUS_PATH) == 0:
                return
            mtime = os.path.getmtime(LATEST_STATUS_PATH)
            if mtime <= self._last_status_file_mtime:
                return
            with open(LATEST_STATUS_PATH, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if mtime < self._last_config_file_mtime and isinstance(payload, dict):
                try:
                    live_count = int(payload.get("drone_count", -1))
                    config_count = len(self._config_drone_positions(self.config))
                    if live_count != config_count:
                        self._last_status_file_mtime = mtime
                        return
                except Exception:
                    pass
            self._last_status_file_mtime = mtime
            self._apply_status_payload(payload)
        except json.JSONDecodeError:
            # Backend writes atomically now, but keep this guard for older files.
            return
        except Exception as exc:
            print(f"[NETLAB-SNAAS] Could not read status file {LATEST_STATUS_PATH}: {exc}")

    def _status_cb(self, msg: Any) -> None:
        try:
            self._apply_status_payload(json.loads(msg.data))
        except Exception as exc:
            print(f"[NETLAB-SNAAS] Could not parse /swarm/chain/status: {exc}")

    def _pose_msg(self, position: Tuple[float, float, float]) -> Any:
        msg = PoseStamped()
        msg.header.stamp = self.ros_node.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.pose.position.x = float(position[0])
        msg.pose.position.y = float(position[1])
        msg.pose.position.z = float(position[2])
        msg.pose.orientation.w = 1.0
        return msg

    def _publish_poses(self) -> None:
        if not self.ros_ready:
            return
        try:
            rclpy.spin_once(self.ros_node, timeout_sec=0.0)
            now = time.time()
            if now - self.last_publish_time < self.publish_period_s:
                return
            self.last_publish_time = now
            for index, position in sorted(self.current_positions.items()):
                if index not in self.pose_publishers:
                    self.pose_publishers[index] = self.ros_node.create_publisher(PoseStamped, f"/swarm/drone_{index}/state", 10)
                self.pose_publishers[index].publish(self._pose_msg(position))
        except Exception as exc:
            print(f"[NETLAB-SNAAS] ROS publish/spin error: {exc}")
            traceback.print_exc()

    def _node_position(self, node_id: str) -> Tuple[float, float, float]:
        if node_id == "station":
            return tuple(float(v) for v in self.last_status.get("station_position", self.config.get("station", {}).get("position", [0.0, 0.0, 1.5])))
        index = int(node_id.split("_")[-1])
        return self.current_positions.get(index, (0.0, 0.0, 0.0))

    def _link_color(self, status: str, active: bool = False) -> Tuple[float, float, float]:
        if not active:
            return GREY
        if status == "strong":
            return GREEN
        if status == "nominal":
            return BLUE
        if status == "weak":
            return YELLOW
        if status in {"outage", "outage_distance_exceeded", "relay_failed", "sionna_unreachable", "degraded_distance_exceeds_nominal_range"}:
            return RED
        return CYAN

    def _motion_offset(self, index: int, t: float, pattern: str, amplitude: float, speed: float) -> Tuple[float, float, float]:
        # High-level, deterministic "physics-lite" motion. It avoids teleporting while
        # adding multi-frequency drift, altitude breathing, and role-dependent behavior.
        a = max(0.0, float(amplitude))
        s = max(0.05, float(speed))
        tt = t * s
        phase = index * 0.61803398875
        micro = 0.75 * math.sin(1.73 * tt + phase) + 0.35 * math.sin(2.91 * tt + index)
        if pattern == "oscillate":
            return (a * math.sin(0.55 * tt + phase), 0.45 * a * math.cos(0.42 * tt + phase), 0.10 * a * math.sin(1.2 * tt + phase) + 0.18 * micro)
        if pattern == "patrol":
            r = a * (0.85 + 0.08 * (index % 4))
            return (r * math.cos(0.28 * tt + phase), r * math.sin(0.28 * tt + phase), 0.08 * a * math.sin(0.85 * tt + phase) + 0.22 * micro)
        if pattern == "figure8":
            return (a * math.sin(0.35 * tt + phase), 0.50 * a * math.sin(0.70 * tt + phase), 0.08 * a * math.sin(0.9 * tt + phase) + 0.2 * micro)
        if pattern == "orbit":
            r = a * (0.65 + 0.04 * (index % 5))
            return (r * math.cos(0.34 * tt + phase), r * math.sin(0.34 * tt + phase), 0.12 * a * math.sin(0.52 * tt + phase))
        if pattern == "survey":
            # Smooth lawnmower-style lateral scan around each relay slot.
            sweep = math.sin(0.38 * tt + phase)
            return (0.35 * a * math.sin(0.19 * tt + phase), a * sweep, 0.06 * a * math.sin(0.75 * tt + phase) + 0.15 * micro)
        if pattern == "swarm":
            # Cohesive flock-like drift with index-dependent phase separation.
            return (0.72 * a * math.sin(0.31 * tt + phase), 0.72 * a * math.cos(0.27 * tt + 1.3 * phase), 0.10 * a * math.sin(0.67 * tt + phase) + 0.25 * micro)
        if pattern == "wind":
            gust = math.sin(0.16 * tt) + 0.45 * math.sin(0.57 * tt + phase)
            return (0.55 * a * gust, 0.20 * a * math.sin(0.43 * tt + phase), 0.08 * a * math.sin(1.05 * tt + phase) + 0.35 * micro)
        if pattern == "spiral":
            # Expanding/contracting helix around each desired relay slot, useful for
            # researchers inspecting link-margin sensitivity to continuous 3D motion.
            radius = a * (0.25 + 0.55 * (0.5 + 0.5 * math.sin(0.12 * tt + phase)))
            return (radius * math.cos(0.46 * tt + phase), radius * math.sin(0.46 * tt + phase), 0.16 * a * math.sin(0.38 * tt + phase) + 0.18 * micro)
        # Hover still has subtle vertical and horizontal micro motion.
        return (0.03 * a * math.sin(0.73 * tt + phase), 0.025 * a * math.cos(0.69 * tt + phase), 0.05 * a * math.sin(2.0 * math.pi * 0.28 * tt + phase) + 0.10 * micro)

    def _update_coverage_area(self, status: Dict[str, Any]) -> None:
        if not _stage().GetPrimAtPath(COVERAGE_PATH).IsValid():
            cfg = dict(self.config)
            cfg["coverage_radius_m"] = status.get("coverage_radius_m", cfg.get("coverage_radius_m", 120.0))
            cfg["coverage_width_m"] = status.get("coverage_width_m", cfg.get("coverage_width_m", 60.0))
            cfg["direction_deg"] = status.get("direction_deg", cfg.get("direction_deg", 0.0))
            cfg["station"] = {"position": status.get("station_position", cfg.get("station", {}).get("position", [0.0, 0.0, 1.5]))}
            _make_coverage_area(cfg)
        try:
            station = tuple(float(v) for v in status.get("station_position", self.config.get("station", {}).get("position", [0.0, 0.0, 1.5])))
            radius = float(status.get("coverage_radius_m", self.config.get("coverage_radius_m", 120.0)) or 120.0)
            width = float(status.get("coverage_width_m", self.config.get("coverage_width_m", 60.0)) or 60.0)
            direction_deg = float(status.get("direction_deg", self.config.get("direction_deg", 0.0)) or 0.0)
            theta = math.radians(direction_deg)
            dx, dy = math.cos(theta), math.sin(theta)
            px, py = -dy, dx
            corners = []
            for along, side in [(0, -1), (radius, -1), (radius, 1), (0, 1), (0, -1)]:
                corners.append((station[0] + dx * along + px * side * width * 0.5, station[1] + dy * along + py * side * width * 0.5, 0.08))
            prim = _stage().GetPrimAtPath(COVERAGE_PATH)
            if prim.IsValid():
                UsdGeom.BasisCurves(prim).GetPointsAttr().Set([Gf.Vec3f(*p) for p in corners])
            center = (station[0] + dx * radius * 0.5, station[1] + dy * radius * 0.5, 0.05)
            if _stage().GetPrimAtPath(f"{DEMO_ROOT}/CoverageCenter").IsValid():
                _set_transform(f"{DEMO_ROOT}/CoverageCenter", translation=center, scale=(0.30, 0.30, 0.04))
        except Exception as exc:
            print(f"[NETLAB-SNAAS] Coverage area update failed: {exc}")

    def _update_drone_coverage_spheres(self, status: Dict[str, Any]) -> None:
        runtime_visual = _load_runtime_visual_config()
        visual = self.config.get("visual", {})
        show = bool(runtime_visual.get("show_coverage_indicators", visual.get("show_drone_coverage_rings", visual.get("show_drone_coverage_spheres", True))))
        # The visual coverage ring MUST match the protocol communication radius.
        # Do not use an old fixed visual radius, otherwise Isaac can show coverage
        # that disagrees with the relay decision.
        visual_radius = float(status.get("communication_radius_m", status.get("max_single_hop_range_m", self.config.get("max_single_hop_range_m", 90.0))))
        visual_radius = max(2.0, min(visual_radius, 300.0))
        failed = set(status.get("failed_indices", [])) if isinstance(status.get("failed_indices", []), list) else set()
        for index in sorted(self.current_positions):
            rings_root = f"{DEMO_ROOT}/Drone_{index}/CoverageRings"
            prim = _stage().GetPrimAtPath(rings_root)
            if not prim.IsValid():
                continue
            # Failed drones lose coverage immediately.
            if (not show) or index in failed:
                UsdGeom.Imageable(prim).MakeInvisible()
            else:
                UsdGeom.Imageable(prim).MakeVisible()
                _set_transform(rings_root, translation=(0, 0, 0), scale=(visual_radius, visual_radius, visual_radius))

    def _ensure_relay_link(self, idx: int) -> str:
        path = f"{DEMO_ROOT}/RelayLink_{idx}"
        if not _stage().GetPrimAtPath(path).IsValid():
            _curve(path, [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0)], GREY, width=0.08)
        return path

    def _update_visual_state(self) -> None:
        now_wall = time.time()
        dt = max(0.01, min(0.08, now_wall - self._last_visual_update))
        self._last_visual_update = now_wall
        t = now_wall - self.start_time
        status = self.last_status or {}
        runtime_visual = _load_runtime_visual_config()
        status_ball_scale = float(runtime_visual.get("status_ball_scale", 0.70))
        packet_marker_scale = float(runtime_visual.get("packet_marker_scale", 0.90))
        movement_pattern = str(status.get("movement_pattern", self.config.get("movement_pattern", "hover"))).lower()
        movement_amplitude = float(status.get("movement_amplitude_m", self.config.get("movement_amplitude_m", 10.0)) or 10.0)
        movement_speed = float(status.get("movement_speed", self.config.get("movement_speed", 1.0)) or 1.0)
        follow_alpha = max(0.02, min(1.0, float(status.get("visual_follow_alpha", self.config.get("visual_follow_alpha", 0.18)) or 0.18)))
        wind_speed = max(0.0, float(status.get("wind_speed_mps", self.config.get("wind_speed_mps", 0.0)) or 0.0))
        wind_dir = math.radians(float(status.get("wind_direction_deg", self.config.get("wind_direction_deg", 0.0)) or 0.0))
        turbulence = max(0.0, float(status.get("turbulence_intensity", self.config.get("turbulence_intensity", 0.0)) or 0.0))
        wind_vec = (math.cos(wind_dir), math.sin(wind_dir), 0.0)
        failed = set(status.get("failed_indices", [])) if isinstance(status.get("failed_indices", []), list) else set()
        standby = set(status.get("standby_indices", [])) if isinstance(status.get("standby_indices", []), list) else set()

        self._update_coverage_area(status)

        for index, target in sorted(self.target_positions.items()):
            current = self.current_positions.get(index, target)
            role_pattern = movement_pattern
            amp = movement_amplitude
            if index in standby:
                amp *= 0.38
                role_pattern = "orbit" if movement_pattern != "hover" else "hover"
            offset = self._motion_offset(index, t, role_pattern, amp, movement_speed)
            gust = wind_speed * (0.34 * math.sin(0.19 * t + index * 0.73) + turbulence * 0.22 * math.sin(1.37 * t + index))
            turb = turbulence * max(0.2, amp) * 0.12
            # Optional rendering micro-motion is disabled by default. It is never
            # used as the authoritative flight dynamics state.
            organic_motion = bool(self.config.get("visual", {}).get("organic_motion", False))
            if organic_motion:
                breath = 0.04 + 0.01 * (index % 3)
                idle_x = 0.012 * math.sin(0.61 * t + index * 1.7)
                idle_y = 0.012 * math.cos(0.53 * t + index * 2.3)
                idle_z = breath * math.sin(0.42 * t + index * 0.9)
            else:
                idle_x = idle_y = idle_z = 0.0
            target_motion = (
                target[0] + offset[0] + wind_vec[0] * gust + turb * math.sin(2.1 * t + index) + idle_x,
                target[1] + offset[1] + wind_vec[1] * gust + turb * math.cos(1.7 * t + index) + idle_y,
                target[2] + offset[2] + turb * 0.35 * math.sin(2.8 * t + index) + idle_z,
            )
            if index in failed:
                # Failed UAVs visibly lose altitude and wobble instead of staying frozen.
                target_motion = (current[0] + 0.08 * math.sin(t + index), current[1] + 0.08 * math.cos(0.7 * t + index), max(0.35, current[2] - 0.22))
            vx, vy, vz = self.motion_velocity.get(index, (0.0, 0.0, 0.0))
            stiffness = 1.25 + 5.5 * follow_alpha
            damping = 2.35
            # Standby drones ease into formation gently (lower stiffness, higher damping)
            # so promotion reads as an organic glide-in rather than a snap.
            if index in standby:
                stiffness *= 0.55
                damping *= 1.35
            ax = (target_motion[0] - current[0]) * stiffness - vx * damping
            ay = (target_motion[1] - current[1]) * stiffness - vy * damping
            az = (target_motion[2] - current[2]) * stiffness - vz * damping
            velocity = (vx + ax * dt, vy + ay * dt, vz + az * dt)
            speed_limit = max(1.8, 4.0 * max(0.1, movement_speed) + 0.28 * amp + 0.45 * wind_speed)
            speed_norm = math.sqrt(velocity[0] ** 2 + velocity[1] ** 2 + velocity[2] ** 2)
            if speed_norm > speed_limit:
                scale_v = speed_limit / max(1e-6, speed_norm)
                velocity = (velocity[0] * scale_v, velocity[1] * scale_v, velocity[2] * scale_v)
            next_pos = (current[0] + velocity[0] * dt, current[1] + velocity[1] * dt, current[2] + velocity[2] * dt)
            self.motion_velocity[index] = velocity
            self.current_positions[index] = next_pos

            speed_xy = math.hypot(velocity[0], velocity[1])
            if speed_xy > 1e-3:
                yaw_target = math.degrees(math.atan2(velocity[1], velocity[0]))
            else:
                yaw_target = 18.0 * math.sin(0.35 * t * max(0.1, movement_speed) + index)
            old_yaw = self.motion_yaw.get(index, yaw_target)
            delta_yaw = ((yaw_target - old_yaw + 180.0) % 360.0) - 180.0
            yaw = old_yaw + _clamp(delta_yaw, -90.0 * dt, 90.0 * dt)
            self.motion_yaw[index] = yaw
            pitch = _clamp(-velocity[0] * 4.5, -16.0, 16.0)
            roll = _clamp(velocity[1] * 4.5, -16.0, 16.0)
            if index in failed:
                roll = 28.0 * math.sin(1.4 * t + index)
                pitch = 18.0 * math.cos(1.1 * t + index)
                yaw += 45.0 * math.sin(0.9 * t + index)
            _set_transform(f"{DEMO_ROOT}/Drone_{index}", translation=next_pos, rotation=(pitch, roll, yaw))
            _set_transform(f"{DEMO_ROOT}/Drone_{index}/MessageBeacon", translation=(0.0, 0.0, 1.45), scale=(status_ball_scale, status_ball_scale, status_ball_scale))
            spin = (t * 2600.0 * max(0.2, movement_speed) + index * 37.0) % 360.0
            for rotor_idx, (x, y) in enumerate([(0.95, 0.95), (0.95, -0.95), (-0.95, 0.95), (-0.95, -0.95)], start=1):
                direction = -1.0 if rotor_idx % 2 else 1.0
                if _stage().GetPrimAtPath(f"{DEMO_ROOT}/Drone_{index}/DefaultVisual/RotorBlade_{rotor_idx}_A").IsValid():
                    _set_transform(f"{DEMO_ROOT}/Drone_{index}/DefaultVisual/RotorBlade_{rotor_idx}_A", translation=(x, y, 0.12), rotation=(0.0, 0.0, direction * spin), scale=(0.34, 0.028, 0.006))
                    _set_transform(f"{DEMO_ROOT}/Drone_{index}/DefaultVisual/RotorBlade_{rotor_idx}_B", translation=(x, y, 0.121), rotation=(0.0, 0.0, 90.0 + direction * spin), scale=(0.028, 0.34, 0.006))

        for index in sorted(self.current_positions):
            _display_color(f"{DEMO_ROOT}/Drone_{index}/MessageBeacon", BLACK)
        _display_color(f"{DEMO_ROOT}/GroundStation/Beacon", BLACK)

        active_branches = status.get("active_branches") or [status.get("active_chain", [])]
        last_hop = status.get("last_hop", {}) or {}
        src = last_hop.get("src")
        dst = last_hop.get("dst")
        link_status = last_hop.get("link_status", "unknown")
        hop_period_s = float(last_hop.get("hop_period_s", status.get("hop_period_s", 0.5)) or 0.5)
        hop_timestamp = float(last_hop.get("timestamp", self.last_event_time) or self.last_event_time)
        progress = max(0.0, min(1.0, (time.time() - hop_timestamp) / max(0.05, hop_period_s)))

        for index in standby:
            if index in self.current_positions:
                _display_color(f"{DEMO_ROOT}/Drone_{index}/MessageBeacon", PURPLE)
        for index in failed:
            if index in self.current_positions:
                _display_color(f"{DEMO_ROOT}/Drone_{index}/MessageBeacon", RED)

        if src:
            if src == "station":
                _display_color(f"{DEMO_ROOT}/GroundStation/Beacon", GREEN)
            elif src.startswith("drone_"):
                src_idx = int(src.split("_")[-1])
                if src_idx in self.current_positions:
                    _display_color(f"{DEMO_ROOT}/Drone_{src_idx}/MessageBeacon", GREEN)
        if dst and dst.startswith("drone_"):
            dst_idx = int(dst.split("_")[-1])
            if dst_idx in self.current_positions and dst_idx not in failed:
                _display_color(f"{DEMO_ROOT}/Drone_{dst_idx}/MessageBeacon", BLUE)

        status_timestamp = float(status.get("timestamp", 0.0) or 0.0)
        runtime_live = status_timestamp > 0.0 and (time.time() - status_timestamp) <= max(5.0, 4.0 * hop_period_s)
        protocol_paused = bool(status.get("connectivity_paused", False))
        hop_link_ok = bool(last_hop.get("link_ok", False))
        rendered_parallel_packets = self._render_branch_packets(status, progress, packet_marker_scale) if runtime_live else False
        if rendered_parallel_packets:
            _set_transform(f"{DEMO_ROOT}/PacketMarker", translation=(0, 0, -1000), scale=(0.001, 0.001, 0.001))
        elif runtime_live and src and dst and (not protocol_paused) and hop_link_ok:
            p_src = self._node_position(src)
            p_dst = self._node_position(dst)
            packet_position = _vec_lerp(p_src, p_dst, progress)
            _set_transform(f"{DEMO_ROOT}/PacketMarker", translation=packet_position, scale=(packet_marker_scale, packet_marker_scale, packet_marker_scale))
            _display_color(f"{DEMO_ROOT}/PacketMarker", self._link_color(str(link_status), active=True))
            self._hide_unused_branch_packets(0)
        else:
            # If the relay protocol has paused because a link is down, no packet should appear to travel.
            _set_transform(f"{DEMO_ROOT}/PacketMarker", translation=(0, 0, -1000), scale=(0.001, 0.001, 0.001))
            self._hide_unused_branch_packets(0)

        edge_idx = 0
        for branch in active_branches:
            if not isinstance(branch, list):
                continue
            nodes = ["station"] + [f"drone_{i}" for i in branch if i in self.current_positions]
            for j in range(len(nodes) - 1):
                path = self._ensure_relay_link(edge_idx)
                curve = UsdGeom.BasisCurves(_stage().GetPrimAtPath(path))
                a = self._node_position(nodes[j])
                b = self._node_position(nodes[j + 1])
                curve.GetPointsAttr().Set([Gf.Vec3f(*a), Gf.Vec3f(*b)])
                is_active_hop = nodes[j] == src and nodes[j + 1] == dst
                curve.CreateDisplayColorAttr([Gf.Vec3f(*self._link_color(str(link_status), active=is_active_hop))])
                edge_idx += 1
        # Hide unused old link curves by collapsing them.
        for rest in range(edge_idx, edge_idx + 80):
            path = f"{DEMO_ROOT}/RelayLink_{rest}"
            prim = _stage().GetPrimAtPath(path)
            if not prim.IsValid():
                continue
            curve = UsdGeom.BasisCurves(prim)
            curve.GetPointsAttr().Set([Gf.Vec3f(0, 0, 0), Gf.Vec3f(0, 0, 0)])
            curve.CreateDisplayColorAttr([Gf.Vec3f(*GREY)])

        self._update_drone_coverage_spheres(status)

    def _on_update(self, event) -> None:  # noqa: ANN001
        self._poll_sync_signal()
        self._poll_config_file()
        self._poll_status_file()
        self._update_visual_state()
        self._publish_poses()
        self._write_heartbeat()


def _start_scene() -> None:
    previous = globals().get("__NETLAB_SNAAS_RELAY_SCENE__")
    if previous is not None:
        try:
            previous.shutdown()
            print("[NETLAB-SNAAS] Previous relay scene stopped.")
        except Exception:
            traceback.print_exc()
    globals()["__NETLAB_SNAAS_RELAY_SCENE__"] = SnaasRelayScene()


_start_scene()

# NETLAB SNaaS runtime visual controls.
try:
    exec(open("/workspace/isaac/scripts/snaas_visual_controls.py").read())
except Exception as exc:
    print(f"[NETLAB-VISUALS][WARN] Could not load visual controls: {exc}")
