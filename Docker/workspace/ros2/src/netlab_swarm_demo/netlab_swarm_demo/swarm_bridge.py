#!/usr/bin/env python3
"""
ROS 2 bridge node for the NETLAB KAUST two-drone hover demo.

Responsibilities
----------------
1. Subscribe to drone poses published by the Isaac Sim live script.
2. Query the Sionna link service with the current Drone 1 -> Drone 2 geometry.
3. Publish link metrics to ROS 2.
4. Relay a real-time application-level message from Drone 1 to Drone 2.

This node intentionally uses only standard ROS 2 message types so that it can
run in the existing ROS 2 Jazzy container without generating custom interfaces.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from std_msgs.msg import String


def pose_to_list(msg: PoseStamped) -> list[float]:
    return [float(msg.pose.position.x), float(msg.pose.position.y), float(msg.pose.position.z)]


class SwarmBridge(Node):
    def __init__(self) -> None:
        super().__init__("netlab_swarm_bridge")

        self.sionna_url = os.environ.get("SIONNA_URL", "http://127.0.0.1:8090/link")
        self.frequency_hz = float(os.environ.get("SWARM_FREQUENCY_HZ", "3500000000.0"))
        self.bandwidth_hz = float(os.environ.get("SWARM_BANDWIDTH_HZ", "20000000.0"))
        self.tx_power_dbm = float(os.environ.get("SWARM_TX_POWER_DBM", "20.0"))
        self.noise_floor_dbm = float(os.environ.get("SWARM_NOISE_FLOOR_DBM", "-95.0"))
        self.query_period_s = float(os.environ.get("SWARM_QUERY_PERIOD_S", "0.2"))

        self.drone_1_pose: Optional[PoseStamped] = None
        self.drone_2_pose: Optional[PoseStamped] = None
        self.sequence = 0
        self.last_log_time = 0.0

        self.create_subscription(PoseStamped, "/swarm/drone_1/state", self._drone_1_pose_cb, 10)
        self.create_subscription(PoseStamped, "/swarm/drone_2/state", self._drone_2_pose_cb, 10)

        self.link_pub = self.create_publisher(String, "/swarm/sionna/link_metrics", 10)
        self.drone_1_outbox_pub = self.create_publisher(String, "/swarm/drone_1/outbox", 10)
        self.drone_2_inbox_pub = self.create_publisher(String, "/swarm/drone_2/inbox", 10)
        self.drone_2_ack_pub = self.create_publisher(String, "/swarm/drone_2/ack", 10)

        self.timer = self.create_timer(self.query_period_s, self._tick)

        self.get_logger().info("NETLAB swarm bridge started")
        self.get_logger().info(f"Sionna URL: {self.sionna_url}")

    def _drone_1_pose_cb(self, msg: PoseStamped) -> None:
        self.drone_1_pose = msg

    def _drone_2_pose_cb(self, msg: PoseStamped) -> None:
        self.drone_2_pose = msg

    def _query_sionna(self, tx: list[float], rx: list[float]) -> Dict[str, Any]:
        payload = {
            "tx": tx,
            "rx": rx,
            "frequency_hz": self.frequency_hz,
            "bandwidth_hz": self.bandwidth_hz,
            "tx_power_dbm": self.tx_power_dbm,
            "noise_floor_dbm": self.noise_floor_dbm,
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.sionna_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=0.5) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        if not response_payload.get("ok", False):
            raise RuntimeError(response_payload.get("error", "unknown Sionna error"))
        return response_payload["metrics"]

    def _publish_json(self, publisher: Any, payload: Dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, sort_keys=True)
        publisher.publish(msg)

    def _tick(self) -> None:
        if self.drone_1_pose is None or self.drone_2_pose is None:
            now = time.time()
            if now - self.last_log_time > 2.0:
                self.get_logger().info("Waiting for Isaac drone pose topics...")
                self.last_log_time = now
            return

        self.sequence += 1
        tx = pose_to_list(self.drone_1_pose)
        rx = pose_to_list(self.drone_2_pose)

        try:
            metrics = self._query_sionna(tx, rx)
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
            metrics = {
                "timestamp": time.time(),
                "engine": "sionna-realtime-link-service",
                "status": "sionna_unreachable",
                "error": str(exc),
                "tx": tx,
                "rx": rx,
            }

        link_payload = {
            "sequence": self.sequence,
            "source": "sionna-engine",
            "target": "ros2-core",
            "link": "drone_1_to_drone_2",
            "metrics": metrics,
        }
        self._publish_json(self.link_pub, link_payload)

        app_message = {
            "sequence": self.sequence,
            "source": "drone_1",
            "target": "drone_2",
            "sent_at": time.time(),
            "message_type": "hover_telemetry",
            "payload": {
                "text": "Drone 1 hover telemetry delivered through ROS 2 using Sionna link metrics.",
                "drone_1_position": tx,
                "drone_2_position": rx,
            },
            "sionna_link_status": metrics.get("status", "unknown"),
            "sionna_snr_db": metrics.get("snr_db"),
            "sionna_capacity_mbps": metrics.get("capacity_mbps"),
        }
        self._publish_json(self.drone_1_outbox_pub, app_message)
        self._publish_json(self.drone_2_inbox_pub, app_message)

        ack_payload = {
            "sequence": self.sequence,
            "source": "drone_2",
            "target": "drone_1",
            "received_sequence": self.sequence,
            "ack_at": time.time(),
            "status": "received",
            "observed_link_status": metrics.get("status", "unknown"),
        }
        self._publish_json(self.drone_2_ack_pub, ack_payload)

        now = time.time()
        if now - self.last_log_time > 2.0:
            self.get_logger().info(
                "Drone 1 -> Drone 2 | status=%s distance=%.2fm snr=%.2fdB capacity=%.2fMbps"
                % (
                    metrics.get("status", "unknown"),
                    float(metrics.get("distance_m", 0.0)),
                    float(metrics.get("snr_db", 0.0)),
                    float(metrics.get("capacity_mbps", 0.0)),
                )
            )
            self.last_log_time = now


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = SwarmBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
