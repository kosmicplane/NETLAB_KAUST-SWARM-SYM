import unittest

from netlab.config import default_experiment
from netlab.topology import generate_branches, graph_metrics, validate_config_topology, validate_topology


class TopologyTests(unittest.TestCase):
    def test_generation_modes(self):
        self.assertEqual(generate_branches(6, 1, "chain"), [[1, 2, 3, 4, 5, 6]])
        parallel = generate_branches(6, 3, "parallel")
        self.assertEqual(len(parallel), 3)
        self.assertEqual(sorted(x for branch in parallel for x in branch), list(range(1, 7)))
        self.assertTrue(generate_branches(8, 3, "forest"))

    def test_default_topology_is_structurally_and_physically_valid(self):
        result = validate_config_topology(default_experiment())
        self.assertTrue(result["structurally_valid"], result["errors"])
        self.assertTrue(result["physically_valid"], result["errors"])
        self.assertTrue(result["operational"])

    def test_manual_editor_detects_invalid_graph(self):
        result = validate_topology(
            mode="manual", relay_count=3, branches=[[1, 2, 3]],
            manual_edges=[{"src":"station","dst":"drone_1"},{"src":"drone_1","dst":"missing"}],
            source="station", sinks=["drone_3"],
        )
        codes = {item["code"] for item in result.errors}
        self.assertIn("MISSING_ENDPOINT", codes)
        self.assertIn("UNREACHABLE_SINK", codes)
        self.assertFalse(result.structurally_valid)

    def test_graph_metrics_expose_resilience_structure(self):
        metrics = graph_metrics(["station","drone_1","drone_2"], [["station","drone_1"],["drone_1","drone_2"]], "station", ["drone_2"])
        self.assertIn("drone_1", metrics["articulation_points"])
        self.assertEqual(metrics["connected_components"], 1)

    def test_advanced_graph_metrics_are_exposed(self):
        result = validate_topology(
            mode="forest", relay_count=4, branches=[[1, 2, 4], [1, 3, 4]],
            source="station", sinks=["drone_4"],
        )
        metrics = result.metrics
        self.assertIn("algebraic_connectivity", metrics)
        self.assertIn("node_betweenness", metrics)
        self.assertEqual(metrics["path_diversity"]["drone_4"], 2)
        self.assertGreaterEqual(metrics["edge_disjoint_paths"]["drone_4"], 1)
        self.assertIn("resilience_score", metrics)
        self.assertIn(metrics["node_betweenness_method"], {"exact_brandes", "deterministic_sampled_brandes"})
        self.assertIn(metrics["algebraic_connectivity_method"], {"dense_eigvalsh", "sparse_eigsh", "unavailable"})


if __name__ == "__main__":
    unittest.main()
