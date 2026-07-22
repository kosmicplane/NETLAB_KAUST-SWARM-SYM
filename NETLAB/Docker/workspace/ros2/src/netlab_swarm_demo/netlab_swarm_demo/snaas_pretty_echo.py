#!/usr/bin/env python3
"""Pretty JSON subscriber for NETLAB SNaaS ROS 2 String topics.

The standard `ros2 topic echo` output is correct, but it is difficult to read
when the message payload is a long JSON string. This tool subscribes to one or
more std_msgs/String topics, parses the embedded JSON, and prints the complete
message with indentation and optional screen clearing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
CLEAR = "\033[2J\033[H"


def _json_loads_maybe(value: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        return value


def _color_enabled(no_color: bool) -> bool:
    return (not no_color) and sys.stdout.isatty()


def _c(text: str, color: str, enabled: bool) -> str:
    return f"{color}{text}{RESET}" if enabled else text


def _render_scalar(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _extract_summary(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": type(payload).__name__}
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics", {}), dict) else {}
    return {
        "event_type": payload.get("event_type"),
        "seq": payload.get("sequence"),
        "packet": payload.get("packet_id"),
        "phase": payload.get("phase") or payload.get("direction"),
        "src": payload.get("src"),
        "dst": payload.get("dst"),
        "decision": payload.get("decision"),
        "link_ok": payload.get("link_ok"),
        "status": payload.get("link_status") or metrics.get("status"),
        "distance_m": metrics.get("distance_m"),
        "snr_db": metrics.get("snr_db"),
        "capacity_mbps": metrics.get("capacity_mbps"),
    }


def _format_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)


class PrettyEcho(Node):
    def __init__(self, topics: List[str], once: bool, clear: bool, no_color: bool) -> None:
        super().__init__("netlab_snaas_pretty_echo")
        self.topics = topics
        self.once = once
        self.clear = clear
        self.color = _color_enabled(no_color)
        self.received = 0
        self.width = shutil.get_terminal_size((120, 30)).columns
        for topic in topics:
            self.create_subscription(String, topic, self._callback_factory(topic), 10)
        self.get_logger().info("Pretty echo subscribed to: " + ", ".join(topics))

    def _callback_factory(self, topic: str):
        def _callback(msg: String) -> None:
            payload = _json_loads_maybe(msg.data)
            self.received += 1
            if self.clear:
                sys.stdout.write(CLEAR)
            ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            line = "=" * min(self.width, 120)
            print(_c(line, DIM, self.color))
            print(_c(f"NETLAB SNaaS Pretty Echo  |  {ts}", BOLD + CYAN, self.color))
            print(_c(f"Topic: {topic}", BOLD + GREEN, self.color))
            print(_c(f"Message number: {self.received}", DIM, self.color))
            print(_c("-" * min(self.width, 120), DIM, self.color))

            summary = _extract_summary(payload)
            printable_summary = {k: v for k, v in summary.items() if v is not None}
            if printable_summary:
                print(_c("Summary", BOLD + YELLOW, self.color))
                for key, value in printable_summary.items():
                    print(f"  {_c(key + ':', BLUE, self.color):<28} {_render_scalar(value)}")
                print(_c("-" * min(self.width, 120), DIM, self.color))

            print(_c("Complete payload", BOLD + MAGENTA, self.color))
            if isinstance(payload, (dict, list)):
                print(_format_json(payload))
            else:
                print(str(payload))
            print(flush=True)
            if self.once:
                raise KeyboardInterrupt
        return _callback


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Pretty-print full NETLAB SNaaS JSON messages from ROS 2 String topics.")
    parser.add_argument("topics", nargs="*", default=["/swarm/sionna/link_metrics"], help="ROS 2 std_msgs/String topic(s) to subscribe to.")
    parser.add_argument("--once", action="store_true", help="Print one message then exit.")
    parser.add_argument("--clear", action="store_true", help="Clear the terminal before every message.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    args = parser.parse_args(argv)

    rclpy.init(args=None)
    node = PrettyEcho(args.topics, args.once, args.clear, args.no_color)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
