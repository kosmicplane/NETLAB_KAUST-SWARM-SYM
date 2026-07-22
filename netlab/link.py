"""Communication models and the failure-aware execution gate.

The analytical implementation is a transparent reference model. It is not a
replacement for geometry-aware Sionna RT. Every result carries a model and
fidelity label so downstream telemetry cannot misrepresent its origin.
"""
from __future__ import annotations

import hashlib
import math
import random
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence

from .models import (
    FeasibilityDecision,
    FidelityProfile,
    GatePredicate,
    GateReason,
    LinkMetrics,
    normalize_vec3,
)

C_MPS = 299_792_458.0
BOLTZMANN_DBM_HZ = -174.0


@dataclass
class LinkRequest:
    src: str
    dst: str
    tx_position: Sequence[float]
    rx_position: Sequence[float]
    frequency_hz: float
    bandwidth_hz: float
    tx_power_dbm: float
    receiver_noise_figure_db: float = 7.0
    implementation_loss_db: float = 2.0
    tx_gain_dbi: float = 0.0
    rx_gain_dbi: float = 0.0
    tx_cable_loss_db: float = 0.0
    rx_cable_loss_db: float = 0.0
    atmospheric_loss_db: float = 0.0
    rain_loss_db: float = 0.0
    foliage_loss_db: float = 0.0
    clutter_loss_db: float = 0.0
    blockage_loss_db: float = 0.0
    polarization_loss_db: float = 0.0
    miscellaneous_loss_db: float = 0.0
    interference_margin_db: float = 0.0
    path_loss_exponent: float = 2.0
    reference_distance_m: float = 1.0
    shadowing_sigma_db: float = 0.0
    seed: int = 0
    model: str = "free_space"
    spectral_efficiency_factor: float = 0.75
    request_id: str = ""

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "LinkRequest":
        tx_position = value.get("tx_position", value.get("tx", [0.0, 0.0, 0.0]))
        rx_position = value.get("rx_position", value.get("rx", [0.0, 0.0, 0.0]))
        return cls(
            src=str(value.get("src", value.get("tx_entity", "tx"))),
            dst=str(value.get("dst", value.get("rx_entity", "rx"))),
            tx_position=tx_position,
            rx_position=rx_position,
            frequency_hz=float(value.get("frequency_hz", 3.5e9)),
            bandwidth_hz=float(value.get("bandwidth_hz", 20e6)),
            tx_power_dbm=float(value.get("tx_power_dbm", 23.0)),
            receiver_noise_figure_db=float(value.get("receiver_noise_figure_db", value.get("noise_figure_db", 7.0))),
            implementation_loss_db=float(value.get("implementation_loss_db", 2.0)),
            tx_gain_dbi=float(value.get("tx_gain_dbi", value.get("tx_antenna_gain_dbi", 0.0))),
            rx_gain_dbi=float(value.get("rx_gain_dbi", value.get("rx_antenna_gain_dbi", 0.0))),
            tx_cable_loss_db=float(value.get("tx_cable_loss_db", 0.0)),
            rx_cable_loss_db=float(value.get("rx_cable_loss_db", 0.0)),
            atmospheric_loss_db=float(value.get("atmospheric_loss_db", 0.0)),
            rain_loss_db=float(value.get("rain_loss_db", 0.0)),
            foliage_loss_db=float(value.get("foliage_loss_db", 0.0)),
            clutter_loss_db=float(value.get("clutter_loss_db", 0.0)),
            blockage_loss_db=float(value.get("blockage_loss_db", 0.0)),
            polarization_loss_db=float(value.get("polarization_loss_db", 0.0)),
            miscellaneous_loss_db=float(value.get("miscellaneous_loss_db", 0.0)),
            interference_margin_db=float(value.get("interference_margin_db", 0.0)),
            path_loss_exponent=float(value.get("path_loss_exponent", 2.0)),
            reference_distance_m=float(value.get("reference_distance_m", 1.0)),
            shadowing_sigma_db=float(value.get("shadowing_sigma_db", value.get("shadow_loss_db", 0.0))),
            seed=int(value.get("seed", 0)),
            model=str(value.get("model", "free_space")),
            spectral_efficiency_factor=float(value.get("spectral_efficiency_factor", 0.75)),
            request_id=str(value.get("request_id", "")),
        )


