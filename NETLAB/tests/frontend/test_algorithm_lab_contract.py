from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "apps" / "mission_control" / "frontend"


class AlgorithmLabFrontendContractTests(unittest.TestCase):
    def test_algorithm_lab_exposes_complete_researcher_workflow(self) -> None:
        source = (FRONTEND / "modules" / "algorithm_lab.js").read_text(encoding="utf-8")
        required_text = (
            "Create Algorithm Project",
            "Validate Package",
            "Run Deterministic Dry Run",
            "Run Invalid-Output Test",
            "Activate and Synchronize",
            "Compare with Chain Baseline",
            "Paired comparison and exports",
            "Safety and Feasibility Shield",
            "Research algorithm registry",
        )
        for text in required_text:
            self.assertIn(text, source)
        for api_call in (
            "api.algorithms()",
            "api.validateAlgorithm",
            "api.dryRunAlgorithm",
            "api.activateAlgorithm",
            "api.compareAlgorithms",
            "api.exportAlgorithmRun",
        ):
            self.assertIn(api_call, source)

    def test_frontend_api_exposes_algorithm_endpoints(self) -> None:
        source = (FRONTEND / "modules" / "api.js").read_text(encoding="utf-8")
        endpoints = (
            "/api/algorithms",
            "/api/algorithm/source",
            "/api/algorithm/validate",
            "/api/algorithm/dry-run",
            "/api/algorithm/activate",
            "/api/algorithm/compare",
            "/api/algorithm/export",
        )
        for endpoint in endpoints:
            self.assertIn(endpoint, source)

    def test_action_registry_maps_algorithm_actions_to_runtime_participants(self) -> None:
        registry_path = ROOT / "apps" / "mission_control" / "action_registry.json"
        self.assertTrue(registry_path.is_file())
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        actions = {item["id"]: item for item in payload["actions"]}
        required = {
            "algorithm.validate",
            "algorithm.dry_run",
            "algorithm.negative_test",
            "algorithm.activate",
            "algorithm.compare",
            "algorithm.export",
        }
        self.assertTrue(required <= set(actions), required - set(actions))
        for identifier in required:
            action = actions[identifier]
            self.assertTrue(action["frontend_control"])
            self.assertTrue(action["api_route"].startswith("/api/"))
            self.assertTrue(action["backend_operation"])
            self.assertTrue(action["acknowledgement"])
            self.assertTrue(action["automated_test"])
        activate = actions["algorithm.activate"]
        self.assertEqual(set(activate["runtime_participants"]), {"ROS 2", "Sionna", "Isaac Sim"})

    def test_every_declared_button_has_an_action_contract(self) -> None:
        registry = json.loads((ROOT / "apps" / "mission_control" / "action_registry.json").read_text(encoding="utf-8"))
        registered = {item["frontend_control"] for item in registry["actions"]}
        button_ids = set()
        for module in (FRONTEND / "modules").glob("*.js"):
            source = module.read_text(encoding="utf-8")
            button_ids.update(re.findall(r'<button[^>]+id=["\']([^"\']+)', source))
        self.assertEqual(button_ids - registered, set(), sorted(button_ids - registered))



if __name__ == "__main__":
    unittest.main()
