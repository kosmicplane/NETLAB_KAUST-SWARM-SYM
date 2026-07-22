#!/usr/bin/env python3
"""NETLAB communication-link service.

The service exposes a stable HTTP contract to ROS 2 and Mission Control.  It
uses the transparent analytical model from :mod:`netlab.link` for F1/F2
experiments.  Geometry-aware Sionna RT is advertised only when a concrete
scene adapter is available; the service never silently labels an analytical
fallback as ray tracing.
"""
from __future__ import annotations

import json
import math
import os
import signal
import sys
import threading
import time
import traceback
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping

REPO_ROOT = Path(os.environ.get("NETLAB_REPO_ROOT", "/workspace/netlab"))
if REPO_ROOT.exists() and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import sionna  # type: ignore

    SIONNA_AVAILABLE = True
    SIONNA_VERSION = str(getattr(sionna, "__version__", "unknown"))
except Exception as exc:  # pragma: no cover - depends on container image
    SIONNA_AVAILABLE = False
    SIONNA_VERSION = "unavailable"
    SIONNA_IMPORT_ERROR = str(exc)

from netlab.link import LinkRequest, compute_analytical_link, evaluate_feasibility  # noqa: E402
from netlab.models import LinkMetrics  # noqa: E402
from netlab.state import atomic_write_json  # noqa: E402

HOST = os.environ.get("SIONNA_HOST", "0.0.0.0")
PORT = int(os.environ.get("SIONNA_PORT", "8090"))
HEARTBEAT = Path(os.environ.get("SIONNA_HEARTBEAT", "/workspace/results/snaas_sionna_heartbeat.json"))
REVISION_ACK = Path(os.environ.get("SIONNA_REVISION_ACK", "/workspace/results/revision_sionna_ack.json"))
COMPAT_REVISION_ACK = REVISION_ACK.parent / "snaas_sionna_revision_ack.json"
MAX_BODY_BYTES = int(os.environ.get("SIONNA_MAX_BODY_BYTES", str(2 * 1024 * 1024)))
SERVICE_VERSION = "2.0.0"
START_TIME = time.time()
STOP = threading.Event()
REVISION_LOCK = threading.RLock()
ACTIVE_REVISION: Dict[str, Any] = {"revision_id": "", "hashes": {}, "applied_at": None, "command_id": ""}


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _write_heartbeat(*, ready: bool = True, last_request_id: str = "", last_error: str = "") -> None:
    payload = {
        "timestamp": time.time(),
        "service": "netlab-link-service",
        "service_version": SERVICE_VERSION,
        "ready": bool(ready),
        "pid": os.getpid(),
        "host": HOST,
        "port": PORT,
        "uptime_s": max(0.0, time.time() - START_TIME),
        "sionna_available": SIONNA_AVAILABLE,
        "sionna_version": SIONNA_VERSION,
        "ray_tracing_adapter_ready": False,
        "last_request_id": last_request_id,
        "last_error": last_error,
        "applied_revision_id": ACTIVE_REVISION.get("revision_id", ""),
        "applied_hashes": ACTIVE_REVISION.get("hashes", {}),
        "revision_applied_at": ACTIVE_REVISION.get("applied_at"),
    }
    try:
        atomic_write_json(HEARTBEAT, payload)
    except Exception:
        # A heartbeat failure must not terminate the link evaluator.
        pass


def _heartbeat_loop() -> None:
    while not STOP.wait(1.0):
        _write_heartbeat(ready=True)


