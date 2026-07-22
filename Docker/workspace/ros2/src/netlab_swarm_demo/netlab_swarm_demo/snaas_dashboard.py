#!/usr/bin/env python3
"""Live terminal dashboard for the NETLAB SNaaS relay-chain experiment."""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
CLEAR = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


def _loads(data: str) -> Any:
    try:
        return json.loads(data)
    except Exception:
        return {"raw": data}


def _fmt_age(ts: Optional[float]) -> str:
    if not ts:
        return "--"
    age = max(0.0, time.time() - ts)
    if age < 1.0:
        return f"{age * 1000:.0f} ms"
    return f"{age:.1f} s"


def _fmt_num(value: Any, digits: int = 2, suffix: str = "") -> str:
    try:
        if value is None:
            return "--"
        return f"{float(value):.{digits}f}{suffix}"
    except Exception:
        return "--"


def _short_pos(value: Any) -> str:
    if not isinstance(value, list) or len(value) < 3:
        return "--"
    try:
        return f"({float(value[0]):.1f},{float(value[1]):.1f},{float(value[2]):.1f})"
    except Exception:
        return "--"


def _truncate(text: Any, width: int) -> str:
    s = str(text)
    if width <= 1:
        return s[:width]
    return s if len(s) <= width else s[: max(0, width - 1)] + "…"


def _color(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}{RESET}" if enabled else text


def _bar(value: Optional[float], width: int = 14, high_good: bool = True) -> str:
    if value is None or math.isnan(value):
        return "[" + " " * width + "]"
    v = max(0.0, min(100.0, value))
    filled = int(round((v / 100.0) * width))
    return "[" + "█" * filled + "░" * (width - filled) + "]"


