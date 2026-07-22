"""Deterministic Monte Carlo parameter sampler for experiment design."""
from __future__ import annotations
import random

PLUGIN_MANIFEST = {
    "plugin_id": "monte_carlo_sampler",
    "name": "Monte Carlo Parameter Sampler",
    "version": "1.0.0",
    "api_version": "1.0",
    "description": "Generates reproducible bounded samples for uncertainty and sensitivity studies.",
    "execution_mode": "isolated_worker",
    "timeout_s": 0.25,
    "required_fidelity": "F1_ANALYTICAL",
    "safety_fallback": "no_samples",
    "parameters": {
        "sample_count": {"type": "integer", "default": 20, "minimum": 1, "maximum": 10000},
        "shadowing_sigma_min_db": {"type": "number", "default": 0.0},
        "shadowing_sigma_max_db": {"type": "number", "default": 8.0},
        "wind_min_mps": {"type": "number", "default": 0.0},
        "wind_max_mps": {"type": "number", "default": 12.0},
    },
}


def generate_samples(context):
    parameters = context.get("parameters", {})
    count = max(1, min(10000, int(parameters.get("sample_count", 20))))
    random_generator = random.Random(int(context.get("seed", 0)))
    shadow_min = float(parameters.get("shadowing_sigma_min_db", 0.0))
    shadow_max = float(parameters.get("shadowing_sigma_max_db", 8.0))
    wind_min = float(parameters.get("wind_min_mps", 0.0))
    wind_max = float(parameters.get("wind_max_mps", 12.0))
    return [
        {
            "replication": index + 1,
            "seed": random_generator.randrange(0, 2**31 - 1),
            "communication.shadowing_sigma_db": random_generator.uniform(shadow_min, shadow_max),
            "world.environment.wind_speed_mps": random_generator.uniform(wind_min, wind_max),
        }
        for index in range(count)
    ]
