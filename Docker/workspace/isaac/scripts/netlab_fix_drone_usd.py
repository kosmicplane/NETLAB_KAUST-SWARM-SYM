# NETLAB robust USD model preparation for custom drone visuals.
# Run in Isaac Script Editor:
#   exec(open("/workspace/isaac/scripts/netlab_fix_drone_usd.py").read())

from __future__ import annotations

import os
from pxr import Usd, UsdGeom

ASSET = os.environ.get("NETLAB_DRONE_USD", "/workspace/isaac/local_assets/drones/tu_drone.usd")

if not os.path.exists(ASSET):
    raise FileNotFoundError(f"Drone USD not found: {ASSET}")

stage = Usd.Stage.Open(ASSET)
if stage is None:
    raise RuntimeError(f"Could not open USD: {ASSET}")

def choose_default_prim():
    current = stage.GetDefaultPrim()
    if current and current.IsValid():
        return current, False
    for prim in stage.GetPseudoRoot().GetChildren():
        for child in Usd.PrimRange(prim):
            if child.IsA(UsdGeom.Mesh):
                return prim, True
    children = list(stage.GetPseudoRoot().GetChildren())
    if not children:
        raise RuntimeError("USD has no root prims; reconvert the model.")
    return children[0], True

prim, changed = choose_default_prim()
if changed:
    stage.SetDefaultPrim(prim)
    stage.GetRootLayer().Save()

print("[NETLAB] Drone USD is ready")
print("[NETLAB] Asset:", ASSET)
print("[NETLAB] defaultPrim:", prim.GetPath())
print("[NETLAB] changed:", changed)
