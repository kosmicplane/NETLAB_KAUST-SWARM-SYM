# NETLAB KAUST SWARM-SYM - Live two-drone hover scene for Isaac Sim.
#
# Usage inside the already-running Isaac Sim WebRTC session:
#   Window -> Script Editor -> paste/run:
#   exec(open("/workspace/isaac/scripts/two_drone_hover_live.py").read())
#
# The script creates two visual UAVs, animates them in hover, publishes their
# poses to ROS 2, and listens for ROS/Sionna link messages to update link color.

from __future__ import annotations

import json
import math
import time
import traceback
from typing import Any, Dict, Optional

from pxr import Gf, Sdf, UsdGeom, UsdLux
import omni.kit.app
import omni.usd

try:
    import rclpy
    from geometry_msgs.msg import PoseStamped
    from std_msgs.msg import String

    ROS_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on Isaac ROS bridge env
    ROS_AVAILABLE = False
    ROS_IMPORT_ERROR = str(exc)

STAGE = omni.usd.get_context().get_stage()
WORLD_PATH = "/World"
DEMO_ROOT = "/World/NETLAB_Two_Drone_Hover_Demo"


def _ensure_world() -> None:
    if not STAGE.GetPrimAtPath(Sdf.Path(WORLD_PATH)):
        UsdGeom.Xform.Define(STAGE, WORLD_PATH)


def _clear_xform(path: str) -> UsdGeom.Xformable:
    prim = STAGE.GetPrimAtPath(path)
    xformable = UsdGeom.Xformable(prim)
    xformable.ClearXformOpOrder()
    return xformable


def _set_transform(path: str, translation=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)) -> None:
    xformable = _clear_xform(path)
    xformable.AddTranslateOp().Set(Gf.Vec3d(*translation))
    xformable.AddRotateXYZOp().Set(Gf.Vec3f(*rotation))
    xformable.AddScaleOp().Set(Gf.Vec3f(*scale))


def _display_color(path: str, color) -> None:
    prim = STAGE.GetPrimAtPath(path)
    if prim and prim.IsValid():
        geom = UsdGeom.Gprim(prim)
        geom.CreateDisplayColorAttr([Gf.Vec3f(float(color[0]), float(color[1]), float(color[2]))])


def _cube(path: str, translation, scale, color) -> None:
    UsdGeom.Cube.Define(STAGE, path)
    _set_transform(path, translation=translation, scale=scale)
    _display_color(path, color)


def _sphere(path: str, translation, scale, color) -> None:
    UsdGeom.Sphere.Define(STAGE, path)
    _set_transform(path, translation=translation, scale=scale)
    _display_color(path, color)


def _cylinder(path: str, translation, radius, height, color) -> None:
    cylinder = UsdGeom.Cylinder.Define(STAGE, path)
    cylinder.CreateRadiusAttr(float(radius))
    cylinder.CreateHeightAttr(float(height))
    _set_transform(path, translation=translation)
    _display_color(path, color)


def _make_drone(name: str, base_color) -> None:
    root = f"{DEMO_ROOT}/{name}"
    UsdGeom.Xform.Define(STAGE, root)

    _cube(f"{root}/Body", (0.0, 0.0, 0.0), (0.55, 0.30, 0.12), base_color)
    _cube(f"{root}/Arm_X", (0.0, 0.0, 0.02), (1.05, 0.045, 0.035), (0.08, 0.08, 0.08))
    _cube(f"{root}/Arm_Y", (0.0, 0.0, 0.025), (0.045, 1.05, 0.035), (0.08, 0.08, 0.08))

    rotor_color = (0.02, 0.02, 0.02)
    for i, (x, y) in enumerate([(0.95, 0.95), (0.95, -0.95), (-0.95, 0.95), (-0.95, -0.95)], start=1):
        _cylinder(f"{root}/Rotor_{i}", (x, y, 0.05), 0.22, 0.025, rotor_color)
        _sphere(f"{root}/Motor_{i}", (x, y, 0.02), (0.08, 0.08, 0.08), base_color)

    _sphere(f"{root}/Status_Light", (0.0, -0.42, 0.18), (0.10, 0.10, 0.10), (0.0, 1.0, 0.0))


def _make_curve(path: str, color) -> UsdGeom.BasisCurves:
    curve = UsdGeom.BasisCurves.Define(STAGE, path)
    curve.CreateTypeAttr("linear")
    curve.CreateCurveVertexCountsAttr([2])
    curve.CreatePointsAttr([Gf.Vec3f(0, 0, 0), Gf.Vec3f(1, 0, 0)])
    curve.CreateWidthsAttr([0.06, 0.06])
    curve.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    return curve


