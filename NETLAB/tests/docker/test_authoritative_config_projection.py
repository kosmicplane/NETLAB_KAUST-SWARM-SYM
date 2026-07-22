import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class AuthoritativeConfigProjectionTests(unittest.TestCase):
    def test_ros_packet_runtime_projects_authoritative_configuration(self):
        source = (ROOT / "Docker/workspace/ros2/src/netlab_swarm_demo/netlab_swarm_demo/snaas_relay_chain.py").read_text(encoding="utf-8")
        self.assertIn("from netlab.config import emit_legacy_config", source)
        self.assertIn('{"experiment", "swarm", "communication", "topology"}', source)

    def test_isaac_scene_projects_authoritative_configuration(self):
        source = (ROOT / "Docker/workspace/isaac/scripts/snaas_relay_scene.py").read_text(encoding="utf-8")
        self.assertIn("from netlab.config import emit_legacy_config", source)
        self.assertIn('{"experiment", "swarm", "communication", "topology"}', source)


if __name__ == "__main__":
    unittest.main()
