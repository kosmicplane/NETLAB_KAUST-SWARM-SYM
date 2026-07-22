from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from netlab.algorithm_contracts import ALGORITHM_API_VERSION, AlgorithmAction, AlgorithmManifest
from netlab.algorithm_runtime import AlgorithmRegistry, AlgorithmRuntime
from netlab.config import default_experiment
from netlab.marl import NetlabParallelEnv
from netlab.safety_shield import apply_safety_shield

ROOT = Path(__file__).resolve().parents[2]


class ResearcherAlgorithmRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # Let isolated subprocess workers import the exact NETLAB code under test.
        (self.root / "netlab").symlink_to(ROOT / "netlab", target_is_directory=True)
        for algorithm_id in ("researcher_chain_spacing", "connectivity_aware_formation"):
            source = ROOT / "plugins" / "research" / algorithm_id
            target = self.root / "plugins" / "research" / algorithm_id
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        config_path = self.root / "Docker" / "workspace" / "shared" / "snaas_relay_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(default_experiment(), indent=2) + "\n", encoding="utf-8")
        (self.root / "Docker" / "workspace" / "results").mkdir(parents=True, exist_ok=True)
        self.runtime = AlgorithmRuntime(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_registry_discovers_valid_v2_packages(self) -> None:
        summary = self.runtime.registry.summary()
        self.assertEqual(summary["api_version"], ALGORITHM_API_VERSION)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["valid_count"], 2)
        self.assertTrue(summary["ok"])

    def test_isolated_dry_run_and_negative_output_rejection(self) -> None:
        dry = self.runtime.dry_run("researcher_chain_spacing", parameters={"spacing_m": 28.0, "altitude_m": 30.0})
        self.assertTrue(dry["ok"], dry)
        self.assertTrue(dry["shield"]["accepted"])
        self.assertFalse(dry["shield"]["fallback_applied"])
        self.assertIn("desired_positions", dry["action"]["payload"])

        negative = self.runtime.dry_run("researcher_chain_spacing", negative_test=True)
        self.assertTrue(negative["ok"], negative)
        self.assertTrue(negative["negative_test_passed"])
        self.assertFalse(negative["shield"]["accepted"])
        self.assertTrue(negative["shield"]["fallback_applied"])

    def test_paired_seed_comparison_is_reproducible(self) -> None:
        first = self.runtime.compare(
            ["researcher_chain_spacing", "connectivity_aware_formation"],
            replications=2,
            seed=42,
        )
        second = self.runtime.compare(
            ["researcher_chain_spacing", "connectivity_aware_formation"],
            replications=2,
            seed=42,
        )
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(first["paired_seeds"], [42, 43])
        self.assertEqual(first["paired_seeds"], second["paired_seeds"])
        self.assertEqual(
            [record["accepted_rate"] for record in first["records"]],
            [record["accepted_rate"] for record in second["records"]],
        )

    def test_safety_shield_rejects_unknown_entity_and_preserves_fallback(self) -> None:
        config = default_experiment()
        observation = self.runtime.build_observation(config=config)
        manifest = AlgorithmManifest(
            algorithm_id="invalid_target_test",
            name="Invalid Target Test",
            version="1.0.0",
            api_version=ALGORITHM_API_VERSION,
            category="controller",
            entrypoint="algorithm.py",
        )
        action = AlgorithmAction.from_mapping(
            {
                "coordinate_frame": "ENU",
                "desired_positions": {"unknown_uav": [0.0, 0.0, 30.0]},
            },
            manifest=manifest,
            source_revision_id=observation["revision_id"],
            duration_s=0.0,
        )
        decision = apply_safety_shield(action, observation, config)
        self.assertFalse(decision.accepted)
        self.assertTrue(decision.fallback_applied)
        self.assertTrue(any(issue.code == "UNKNOWN_ENTITY" for issue in decision.issues))

    def test_pettingzoo_parallel_contract_uses_same_safety_shield(self) -> None:
        config = default_experiment()
        observation = self.runtime.build_observation(config=config)
        env = NetlabParallelEnv(config, observation, max_steps=2)
        observations, infos = env.reset(seed=123)
        self.assertEqual(set(observations), set(env.agents))
        self.assertTrue(all("action_mask" in item for item in observations.values()))
        actions = {agent: [0.0, 0.0, 0.0] for agent in env.agents}
        next_observations, rewards, terminations, truncations, step_infos = env.step(actions)
        self.assertEqual(set(rewards), set(actions))
        self.assertTrue(all("reward_terms" in value and "shield" in value for value in step_infos.values()))
        self.assertTrue(all(not value for value in terminations.values()))
        self.assertTrue(all(not value for value in truncations.values()))
        self.assertEqual(set(next_observations), set(actions))