def thermal_noise_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
    if bandwidth_hz <= 0:
        raise ValueError("bandwidth_hz must be positive")
    return BOLTZMANN_DBM_HZ + 10.0 * math.log10(bandwidth_hz) + noise_figure_db


def free_space_path_loss_db(distance_m: float, frequency_hz: float) -> float:
    if distance_m <= 0 or frequency_hz <= 0:
        raise ValueError("distance_m and frequency_hz must be positive")
    wavelength_m = C_MPS / frequency_hz
    return 20.0 * math.log10(4.0 * math.pi * distance_m / wavelength_m)


def log_distance_path_loss_db(
    distance_m: float,
    frequency_hz: float,
    exponent: float,
    reference_distance_m: float = 1.0,
) -> float:
    if exponent < 1.0 or exponent > 8.0:
        raise ValueError("path-loss exponent must be within [1, 8]")
    d0 = max(1e-3, reference_distance_m)
    d = max(distance_m, d0)
    return free_space_path_loss_db(d0, frequency_hz) + 10.0 * exponent * math.log10(d / d0)


def compute_analytical_link(request: LinkRequest) -> LinkMetrics:
    started = time.perf_counter()
    tx = normalize_vec3(request.tx_position, name="tx_position")
    rx = normalize_vec3(request.rx_position, name="rx_position")
    distance_m = max(1e-3, math.dist(tx, rx))
    model = request.model.lower().strip()

    if model in {"free_space", "sionna_analytical", "analytical_fspl"}:
        base_path_loss_db = free_space_path_loss_db(distance_m, request.frequency_hz)
        normalized_model = "free_space" if model == "free_space" else "sionna_analytical_reference"
    elif model in {"log_distance", "stochastic_shadowing", "probabilistic_air_to_ground"}:
        base_path_loss_db = log_distance_path_loss_db(
            distance_m,
            request.frequency_hz,
            request.path_loss_exponent,
            request.reference_distance_m,
        )
        normalized_model = model
    else:
        raise ValueError(f"analytical link engine does not implement model {request.model!r}")

    shadowing_db = 0.0
    if request.shadowing_sigma_db > 0.0:
        seed_material = f"{request.seed}|{request.src}|{request.dst}|{distance_m:.3f}".encode("utf-8")
        stable_seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
        shadowing_db = random.Random(stable_seed).gauss(0.0, request.shadowing_sigma_db)

    components = {
        "base_path_loss_db": base_path_loss_db,
        "shadowing_db": shadowing_db,
        "atmospheric_loss_db": request.atmospheric_loss_db,
        "rain_loss_db": request.rain_loss_db,
        "foliage_loss_db": request.foliage_loss_db,
        "clutter_loss_db": request.clutter_loss_db,
        "blockage_loss_db": request.blockage_loss_db,
        "polarization_loss_db": request.polarization_loss_db,
        "tx_cable_loss_db": request.tx_cable_loss_db,
        "rx_cable_loss_db": request.rx_cable_loss_db,
        "implementation_loss_db": request.implementation_loss_db,
        "miscellaneous_loss_db": request.miscellaneous_loss_db,
    }
    path_loss_db = sum(components.values())
    rx_power_dbm = request.tx_power_dbm + request.tx_gain_dbi + request.rx_gain_dbi - path_loss_db
    noise_dbm = thermal_noise_dbm(request.bandwidth_hz, request.receiver_noise_figure_db)
    snr_db = rx_power_dbm - noise_dbm
    sinr_db = snr_db - request.interference_margin_db
    sinr_linear = 10.0 ** (sinr_db / 10.0)
    capacity_mbps = (
        request.spectral_efficiency_factor
        * request.bandwidth_hz
        * math.log2(1.0 + max(0.0, sinr_linear))
        / 1e6
    )
    propagation_delay_ms = distance_m / C_MPS * 1000.0
    computation_ms = (time.perf_counter() - started) * 1000.0
    request_id = request.request_id or str(uuid.uuid4())

    return LinkMetrics(
        link_id=f"{request.src}->{request.dst}:{request_id[:8]}",
        src=request.src,
        dst=request.dst,
        distance_m=distance_m,
        path_loss_db=path_loss_db,
        rx_power_dbm=rx_power_dbm,
        snr_db=snr_db,
        sinr_db=sinr_db,
        capacity_mbps=capacity_mbps,
        propagation_delay_ms=propagation_delay_ms,
        total_delay_ms=propagation_delay_ms,
        los_state="UNDETERMINED_ANALYTICAL",
        model=normalized_model,
        model_version="2.0",
        fidelity=FidelityProfile.STOCHASTIC if request.shadowing_sigma_db > 0 else FidelityProfile.ANALYTICAL,
        components_db=components,
        request_id=request_id,
        computation_ms=computation_ms,
    )