def _create_scene() -> None:
    _ensure_world()
    UsdGeom.Xform.Define(STAGE, DEMO_ROOT)

    if not STAGE.GetPrimAtPath("/World/Sun"):
        UsdLux.DistantLight.Define(STAGE, "/World/Sun").CreateIntensityAttr(3500)
    if not STAGE.GetPrimAtPath("/World/Sky"):
        UsdLux.DomeLight.Define(STAGE, "/World/Sky").CreateIntensityAttr(400)

    _cube(f"{DEMO_ROOT}/Ground", (0, 0, -0.03), (20.0, 14.0, 0.03), (0.18, 0.22, 0.18))
    _cube(f"{DEMO_ROOT}/ROS_Node", (-6.5, -5.5, 0.7), (0.55, 0.55, 0.55), (0.1, 0.4, 0.9))
    _cube(f"{DEMO_ROOT}/Sionna_Node", (6.5, -5.5, 0.7), (0.55, 0.55, 0.55), (0.7, 0.1, 0.9))
    _make_curve(f"{DEMO_ROOT}/Drone_Link", (0.0, 0.8, 1.0))
    _make_curve(f"{DEMO_ROOT}/ROS_Sionna_Link", (0.6, 0.6, 1.0))

    _make_drone("Drone_1", (1.0, 0.72, 0.08))
    _make_drone("Drone_2", (0.05, 0.85, 1.0))

    camera = UsdGeom.Camera.Define(STAGE, f"{DEMO_ROOT}/Overview_Camera")
    _set_transform(f"{DEMO_ROOT}/Overview_Camera", translation=(9.0, -11.0, 8.0), rotation=(58.0, 0.0, 39.0))
    camera.CreateFocalLengthAttr(22)


