import asyncio
import os
import omni.kit.asset_converter

INPUT_GLB = "/workspace/isaac/local_assets/raw/drones/dji4.glb"
OUTPUT_USD = "/workspace/isaac/local_assets/drones/tu_drone.usd"


def progress_callback(current_step, total):
    print(f"[NETLAB Drone Converter] Progress: {current_step}/{total}")


async def convert_drone():
    if not os.path.exists(INPUT_GLB):
        raise FileNotFoundError(f"Input GLB not found: {INPUT_GLB}")

    os.makedirs(os.path.dirname(OUTPUT_USD), exist_ok=True)

    converter = omni.kit.asset_converter.get_instance()

    context = omni.kit.asset_converter.AssetConverterContext()
    context.ignore_materials = False
    context.ignore_animations = False
    context.ignore_camera = True
    context.ignore_light = True
    context.smooth_normals = True
    context.use_meter_as_world_unit = True
    context.create_world_as_default_root_prim = False
    context.export_preview_surface = True

    task = converter.create_converter_task(
        INPUT_GLB,
        OUTPUT_USD,
        progress_callback,
        context
    )

    success = await task.wait_until_finished()

    if not success:
        print("[NETLAB Drone Converter] Conversion failed.")
        print("[NETLAB Drone Converter] Status:", task.get_status())
        print("[NETLAB Drone Converter] Error:", task.get_error_message())
        return

    print("[NETLAB Drone Converter] Conversion completed successfully.")
    print("[NETLAB Drone Converter] Output USD:", OUTPUT_USD)


asyncio.ensure_future(convert_drone())
