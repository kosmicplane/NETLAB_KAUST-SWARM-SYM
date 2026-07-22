"""
Minimal visual validation scene for Isaac Sim on NVIDIA Brev.
This creates simple geometry so you can confirm that WebRTC visualization works.
It does not implement full Pegasus/PX4 dynamics.
"""

from isaacsim import SimulationApp

simulation_app = SimulationApp({"headless": True})

import math
from pxr import Gf, Sdf, UsdGeom, UsdLux
import omni.usd

stage = omni.usd.get_context().get_stage()

# Clear/create world root
world_path = Sdf.Path("/World")
if not stage.GetPrimAtPath(world_path):
    UsdGeom.Xform.Define(stage, world_path)

# Helpers

def make_cube(path, translation, scale, color):
    cube = UsdGeom.Cube.Define(stage, path)
    cube.AddTranslateOp().Set(Gf.Vec3d(*translation))
    cube.AddScaleOp().Set(Gf.Vec3f(*scale))
    cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return cube


def make_sphere(path, translation, scale, color):
    sphere = UsdGeom.Sphere.Define(stage, path)
    sphere.AddTranslateOp().Set(Gf.Vec3d(*translation))
    sphere.AddScaleOp().Set(Gf.Vec3f(*scale))
    sphere.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return sphere


def make_cylinder(path, translation, radius, height, color):
    cylinder = UsdGeom.Cylinder.Define(stage, path)
    cylinder.CreateRadiusAttr(radius)
    cylinder.CreateHeightAttr(height)
    cylinder.AddTranslateOp().Set(Gf.Vec3d(*translation))
    cylinder.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return cylinder

# Lighting
UsdLux.DistantLight.Define(stage, "/World/Sun").CreateIntensityAttr(3500)
UsdLux.DomeLight.Define(stage, "/World/Sky").CreateIntensityAttr(400)

# Ground and urban blocks
make_cube("/World/Ground", (0, 0, -0.05), (50, 50, 0.05), (0.25, 0.28, 0.25))

for i, (x, y, h) in enumerate([(-14, -12, 4), (-7, 10, 8), (4, -8, 6), (13, 9, 10), (17, -14, 5)]):
    make_cube(f"/World/Urban_Block_{i+1}", (x, y, h / 2), (2.5, 2.5, h / 2), (0.45, 0.45, 0.48))

# Communication towers
for i, (x, y) in enumerate([(-18, 15), (18, -15)]):
    make_cylinder(f"/World/Comms_Tower_{i+1}", (x, y, 5), 0.25, 10, (0.05, 0.25, 0.85))
    make_sphere(f"/World/Comms_Tower_{i+1}_Antenna", (x, y, 10.4), (0.8, 0.8, 0.8), (0.0, 0.6, 1.0))
    make_cylinder(f"/World/Coverage_Ring_{i+1}", (x, y, 0.03), 9.5, 0.03, (0.0, 0.35, 0.9))

# Drones as visual placeholders
for i, (x, y, z) in enumerate([(-5, -4, 8), (0, 5, 10), (8, -2, 9)]):
    body_path = f"/World/Drone_{i+1}"
    make_cube(body_path, (x, y, z), (0.7, 0.35, 0.15), (1.0, 0.8, 0.05))
    # arms
    make_cube(f"{body_path}_Arm_X", (x, y, z), (1.1, 0.06, 0.04), (0.15, 0.15, 0.15))
    make_cube(f"{body_path}_Arm_Y", (x, y, z), (0.06, 1.1, 0.04), (0.15, 0.15, 0.15))
    for j, (dx, dy) in enumerate([(1.1, 1.1), (1.1, -1.1), (-1.1, 1.1), (-1.1, -1.1)]):
        make_cylinder(f"{body_path}_Rotor_{j+1}", (x + dx, y + dy, z), 0.22, 0.025, (0.05, 0.05, 0.05))

# Ground users/devices
for i, (x, y) in enumerate([(-2, -12), (3, -15), (5, 13), (-11, 2), (14, 4), (10, -9)]):
    make_sphere(f"/World/User_Device_{i+1}", (x, y, 0.35), (0.35, 0.35, 0.35), (0.95, 0.15, 0.15))

# Camera
camera = UsdGeom.Camera.Define(stage, "/World/Overview_Camera")
camera.AddTranslateOp().Set(Gf.Vec3d(28, -32, 24))
camera.AddRotateXYZOp().Set(Gf.Vec3f(60, 0, 40))
camera.CreateFocalLengthAttr(24)

# Save USD for later inspection
output_path = "/workspace/results/basic_swarm_scene.usd"
stage.GetRootLayer().Export(output_path)
print(f"[OK] Visual validation scene exported to {output_path}")
print("[OK] If Isaac Sim WebRTC is connected, the objects should be visible in the stage.")

# Step briefly then exit. The headless Isaac service remains available separately.
for _ in range(30):
    simulation_app.update()

simulation_app.close()