def _metric_payload(metrics: LinkMetrics, request: Mapping[str, Any]) -> Dict[str, Any]:
    data = metrics.as_dict()
    # Preserve the established ROS contract while adding provenance fields.
    data.update(
        {
            "timestamp": metrics.timestamp_wall_s,
            "engine": "netlab-link-service",
            "status": "ok",
            "model_source": metrics.model,
            "fidelity_profile": metrics.fidelity.value,
            "tx_antenna": request.get("tx_antenna", request.get("tx_antenna_id", "unspecified")),
            "rx_antenna": request.get("rx_antenna", request.get("rx_antenna_id", "unspecified")),
            "tx_antenna_gain_dbi": float(request.get("tx_antenna_gain_dbi", request.get("tx_gain_dbi", 0.0))),
            "rx_antenna_gain_dbi": float(request.get("rx_antenna_gain_dbi", request.get("rx_gain_dbi", 0.0))),
            "cache_status": "MISS",
            "uncertainty": {
                "kind": "analytical_or_seeded_stochastic",
                "shadowing_sigma_db": float(request.get("shadowing_sigma_db", 0.0)),
            },
        }
    )

    # Legacy clients historically supplied a precomputed noise floor.  Keep the
    # contract deterministic while the v5 schema migrates to receiver noise
    # figure.  The response states exactly which method was used.
    if "noise_floor_dbm" in request:
        noise_dbm = float(request["noise_floor_dbm"])
        data["noise_dbm"] = noise_dbm
        data["snr_db"] = float(data["rx_power_dbm"]) - noise_dbm
        interference_margin = float(request.get("interference_margin_db", 0.0))
        data["sinr_db"] = float(data["snr_db"]) - interference_margin
        sinr_linear = 10.0 ** (float(data["sinr_db"]) / 10.0)
        factor = float(request.get("spectral_efficiency_factor", 0.75))
        bandwidth_hz = float(request.get("bandwidth_hz", 20e6))
        data["capacity_mbps"] = factor * bandwidth_hz * math.log2(1.0 + max(0.0, sinr_linear)) / 1e6
        data["noise_model"] = "explicit_legacy_noise_floor"
    else:
        data["noise_model"] = "thermal_noise_plus_receiver_noise_figure"
    return _json_safe(data)


def evaluate_one(raw: Mapping[str, Any]) -> Dict[str, Any]:
    request_id = str(raw.get("request_id") or uuid.uuid4())
    requested_model = str(raw.get("model", "sionna_analytical")).strip().lower()
    allow_fallback = bool(raw.get("allow_fallback", True))

    if requested_model == "sionna_rt":
        if not allow_fallback:
            return {
                "ok": False,
                "request_id": request_id,
                "error": {
                    "code": "SIONNA_RT_ADAPTER_NOT_READY",
                    "message": "A geometry-aware Sionna RT scene adapter is not active for this request.",
                    "component": "link_service",
                    "recommendation": "Load a validated world with electromagnetic materials or enable an explicit analytical fallback.",
                },
            }
        normalized = dict(raw)
        normalized["model"] = str(raw.get("fallback_model", "free_space"))
        fallback = True
    else:
        normalized = dict(raw)
        fallback = False

    normalized["request_id"] = request_id
    link_request = LinkRequest.from_mapping(normalized)
    metrics = compute_analytical_link(link_request)
    metric_dict = _metric_payload(metrics, raw)
    metric_dict["requested_model"] = requested_model
    metric_dict["fallback_used"] = fallback
    if fallback:
        metric_dict["fallback_reason"] = "SIONNA_RT_ADAPTER_NOT_READY"
        metric_dict["status"] = "analytical_fallback"

    # Optional gate evaluation lets Mission Control preview the exact predicate
    # breakdown. ROS remains the authoritative packet-advancement gate.  Both
    # the v5 nested ``thresholds`` object and the established flat request
    # fields are accepted during the brownfield migration.
    threshold_block = raw.get("thresholds", {})
    thresholds = dict(threshold_block) if isinstance(threshold_block, Mapping) else {}

    def threshold(name: str, *aliases: str, default: float) -> float:
        for key in (name, *aliases):
            if key in raw:
                return float(raw[key])
            if key in thresholds:
                return float(thresholds[key])
        return float(default)

    gate_keys = {
        "operational_range_m",
        "max_single_hop_range_m",
        "hard_outage_distance_m",
        "hard_outage_range_m",
        "min_snr_db",
        "min_sinr_db",
        "min_capacity_mbps",
        "required_capacity_mbps",
        "source_active",
        "destination_active",
        "source_failed",
        "destination_failed",
    }
    has_gate_request = bool(gate_keys.intersection(raw)) or bool(gate_keys.intersection(thresholds))
    decision_payload = None
    gate_reason = None
    link_budget_ok = None
    if has_gate_request:
        min_snr_db = threshold("min_snr_db", default=3.0)
        decision = evaluate_feasibility(
            metrics,
            source_active=bool(raw.get("source_active", True)),
            destination_active=bool(raw.get("destination_active", True)),
            source_failed=bool(raw.get("source_failed", False)),
            destination_failed=bool(raw.get("destination_failed", False)),
            operational_range_m=threshold("operational_range_m", "max_single_hop_range_m", default=90.0),
            hard_outage_distance_m=threshold("hard_outage_distance_m", "hard_outage_range_m", default=220.0),
            min_snr_db=min_snr_db,
            min_sinr_db=threshold("min_sinr_db", default=min_snr_db),
            min_capacity_mbps=threshold("min_capacity_mbps", "required_capacity_mbps", default=1.0),
            metric_ttl_s=threshold("metric_ttl_s", default=2.0),
        )
        decision_payload = decision.as_dict()
        gate_reason = decision.reason.value
        link_budget_ok = bool(decision.feasible)
        metric_dict["feasibility"] = decision_payload
        metric_dict["gate_reason"] = gate_reason
        metric_dict["link_budget_ok"] = link_budget_ok

    _write_heartbeat(ready=True, last_request_id=request_id)
    response = {
        "ok": True,
        "request_id": request_id,
        "service": "NETLAB communication link service",
        "service_version": SERVICE_VERSION,
        # Compatibility aliases intentionally remain at the top level while
        # ``metrics`` is the authoritative scientific payload.
        "model_source": metric_dict.get("model_source"),
        "fidelity_profile": metric_dict.get("fidelity_profile"),
        "metrics": metric_dict,
    }
    if decision_payload is not None:
        response.update(
            {
                "feasibility": decision_payload,
                "gate_reason": gate_reason,
                "link_budget_ok": link_budget_ok,
            }
        )
    return response