def evaluate_feasibility(
    metrics: Optional[LinkMetrics],
    *,
    source_active: bool,
    destination_active: bool,
    source_failed: bool,
    destination_failed: bool,
    operational_range_m: float,
    hard_outage_distance_m: float,
    min_snr_db: float,
    min_capacity_mbps: float,
    min_sinr_db: Optional[float] = None,
    metric_ttl_s: float = 2.0,
) -> FeasibilityDecision:
    predicates: list[GatePredicate] = []

    predicates.append(GatePredicate("source_active", source_active, source_active, True))
    predicates.append(GatePredicate("destination_active", destination_active, destination_active, True))
    predicates.append(GatePredicate("source_not_failed", not source_failed, source_failed, False))
    predicates.append(GatePredicate("destination_not_failed", not destination_failed, destination_failed, False))

    if not source_active:
        return FeasibilityDecision(False, GateReason.SOURCE_INACTIVE, predicates)
    if not destination_active:
        return FeasibilityDecision(False, GateReason.DESTINATION_INACTIVE, predicates)
    if source_failed:
        return FeasibilityDecision(False, GateReason.SOURCE_FAILED, predicates)
    if destination_failed:
        return FeasibilityDecision(False, GateReason.DESTINATION_FAILED, predicates)
    if metrics is None:
        predicates.append(GatePredicate("link_metric_available", False, None, "available"))
        return FeasibilityDecision(False, GateReason.LINK_SERVICE_UNAVAILABLE, predicates)

    age_s = metrics.age_s
    fresh = age_s <= metric_ttl_s
    predicates.append(GatePredicate("metric_fresh", fresh, age_s, metric_ttl_s, metric_ttl_s - age_s, "s"))
    if not fresh:
        return FeasibilityDecision(False, GateReason.STALE_LINK_METRIC, predicates, metric_age_s=age_s)

    within_hard = metrics.distance_m < hard_outage_distance_m
    predicates.append(
        GatePredicate(
            "hard_outage_distance",
            within_hard,
            metrics.distance_m,
            hard_outage_distance_m,
            hard_outage_distance_m - metrics.distance_m,
            "m",
        )
    )
    if not within_hard:
        return FeasibilityDecision(False, GateReason.HARD_OUTAGE_DISTANCE, predicates, metric_age_s=age_s)

    within_operational = metrics.distance_m <= operational_range_m
    predicates.append(
        GatePredicate(
            "operational_range",
            within_operational,
            metrics.distance_m,
            operational_range_m,
            operational_range_m - metrics.distance_m,
            "m",
        )
    )
    if not within_operational:
        return FeasibilityDecision(False, GateReason.OUT_OF_RANGE, predicates, metric_age_s=age_s)

    snr_ok = metrics.snr_db >= min_snr_db
    predicates.append(GatePredicate("snr", snr_ok, metrics.snr_db, min_snr_db, metrics.snr_db - min_snr_db, "dB"))
    if not snr_ok:
        return FeasibilityDecision(False, GateReason.SNR_BELOW_THRESHOLD, predicates, metric_age_s=age_s)

    if min_sinr_db is not None and metrics.sinr_db is not None:
        sinr_ok = metrics.sinr_db >= min_sinr_db
        predicates.append(GatePredicate("sinr", sinr_ok, metrics.sinr_db, min_sinr_db, metrics.sinr_db - min_sinr_db, "dB"))
        if not sinr_ok:
            return FeasibilityDecision(False, GateReason.SINR_BELOW_THRESHOLD, predicates, metric_age_s=age_s)

    capacity_ok = metrics.capacity_mbps >= min_capacity_mbps
    predicates.append(
        GatePredicate(
            "capacity",
            capacity_ok,
            metrics.capacity_mbps,
            min_capacity_mbps,
            metrics.capacity_mbps - min_capacity_mbps,
            "Mbit/s",
        )
    )
    if not capacity_ok:
        return FeasibilityDecision(False, GateReason.CAPACITY_BELOW_THRESHOLD, predicates, metric_age_s=age_s)

    return FeasibilityDecision(True, GateReason.FEASIBLE, predicates, metric_age_s=age_s)


