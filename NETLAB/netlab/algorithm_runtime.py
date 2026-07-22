"""Researcher Algorithm Runtime and benchmark registry.

This module provides one operational path for built-in and researcher-defined
algorithms. It validates packages, executes hooks in isolated workers, applies
the NETLAB safety/feasibility shield, writes reproducible evidence, and emits a
selection contract consumed by the ROS 2 packet/swarm runtime.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from .algorithm_contracts import (
    ALGORITHM_API_VERSION,
    AlgorithmAction,
    AlgorithmContractError,
    AlgorithmManifest,
    AlgorithmObservation,
    canonical_json_hash,
    load_manifest,
    package_hash,
)
from .config import load_experiment
from .io import atomic_write_json, ensure_shared_directory
from .safety_shield import apply_safety_shield
from .state import read_json


@dataclass(frozen=True)
class AlgorithmPackage:
    manifest: AlgorithmManifest
    package_dir: Path
    manifest_path: Path
    entrypoint: Path
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "package_dir": str(self.package_dir),
            "manifest_path": str(self.manifest_path),
            "entrypoint": str(self.entrypoint),
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class AlgorithmRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.plugins_root = self.root / "plugins"

    def _package(self, manifest_path: Path) -> AlgorithmPackage:
        errors: list[str] = []
        warnings: list[str] = []
        try:
            manifest = load_manifest(manifest_path)
        except Exception as exc:
            placeholder = AlgorithmManifest(
                algorithm_id=manifest_path.parent.name.lower().replace("-", "_"),
                name=manifest_path.parent.name,
                version="0.0.0",
                api_version=ALGORITHM_API_VERSION,
                category="controller",
                entrypoint="algorithm.py",
                package_path=str(manifest_path.parent),
            )
            return AlgorithmPackage(placeholder, manifest_path.parent, manifest_path, manifest_path.parent / "algorithm.py", False, (str(exc),))
        errors.extend(manifest.validate())
        entrypoint = (manifest_path.parent / manifest.entrypoint).resolve()
        try:
            entrypoint.relative_to(manifest_path.parent.resolve())
        except ValueError:
            errors.append("entrypoint escapes the algorithm package directory.")
        if manifest.execution_mode in {"isolated_python", "pettingzoo_parallel"}:
            if not entrypoint.is_file():
                errors.append(f"entrypoint does not exist: {entrypoint.name}.")
            else:
                try:
                    tree = ast.parse(entrypoint.read_text(encoding="utf-8"), filename=str(entrypoint))
                    hooks = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
                    if "step" not in hooks and "plan_positions" not in hooks:
                        errors.append("entrypoint must define step(snapshot, parameters) or plan_positions(context).")
                    forbidden = {"eval", "exec", "compile", "__import__"}
                    used = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
                    if forbidden & used:
                        warnings.append(f"entrypoint uses high-risk builtins: {sorted(forbidden & used)}.")
                except Exception as exc:
                    errors.append(f"entrypoint syntax error: {exc}")
        if manifest.execution_mode == "replay":
            replay_path = manifest_path.parent / str(manifest.action_schema.get("replay_file", "actions.jsonl"))
            if not replay_path.is_file():
                errors.append("replay mode requires the configured actions JSONL file.")
        return AlgorithmPackage(manifest, manifest_path.parent, manifest_path, entrypoint, not errors, tuple(errors), tuple(warnings))

    def discover(self) -> list[AlgorithmPackage]:
        if not self.plugins_root.exists():
            return []
        packages = [self._package(path) for path in sorted(self.plugins_root.rglob("manifest.json"))]
        unique: Dict[str, AlgorithmPackage] = {}
        for package in packages:
            current = unique.get(package.manifest.algorithm_id)
            if current is None or (package.valid and not current.valid):
                unique[package.manifest.algorithm_id] = package
        return sorted(unique.values(), key=lambda item: (item.manifest.category, item.manifest.name.lower()))

    def get(self, algorithm_id: str) -> AlgorithmPackage:
        for package in self.discover():
            if package.manifest.algorithm_id == algorithm_id:
                return package
        raise KeyError(f"Unknown algorithm {algorithm_id!r}")

    def summary(self) -> Dict[str, Any]:
        packages = self.discover()
        return {
            "ok": all(package.valid for package in packages),
            "api_version": ALGORITHM_API_VERSION,
            "count": len(packages),
            "valid_count": sum(package.valid for package in packages),
            "categories": sorted({package.manifest.category for package in packages}),
            "algorithms": [package.to_dict() for package in packages],
        }

    def create_project(self, algorithm_id: str, *, name: str = "", category: str = "controller") -> AlgorithmPackage:
        if not algorithm_id or not algorithm_id.replace("_", "").isalnum() or not algorithm_id[0].isalpha():
            raise AlgorithmContractError("algorithm_id must be lower_snake_case.")
        target = (self.plugins_root / "researcher" / algorithm_id).resolve()
        target.relative_to(self.plugins_root.resolve())
        if target.exists():
            raise FileExistsError(f"Algorithm package already exists: {algorithm_id}")
        target.mkdir(parents=True)
        manifest = {
            "algorithm_id": algorithm_id,
            "name": name or algorithm_id.replace("_", " ").title(),
            "version": "0.1.0",
            "api_version": ALGORITHM_API_VERSION,
            "category": category,
            "entrypoint": "algorithm.py",
            "execution_mode": "isolated_python",
            "author": "Researcher",
            "organization": "",
            "license": "Research use",
            "description": "Researcher-defined NETLAB algorithm.",
            "supported_fidelity_profiles": ["F1_ANALYTICAL", "F2_STOCHASTIC"],
            "resource_budget": {"timeout_s": 0.25, "memory_mb": 256, "cpu_cores": 1, "output_kb": 256, "network_policy": "deny"},
            "parameter_schema": {
                "type": "object",
                "properties": {
                    "spacing_m": {"type": "number", "minimum": 5, "maximum": 200, "default": 28},
                    "altitude_m": {"type": "number", "minimum": 10, "maximum": 120, "default": 30},
                },
                "additionalProperties": False,
            },
            "observation_schema": {"type": "object", "required": ["uavs", "topology", "links", "constraints"]},
            "action_schema": {"type": "object", "properties": {"desired_positions": {"type": "object"}}},
            "deterministic_seed": True,
            "safety_fallback": "hold_position",
            "assumptions": ["ENU local frame", "NETLAB safety and feasibility shield remains authoritative"],
            "validity_domain": "Research controller example for local UAV relay formations.",
            "known_limitations": ["This template does not include a numerical optimizer."],
        }
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        (target / "algorithm.py").write_text(
            '''"""Minimal researcher algorithm. Only step() is researcher-owned."""\n\ndef step(snapshot, parameters):\n    spacing = float(parameters.get("spacing_m", 28.0))\n    altitude = float(parameters.get("altitude_m", 30.0))\n    active = [item for item in snapshot.get("uavs", []) if item.get("active", True) and not item.get("failed", False)]\n    desired = {item["id"]: [spacing * (index + 1), 0.0, altitude] for index, item in enumerate(active)}\n    return {\n        "coordinate_frame": "ENU",\n        "desired_positions": desired,\n        "objective_value": 0.0,\n        "constraint_residuals": {},\n        "termination_reason": "deterministic_template",\n    }\n''',
            encoding="utf-8",
        )
        (target / "test_algorithm.py").write_text(
            '''from algorithm import step\n\ndef test_step():\n    snapshot={"uavs":[{"id":"drone_1","active":True,"failed":False}]}\n    result=step(snapshot,{"spacing_m":20,"altitude_m":30})\n    assert result["desired_positions"]["drone_1"] == [20.0,0.0,30.0]\n''',
            encoding="utf-8",
        )
        return self._package(target / "manifest.json")


class AlgorithmRuntime:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.registry = AlgorithmRegistry(self.root)
        self.results_dir = ensure_shared_directory(self.root / "Docker" / "workspace" / "results" / "algorithms")
        self.selection_path = self.root / "Docker" / "workspace" / "results" / "snaas_active_algorithm.json"
        self.config_path = self.root / "Docker" / "workspace" / "shared" / "snaas_relay_config.json"
        self.status_path = self.root / "Docker" / "workspace" / "results" / "snaas_relay_latest_status.json"
        self.runtime_state_path = self.root / "Docker" / "workspace" / "results" / "netlab_runtime_state.json"

    def _invoke_python(
        self,
        package: AlgorithmPackage,
        hook: str,
        observation: Mapping[str, Any],
        parameters: Mapping[str, Any],
    ) -> Dict[str, Any]:
        manifest = package.manifest
        request = {
            "package_root": str(package.package_dir),
            "entrypoint": str(package.entrypoint),
            "hook": hook,
            "observation": dict(observation),
            "parameters": dict(parameters),
            "timeout_s": manifest.resource_budget.timeout_s,
            "memory_mb": manifest.resource_budget.memory_mb,
            "output_kb": manifest.resource_budget.output_kb,
        }
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.root) + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "netlab.algorithm_worker"],
                input=json.dumps(request, separators=(",", ":"), ensure_ascii=False, allow_nan=False),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.root),
                env=environment,
                timeout=manifest.resource_budget.timeout_s + 3.0,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": {"code": "ALGORITHM_WORKER_TIMEOUT", "message": "The isolated worker did not terminate."}, "duration_s": time.perf_counter() - started}
        duration = time.perf_counter() - started
        try:
            result = json.loads(completed.stdout or "{}")
        except json.JSONDecodeError:
            return {
                "ok": False,
                "error": {"code": "ALGORITHM_WORKER_PROTOCOL", "message": "Worker returned invalid JSON."},
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
                "returncode": completed.returncode,
                "duration_s": duration,
            }
        result["duration_s"] = duration
        result["returncode"] = completed.returncode
        if completed.stderr:
            result["stderr"] = completed.stderr[-4000:]
        return result

    def _invoke_replay(self, package: AlgorithmPackage, observation: Mapping[str, Any]) -> Dict[str, Any]:
        path = package.package_dir / str(package.manifest.action_schema.get("replay_file", "actions.jsonl"))
        sequence = int(observation.get("sequence", 0))
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not records:
            return {"ok": False, "error": {"code": "REPLAY_EMPTY", "message": "Replay file contains no actions."}}
        return {"ok": True, "result": records[min(sequence, len(records) - 1)], "duration_s": 0.0}

    def _invoke_oci(self, package: AlgorithmPackage, observation: Mapping[str, Any], parameters: Mapping[str, Any]) -> Dict[str, Any]:
        image = str(package.manifest.action_schema.get("container_image", ""))
        if not image:
            return {"ok": False, "error": {"code": "OCI_IMAGE_MISSING", "message": "Container algorithm manifest has no container_image."}}
        if shutil.which("docker") is None:
            return {"ok": False, "error": {"code": "DOCKER_UNAVAILABLE", "message": "Docker is required for OCI algorithm execution."}}
        payload = json.dumps({"observation": observation, "parameters": parameters}, separators=(",", ":"), allow_nan=False)
        command = [
            "docker", "run", "--rm", "--network", "none", "--read-only",
            "--memory", f"{package.manifest.resource_budget.memory_mb}m",
            "--cpus", str(package.manifest.resource_budget.cpu_cores),
            "--pids-limit", "64", "--security-opt", "no-new-privileges",
            image,
        ]
        started = time.perf_counter()
        try:
            completed = subprocess.run(command, input=payload, text=True, capture_output=True, timeout=package.manifest.resource_budget.timeout_s + 5, check=False)
            value = json.loads(completed.stdout or "{}")
            return {"ok": completed.returncode == 0, "result": value if completed.returncode == 0 else None, "stderr": completed.stderr[-4000:], "duration_s": time.perf_counter() - started}
        except Exception as exc:
            return {"ok": False, "error": {"code": "OCI_EXECUTION_FAILED", "message": str(exc)}, "duration_s": time.perf_counter() - started}

    def invoke(
        self,
        algorithm_id: str,
        observation: Mapping[str, Any],
        parameters: Optional[Mapping[str, Any]] = None,
        *,
        hook: str = "step",
    ) -> Dict[str, Any]:
        package = self.registry.get(algorithm_id)
        if not package.valid:
            return {"ok": False, "error": {"code": "ALGORITHM_INVALID", "message": "Algorithm package is invalid.", "details": list(package.errors)}}
        mode = package.manifest.execution_mode
        params = dict(parameters or {})
        if mode in {"isolated_python", "pettingzoo_parallel"}:
            return self._invoke_python(package, hook, observation, params)
        if mode == "replay":
            return self._invoke_replay(package, observation)
        if mode == "oci_container":
            return self._invoke_oci(package, observation, params)
        if mode == "external_ros2":
            return {
                "ok": True,
                "pending_external_ros2": True,
                "result": {
                    "algorithm_id": algorithm_id,
                    "observation_hash": canonical_json_hash(observation),
                    "required_ros_interfaces": list(package.manifest.required_ros_interfaces),
                },
                "duration_s": 0.0,
            }
        return {"ok": False, "error": {"code": "EXECUTION_MODE_UNSUPPORTED", "message": mode}}

    def build_observation(
        self,
        *,
        config: Optional[Mapping[str, Any]] = None,
        status: Optional[Mapping[str, Any]] = None,
        revision_id: str = "",
        sequence: int = 0,
    ) -> Dict[str, Any]:
        cfg = dict(config or load_experiment(self.config_path))
        runtime = dict(status or read_json(self.status_path, {}) or {})
        state = read_json(self.runtime_state_path, {}) or {}
        drones = cfg.get("swarm", {}).get("drones", [])
        current_positions = runtime.get("drone_positions", {}) if isinstance(runtime.get("drone_positions"), Mapping) else {}
        uavs: list[Dict[str, Any]] = []
        for item in drones:
            if not isinstance(item, Mapping):
                continue
            uav = dict(item)
            index = str(item.get("index", ""))
            uav_id = str(item.get("id", f"drone_{index}"))
            position = current_positions.get(uav_id, current_positions.get(index, item.get("position", [0, 0, 0])))
            uav.update(
                {
                    "id": uav_id,
                    "desired_position": item.get("position", [0, 0, 0]),
                    "commanded_position": runtime.get("desired_positions", {}).get(uav_id, item.get("position", [0, 0, 0])) if isinstance(runtime.get("desired_positions"), Mapping) else item.get("position", [0, 0, 0]),
                    "simulated_position": position,
                    "measured_position": position,
                    "rendered_position": position,
                    "failed": bool(item.get("failed", False) or int(item.get("index", -1)) in runtime.get("failed_indices", [])),
                }
            )
            uavs.append(uav)
        links = runtime.get("link_metrics", runtime.get("links", []))
        if isinstance(links, Mapping):
            links = list(links.values())
        observation = AlgorithmObservation(
            experiment_id=str(cfg.get("experiment", {}).get("id", "")),
            run_id=str(state.get("run_id", "")),
            revision_id=revision_id or str(state.get("committed_revision_id") or state.get("desired_revision_id") or "offline-draft"),
            seed=int(cfg.get("experiment", {}).get("seed", 0)),
            wall_time_s=time.time(),
            simulation_time_s=float(runtime.get("simulation_time_s", 0.0)),
            step_s=float(cfg.get("clock", {}).get("control_step_s", 0.1)),
            real_time_factor=float(runtime.get("real_time_factor", 0.0)),
            uavs=uavs,
            ground_entities=[dict(cfg.get("station", {}))] + [dict(item) for item in cfg.get("world", {}).get("ground_users", []) if isinstance(item, Mapping)],
            topology=dict(cfg.get("topology", {})),
            links=[dict(item) for item in links if isinstance(item, Mapping)],
            packets=dict(runtime.get("packet", runtime.get("packet_state", {}))) if isinstance(runtime.get("packet", runtime.get("packet_state", {})), Mapping) else {},
            flows=[dict(item) for item in cfg.get("traffic", {}).get("flows", []) if isinstance(item, Mapping)],
            world=dict(cfg.get("world", {})),
            antennas=dict(cfg.get("antennas", {})),
            failures=[dict(item) for item in cfg.get("failures", {}).get("schedule", []) if isinstance(item, Mapping)],
            recovery=dict(runtime.get("recovery", {})) if isinstance(runtime.get("recovery", {}), Mapping) else {},
            service_requirements={"traffic": cfg.get("traffic", {}), "communication": cfg.get("communication", {})},
            constraints={
                "service_region": cfg.get("service_region", {}),
                "max_horizontal_speed_mps": cfg.get("swarm", {}).get("max_horizontal_speed_mps", 12.0),
                "max_vertical_speed_mps": cfg.get("swarm", {}).get("max_vertical_speed_mps", 4.0),
                "max_acceleration_mps2": cfg.get("swarm", {}).get("max_acceleration_mps2", 5.0),
                "max_jerk_mps3": cfg.get("swarm", {}).get("max_jerk_mps3", 8.0),
                "minimum_separation_m": cfg.get("swarm", {}).get("minimum_separation_m", 4.0),
            },
            uncertainty=dict(runtime.get("uncertainty", {})) if isinstance(runtime.get("uncertainty", {}), Mapping) else {},
        ).to_dict()
        observation["sequence"] = int(sequence)
        observation["observation_hash"] = canonical_json_hash(observation)
        return observation

    def dry_run(
        self,
        algorithm_id: str,
        *,
        parameters: Optional[Mapping[str, Any]] = None,
        observation: Optional[Mapping[str, Any]] = None,
        negative_test: bool = False,
    ) -> Dict[str, Any]:
        package = self.registry.get(algorithm_id)
        snapshot = dict(observation or self.build_observation())
        invocation = self.invoke(algorithm_id, snapshot, parameters or {})
        run_id = f"dry-{uuid.uuid4()}"
        evidence_dir = ensure_shared_directory(self.results_dir / run_id)
        result: Dict[str, Any] = {
            "ok": False,
            "run_id": run_id,
            "mode": "DRY_RUN",
            "algorithm": package.to_dict(),
            "observation_hash": canonical_json_hash(snapshot),
            "invocation": invocation,
        }
        if invocation.get("ok") and not invocation.get("pending_external_ros2"):
            raw = invocation.get("result")
            if not isinstance(raw, Mapping):
                raw = {"desired_positions": raw} if isinstance(raw, Mapping) else {"metrics": {"result": raw}}
            if negative_test:
                raw = {"desired_positions": {"unknown_uav": [0.0, 0.0, -9999.0]}}
            try:
                action = AlgorithmAction.from_mapping(raw, manifest=package.manifest, source_revision_id=str(snapshot.get("revision_id", "offline-draft")), duration_s=float(invocation.get("duration_s", 0.0)))
                config = load_experiment(self.config_path)
                shield = apply_safety_shield(action, snapshot, config, project=True, require_connectivity=bool(config.get("swarm", {}).get("controller", {}).get("connectivity_preservation", True)))
                result.update({"ok": shield.accepted, "action": action.to_dict(), "shield": shield.to_dict(), "negative_test": negative_test})
                if negative_test:
                    result["ok"] = not shield.accepted
                    result["negative_test_passed"] = not shield.accepted
            except Exception as exc:
                result["error"] = {"code": "ALGORITHM_ACTION_INVALID", "message": str(exc)}
        elif invocation.get("pending_external_ros2"):
            result.update({"ok": True, "pending_external_ros2": True})
        else:
            result["error"] = invocation.get("error", {"code": "ALGORITHM_INVOCATION_FAILED"})
        atomic_write_json(evidence_dir / "observation.json", snapshot)
        atomic_write_json(evidence_dir / "result.json", result)
        atomic_write_json(evidence_dir / "manifest.json", package.manifest.to_dict())
        result["evidence_dir"] = str(evidence_dir)
        return result

    def activate(self, algorithm_id: str, parameters: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
        package = self.registry.get(algorithm_id)
        if not package.valid:
            return {"ok": False, "error": {"code": "ALGORITHM_INVALID", "details": list(package.errors)}}
        selection = {
            "schema_version": "2.0",
            "active": algorithm_id,
            "algorithm_id": algorithm_id,
            "version": package.manifest.version,
            "source_hash": package.manifest.source_hash,
            "execution_mode": package.manifest.execution_mode,
            "package_dir": str(package.package_dir),
            "entrypoint": str(package.entrypoint),
            "parameters": dict(parameters or {}),
            "safety_fallback": package.manifest.safety_fallback,
            "timestamp": time.time(),
            "selection_id": str(uuid.uuid4()),
        }
        atomic_write_json(self.selection_path, selection)
        return {"ok": True, "selection": selection}

    def compare(
        self,
        algorithm_ids: Sequence[str],
        *,
        parameters: Optional[Mapping[str, Mapping[str, Any]]] = None,
        replications: int = 3,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        config = load_experiment(self.config_path)
        base_seed = int(seed if seed is not None else config.get("experiment", {}).get("seed", 0))
        replications = max(1, min(100, int(replications)))
        records: list[Dict[str, Any]] = []
        for algorithm_id in algorithm_ids:
            durations: list[float] = []
            accepted = 0
            fallbacks = 0
            objective_values: list[float] = []
            for replication in range(replications):
                cfg = json.loads(json.dumps(config))
                cfg.setdefault("experiment", {})["seed"] = base_seed + replication
                observation = self.build_observation(config=cfg, sequence=replication)
                result = self.dry_run(algorithm_id, parameters=(parameters or {}).get(algorithm_id, {}), observation=observation)
                durations.append(float(result.get("invocation", {}).get("duration_s", 0.0)))
                accepted += int(bool(result.get("shield", {}).get("accepted")))
                fallbacks += int(bool(result.get("shield", {}).get("fallback_applied")))
                value = result.get("action", {}).get("objective_value")
                if isinstance(value, (int, float)):
                    objective_values.append(float(value))
            durations_sorted = sorted(durations)
            records.append(
                {
                    "algorithm_id": algorithm_id,
                    "replications": replications,
                    "seed_start": base_seed,
                    "accepted_rate": accepted / replications,
                    "fallback_rate": fallbacks / replications,
                    "mean_execution_ms": 1000.0 * sum(durations) / len(durations),
                    "p95_execution_ms": 1000.0 * durations_sorted[max(0, int(0.95 * len(durations_sorted)) - 1)],
                    "mean_objective": sum(objective_values) / len(objective_values) if objective_values else None,
                }
            )
        comparison_id = f"compare-{uuid.uuid4()}"
        output = {"ok": True, "comparison_id": comparison_id, "records": records, "paired_seeds": [base_seed + index for index in range(replications)], "fidelity_profile": config.get("experiment", {}).get("fidelity_profile")}
        atomic_write_json(self.results_dir / f"{comparison_id}.json", output)
        return output

    def export_bundle(self, run_id: str) -> Dict[str, Any]:
        source = (self.results_dir / run_id).resolve()
        source.relative_to(self.results_dir.resolve())
        if not source.is_dir():
            return {"ok": False, "error": {"code": "ALGORITHM_RUN_NOT_FOUND", "message": run_id}}
        target = self.results_dir / f"{run_id}.zip"
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=f"{run_id}/{path.relative_to(source)}")
        return {"ok": True, "path": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "size_bytes": target.stat().st_size}