class SnaasDashboard(Node):
    def __init__(self, drones: int, refresh_hz: float, no_color: bool) -> None:
        super().__init__("netlab_snaas_dashboard")
        self.drone_count = max(1, drones)
        self.refresh_s = max(0.1, 1.0 / max(0.1, refresh_hz))
        self.color = (not no_color) and sys.stdout.isatty()
        self.status: Dict[str, Any] = {}
        self.last_link: Dict[str, Any] = {}
        self.last_event: Dict[str, Any] = {}
        self.last_terminal: Dict[int, Dict[str, Any]] = {}
        self.last_rx: Dict[int, Dict[str, Any]] = {}
        self.last_tx: Dict[int, Dict[str, Any]] = {}
        self.event_log: Deque[str] = deque(maxlen=12)
        self.create_subscription(String, "/swarm/chain/status", self._status_cb, 10)
        self.create_subscription(String, "/swarm/sionna/link_metrics", self._link_cb, 10)
        self.create_subscription(String, "/swarm/chain/events", self._event_cb, 10)
        self.create_subscription(String, "/swarm/station/inbox", self._station_cb_factory("RX"), 10)
        self.create_subscription(String, "/swarm/station/outbox", self._station_cb_factory("TX"), 10)
        for i in range(1, self.drone_count + 1):
            self.create_subscription(String, f"/swarm/drone_{i}/terminal", self._terminal_cb_factory(i), 10)
        self.create_timer(self.refresh_s, self._draw)
        if sys.stdout.isatty():
            sys.stdout.write(HIDE_CURSOR)
            sys.stdout.flush()
        self.get_logger().info("SNaaS dashboard started")

    def _status_cb(self, msg: String) -> None:
        payload = _loads(msg.data)
        if isinstance(payload, dict):
            self.status = payload

    def _link_cb(self, msg: String) -> None:
        payload = _loads(msg.data)
        if isinstance(payload, dict):
            self.last_link = payload
            self._append_event("LINK", payload)

    def _event_cb(self, msg: String) -> None:
        payload = _loads(msg.data)
        if isinstance(payload, dict):
            self.last_event = payload
            event_type = payload.get("event_type", "event")
            if event_type != "hop":
                self._append_event(str(event_type).upper(), payload)

    def _station_cb_factory(self, kind: str):
        def _cb(msg: String) -> None:
            payload = _loads(msg.data)
            if isinstance(payload, dict):
                payload = dict(payload)
                payload["terminal_event"] = kind
                payload["local_node"] = "station"
                self._append_event(f"STATION {kind}", payload)
        return _cb

    def _terminal_cb_factory(self, index: int):
        def _cb(msg: String) -> None:
            payload = _loads(msg.data)
            if not isinstance(payload, dict):
                return
            payload = dict(payload)
            payload["received_at"] = time.time()
            kind = str(payload.get("terminal_event", "RXTX")).upper()
            self.last_terminal[index] = payload
            if kind == "TX":
                self.last_tx[index] = payload
            elif kind == "RX":
                self.last_rx[index] = payload
            else:
                # Backward compatibility with earlier payloads.
                local = f"drone_{index}"
                if payload.get("src") == local:
                    self.last_tx[index] = payload
                if payload.get("dst") == local:
                    self.last_rx[index] = payload
            self._append_event(f"D{index} {kind}", payload)
        return _cb

    def _append_event(self, label: str, payload: Dict[str, Any]) -> None:
        metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics", {}), dict) else {}
        src = payload.get("src", "?")
        dst = payload.get("dst", "?")
        packet = payload.get("packet_id", payload.get("packet", "?"))
        decision = payload.get("decision", payload.get("event_type", ""))
        snr = metrics.get("snr_db")
        cap = metrics.get("capacity_mbps")
        text = f"{time.strftime('%H:%M:%S')} {label:<14} pkt={packet} {src}->{dst} {decision} snr={_fmt_num(snr,1,'dB')} cap={_fmt_num(cap,2,'Mbps')}"
        self.event_log.append(text)

    def _draw(self) -> None:
        cols, rows = shutil.get_terminal_size((140, 40))
        lines: List[str] = []
        if sys.stdout.isatty():
            lines.append(CLEAR)
        lines.extend(self._render_header(cols))
        lines.extend(self._render_chain(cols))
        lines.extend(self._render_drones(cols))
        lines.extend(self._render_link(cols))
        lines.extend(self._render_events(cols, max(3, rows - len(lines) - 3)))
        # Do not crop the drone table: experiments may use more than 8 drones.
        # Let the terminal scroll if the table is taller than the visible window.
        output = "\n".join(lines)
        sys.stdout.write(output)
        sys.stdout.flush()

    def _render_header(self, cols: int) -> List[str]:
        title = "NETLAB SNaaS Relay-Chain Live Dashboard"
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        exp = self.status.get("experiment_name", "waiting for /swarm/chain/status")
        version = self.status.get("chain_version", "--")
        phase = self.status.get("phase", "--")
        packet = self.status.get("packet_id", "--")
        failed = self.status.get("failed_indices", [])
        pending = self.status.get("pending_failure")
        line = "═" * min(cols, 150)
        head = f"{title}  |  {now}"
        meta = f"experiment={exp}  chain_v={version}  phase={phase}  packet={packet}  failed={failed}"
        if pending:
            meta += f"  pending_failure={pending}"
        return [
            _color(line, CYAN, self.color),
            _color(head, BOLD + CYAN, self.color),
            _color(_truncate(meta, min(cols, 150)), YELLOW if failed or pending else GREEN, self.color),
            _color(line, CYAN, self.color),
        ]

    def _render_chain(self, cols: int) -> List[str]:
        branches = self.status.get("active_branches", [])
        branch_lines = []
        if isinstance(branches, list) and branches:
            for bi, branch in enumerate(branches):
                branch_lines.append(f"B{bi}: " + "  →  ".join(["station"] + [f"D{i}" for i in branch]))
        else:
            active = self.status.get("active_chain", [])
            branch_lines = ["  →  ".join(["station"] + [f"D{i}" for i in active])] if isinstance(active, list) and active else ["waiting"]
        chain_text = "   |   ".join(branch_lines)
        last = self.status.get("last_hop", {}) if isinstance(self.status.get("last_hop", {}), dict) else {}
        cursor_text = ""
        if last:
            cursor_text = f"last_hop: {last.get('src','?')} → {last.get('dst','?')} | {last.get('decision','?')} | {last.get('link_status','?')}"
        coverage = f"coverage={_fmt_num(self.status.get('coverage_radius_m'),1,'m')} width={_fmt_num(self.status.get('coverage_width_m'),1,'m')} feasible={self.status.get('coverage_feasible','--')} pattern={self.status.get('movement_pattern','--')} amp={_fmt_num(self.status.get('movement_amplitude_m'),1,'m')} speed={_fmt_num(self.status.get('movement_speed'),2,'x')}"
        return [
            _color("Active relay branches", BOLD + WHITE, self.color),
            _truncate(chain_text, min(cols, 150)),
            _color(_truncate(coverage, min(cols, 150)), GREEN if self.status.get('coverage_feasible', True) else RED, self.color),
            _color(_truncate(cursor_text, min(cols, 150)), DIM, self.color),
            "",
        ]

    def _render_drones(self, cols: int) -> List[str]:
        lines = [_color("Drone state, RX/TX, and current assignment", BOLD + WHITE, self.color)]
        header = f"{'ID':<4} {'ROLE':<7} {'STATE':<10} {'BATTERY':<23} {'POS':<21} {'TARGET':<21} {'LAST RX':<34} {'LAST TX':<34}"
        lines.append(_color(header, BOLD, self.color))
        lines.append(_color("─" * min(len(header), cols), DIM, self.color))
        drones = self.status.get("drones", {}) if isinstance(self.status.get("drones", {}), dict) else {}
        failed = set(self.status.get("failed_indices", [])) if isinstance(self.status.get("failed_indices", []), list) else set()
        active_all = []
        for branch in self.status.get("active_branches", []):
            if isinstance(branch, list):
                active_all.extend(branch)
        active = set(active_all or (self.status.get("active_chain", []) if isinstance(self.status.get("active_chain", []), list) else []))
        max_status_index = 0
        for key in drones.keys():
            try:
                if str(key).startswith("drone_"):
                    max_status_index = max(max_status_index, int(str(key).split("_")[-1]))
            except Exception:
                pass
        display_count = max(self.drone_count, max_status_index)
        for i in range(1, display_count + 1):
            d = drones.get(f"drone_{i}", {}) if isinstance(drones.get(f"drone_{i}", {}), dict) else {}
            battery = d.get("battery_pct")
            role = str(d.get("role", "relay"))
            if i in failed or d.get("failed"):
                state = _color("FAILED", RED, self.color)
            elif i in active:
                state = _color("ACTIVE", GREEN, self.color)
            else:
                state = _color("STANDBY", YELLOW, self.color)
            rx = self.last_rx.get(i, {})
            tx = self.last_tx.get(i, {})
            rx_text = self._event_summary(rx)
            tx_text = self._event_summary(tx)
            bat_bar = _bar(float(battery) if battery is not None else None, 10)
            bat_text = f"{bat_bar} {_fmt_num(battery,1,'%')}"
            line = f"D{i:<3} {role:<7} {state:<19} {bat_text:<23} {_short_pos(d.get('position')):<21} {_short_pos(d.get('desired_position')):<21} {_truncate(rx_text, 33):<34} {_truncate(tx_text, 33):<34}"
            lines.append(_truncate(line, min(cols, 180)))
        lines.append("")
        return lines

    def _event_summary(self, event: Dict[str, Any]) -> str:
        if not event:
            return "--"
        metrics = event.get("metrics", {}) if isinstance(event.get("metrics", {}), dict) else {}
        peer = event.get("peer_node") or (event.get("src") if event.get("terminal_event") == "RX" else event.get("dst"))
        packet = event.get("packet_id", "?")
        snr = metrics.get("snr_db")
        age = _fmt_age(event.get("received_at") or event.get("timestamp"))
        return f"pkt={packet} peer={peer} snr={_fmt_num(snr,1)} age={age}"

    def _render_link(self, cols: int) -> List[str]:
        fallback = self.status.get("last_hop", {})
        if not isinstance(fallback, dict):
            fallback = {}
        payload = self.last_link if self.last_link else fallback
        metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics", {}), dict) else {}
        line = (
            f"src={payload.get('src','--')} dst={payload.get('dst','--')} "
            f"distance={_fmt_num(metrics.get('distance_m'),2,'m')} "
            f"path_loss={_fmt_num(metrics.get('path_loss_db'),2,'dB')} "
            f"snr={_fmt_num(metrics.get('snr_db'),2,'dB')} "
            f"capacity={_fmt_num(metrics.get('capacity_mbps'),3,'Mbps')} "
            f"delay={_fmt_num(metrics.get('propagation_delay_ms'),3,'ms')} "
            f"txAnt={metrics.get('tx_antenna','--')} rxAnt={metrics.get('rx_antenna','--')} "
            f"decision={payload.get('decision','--')} status={payload.get('link_status', metrics.get('status','--'))}"
        )
        ok = bool(payload.get("link_ok", True))
        return [
            _color("Latest Sionna hop metrics", BOLD + WHITE, self.color),
            _color(_truncate(line, min(cols, 180)), GREEN if ok else RED, self.color),
            "",
        ]

    def _render_events(self, cols: int, max_lines: int) -> List[str]:
        lines = [_color("Recent relay events", BOLD + WHITE, self.color)]
        if not self.event_log:
            lines.append(_color("waiting for relay events...", DIM, self.color))
            return lines
        for item in list(self.event_log)[-max_lines:]:
            lines.append(_truncate(item, min(cols, 180)))
        return lines


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Live dashboard for the NETLAB SNaaS relay-chain experiment.")
    parser.add_argument("--drones", type=int, default=int(os.environ.get("SNAAS_DRONE_COUNT", "7")), help="Number of drone terminal topics to watch.")
    parser.add_argument("--refresh-hz", type=float, default=4.0, help="Dashboard refresh rate.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors.")
    args = parser.parse_args(argv)

    rclpy.init(args=None)
    node = SnaasDashboard(args.drones, args.refresh_hz, args.no_color)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if sys.stdout.isatty():
            sys.stdout.write(SHOW_CURSOR + RESET + "\n")
            sys.stdout.flush()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
