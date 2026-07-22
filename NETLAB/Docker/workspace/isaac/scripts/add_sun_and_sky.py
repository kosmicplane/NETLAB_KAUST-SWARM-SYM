import omni.usd
from pxr import UsdLux, UsdGeom, Gf

SUN_PRIM = "/World/NETLAB_Sun"
SKY_PRIM = "/World/NETLAB_Sky"

# Ajustes principales
SUN_INTENSITY = 5000.0
SUN_ANGLE = 0.53
SUN_COLOR = Gf.Vec3f(1.0, 0.96, 0.86)
SUN_COLOR_TEMPERATURE = 5500.0

# Sun rotation.
# Change these values to adjust the light direction.
# A more negative X rotation raises the apparent sun elevation.
SUN_ROTATION_XYZ = Gf.Vec3f(-55.0, 0.0, -35.0)

# Cielo / luz ambiental
SKY_INTENSITY = 350.0
SKY_COLOR = Gf.Vec3f(0.58, 0.72, 1.0)


def remove_if_exists(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if prim.IsValid():
        stage.RemovePrim(prim_path)


def add_sun_and_sky():
    stage = omni.usd.get_context().get_stage()

    if stage is None:
        raise RuntimeError("[NETLAB] No active USD stage found.")

    # Limpiar luces anteriores para evitar duplicados
    remove_if_exists(stage, SUN_PRIM)
    remove_if_exists(stage, SKY_PRIM)

    # Sol: luz direccional
    sun = UsdLux.DistantLight.Define(stage, SUN_PRIM)
    sun.CreateIntensityAttr(SUN_INTENSITY)
    sun.CreateAngleAttr(SUN_ANGLE)
    sun.CreateColorAttr(SUN_COLOR)
    sun.CreateEnableColorTemperatureAttr(True)
    sun.CreateColorTemperatureAttr(SUN_COLOR_TEMPERATURE)

    sun_xform = UsdGeom.Xformable(sun.GetPrim())
    sun_xform.ClearXformOpOrder()
    sun_xform.AddRotateXYZOp().Set(SUN_ROTATION_XYZ)

    # Sky: dome-based ambient illumination.
    sky = UsdLux.DomeLight.Define(stage, SKY_PRIM)
    sky.CreateIntensityAttr(SKY_INTENSITY)
    sky.CreateColorAttr(SKY_COLOR)

    print("[NETLAB] Sun and sky added successfully.")
    print(f"[NETLAB] Sun prim: {SUN_PRIM}")
    print(f"[NETLAB] Sun intensity: {SUN_INTENSITY}")
    print(f"[NETLAB] Sun rotation XYZ: {tuple(SUN_ROTATION_XYZ)}")
    print(f"[NETLAB] Sky prim: {SKY_PRIM}")
    print(f"[NETLAB] Sky intensity: {SKY_INTENSITY}")


add_sun_and_sky()
