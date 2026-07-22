import json
import tempfile
import unittest
from pathlib import Path

from netlab.config import configuration_hash, default_experiment, emit_legacy_config, load_experiment, save_experiment, validate_experiment


class ConfigTests(unittest.TestCase):
    def test_default_configuration_is_valid_and_scale_is_separate(self):
        cfg = default_experiment()
        result = validate_experiment(cfg, strict=False)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(cfg["swarm"]["visual_asset_scale"], 0.2)
        self.assertEqual(cfg["visualization"]["visual_asset_scale"], 0.2)
        self.assertNotEqual(cfg["swarm"]["physical_collision_dimensions_m"], [0.2, 0.2, 0.2])

    def test_legacy_round_trip_preserves_authoritative_v6_and_v5_alias(self):
        cfg = default_experiment()
        cfg["swarm"]["controller"]["parameters"] = {"custom_gain": 4.25}
        cfg["world"]["assets"] = [{"id": "scene", "path": "/tmp/scene.usd", "semantic_category": "urban"}]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            emitted = save_experiment(path, cfg, emit_legacy=True)
            self.assertIn("v5", emitted)
            loaded = load_experiment(path)
        self.assertEqual(loaded["swarm"]["controller"]["parameters"]["custom_gain"], 4.25)
        self.assertEqual(loaded["world"]["assets"][0]["id"], "scene")
        self.assertEqual(configuration_hash(loaded), configuration_hash(cfg))

    def test_invalid_count_is_rejected(self):
        cfg = default_experiment()
        cfg["swarm"]["standby_count"] = 99
        result = validate_experiment(cfg, strict=False)
        self.assertFalse(result["ok"])
        self.assertTrue(any(item["code"] == "COUNT_CONSISTENCY" for item in result["errors"]))

    def test_example_scenarios_validate(self):
        root = Path(__file__).resolve().parents[2]
        for path in sorted((root / "scenarios").glob("**/*.json")):
            if path.name.endswith("schema.json"):
                continue
            with self.subTest(path=path.name):
                payload = json.loads(path.read_text())
                result = validate_experiment(payload, strict=False)
                self.assertTrue(result["ok"], result["errors"])

    def test_default_antenna_assignments_and_failure_state_are_self_consistent(self):
        config = default_experiment()
        known = {item["id"] for item in config["antennas"]["definitions"]}
        for entity, antenna_id in config["antennas"]["assignments"].items():
            self.assertIn(antenna_id, known, entity)
        self.assertTrue(all(drone.get("failed") is False for drone in config["swarm"]["drones"]))
        legacy = emit_legacy_config(config)
        self.assertEqual(legacy["failed_indices"], [])


if __name__ == "__main__":
    unittest.main()
