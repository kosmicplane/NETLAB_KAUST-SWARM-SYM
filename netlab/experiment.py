"""Experiment lifecycle utilities and deterministic parameter-sweep generation."""
from __future__ import annotations

import copy
import itertools
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .config import deep_merge, save_experiment, validate_experiment


def _set_dotted(target: Dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    cursor: Dict[str, Any] = target
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[parts[-1]] = value


def grid_sweep(base: Mapping[str, Any], parameters: Mapping[str, Sequence[Any]]) -> List[Dict[str, Any]]:
    keys = list(parameters)
    values = [list(parameters[key]) for key in keys]
    runs: List[Dict[str, Any]] = []
    for index, combination in enumerate(itertools.product(*values)):
        config = copy.deepcopy(dict(base))
        for key, value in zip(keys, combination):
            _set_dotted(config, key, value)
        meta = config.setdefault("experiment", {})
        meta["id"] = f"{meta.get('id', 'experiment')}_grid_{index:04d}"
        meta["updated_at"] = time.time()
        runs.append(validate_experiment(config, strict=True)["config"])
    return runs


def random_sweep(
    base: Mapping[str, Any],
    parameters: Mapping[str, Sequence[float]],
    *,
    count: int,
    seed: int,
) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    runs = []
    for index in range(count):
        config = copy.deepcopy(dict(base))
        for key, bounds in parameters.items():
            if len(bounds) != 2:
                raise ValueError(f"random-sweep bounds for {key} must contain [minimum, maximum]")
            _set_dotted(config, key, rng.uniform(float(bounds[0]), float(bounds[1])))
        meta = config.setdefault("experiment", {})
        meta["id"] = f"{meta.get('id', 'experiment')}_random_{index:04d}"
        meta["seed"] = seed + index
        meta["updated_at"] = time.time()
        runs.append(validate_experiment(config, strict=True)["config"])
    return runs


def write_sweep(directory: Path, runs: Iterable[Mapping[str, Any]]) -> List[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, config in enumerate(runs):
        path = directory / f"run_{index:04d}.json"
        save_experiment(path, config, emit_legacy=False)
        paths.append(path)
    return paths
