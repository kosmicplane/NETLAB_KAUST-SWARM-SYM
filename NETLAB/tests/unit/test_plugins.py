import tempfile
import unittest
from pathlib import Path

from netlab.plugins import discover, invoke_isolated, validate_position_plan


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.plugins = self.root / "plugins" / "controllers"

    def test_registry_is_valid(self):
        items = discover(self.plugins)
        self.assertGreaterEqual(len(items), 4)
        self.assertTrue(all(item["valid"] for item in items), items)

    def test_isolated_controller_invocation(self):
        plugin = self.plugins / "communication_aware_spacing.py"
        context = {"uav_states": {"drone_1": {"position":[0,0,30]}, "drone_2": {"position":[30,0,30]}}, "parameters": {"target_spacing_m": 25, "altitude_m": 30}}
        result = invoke_isolated(plugin, "plan_positions", context, timeout_s=2.0)
        self.assertTrue(result["ok"], result)
        plan = result["result"]
        normalized = validate_position_plan(plan, known_uav_ids=["drone_1","drone_2"], current_positions={"drone_1":[0,0,30],"drone_2":[30,0,30]}, max_displacement_m=100.0, altitude_bounds_m=[10,120], minimum_separation_m=4.0)
        self.assertEqual(set(normalized), {"drone_1", "drone_2"})

    def test_invalid_position_plan_is_rejected(self):
        with self.assertRaises(Exception):
            validate_position_plan({"unknown":[0,0,20]}, known_uav_ids=["drone_1"], current_positions={"drone_1":[0,0,20]}, max_displacement_m=100.0, altitude_bounds_m=[10,120], minimum_separation_m=4.0)

    def test_v6_research_plugins_are_discoverable(self):
        root = Path(__file__).resolve().parents[2]
        expected = {
            "connectivity_preserving_formation",
            "maximum_bottleneck_routing",
            "latency_aware_routing",
            "energy_aware_trajectory",
            "antenna_orientation_optimizer",
            "monte_carlo_sampler",
        }
        found = {item.get("manifest", {}).get("plugin_id") for item in discover(root / "plugins" / "controllers") if item.get("valid")}
        self.assertTrue(expected.issubset(found), expected - found)


    def test_isolated_worker_enforces_plugin_execution_deadline(self):
        with tempfile.TemporaryDirectory() as td:
            plugin = Path(td) / "slow_plugin.py"
            plugin.write_text(
                "import time\n"
                "def plan_positions(context):\n"
                "    time.sleep(1.0)\n"
                "    return {}\n",
                encoding="utf-8",
            )
            result = invoke_isolated(plugin, "plan_positions", {}, timeout_s=0.05)
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"], "PLUGIN_TIMEOUT")


if __name__ == "__main__":
    unittest.main()