def evaluate_mapping(payload: Mapping[str, Any], thresholds: Mapping[str, Any]) -> Dict[str, Any]:
    request = LinkRequest.from_mapping(payload)
    metrics = compute_analytical_link(request)
    decision = evaluate_feasibility(
        metrics,
        source_active=bool(payload.get("source_active", True)),
        destination_active=bool(payload.get("destination_active", True)),
        source_failed=bool(payload.get("source_failed", False)),
        destination_failed=bool(payload.get("destination_failed", False)),
        operational_range_m=float(thresholds.get("operational_range_m", 90.0)),
        hard_outage_distance_m=float(thresholds.get("hard_outage_distance_m", 220.0)),
        min_snr_db=float(thresholds.get("min_snr_db", 3.0)),
        min_sinr_db=float(thresholds.get("min_sinr_db", thresholds.get("min_snr_db", 3.0))),
        min_capacity_mbps=float(thresholds.get("min_capacity_mbps", 1.0)),
        metric_ttl_s=float(thresholds.get("metric_ttl_s", 2.0)),
    )
    return {"metrics": metrics.as_dict(), "decision": decision.as_dict()}


def evaluate_experiment_topology_preview(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Evaluate every configured topology edge with an explicitly labelled preview model.

    This helper is used by editors before a live runtime exists. It never labels
    its output LIVE and never proves that a deployed route is operational. A
    runtime route still requires fresh Sionna/ROS metrics and participant ACKs.
    """
    from .topology import branches_to_edges, normalize_manual_edges

    topology = config.get("topology", {}) if isinstance(config.get("topology"), Mapping) else {}
    swarm = config.get("swarm", {}) if isinstance(config.get("swarm"), Mapping) else {}
    communication = config.get("communication", {}) if isinstance(config.get("communication"), Mapping) else {}
    antennas = config.get("antennas", {}) if isinstance(config.get("antennas"), Mapping) else {}
    station = config.get("station", {}) if isinstance(config.get("station"), Mapping) else {}
    definitions = {str(item.get("id")): item for item in antennas.get("definitions", []) if isinstance(item, Mapping)}
    assignments = antennas.get("assignments", {}) if isinstance(antennas.get("assignments"), Mapping) else {}
    entities: Dict[str, Mapping[str, Any]] = {str(station.get("id", "station")): station}
    for item in swarm.get("drones", []):
        if isinstance(item, Mapping):
            entities[str(item.get("id"))] = item

    if str(topology.get("mode", "chain")) == "manual" and topology.get("manual_edges"):
        edges = normalize_manual_edges(topology.get("manual_edges"))
    else:
        edges = branches_to_edges(topology.get("branches", []), str(topology.get("source", "station")))

    configured_model = str(communication.get("model", "free_space"))
    analytical_models = {"free_space", "log_distance", "stochastic_shadowing", "probabilistic_air_to_ground", "sionna_analytical"}
    preview_model = configured_model if configured_model in analytical_models else str(communication.get("fallback_model", "free_space"))
    fallback_used = preview_model != configured_model
    records = []
    feasibility: Dict[tuple[str, str], bool] = {}
    for src, dst in edges:
        source = entities.get(src)
        destination = entities.get(dst)
        if source is None or destination is None:
            records.append({"src": src, "dst": dst, "feasible": False, "gate_reason": "MISSING_ENDPOINT", "source": "PREVIEW"})
            feasibility[(src, dst)] = False
            continue
        tx_antenna_id = str(assignments.get(src, source.get("antenna_id", "")))
        rx_antenna_id = str(assignments.get(dst, destination.get("antenna_id", "")))
        tx_antenna = definitions.get(tx_antenna_id, {})
        rx_antenna = definitions.get(rx_antenna_id, {})
        request = LinkRequest(
            src=src,
            dst=dst,
            tx_position=source.get("position", [0.0, 0.0, 0.0]),
            rx_position=destination.get("position", [0.0, 0.0, 0.0]),
            frequency_hz=float(communication.get("carrier_frequency_hz", 3.5e9)),
            bandwidth_hz=float(communication.get("bandwidth_hz", 20e6)),
            tx_power_dbm=float(communication.get("tx_power_dbm", 23.0)),
            receiver_noise_figure_db=float(communication.get("receiver_noise_figure_db", 7.0)),
            implementation_loss_db=float(communication.get("implementation_loss_db", 2.0)),
            tx_gain_dbi=float(tx_antenna.get("gain_dbi", 0.0)),
            rx_gain_dbi=float(rx_antenna.get("gain_dbi", 0.0)),
            tx_cable_loss_db=float(tx_antenna.get("cable_loss_db", 0.0)),
            rx_cable_loss_db=float(rx_antenna.get("cable_loss_db", 0.0)),
            interference_margin_db=float(communication.get("interference_margin_db", 0.0)),
            path_loss_exponent=float(communication.get("path_loss_exponent", 2.0)),
            shadowing_sigma_db=float(communication.get("shadowing_sigma_db", 0.0)),
            seed=int(config.get("experiment", {}).get("seed", 0)),
            model=preview_model,
            spectral_efficiency_factor=float(communication.get("spectral_efficiency_factor", 0.75)),
        )
        try:
            metrics = compute_analytical_link(request)
            decision = evaluate_feasibility(
                metrics,
                source_active=bool(source.get("active", True)),
                destination_active=bool(destination.get("active", True)),
                source_failed=bool(source.get("failed", False)),
                destination_failed=bool(destination.get("failed", False)),
                operational_range_m=float(communication.get("operational_range_m", 90.0)),
                hard_outage_distance_m=float(communication.get("hard_outage_distance_m", 220.0)),
                min_snr_db=float(communication.get("min_snr_db", 3.0)),
                min_sinr_db=float(communication.get("min_sinr_db", communication.get("min_snr_db", 3.0))),
                min_capacity_mbps=float(communication.get("min_capacity_mbps", 1.0)),
                metric_ttl_s=max(2.0, float(communication.get("metric_ttl_s", 2.0))),
            )
            record = {**metrics.as_dict(), **decision.as_dict(), "src": src, "dst": dst}
            record.update({
                "feasible": bool(decision.feasible),
                "gate_reason": decision.reason.value,
                "source": "PREVIEW",
                "configured_model": configured_model,
                "preview_model": preview_model,
                "fallback_used": fallback_used,
                "tx_antenna": tx_antenna_id,
                "rx_antenna": rx_antenna_id,
            })
        except Exception as exc:
            record = {
                "src": src,
                "dst": dst,
                "feasible": False,
                "gate_reason": "PREVIEW_MODEL_UNAVAILABLE",
                "source": "UNAVAILABLE",
                "configured_model": configured_model,
                "preview_model": preview_model,
                "fallback_used": fallback_used,
                "error": str(exc),
            }
        records.append(record)
        feasibility[(src, dst)] = bool(record.get("feasible"))
    return {
        "ok": all(record.get("source") != "UNAVAILABLE" for record in records),
        "source": "PREVIEW",
        "configured_model": configured_model,
        "preview_model": preview_model,
        "fallback_used": fallback_used,
        "links": records,
        "feasibility": feasibility,
        "all_feasible": bool(records) and all(record.get("feasible") for record in records),
        "warning": "Editor preview only. Operational status requires fresh live metrics and matching ROS, Sionna, and Isaac revision acknowledgements.",
    }
