"""ROS 2 participant for revisioned NETLAB configuration application.

The agent persists the authoritative candidate, publishes a compatibility
projection to the running packet controller, and waits for the packet node to
write the canonical ROS acknowledgement.  It never acknowledges a revision
merely because a file was written.
"""
from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from netlab.config import emit_legacy_config
from netlab.io import atomic_write_json, ensure_shared_directory, read_json

SHARED = ensure_shared_directory(os.environ.get("NETLAB_SHARED_DIR", "/workspace/shared"))
RESULTS = ensure_shared_directory(os.environ.get("NETLAB_RESULTS_DIR", "/workspace/results"))
REQUEST = SHARED / "revision_ros_request.json"
ACK = RESULTS / "revision_ros_ack.json"
COMPAT_ACK = RESULTS / "snaas_ros_revision_ack.json"
HEARTBEAT = RESULTS / "snaas_ros_revision_agent_heartbeat.json"
CONFIG = SHARED / "snaas_relay_config.json"
TOPIC = "/swarm/control/update_config"


class RevisionAgent(Node):
    def __init__(self) -> None:
        super().__init__("netlab_revision_agent")
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self.publisher = self.create_publisher(String, TOPIC, qos)
        self.pending_revision = ""
        self.pending_payload: dict[str, Any] = {}
        self.last_published = 0.0
        self.last_acknowledged = ""
        self.last_error = ""
        self.started_at = time.time()
        self.sequence = 0
        self.timer = self.create_timer(0.25, self._tick)

    @staticmethod
    def _revision_meta(request: dict[str, Any]) -> dict[str, Any]:
        hashes = dict(request.get("hashes") or {})
        return {
            "revision_id": str(request.get("revision_id") or request.get("revision") or ""),
            "parent_revision_id": str(request.get("parent_revision_id", "")),
            "command_id": str(request.get("command_id", "")),
            **hashes,
        }

    def _prepare(self, request: dict[str, Any]) -> None:
        revision_id = str(request.get("revision_id") or request.get("revision") or "")
        candidate = request.get("candidate") or request.get("configuration") or request.get("config")
        if not revision_id:
            raise ValueError("revision_id is required")
        if not isinstance(candidate, dict):
            raise ValueError("revision candidate must be a JSON object")
        # Preserve the authoritative candidate for all participants.
        atomic_write_json(CONFIG, candidate)
        projected = emit_legacy_config(candidate)
        projected["_netlab_revision"] = self._revision_meta(request)
        self.pending_revision = revision_id
        self.pending_payload = projected
        self.last_published = 0.0
        self.last_error = ""

    def _publish_pending(self) -> None:
        if not self.pending_revision or not self.pending_payload:
            return
        now = time.monotonic()
        if now - self.last_published < 0.5:
            return
        message = String()
        message.data = json.dumps(self.pending_payload, sort_keys=True, separators=(",", ":"))
        self.publisher.publish(message)
        self.last_published = now

    def _observe_packet_ack(self) -> None:
        if not self.pending_revision:
            return
        acknowledgement = read_json(ACK, {}) or {}
        observed = str(acknowledgement.get("revision_id") or acknowledgement.get("revision") or "")
        if observed != self.pending_revision:
            return
        hashes = acknowledgement.get("applied_hashes") or acknowledgement.get("observed_hashes") or {}
        accepted = bool(acknowledgement.get("ready", True)) and bool(hashes)
        canonical = {
            **acknowledgement,
            "accepted": accepted,
            "participant": "ros",
            "observed_revision": observed,
            "observed_hashes": hashes,
            "message": acknowledgement.get("message") or "ROS packet runtime applied the revision.",
        }
        atomic_write_json(ACK, canonical)
        atomic_write_json(COMPAT_ACK, canonical)
        self.last_acknowledged = observed
        self.pending_revision = ""
        self.pending_payload = {}

    def _heartbeat(self) -> None:
        self.sequence += 1
        atomic_write_json(
            HEARTBEAT,
            {
                "ready": True,
                "state": "WAITING_FOR_PACKET_ACK" if self.pending_revision else "RUNNING",
                "pending_revision_id": self.pending_revision,
                "acknowledged_revision_id": self.last_acknowledged,
                "last_error": self.last_error,
                "timestamp": time.time(),
                "uptime_s": time.time() - self.started_at,
                "sequence": self.sequence,
                "pid": os.getpid(),
                "node_name": self.get_name(),
                "topic": TOPIC,
            },
        )

    def _tick(self) -> None:
        try:
            request = read_json(REQUEST, {}) or {}
            requested_revision = str(request.get("revision_id") or request.get("revision") or "")
            if requested_revision and requested_revision not in {self.pending_revision, self.last_acknowledged}:
                self._prepare(request)
            self._publish_pending()
            self._observe_packet_ack()
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.get_logger().error(self.last_error)
        self._heartbeat()


def main() -> int:
    rclpy.init()
    node = RevisionAgent()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
