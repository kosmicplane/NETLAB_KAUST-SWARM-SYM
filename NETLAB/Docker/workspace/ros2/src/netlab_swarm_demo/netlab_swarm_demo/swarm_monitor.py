#!/usr/bin/env python3
"""Console monitor for the NETLAB two-drone hover demo."""

from __future__ import annotations

import json
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class SwarmMonitor(Node):
    def __init__(self) -> None:
        super().__init__("netlab_swarm_monitor")
        self.create_subscription(String, "/swarm/sionna/link_metrics", self._metrics_cb, 10)
        self.create_subscription(String, "/swarm/drone_2/inbox", self._inbox_cb, 10)
        self.create_subscription(String, "/swarm/drone_2/ack", self._ack_cb, 10)
        self.get_logger().info("Monitoring /swarm/sionna/link_metrics, /swarm/drone_2/inbox, /swarm/drone_2/ack")

    def _metrics_cb(self, msg: String) -> None:
        try:
            data = json.loads(msg.data)
            metrics = data.get("metrics", {})
            self.get_logger().info(
                "SIONNA link=%s distance=%.2fm snr=%.2fdB capacity=%.2fMbps"
                % (
                    metrics.get("status", "unknown"),
                    float(metrics.get("distance_m", 0.0)),
                    float(metrics.get("snr_db", 0.0)),
                    float(metrics.get("capacity_mbps", 0.0)),
                )
            )
        except Exception:
            self.get_logger().info(f"SIONNA raw: {msg.data}")

    def _inbox_cb(self, msg: String) -> None:
        self.get_logger().info(f"Drone 2 inbox: {msg.data[:240]}")

    def _ack_cb(self, msg: String) -> None:
        self.get_logger().info(f"Drone 2 ack: {msg.data[:240]}")


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node = SwarmMonitor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
