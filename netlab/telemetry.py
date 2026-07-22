"""Telemetry ingestion, source classification, and research metrics."""
from __future__ import annotations

import csv
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .models import TelemetrySource
from .state import read_json, tail_jsonl


def _coerce(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    try:
        return float(text) if any(ch in text.lower() for ch in (".", "e")) else int(text)
    except Exception:
        return text


def read_csv_tail(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.DictReader(handle))[-limit:]
    return [{key: _coerce(value) for key, value in row.items()} for row in rows]


def percentile(values: Iterable[float], q: float) -> Optional[float]:
    ordered = sorted(float(v) for v in values if math.isfinite(float(v)))
    if not ordered:
        return None
    position = (len(ordered) - 1) * max(0.0, min(1.0, q))
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def describe(values: Iterable[float]) -> Dict[str, Optional[float]]:
    data = [float(v) for v in values if math.isfinite(float(v))]
    if not data:
        return {key: None for key in ("count", "mean", "median", "stddev", "min", "max", "p05", "p50", "p95")}
    return {
        "count": float(len(data)),
        "mean": statistics.fmean(data),
        "median": statistics.median(data),
        "stddev": statistics.pstdev(data) if len(data) > 1 else 0.0,
        "min": min(data),
        "max": max(data),
        "p05": percentile(data, 0.05),
        "p50": percentile(data, 0.50),
        "p95": percentile(data, 0.95),
    }


def classify_source(rows: List[Mapping[str, Any]], latest_status: Mapping[str, Any], *, stale_after_s: float = 5.0) -> Dict[str, Any]:
    if rows:
        timestamps = []
        for row in rows:
            try:
                timestamps.append(float(row.get("timestamp", 0.0)))
            except Exception:
                pass
        latest = max(timestamps, default=0.0)
        age = max(0.0, time.time() - latest) if latest > 0 else None
        if age is not None and age <= stale_after_s:
            return {"source": TelemetrySource.LIVE.value, "age_s": age, "reason": "fresh metric samples"}
        return {"source": TelemetrySource.STALE.value, "age_s": age, "reason": "metric file exists but samples are stale"}
    status_source = str(latest_status.get("source", "")).lower()
    if "preview" in status_source or "snapshot" in status_source:
        return {"source": TelemetrySource.PREVIEW.value, "age_s": None, "reason": "configuration snapshot without live link samples"}
    if latest_status:
        return {"source": TelemetrySource.DEGRADED.value, "age_s": None, "reason": "runtime status exists without link samples"}
    return {"source": TelemetrySource.OFFLINE.value, "age_s": None, "reason": "no runtime status or metric samples"}


def aggregate(rows: List[Mapping[str, Any]], events: List[Mapping[str, Any]]) -> Dict[str, Any]:
    numeric_keys = {
        "snr_db": "snr_db",
        "sinr_db": "sinr_db",
        "capacity_mbps": "capacity_mbps",
        "distance_m": "distance_m",
        "path_loss_db": "path_loss_db",
        "rx_power_dbm": "rx_power_dbm",
        "propagation_delay_ms": "propagation_delay_ms",
        "range_margin_m": "range_margin_m",
        "queue_delay_ms": "queue_delay_ms",
        "total_delay_ms": "total_delay_ms",
        "age_of_information_ms": "age_of_information_ms",
    }
    distributions: Dict[str, Dict[str, Optional[float]]] = {}
    for output_name, key in numeric_keys.items():
        values = []
        for row in rows:
            try:
                values.append(float(row[key]))
            except Exception:
                continue
        distributions[output_name] = describe(values)

    success_tokens = {"true", "1", "feasible", "forwarded", "ok"}
    blocked_tokens = {"false", "0", "blocked", "outage", "paused"}
    feasible = 0
    blocked = 0
    by_branch: Dict[str, Dict[str, int]] = defaultdict(lambda: {"samples": 0, "feasible": 0, "blocked": 0})
    by_reason: Counter[str] = Counter()
    by_link: Counter[str] = Counter()
    for row in rows:
        branch = str(row.get("branch_id", row.get("branch", "unknown")))
        by_branch[branch]["samples"] += 1
        raw = str(row.get("link_ok", row.get("decision", row.get("gate_reason", "")))).lower()
        if raw in success_tokens or "forward" in raw or raw == "feasible":
            feasible += 1
            by_branch[branch]["feasible"] += 1
        elif raw in blocked_tokens or "block" in raw or "outage" in raw:
            blocked += 1
            by_branch[branch]["blocked"] += 1
        reason = str(row.get("gate_reason", row.get("outage_reason", row.get("decision", "UNKNOWN"))))
        by_reason[reason] += 1
        by_link[f"{row.get('src', '?')}->{row.get('dst', '?')}"] += 1

    branch_metrics = {}
    for branch, counts in by_branch.items():
        denominator = counts["feasible"] + counts["blocked"]
        branch_metrics[branch] = {
            **counts,
            "availability_pct": 100.0 * counts["feasible"] / denominator if denominator else None,
        }

    event_types = Counter(str(event.get("event_type", event.get("type", "UNKNOWN"))) for event in events)
    generated = sum(count for name, count in event_types.items() if "CREATED" in name.upper())
    delivered = sum(count for name, count in event_types.items() if "DELIVERED" in name.upper() or "ROUND_TRIP_COMPLETED" in name.upper())
    advanced = sum(count for name, count in event_types.items() if "ADVANCED" in name.upper() or name.upper() == "HOP")
    dropped = sum(count for name, count in event_types.items() if "DROPPED" in name.upper())
    paused = sum(count for name, count in event_types.items() if "PAUSED" in name.upper() or "BLOCKED" in name.upper())
    outage_events = sum(count for name, count in event_types.items() if "OUTAGE" in name.upper() or "CONNECTIVITY_LOST" in name.upper())
    recovery_events = sum(count for name, count in event_types.items() if "RECOVER" in name.upper() or "PROMOT" in name.upper())

    timestamps = []
    for row in rows:
        try:
            value = float(row.get("timestamp", 0.0))
            if value > 0:
                timestamps.append(value)
        except Exception:
            pass
    observation_window_s = max(timestamps) - min(timestamps) if len(timestamps) > 1 else 0.0
    sample_rate_hz = (len(timestamps) - 1) / observation_window_s if observation_window_s > 0 else None

    event_timeline = []
    for event in events[-200:]:
        event_type = str(event.get("event_type", event.get("type", "UNKNOWN")))
        upper = event_type.upper()
        if any(token in upper for token in ("OUTAGE", "FAIL", "RECOVER", "PROMOT", "DELIVER", "ADVANC", "HOP", "REVISION")):
            event_timeline.append({
                "timestamp": event.get("timestamp", event.get("timestamp_wall", event.get("created_at"))),
                "event_type": event_type,
                "branch_id": event.get("branch_id", event.get("branch")),
                "packet_id": event.get("packet_id"),
                "reason": event.get("gate_reason", event.get("outage_reason", event.get("reason", ""))),
                "source_file": event.get("source_file", ""),
            })

    return {
        "samples": len(rows),
        "events": len(events),
        "feasible_samples": feasible,
        "blocked_samples": blocked,
        "link_feasibility_ratio": feasible / max(1, feasible + blocked),
        "packet_delivery_ratio": delivered / max(1, generated),
        "generated_packets": generated,
        "advanced_packets": advanced,
        "delivered_packets": delivered,
        "dropped_packets": dropped,
        "paused_packets": paused,
        "packet_advancement_rate_hz": advanced / observation_window_s if observation_window_s > 0 else None,
        "observation_window_s": observation_window_s,
        "sample_rate_hz": sample_rate_hz,
        "outage_events": outage_events,
        "recovery_events": recovery_events,
        "distributions": distributions,
        "branch_metrics": branch_metrics,
        "gate_reason_distribution": dict(by_reason),
        "event_type_distribution": dict(event_types),
        "event_timeline": event_timeline,
        "top_links": by_link.most_common(20),
    }


def collect(results_dir: Path, *, limit: int = 500, stale_after_s: float = 5.0) -> Dict[str, Any]:
    metric_files = sorted(results_dir.glob("*_link_metrics.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    canonical_metric = results_dir / "snaas_link_metrics.csv"
    if canonical_metric.exists():
        metric_files = [canonical_metric] + [p for p in metric_files if p.resolve() != canonical_metric.resolve()]
    rows: List[Dict[str, Any]] = []
    for path in metric_files[:4]:
        for row in read_csv_tail(path, limit):
            row["source_file"] = path.name
            rows.append(row)
        if len(rows) >= limit:
            break
    rows = rows[-limit:]

    event_files = sorted(results_dir.glob("*_events.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    canonical_event_log = results_dir / "netlab_events.jsonl"
    if canonical_event_log.exists():
        event_files = [canonical_event_log] + [p for p in event_files if p.resolve() != canonical_event_log.resolve()]
    events: List[Dict[str, Any]] = []
    for path in event_files[:4]:
        for event in tail_jsonl(path, 200):
            event["source_file"] = path.name
            events.append(event)
    events = events[-200:]

    latest_status = read_json(results_dir / "snaas_relay_latest_status.json", {}) or {}
    source = classify_source(rows, latest_status, stale_after_s=stale_after_s)
    return {
        "ok": True,
        "source": source,
        "rows": rows,
        "events": events,
        "analytics": aggregate(rows, events),
        "metric_files": [p.name for p in metric_files[:10]],
        "event_files": [p.name for p in event_files[:10]],
        "generated_at": time.time(),
    }


class TelemetryReader:
    """Bounded, file-backed telemetry adapter used by Mission Control.

    The adapter never synthesizes live samples. Empty runtime data remains
    OFFLINE or PREVIEW according to the authoritative status source.
    """

    def __init__(self, root: Path, *, limit: int = 500, stale_after_s: float = 5.0) -> None:
        self.root = root.resolve()
        self.results_dir = self.root / "Docker" / "workspace" / "results"
        self.limit = max(10, int(limit))
        self.stale_after_s = max(0.5, float(stale_after_s))

    def snapshot(self) -> Dict[str, Any]:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        return collect(self.results_dir, limit=self.limit, stale_after_s=self.stale_after_s)
