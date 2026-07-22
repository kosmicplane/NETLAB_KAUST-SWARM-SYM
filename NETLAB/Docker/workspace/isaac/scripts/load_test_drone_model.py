import os
import omni.usd
from pxr import UsdGeom, Gf

DRONE_USD = "/workspace/isaac/local_assets/drones/tu_drone.usd"
DRONE_PRIM = "/World/TestDroneModel"

if not os.path.exists(DRONE_USD):
    raise FileNotFoundError(DRONE_USD)

stage = omni.usd.get_context().get_stage()

if stage.GetPrimAtPath(DRONE_PRIM).IsValid():
    stage.RemovePrim(DRONE_PRIM)

prim = stage.DefinePrim(DRONE_PRIM, "Xform")
prim.GetReferences().AddReference(DRONE_USD)

xform = UsdGeom.Xformable(prim)
xform.ClearXformOpOrder()
xform.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 5.0))

# Adjust these values if the model appears rotated, oversized, or undersized.
xform.AddRotateXYZOp().Set(Gf.Vec3f(0.0, 0.0, 0.0))
xform.AddScaleOp().Set(Gf.Vec3f(0.01, 0.01, 0.01))

print("[NETLAB] Test drone model loaded:", DRONE_USD)
print("[NETLAB] Prim:", DRONE_PRIM)