class ResearchAlgorithmLibraryTests(unittest.TestCase):
    def test_every_packaged_algorithm_manifest_is_valid(self) -> None:
        registry = AlgorithmRegistry(ROOT)
        packages = registry.discover()
        self.assertGreaterEqual(len(packages), 27)
        invalid = {package.manifest.algorithm_id: list(package.errors) for package in packages if not package.valid}
        self.assertEqual(invalid, {})
        identifiers = {package.manifest.algorithm_id for package in packages}
        required = {
            "researcher_chain_spacing",
            "connectivity_aware_formation",
            "learn_as_you_fly_placement",
            "joint_trajectory_communication_optimizer",
            "rotary_wing_energy_optimizer",
            "graph_connectivity_controller",
            "voronoi_coverage_controller",
            "distributed_flocking_controller",
            "cbf_safety_filter",
            "data_driven_connectivity_controller",
            "mobility_resilient_spectrum_sharing",
            "collaborative_beamforming",
            "aoi_aware_scheduler",
        }
        self.assertTrue(required <= identifiers, required - identifiers)

    def test_every_packaged_algorithm_entrypoint_executes_against_canonical_snapshot(self) -> None:
        import importlib.util

        runtime = AlgorithmRuntime(ROOT)
        observation = runtime.build_observation(config=default_experiment(), revision_id="algorithm-library-test")
        config = default_experiment()
        failures = {}
        for package in runtime.registry.discover():
            if package.manifest.execution_mode not in {"isolated_python", "pettingzoo_parallel"}:
                continue
            try:
                module_name = f"netlab_test_{package.manifest.algorithm_id}"
                spec = importlib.util.spec_from_file_location(module_name, package.entrypoint)
                if spec is None or spec.loader is None:
                    raise RuntimeError("entrypoint could not be loaded")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                step_hook = getattr(module, "step", None)
                plan_hook = getattr(module, "plan_positions", None)
                if not callable(step_hook) and not callable(plan_hook):
                    raise RuntimeError("no step or plan_positions hook")
                properties = package.manifest.parameter_schema.get("properties", {})
                parameters = {
                    name: schema.get("default")
                    for name, schema in properties.items()
                    if isinstance(schema, dict) and "default" in schema
                }
                if callable(step_hook):
                    try:
                        raw = step_hook(observation, parameters)
                    except TypeError:
                        context = dict(observation)
                        context["parameters"] = parameters
                        raw = step_hook(context)
                else:
                    context = dict(observation)
                    context["parameters"] = parameters
                    raw = {"desired_positions": plan_hook(context)}
                if package.manifest.category == "safety_filter" and isinstance(raw, dict) and "payload" not in raw and not any(key in raw for key in ("desired_positions", "desired_velocities", "metrics", "optimization_result")):
                    # Safety filters may return a transparent diagnostic envelope in their reference mode.
                    raw = {"metrics": raw}
                action = AlgorithmAction.from_mapping(
                    raw if isinstance(raw, dict) else {"metrics": {"result": raw}},
                    manifest=package.manifest,
                    source_revision_id=observation["revision_id"],
                    duration_s=0.0,
                )
                errors = action.validate(now_s=action.timestamp_s)
                if errors:
                    raise RuntimeError("; ".join(errors))
                apply_safety_shield(action, observation, config, project=True, require_connectivity=True)
            except Exception as exc:
                failures[package.manifest.algorithm_id] = str(exc)
        self.assertEqual(failures, {})


if __name__ == "__main__":
    unittest.main()