class TwoDroneHoverDemo:
    def __init__(self) -> None:
        self.start_time = time.time()
        self.last_publish_time = 0.0
        self.publish_period_s = 0.1
        self.last_link_metrics: Dict[str, Any] = {}
        self.last_inbox: Dict[str, Any] = {}
        self.ros_node = None
        self.ros_ready = False
        self.pose_pub_1 = None
        self.pose_pub_2 = None
        self.telemetry_pub_1 = None
        self.telemetry_pub_2 = None

        _create_scene()
        self._setup_ros()
        self.subscription = omni.kit.app.get_app().get_update_event_stream().create_subscription_to_pop(
            self._on_update, name="NETLAB two-drone hover update"
        )
        print("[NETLAB-DEMO] Two-drone hover demo started.")
        if self.ros_ready:
            print("[NETLAB-DEMO] ROS 2 publishers/subscribers are active.")
        else:
            print("[NETLAB-DEMO] ROS 2 is not active; visual hover will still run.")

    def shutdown(self) -> None:
        try:
            self.subscription = None
            if self.ros_node is not None:
                self.ros_node.destroy_node()
        except Exception:
            traceback.print_exc()

    def _setup_ros(self) -> None:
        if not ROS_AVAILABLE:
            print(f"[NETLAB-DEMO] rclpy unavailable in Isaac context: {ROS_IMPORT_ERROR}")
            return

        try:
            if not rclpy.ok():
                rclpy.init(args=None)
            self.ros_node = rclpy.create_node("isaac_two_drone_hover_demo")
            self.pose_pub_1 = self.ros_node.create_publisher(PoseStamped, "/swarm/drone_1/state", 10)
            self.pose_pub_2 = self.ros_node.create_publisher(PoseStamped, "/swarm/drone_2/state", 10)
            self.telemetry_pub_1 = self.ros_node.create_publisher(String, "/swarm/drone_1/telemetry", 10)
            self.telemetry_pub_2 = self.ros_node.create_publisher(String, "/swarm/drone_2/telemetry", 10)
            self.ros_node.create_subscription(String, "/swarm/sionna/link_metrics", self._link_metrics_cb, 10)
            self.ros_node.create_subscription(String, "/swarm/drone_2/inbox", self._drone_2_inbox_cb, 10)
            self.ros_ready = True
        except Exception as exc:
            print(f"[NETLAB-DEMO] ROS setup failed: {exc}")
            traceback.print_exc()
            self.ros_ready = False

    def _link_metrics_cb(self, msg: Any) -> None:
        try:
            payload = json.loads(msg.data)
            self.last_link_metrics = payload.get("metrics", payload)
        except Exception:
            self.last_link_metrics = {"status": "parse_error", "raw": msg.data}

    def _drone_2_inbox_cb(self, msg: Any) -> None:
        try:
            self.last_inbox = json.loads(msg.data)
        except Exception:
            self.last_inbox = {"raw": msg.data}

    def _pose_msg(self, drone_name: str, position) -> Any:
        msg = PoseStamped()
        msg.header.stamp = self.ros_node.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.pose.position.x = float(position[0])
        msg.pose.position.y = float(position[1])
        msg.pose.position.z = float(position[2])
        msg.pose.orientation.w = 1.0
        return msg

    def _publish_ros(self, p1, p2) -> None:
        if not self.ros_ready:
            return

        try:
            rclpy.spin_once(self.ros_node, timeout_sec=0.0)
            now = time.time()
            if now - self.last_publish_time < self.publish_period_s:
                return
            self.last_publish_time = now

            self.pose_pub_1.publish(self._pose_msg("drone_1", p1))
            self.pose_pub_2.publish(self._pose_msg("drone_2", p2))

            link_status = self.last_link_metrics.get("status", "waiting_for_sionna")
            for name, position, publisher in [
                ("drone_1", p1, self.telemetry_pub_1),
                ("drone_2", p2, self.telemetry_pub_2),
            ]:
                msg = String()
                msg.data = json.dumps(
                    {
                        "source": name,
                        "timestamp": now,
                        "position": [float(position[0]), float(position[1]), float(position[2])],
                        "mode": "hover",
                        "ros_connected": True,
                        "last_sionna_link_status": link_status,
                    },
                    sort_keys=True,
                )
                publisher.publish(msg)
        except Exception as exc:
            print(f"[NETLAB-DEMO] ROS publish/spin error: {exc}")
            traceback.print_exc()

    def _update_visuals(self, p1, p2) -> None:
        t = time.time() - self.start_time
        yaw_1 = 8.0 * math.sin(t * 0.5)
        yaw_2 = -8.0 * math.sin(t * 0.5 + 0.6)
        _set_transform(f"{DEMO_ROOT}/Drone_1", translation=p1, rotation=(0.0, 0.0, yaw_1))
        _set_transform(f"{DEMO_ROOT}/Drone_2", translation=p2, rotation=(0.0, 0.0, yaw_2))

        curve = UsdGeom.BasisCurves(STAGE.GetPrimAtPath(f"{DEMO_ROOT}/Drone_Link"))
        curve.GetPointsAttr().Set([Gf.Vec3f(*p1), Gf.Vec3f(*p2)])

        ros_sionna = UsdGeom.BasisCurves(STAGE.GetPrimAtPath(f"{DEMO_ROOT}/ROS_Sionna_Link"))
        ros_sionna.GetPointsAttr().Set([Gf.Vec3f(-6.5, -5.5, 0.7), Gf.Vec3f(6.5, -5.5, 0.7)])

        status = self.last_link_metrics.get("status", "waiting")
        if status == "strong":
            color = (0.0, 1.0, 0.15)
        elif status == "nominal":
            color = (0.2, 0.8, 1.0)
        elif status == "weak":
            color = (1.0, 0.8, 0.0)
        elif status == "outage":
            color = (1.0, 0.0, 0.0)
        else:
            color = (0.6, 0.6, 0.6)

        curve.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        _display_color(f"{DEMO_ROOT}/Drone_1/Status_Light", color)
        _display_color(f"{DEMO_ROOT}/Drone_2/Status_Light", color)

    def _on_update(self, event) -> None:  # noqa: ANN001 - Kit callback signature
        t = time.time() - self.start_time
        p1 = (-2.75, 0.0, 3.0 + 0.12 * math.sin(2.0 * math.pi * 0.35 * t))
        p2 = (2.75, 0.0, 3.0 + 0.12 * math.sin(2.0 * math.pi * 0.35 * t + math.pi / 5.0))
        self._update_visuals(p1, p2)
        self._publish_ros(p1, p2)


def _start_demo() -> None:
    previous = globals().get("__NETLAB_TWO_DRONE_DEMO__")
    if previous is not None:
        try:
            previous.shutdown()
            print("[NETLAB-DEMO] Previous demo instance stopped.")
        except Exception:
            traceback.print_exc()

    globals()["__NETLAB_TWO_DRONE_DEMO__"] = TwoDroneHoverDemo()


_start_demo()
