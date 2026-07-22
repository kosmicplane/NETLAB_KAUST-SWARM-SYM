import unittest

from netlab.config import default_experiment
from netlab.link import evaluate_experiment_topology_preview


class TopologyLinkPreviewTests(unittest.TestCase):
    def test_preview_is_explicit_and_covers_every_chain_edge(self):
        config = default_experiment()
        preview = evaluate_experiment_topology_preview(config)
        self.assertEqual(preview["source"], "PREVIEW")
        self.assertEqual(len(preview["links"]), config["swarm"]["relay_count"])
        self.assertTrue(all(link["source"] == "PREVIEW" for link in preview["links"]))
        self.assertTrue(all("gate_reason" in link for link in preview["links"]))
        self.assertTrue(preview["all_feasible"])

    def test_preview_blocks_failed_endpoint(self):
        config = default_experiment()
        config["swarm"]["drones"][0]["failed"] = True
        preview = evaluate_experiment_topology_preview(config)
        first = preview["links"][0]
        self.assertFalse(first["feasible"])
        self.assertEqual(first["gate_reason"], "DESTINATION_FAILED")


if __name__ == "__main__":
    unittest.main()
