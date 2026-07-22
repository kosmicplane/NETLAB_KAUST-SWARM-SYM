import os
import omni.usd
from pxr import UsdGeom, Gf


# ============================================================
# NETLAB Custom Drone Visual Modifier
# ============================================================
# This script replaces the simple visual drone geometry with
# a custom USD drone model converted from GLB/gltf/fbx/obj.
#
# It does NOT change:
#   - ROS 2 topics
#   - Sionna link metrics
#   - drone hover behavior
#   - telemetry publication
#   - drone-to-drone communication logic
# ============================================================


CUSTOM_DRONE_USD = os.environ.get(
    "NETLAB_CUSTOM_DRONE_USD",
    "/workspace/isaac/local_assets/drones/my_drone.usd"
)

DRONE_ROOTS = [
    "/World/Drone_1",
    "/World/Drone_2",
]

CUSTOM_VISUAL_NAME = "CustomDroneVisual"

# Adjust these values after the first test.
# If your model appears too large, try 0.01 or 0.1.
# If it appears too small, try 10.0 or 100.0.
DRONE_SCALE = float(os.environ.get("NETLAB_CUSTOM_DRONE_SCALE", "1.0"))

# Orientation correction.
# Common values:
#   0, 0, 0       -> if the drone loads correctly
#   90, 0, 0      -> if the drone appears lying on its side
#   -90, 0, 0     -> if it is rotated the opposite way
#   0, 0, 180     -> if the drone faces backward
DRONE_ROT_X = float(os.environ.get("NETLAB_CUSTOM_DRONE_RX", "0.0"))
DRONE_ROT_Y = float(os.environ.get("NETLAB_CUSTOM_DRONE_RY", "0.0"))
DRONE_ROT_Z = float(os.environ.get("NETLAB_CUSTOM_DRONE_RZ", "0.0"))

# Offset relative to each drone root.
# Use this if the model appears above/below the hover point.
DRONE_OFFSET_X = float(os.environ.get("NETLAB_CUSTOM_DRONE_TX", "0.0"))
DRONE_OFFSET_Y = float(os.environ.get("NETLAB_CUSTOM_DRONE_TY", "0.0"))
DRONE_OFFSET_Z = float(os.environ.get("NETLAB_CUSTOM_DRONE_TZ", "0.0"))

# Hide the old primitive geometry created by the demo script.
HIDE_OLD_VISUALS = os.environ.get("NETLAB_HIDE_OLD_DRONE_VISUALS", "1") == "1"


def _hide_old_visuals(stage, drone_root_path, custom_visual_path):
    root = stage.GetPrimAtPath(drone_root_path)

    if not root.IsValid():
        print(f"[NETLAB][WARN] Drone root not found: {drone_root_path}")
        return

    for prim in stage.Traverse():
        path = str(prim.GetPath())

        if not path.startswith(drone_root_path):
            continue

        if path.startswith(custom_visual_path):
            continue

        # Hide visual geometry only. The Xform/root remains active.
        if prim.IsA(UsdGeom.Gprim):
            try:
                UsdGeom.Imageable(prim).MakeInvisible()
            except Exception as exc:
                print(f"[NETLAB][WARN] Could not hide {path}: {exc}")


def _attach_custom_visual(stage, drone_root_path):
    drone_root = stage.GetPrimAtPath(drone_root_path)

    if not drone_root.IsValid():
        print(f"[NETLAB][WARN] Skipping missing drone root: {drone_root_path}")
        return False

    custom_visual_path = f"{drone_root_path}/{CUSTOM_VISUAL_NAME}"

    if HIDE_OLD_VISUALS:
        _hide_old_visuals(stage, drone_root_path, custom_visual_path)

    if stage.GetPrimAtPath(custom_visual_path).IsValid():
        stage.RemovePrim(custom_visual_path)

    visual_prim = stage.DefinePrim(custom_visual_path, "Xform")
    visual_prim.GetReferences().AddReference(CUSTOM_DRONE_USD)

    xform = UsdGeom.Xformable(visual_prim)
    xform.ClearXformOpOrder()
    xform.AddTranslateOp().Set(
        Gf.Vec3d(DRONE_OFFSET_X, DRONE_OFFSET_Y, DRONE_OFFSET_Z)
    )
    xform.AddRotateXYZOp().Set(
        Gf.Vec3f(DRONE_ROT_X, DRONE_ROT_Y, DRONE_ROT_Z)
    )
    xform.AddScaleOp().Set(
        Gf.Vec3f(DRONE_SCALE, DRONE_SCALE, DRONE_SCALE)
    )

    print(f"[NETLAB] Custom drone visual attached:")
    print(f"[NETLAB]   root:   {drone_root_path}")
    print(f"[NETLAB]   visual: {custom_visual_path}")
    print(f"[NETLAB]   asset:  {CUSTOM_DRONE_USD}")

    return True


def apply_custom_drone_visuals():
    if not os.path.exists(CUSTOM_DRONE_USD):
        raise FileNotFoundError(
            f"[NETLAB] Custom drone USD not found: {CUSTOM_DRONE_USD}\n"
            "Convert your GLB to USD first or update CUSTOM_DRONE_USD."
        )

    stage = omni.usd.get_context().get_stage()

    if stage is None:
        raise RuntimeError("[NETLAB] No active USD stage found.")

    loaded = 0

    for drone_root_path in DRONE_ROOTS:
        if _attach_custom_visual(stage, drone_root_path):
            loaded += 1

    print("[NETLAB] Custom drone visual modifier completed.")
    print(f"[NETLAB] Drones updated: {loaded}/{len(DRONE_ROOTS)}")
    print(f"[NETLAB] Scale: {DRONE_SCALE}")
    print(f"[NETLAB] Rotation XYZ: ({DRONE_ROT_X}, {DRONE_ROT_Y}, {DRONE_ROT_Z})")
    print(f"[NETLAB] Offset XYZ: ({DRONE_OFFSET_X}, {DRONE_OFFSET_Y}, {DRONE_OFFSET_Z})")


apply_custom_drone_visuals()
