#!/usr/bin/env python3
"""
NETLAB SNaaS runtime visual controls for Isaac Sim.

This module is intentionally visual-only. It does not create drones, coverage
rings, packets, links, or topology. It only applies three operator-controlled
settings to existing prims produced by snaas_relay_scene.py:

  1. show_coverage_indicators: show/hide per-drone CoverageRings.
  2. status_ball_scale: scale each drone MessageBeacon.
  3. packet_marker_scale: scale PacketMarker when it is visible.
"""

import json
import os
import re
import builtins
from pxr import Usd, UsdGeom, Gf
import omni.kit.app
import omni.usd

VISUAL_CONFIG_PATH = "/workspace/results/snaas_relay_visual_config.json"
DEMO_ROOT = "/World/NETLAB_SNAAS_Relay_Chain_Demo"

DEFAULT_CONFIG = {
    "show_coverage_indicators": True,
    "status_ball_scale": 0.70,
    "packet_marker_scale": 0.90,
}

DRONE_COVERAGE_RE = re.compile(r"^/World/NETLAB_SNAAS_Relay_Chain_Demo/Drone_\d+/CoverageRings(?:/.*)?$")
DRONE_BEACON_RE = re.compile(r"^/World/NETLAB_SNAAS_Relay_Chain_Demo/Drone_\d+/MessageBeacon$")
PACKET_MARKER_PATH = f"{DEMO_ROOT}/PacketMarker"


def _stage():
    return omni.usd.get_context().get_stage()


def _as_bool(value, default=True):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_scale(value, default):
    try:
        return max(0.05, min(float(value), 5.0))
    except Exception:
        return float(default)


def _load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(VISUAL_CONFIG_PATH):
            with open(VISUAL_CONFIG_PATH, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                cfg.update(loaded)
    except Exception as exc:
        print(f"[NETLAB-VISUALS][WARN] Could not read config: {exc}")

    cfg["show_coverage_indicators"] = _as_bool(cfg.get("show_coverage_indicators"), True)
    cfg["status_ball_scale"] = _as_scale(cfg.get("status_ball_scale"), 0.70)
    cfg["packet_marker_scale"] = _as_scale(cfg.get("packet_marker_scale"), 0.90)
    return cfg


def _set_visible(prim, visible):
    try:
        imageable = UsdGeom.Imageable(prim)
        if visible:
            imageable.MakeVisible()
        else:
            imageable.MakeInvisible()
    except Exception:
        pass


def _set_uniform_scale(prim, value):
    try:
        xformable = UsdGeom.Xformable(prim)
        scale_op = None
        for op in xformable.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeScale:
                scale_op = op
                break
        vec = Gf.Vec3f(float(value), float(value), float(value))
        if scale_op is not None:
            scale_op.Set(vec)
        else:
            xformable.AddScaleOp().Set(vec)
    except Exception:
        try:
            UsdGeom.XformCommonAPI(prim).SetScale((float(value), float(value), float(value)))
        except Exception:
            pass


def _apply_visual_controls():
    stage = _stage()
    if stage is None:
        return
    root = stage.GetPrimAtPath(DEMO_ROOT)
    if not root or not root.IsValid():
        return

    cfg = _load_config()
    show_coverage = cfg["show_coverage_indicators"]
    status_scale = cfg["status_ball_scale"]
    packet_scale = cfg["packet_marker_scale"]

    for prim in Usd.PrimRange(root):
        path = str(prim.GetPath())
        if DRONE_COVERAGE_RE.match(path):
            _set_visible(prim, show_coverage)
        elif DRONE_BEACON_RE.match(path):
            _set_uniform_scale(prim, status_scale)
        elif path == PACKET_MARKER_PATH:
            _set_uniform_scale(prim, packet_scale)


def _on_update(_event):
    _apply_visual_controls()


try:
    old_sub = getattr(builtins, "_NETLAB_SNAAS_VISUAL_CONTROLS_SUB", None)
    if old_sub is not None:
        builtins._NETLAB_SNAAS_VISUAL_CONTROLS_SUB = None

    builtins._NETLAB_SNAAS_VISUAL_CONTROLS_SUB = (
        omni.kit.app.get_app()
        .get_update_event_stream()
        .create_subscription_to_pop(_on_update, name="NETLAB_SNaaS_VisualControls")
    )
    _apply_visual_controls()
    print("[NETLAB-VISUALS] Runtime visual controls enabled.")
    print(f"[NETLAB-VISUALS] Config file: {VISUAL_CONFIG_PATH}")
except Exception as exc:
    print(f"[NETLAB-VISUALS][ERROR] Failed to enable visual controls: {exc}")
