import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RosRevisionApplicationContractTests(unittest.TestCase):
    def test_revision_agent_publishes_runtime_configuration_and_waits_for_packet_ack(self):
        source = (ROOT / "Docker/workspace/ros2/netlab_revision_agent.py").read_text(encoding="utf-8")
        self.assertIn("/swarm/control/update_config", source)
        self.assertIn("emit_legacy_config", source)
        self.assertIn("_netlab_revision", source)
        self.assertIn("_observe_packet_ack", source)
        self.assertNotIn('"accepted": True,\n                    "ready": True', source)

    def test_packet_runtime_writes_revision_ack_after_callback_application(self):
        source = (ROOT / "Docker/workspace/ros2/src/netlab_swarm_demo/netlab_swarm_demo/snaas_relay_chain.py").read_text(encoding="utf-8")
        self.assertIn("def _update_config_cb", source)
        self.assertIn("atomic_write_json(self.ros_revision_ack_path", source)
        self.assertIn("applied_hashes", source)


if __name__ == "__main__":
    unittest.main()
