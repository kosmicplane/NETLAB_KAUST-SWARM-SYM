import omni.usd
from pxr import UsdGeom, UsdPhysics, UsdShade
from omni.physx.scripts import utils

stage = omni.usd.get_context().get_stage()

WORLD_ROOT = "/World/ImportedWorld"
ROBOT_ROOT = "/nova_carter"
MAT_PATH = "/World/NETLAB_PhysicsMaterials/HighFrictionRubber"

# Create a high-friction physics material.
mat = UsdShade.Material.Define(stage, MAT_PATH)
phys_mat = UsdPhysics.MaterialAPI.Apply(mat.GetPrim())
phys_mat.CreateStaticFrictionAttr(1.8)
phys_mat.CreateDynamicFrictionAttr(1.4)
phys_mat.CreateRestitutionAttr(0.0)

def bind_physics_material(prim):
    try:
        UsdShade.MaterialBindingAPI.Apply(prim).Bind(
            mat,
            bindingStrength=UsdShade.Tokens.strongerThanDescendants,
            materialPurpose="physics"
        )
        return True
    except Exception as e:
        print("[WARN] Could not bind physics material:", prim.GetPath(), e)
        return False

world_count = 0
wheel_count = 0
collider_count = 0

# Apply collision and friction to the imported world.
for prim in stage.Traverse():
    path = str(prim.GetPath())

    if path.startswith(WORLD_ROOT) and prim.IsA(UsdGeom.Mesh):
        try:
            # Mesh simplification is usually more stable than a pure triangle mesh for large worlds.
            utils.setCollider(prim, approximationShape="meshSimplification")
            collider_count += 1
        except Exception as e:
            print("[WARN] Could not set collider:", path, e)

        if bind_physics_material(prim):
            world_count += 1

# Apply friction to robot wheels and colliders.
for prim in stage.Traverse():
    path = str(prim.GetPath()).lower()

    if not path.startswith(ROBOT_ROOT.lower()):
        continue

    name = prim.GetName().lower()

    if (
        "wheel" in name
        or "collider" in name
        or "collision" in name
    ):
        if bind_physics_material(prim):
            wheel_count += 1

print("[NETLAB] High friction physics material applied.")
print(f"[NETLAB] Material: {MAT_PATH}")
print(f"[NETLAB] World meshes with material: {world_count}")
print(f"[NETLAB] World colliders configured: {collider_count}")
print(f"[NETLAB] Robot wheel/collider prims with material: {wheel_count}")
print("[NETLAB] Now press Stop, then Play again.")