def evaluate(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Compatibility evaluator used by tests, plugins, and lightweight clients.

    Accepts the canonical versioned fields as well as the established
    ``source_position_m``/``destination_position_m`` and nested ``parameters``
    shape. The returned dictionary is flattened for convenient scientific
    inspection while preserving the full metrics and predicate breakdown.
    """
    payload = dict(raw)
    parameters = payload.pop("parameters", {})
    if isinstance(parameters, Mapping):
        for key, value in parameters.items():
            payload.setdefault(str(key), value)
    if "source_position_m" in payload and "tx_position" not in payload:
        payload["tx_position"] = payload["source_position_m"]
    if "destination_position_m" in payload and "rx_position" not in payload:
        payload["rx_position"] = payload["destination_position_m"]
    result = evaluate_one(payload)
    if not result.get("ok"):
        return result
    metrics = dict(result.get("metrics", {}))
    decision = result.get("feasibility", metrics.get("feasibility", {}))
    gate_reason = result.get("gate_reason") or metrics.get("gate_reason") or (decision.get("reason") if isinstance(decision, Mapping) else None)
    feasible = bool(result.get("link_budget_ok", metrics.get("link_budget_ok", decision.get("feasible", False) if isinstance(decision, Mapping) else False)))
    flattened = dict(metrics)
    flattened.update({
        "ok": True,
        "request_id": result.get("request_id", ""),
        "feasible": feasible,
        "gate_reason": gate_reason or "UNKNOWN",
        "feasibility": decision,
        "metrics": metrics,
        "service_version": SERVICE_VERSION,
    })
    return flattened


class Handler(BaseHTTPRequestHandler):
    server_version = "NETLABLinkService/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[NETLAB-LINK] " + fmt % args + "\n")
        sys.stdout.flush()

    def _send(self, status: int, payload: Any) -> None:
        body = (json.dumps(_json_safe(payload), sort_keys=True) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            raise ValueError("A non-empty JSON request body is required.")
        if length > MAX_BODY_BYTES:
            raise ValueError(f"Request body exceeds the {MAX_BODY_BYTES}-byte limit.")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON request body must be an object.")
        return value

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/health", "/ready"}:
            payload = {
                "ok": True,
                "ready": True,
                "service": "NETLAB communication link service",
                "service_version": SERVICE_VERSION,
                "port": PORT,
                "uptime_s": max(0.0, time.time() - START_TIME),
                "sionna_available": SIONNA_AVAILABLE,
                "sionna_version": SIONNA_VERSION,
                "ray_tracing_adapter_ready": False,
                "models": ["free_space", "log_distance", "stochastic_shadowing", "sionna_analytical"],
                "applied_revision_id": ACTIVE_REVISION.get("revision_id", ""),
                "applied_hashes": ACTIVE_REVISION.get("hashes", {}),
            }
            if not SIONNA_AVAILABLE:
                payload["sionna_import_error"] = globals().get("SIONNA_IMPORT_ERROR", "")
            self._send(HTTPStatus.OK, payload)
            return
        if self.path == "/models":
            self._send(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "models": [
                        {"id": "free_space", "fidelity": "F1_ANALYTICAL", "ready": True},
                        {"id": "log_distance", "fidelity": "F1_ANALYTICAL", "ready": True},
                        {"id": "stochastic_shadowing", "fidelity": "F2_STOCHASTIC", "ready": True},
                        {"id": "sionna_analytical", "fidelity": "F1_ANALYTICAL", "ready": True},
                        {"id": "sionna_rt", "fidelity": "F3_GEOMETRY_AWARE", "ready": False, "reason": "No scene adapter active"},
                    ],
                },
            )
            return
        self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"code": "NOT_FOUND", "message": self.path}})

    def do_POST(self) -> None:  # noqa: N802
        try:
            payload = self._read_json()
            if self.path == "/config/apply":
                revision_id = str(payload.get("revision_id") or payload.get("revision") or "")
                if not revision_id:
                    raise ValueError("revision_id is required")
                hashes = payload.get("hashes", {}) if isinstance(payload.get("hashes", {}), Mapping) else {}
                command_id = str(payload.get("command_id", ""))
                with REVISION_LOCK:
                    ACTIVE_REVISION.update({
                        "revision_id": revision_id,
                        "hashes": dict(hashes),
                        "applied_at": time.time(),
                        "command_id": command_id,
                        "reason": str(payload.get("reason", "configuration_apply")),
                        "cache_invalidated": True,
                    })
                    acknowledgement = {
                        "ok": True,
                        "accepted": True,
                        "ready": True,
                        "participant": "sionna",
                        "component": "sionna_link_service",
                        "revision": revision_id,
                        "revision_id": revision_id,
                        "command_id": command_id,
                        "applied_config_hash": str(hashes.get("config_hash", "")),
                        "applied_hashes": dict(hashes),
                        "observed_hashes": dict(hashes),
                        "cache_invalidated": True,
                        "timestamp": ACTIVE_REVISION["applied_at"],
                    }
                    atomic_write_json(REVISION_ACK, acknowledgement)
                    atomic_write_json(COMPAT_REVISION_ACK, acknowledgement)
                _write_heartbeat(ready=True, last_request_id=command_id)
                self._send(HTTPStatus.OK, acknowledgement)
                return
            if self.path == "/link":
                result = evaluate_one(payload)
                self._send(HTTPStatus.OK if result.get("ok") else HTTPStatus.UNPROCESSABLE_ENTITY, result)
                return
            if self.path == "/links":
                items = payload.get("links", [])
                if not isinstance(items, list) or not items:
                    raise ValueError("The `links` field must be a non-empty array.")
                if len(items) > 4096:
                    raise ValueError("A batch may contain at most 4096 links.")
                results = [evaluate_one(item) if isinstance(item, Mapping) else {"ok": False, "error": {"code": "INVALID_LINK", "message": "Link entry must be an object."}} for item in items]
                self._send(HTTPStatus.OK, {"ok": all(item.get("ok") for item in results), "count": len(results), "results": results})
                return
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": {"code": "NOT_FOUND", "message": self.path}})
        except (ValueError, TypeError, KeyError) as exc:
            _write_heartbeat(ready=True, last_error=str(exc))
            self._send(HTTPStatus.BAD_REQUEST, {"ok": False, "error": {"code": "INVALID_REQUEST", "message": str(exc), "component": "link_service"}})
        except Exception as exc:  # pragma: no cover - defensive runtime path
            _write_heartbeat(ready=False, last_error=str(exc))
            traceback.print_exc()
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": {"code": "LINK_EVALUATION_FAILED", "message": str(exc), "component": "link_service"}})


def _stop(*_: Any) -> None:
    STOP.set()


def main() -> None:
    HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
    _write_heartbeat(ready=True)
    threading.Thread(target=_heartbeat_loop, name="netlab-link-heartbeat", daemon=True).start()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.timeout = 1.0
    print(f"[NETLAB-LINK] listening on http://{HOST}:{PORT}; Sionna available={SIONNA_AVAILABLE} version={SIONNA_VERSION}")
    try:
        while not STOP.is_set():
            server.handle_request()
    finally:
        server.server_close()
        _write_heartbeat(ready=False)


if __name__ == "__main__":
    main()
