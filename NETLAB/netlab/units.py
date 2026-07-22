"""Unit conversions and coordinate-frame helpers used at API boundaries."""
from __future__ import annotations

import math
from typing import Iterable, Sequence, Tuple

Vec3 = Tuple[float, float, float]


def hz(value: float, unit: str) -> float:
    factors = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}
    key = unit.strip().lower()
    if key not in factors:
        raise ValueError(f"unsupported frequency unit {unit!r}")
    return float(value) * factors[key]


def seconds(value: float, unit: str) -> float:
    factors = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9}
    key = unit.strip().lower()
    if key not in factors:
        raise ValueError(f"unsupported time unit {unit!r}")
    return float(value) * factors[key]


def dbm_to_watts(dbm: float) -> float:
    return 10.0 ** ((float(dbm) - 30.0) / 10.0)


def watts_to_dbm(watts: float) -> float:
    if watts <= 0:
        raise ValueError("watts must be positive")
    return 10.0 * math.log10(float(watts)) + 30.0


def enu_to_ned(position: Sequence[float]) -> Vec3:
    if len(position) != 3:
        raise ValueError("position must contain exactly three coordinates")
    e, n, u = (float(x) for x in position)
    return n, e, -u


def ned_to_enu(position: Sequence[float]) -> Vec3:
    if len(position) != 3:
        raise ValueError("position must contain exactly three coordinates")
    n, e, d = (float(x) for x in position)
    return e, n, -d


def finite_vec3(value: Iterable[float]) -> Vec3:
    values = tuple(float(v) for v in value)
    if len(values) != 3 or not all(math.isfinite(v) for v in values):
        raise ValueError("expected a finite three-element vector")
    return values[0], values[1], values[2]
