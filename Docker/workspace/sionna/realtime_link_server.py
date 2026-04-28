#!/usr/bin/env python3
"""
NETLAB KAUST SWARM-SYM - Real-time Sionna link service.

This process runs inside the Sionna container and exposes a minimal HTTP API
used by ROS 2 to request link-quality estimates between two UAVs.  The current
implementation is intentionally lightweight and deterministic so that it can be
used as a live integration test while the full ray-tracing scene pipeline is
being developed.

Endpoint:
    POST /link

Payload:
    {
      "tx": [x, y, z],
      "rx": [x, y, z],
      "frequency_hz": 3500000000.0,
      "bandwidth_hz": 20000000.0,
      "tx_power_dbm": 20.0,
      "noise_floor_dbm": -95.0
    }

Response:
    JSON link metrics including distance, path loss, received power, SNR,
    Shannon-capacity estimate, propagation delay, and qualitative status.
"""

from __future__ import annotations

import json
import math
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Iterable, Tuple

try:
    import sionna  # type: ignore

    SIONNA_AVAILABLE = True
    SIONNA_VERSION = getattr(sionna, "__version__", "unknown")
except Exception as exc:  # pragma: no cover - diagnostic path
    SIONNA_AVAILABLE = False
    SIONNA_VERSION = f"unavailable: {exc}"

HOST = os.environ.get("SIONNA_LINK_HOST", "0.0.0.0")
PORT = int(os.environ.get("SIONNA_LINK_PORT", "8090"))
DEFAULT_FREQUENCY_HZ = float(os.environ.get("SIONNA_FREQUENCY_HZ", "3500000000.0"))
DEFAULT_BANDWIDTH_HZ = float(os.environ.get("SIONNA_BANDWIDTH_HZ", "20000000.0"))
DEFAULT_TX_POWER_DBM = float(os.environ.get("SIONNA_TX_POWER_DBM", "20.0"))
DEFAULT_NOISE_FLOOR_DBM = float(os.environ.get("SIONNA_NOISE_FLOOR_DBM", "-95.0"))
DEFAULT_SHADOW_LOSS_DB = float(os.environ.get("SIONNA_SHADOW_LOSS_DB", "3.0"))
C = 299_792_458.0


def _as_vec3(value: Any, name: str) -> Tuple[float, float, float]:
    if not isinstance(value, Iterable):
        raise ValueError(f"{name} must be a length-3 iterable")
    values = list(value)
    if len(values) != 3:
        raise ValueError(f"{name} must contain exactly three numeric values")
    return (float(values[0]), float(values[1]), float(values[2]))


def _status_from_snr(snr_db: float) -> str:
    if snr_db >= 25.0:
        return "strong"
    if snr_db >= 12.0:
        return "nominal"
    if snr_db >= 3.0:
        return "weak"
    return "outage"


def compute_link_metrics(payload: Dict[str, Any]) -> Dict[str, Any]:
    tx = _as_vec3(payload.get("tx", [0.0, 0.0, 0.0]), "tx")
    rx = _as_vec3(payload.get("rx", [0.0, 0.0, 0.0]), "rx")

    frequency_hz = float(payload.get("frequency_hz", DEFAULT_FREQUENCY_HZ))
    bandwidth_hz = float(payload.get("bandwidth_hz", DEFAULT_BANDWIDTH_HZ))
    tx_power_dbm = float(payload.get("tx_power_dbm", DEFAULT_TX_POWER_DBM))
    noise_floor_dbm = float(payload.get("noise_floor_dbm", DEFAULT_NOISE_FLOOR_DBM))
    shadow_loss_db = float(payload.get("shadow_loss_db", DEFAULT_SHADOW_LOSS_DB))

    dx = rx[0] - tx[0]
    dy = rx[1] - tx[1]
    dz = rx[2] - tx[2]
    distance_m = max(math.sqrt(dx * dx + dy * dy + dz * dz), 1e-3)

    wavelength_m = C / frequency_hz
    fspl_db = 20.0 * math.log10((4.0 * math.pi * distance_m) / wavelength_m)

    # Small deterministic altitude penalty/bonus term.  This is not a substitute
    # for full Sionna RT geometry, but it makes the live demo respond to 3D motion
    # while remaining stable enough for reproducible integration tests.
    altitude_delta_m = abs(tx[2] - rx[2])
    altitude_penalty_db = min(3.0, altitude_delta_m * 0.05)
    total_path_loss_db = fspl_db + shadow_loss_db + altitude_penalty_db

    rx_power_dbm = tx_power_dbm - total_path_loss_db
    snr_db = rx_power_dbm - noise_floor_dbm
    snr_linear = max(10.0 ** (snr_db / 10.0), 0.0)
    capacity_mbps = (bandwidth_hz * math.log2(1.0 + snr_linear)) / 1e6
    propagation_delay_ms = (distance_m / C) * 1000.0

    return {
        "timestamp": time.time(),
        "engine": "sionna-realtime-link-service",
        "sionna_available": SIONNA_AVAILABLE,
        "sionna_version": SIONNA_VERSION,
        "tx": list(tx),
        "rx": list(rx),
        "distance_m": distance_m,
        "frequency_hz": frequency_hz,
        "bandwidth_hz": bandwidth_hz,
        "tx_power_dbm": tx_power_dbm,
        "noise_floor_dbm": noise_floor_dbm,
        "fspl_db": fspl_db,
        "shadow_loss_db": shadow_loss_db,
        "altitude_penalty_db": altitude_penalty_db,
        "path_loss_db": total_path_loss_db,
        "rx_power_dbm": rx_power_dbm,
        "snr_db": snr_db,
        "capacity_mbps": capacity_mbps,
        "propagation_delay_ms": propagation_delay_ms,
        "status": _status_from_snr(snr_db),
    }


class LinkRequestHandler(BaseHTTPRequestHandler):
    server_version = "NETLABSionnaLink/0.1"

    def _send_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path in {"/", "/health"}:
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "NETLAB Sionna real-time link service",
                    "sionna_available": SIONNA_AVAILABLE,
                    "sionna_version": SIONNA_VERSION,
                    "port": PORT,
                },
            )
            return
        self._send_json(404, {"ok": False, "error": f"unknown path: {self.path}"})

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path != "/link":
            self._send_json(404, {"ok": False, "error": f"unknown path: {self.path}"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body or "{}")
            metrics = compute_link_metrics(payload)
            self._send_json(200, {"ok": True, "metrics": metrics})
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[SIONNA-LINK] {self.address_string()} - {fmt % args}", flush=True)


def main() -> None:
    print("[SIONNA-LINK] Starting NETLAB Sionna real-time link service", flush=True)
    print(f"[SIONNA-LINK] Sionna available: {SIONNA_AVAILABLE} ({SIONNA_VERSION})", flush=True)
    print(f"[SIONNA-LINK] Listening on {HOST}:{PORT}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), LinkRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[SIONNA-LINK] Stopping service", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
