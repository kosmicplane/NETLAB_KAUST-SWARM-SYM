import os
import omni.usd
from pxr import UsdGeom, Gf

ACTIVE_WORLD_FILE = "/workspace/isaac/local_assets/active_world_path.txt"
WORLD_PRIM = "/World/ImportedWorld"

DEFAULT_TX = 0.0
DEFAULT_TY = 0.0
DEFAULT_TZ = 0.0
DEFAULT_RX = 90.0
DEFAULT_RY = 0.0
DEFAULT_RZ = 0.0
DEFAULT_SCALE = 1.0


def _read_active_world():
    if not os.path.exists(ACTIVE_WORLD_FILE):
        raise FileNotFoundError(
            f"[NETLAB] Active world file not found: {ACTIVE_WORLD_FILE}"
        )

    with open(ACTIVE_WORLD_FILE, "r", encoding="utf-8") as f:
        world_path = f.read().strip()

    if not world_path:
        raise RuntimeError("[NETLAB] Active world file is empty.")

    if not os.path.exists(world_path):
        raise FileNotFoundError(
            f"[NETLAB] Selected world does not exist inside Isaac container: {world_path}"
        )

    return world_path


def load_selected_world():
    world_path = _read_active_world()

    context = omni.usd.get_context()
    stage = context.get_stage()

    if stage is None:
        raise RuntimeError("[NETLAB] No active USD stage found in Isaac Sim.")

    old_prim = stage.GetPrimAtPath(WORLD_PRIM)
    if old_prim.IsValid():
        print(f"[NETLAB] Removing previous imported world at {WORLD_PRIM}")
        stage.RemovePrim(WORLD_PRIM)

    print(f"[NETLAB] Loading selected world:")
    print(f"[NETLAB]   {world_path}")

    world_prim = stage.DefinePrim(WORLD_PRIM, "Xform")
    world_prim.GetReferences().AddReference(world_path)

    xform = UsdGeom.Xformable(world_prim)
    xform.ClearXformOpOrder()

    xform.AddTranslateOp().Set(Gf.Vec3d(DEFAULT_TX, DEFAULT_TY, DEFAULT_TZ))
    xform.AddRotateXYZOp().Set(Gf.Vec3f(DEFAULT_RX, DEFAULT_RY, DEFAULT_RZ))
    xform.AddScaleOp().Set(Gf.Vec3f(DEFAULT_SCALE, DEFAULT_SCALE, DEFAULT_SCALE))

    print("[NETLAB] World imported successfully.")
    print(f"[NETLAB] Prim path: {WORLD_PRIM}")
    print("[NETLAB] If scale/orientation is wrong, adjust the transform values in load_selected_world.py")

    return world_prim


load_selected_world()
