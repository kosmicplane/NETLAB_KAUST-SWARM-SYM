import math
import random
import time
import builtins

import omni.usd
import omni.kit.app

from pxr import UsdGeom, UsdLux, UsdShade, Sdf, Gf


SUN_PRIM = "/World/NETLAB_Sun"
SKY_PRIM = "/World/NETLAB_Sky"
CLOUD_ROOT = "/World/NETLAB_MovingClouds"

SUN_INTENSITY = 5000.0
SKY_INTENSITY = 300.0

# Adjust altitude and scale for the dimensions of the selected world.
CLOUD_COUNT = 10
CLOUD_ALTITUDE = 55.0
CLOUD_AREA_X = 180.0
CLOUD_AREA_Y = 120.0
CLOUD_SPEED = 2.0       # metros por segundo aprox
CLOUD_WRAP_X = 120.0

CLOUD_MATERIAL = "/World/NETLAB_Materials/CloudMat"


def remove_if_exists(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if prim.IsValid():
        stage.RemovePrim(prim_path)


def create_cloud_material(stage):
    mat_path = Sdf.Path(CLOUD_MATERIAL)
    material = UsdShade.Material.Define(stage, mat_path)

    shader = UsdShade.Shader.Define(stage, mat_path.AppendPath("PreviewSurface"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.86, 0.88, 0.90))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.85)
    shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.72)

    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def add_sun_and_sky(stage):
    remove_if_exists(stage, SUN_PRIM)
    remove_if_exists(stage, SKY_PRIM)

    sun = UsdLux.DistantLight.Define(stage, SUN_PRIM)
    sun.CreateIntensityAttr(SUN_INTENSITY)
    sun.CreateAngleAttr(0.53)
    sun.CreateColorAttr(Gf.Vec3f(1.0, 0.96, 0.86))
    sun.CreateEnableColorTemperatureAttr(True)
    sun.CreateColorTemperatureAttr(5500.0)

    sun_xform = UsdGeom.Xformable(sun.GetPrim())
    sun_xform.ClearXformOpOrder()
    sun_xform.AddRotateXYZOp().Set(Gf.Vec3f(-55.0, 0.0, -35.0))

    sky = UsdLux.DomeLight.Define(stage, SKY_PRIM)
    sky.CreateIntensityAttr(SKY_INTENSITY)
    sky.CreateColorAttr(Gf.Vec3f(0.58, 0.72, 1.0))


def create_cloud(stage, material, cloud_id, x, y, z):
    cloud_path = f"{CLOUD_ROOT}/Cloud_{cloud_id:02d}"
    cloud_xform = stage.DefinePrim(cloud_path, "Xform")

    UsdGeom.XformCommonAPI(cloud_xform).SetTranslate(Gf.Vec3d(x, y, z))
    UsdGeom.XformCommonAPI(cloud_xform).SetScale(Gf.Vec3f(1.0, 1.0, 1.0))

    # Each cloud is composed of several flattened-sphere lobes.
    lobes = [
        (0.0, 0.0, 0.0, 8.0, 3.0, 1.3),
        (5.0, 1.0, 0.4, 6.0, 2.5, 1.1),
        (-5.0, -1.0, 0.2, 6.5, 2.8, 1.0),
        (1.0, 3.5, 0.1, 5.5, 2.2, 0.9),
        (-1.0, -3.5, 0.3, 5.0, 2.0, 0.8),
    ]

    for j, (lx, ly, lz, sx, sy, sz) in enumerate(lobes):
        sphere_path = f"{cloud_path}/Lobe_{j:02d}"
        sphere = UsdGeom.Sphere.Define(stage, sphere_path)
        sphere.CreateRadiusAttr(1.0)

        prim = sphere.GetPrim()
        UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(lx, ly, lz))
        UsdGeom.XformCommonAPI(prim).SetScale(Gf.Vec3f(sx, sy, sz))

        UsdShade.MaterialBindingAPI(prim).Bind(material)

    return cloud_path


def add_clouds(stage):
    remove_if_exists(stage, CLOUD_ROOT)

    stage.DefinePrim(CLOUD_ROOT, "Xform")
    material = create_cloud_material(stage)

    random.seed(42)
    clouds = []

    for i in range(CLOUD_COUNT):
        x = random.uniform(-CLOUD_AREA_X / 2.0, CLOUD_AREA_X / 2.0)
        y = random.uniform(-CLOUD_AREA_Y / 2.0, CLOUD_AREA_Y / 2.0)
        z = CLOUD_ALTITUDE + random.uniform(-8.0, 8.0)

        cloud_path = create_cloud(stage, material, i, x, y, z)
        clouds.append({
            "path": cloud_path,
            "x0": x,
            "y": y,
            "z": z,
            "speed": CLOUD_SPEED * random.uniform(0.6, 1.4),
            "phase": random.uniform(0.0, 100.0),
        })

    return clouds


def start_cloud_animation(stage, clouds):
    start_time = time.time()

    def on_update(event):
        t = time.time() - start_time

        for cloud in clouds:
            x = cloud["x0"] + cloud["speed"] * t
            y = cloud["y"] + math.sin(t * 0.08 + cloud["phase"]) * 3.0
            z = cloud["z"] + math.sin(t * 0.05 + cloud["phase"]) * 1.2

            # wrap horizontal
            if x > CLOUD_WRAP_X:
                x = -CLOUD_WRAP_X + (x - CLOUD_WRAP_X)

            prim = stage.GetPrimAtPath(cloud["path"])
            if prim.IsValid():
                UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(x, y, z))

    # Retaining the subscription globally prevents Python from destroying it.
    builtins.NETLAB_CLOUD_ANIMATION_SUB = (
        omni.kit.app.get_app()
        .get_update_event_stream()
        .create_subscription_to_pop(on_update, name="NETLAB Moving Clouds")
    )

    print("[NETLAB] Moving cloud animation started.")


def main():
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("[NETLAB] No active USD stage found.")

    add_sun_and_sky(stage)
    clouds = add_clouds(stage)
    start_cloud_animation(stage, clouds)

    print("[NETLAB] Dynamic weather loaded.")
    print("[NETLAB] Added: sun, sky dome, moving clouds.")
    print(f"[NETLAB] Clouds: {len(clouds)}")
    print(f"[NETLAB] Cloud root: {CLOUD_ROOT}")


main()
