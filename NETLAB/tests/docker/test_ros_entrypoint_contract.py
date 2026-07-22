import re
import unittest
from pathlib import Path


class RosEntrypointContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]

    def test_nounset_is_deferred_until_ros_environment_is_sourced(self):
        script = (self.root / "Docker" / "workspace" / "ros2" / "runtime_entrypoint.sh").read_text()
        helper = (self.root / "Docker" / "workspace" / "ros2" / "netlab_ros_env.sh").read_text()
        self.assertIn("netlab_source_ros_environment", script)
        self.assertIn("set +u", helper)
        self.assertLess(script.index("netlab_source_ros_environment"), script.index("set -u"))
        prefix = script[: script.index("netlab_source_ros_environment")]
        self.assertNotRegex(prefix, re.compile(r"(^|\n)\s*set\s+-[^\n]*u"))

    def test_compose_mounts_the_ros_environment_helper(self):
        compose = (self.root / "Docker" / "compose" / "docker-compose.yml").read_text()
        self.assertIn("/workspace/ros2/runtime_entrypoint.sh", compose)
        self.assertTrue((self.root / "Docker" / "workspace" / "ros2" / "netlab_ros_env.sh").exists())


if __name__ == "__main__":
    unittest.main()
