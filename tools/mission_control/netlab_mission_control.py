#!/usr/bin/env python3
"""Compatibility entry point for the modular NETLAB Mission Control server.

New code lives under apps/mission_control and netlab. This wrapper preserves the
historical command used by deployment scripts while avoiding a second backend.
"""
from __future__ import annotations

import argparse
import compileall
import json
import os
import sys
from pathlib import Path


def root_path() -> Path:
    return Path(os.environ.get("NETLAB_ROOT", Path(__file__).resolve().parents[2])).resolve()


def self_test(root: Path) -> dict:
    required = [
        root / "apps" / "mission_control" / "backend" / "server.py",
        root / "apps" / "mission_control" / "frontend" / "index.html",
        root / "netlab" / "orchestrator.py",
        root / "netlab" / "link.py",
        root / "scripts" / "netlab",
        root / "Docker" / "compose" / "docker-compose.yml",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    compiled = compileall.compile_dir(str(root / "netlab"), quiet=1) and compileall.compile_dir(str(root / "apps"), quiet=1)
    from netlab.config import default_experiment, validate_experiment
    from netlab.link import LinkRequest, compute_analytical_link, evaluate_feasibility
    config = default_experiment()
    validation = validate_experiment(config, strict=False)
    metric = compute_analytical_link(LinkRequest(src="station", dst="drone_1", tx_position=[0,0,1.5], rx_position=[28,0,28], frequency_hz=3.5e9, bandwidth_hz=20e6, tx_power_dbm=23))
    gate = evaluate_feasibility(metric, source_active=True, destination_active=True, source_failed=False, destination_failed=False, operational_range_m=90, hard_outage_distance_m=220, min_snr_db=3, min_sinr_db=3, min_capacity_mbps=1)
    return {
        "ok": not missing and compiled and validation["ok"] and gate.feasible,
        "missing": missing,
        "python_compile": compiled,
        "default_config_valid": validation["ok"],
        "reference_gate_feasible": gate.feasible,
        "reference_gate_reason": gate.reason.value,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("NETLAB_MISSION_CONTROL_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("NETLAB_MISSION_CONTROL_PORT", "8765")))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    root = root_path()
    sys.path.insert(0, str(root))
    if args.self_test:
        result = self_test(root)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1
    from apps.mission_control.backend.server import serve
    serve(root=root, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
