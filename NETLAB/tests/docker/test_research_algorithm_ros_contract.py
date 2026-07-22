from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ResearchAlgorithmRosContractTests(unittest.TestCase):
    def test_typed_interfaces_are_declared_and_generated(self) -> None:
        package = ROOT / "Docker" / "workspace" / "ros2" / "src" / "netlab_interfaces"
        required = {
            "msg/AlgorithmObservation.msg",
            "msg/AlgorithmAction.msg",
            "msg/AlgorithmStatus.msg",
            "srv/ValidateAlgorithm.srv",
            "action/RunAlgorithm.action",
        }
        for relative in required:
            self.assertTrue((package / relative).is_file(), relative)
        cmake = (package / "CMakeLists.txt").read_text(encoding="utf-8")
        for relative in required:
            self.assertIn(relative, cmake)
        self.assertIn("rosidl_generate_interfaces", cmake)

    def test_algorithm_bridge_uses_typed_ros_contract_and_safety_shield(self) -> None:
        bridge = (ROOT / "Docker" / "workspace" / "ros2" / "src" / "netlab_swarm_demo" / "netlab_swarm_demo" / "algorithm_bridge.py").read_text(encoding="utf-8")
        for symbol in ("AlgorithmObservation", "AlgorithmAction", "AlgorithmStatus", "ValidateAlgorithm"):
            self.assertIn(symbol, bridge)
        self.assertIn("apply_safety_shield", bridge)
        self.assertIn("AlgorithmRuntime", bridge)
        self.assertIn("atomic_write_json", bridge)
        self.assertIn("snaas_algorithm_runtime_heartbeat.json", bridge)

    def test_entrypoint_supervises_revision_agent_bridge_and_packet_runtime(self) -> None:
        entrypoint = (ROOT / "Docker" / "workspace" / "ros2" / "runtime_entrypoint.sh").read_text(encoding="utf-8")
        self.assertIn("netlab_source_ros_environment --base-only", entrypoint)
        self.assertIn("colcon build", entrypoint)
        self.assertIn("netlab_interfaces", entrypoint)
        self.assertIn("algorithm_bridge", entrypoint)
        self.assertIn("revision_agent", entrypoint)
        self.assertIn("snaas_relay_chain", entrypoint)
        self.assertNotRegex(entrypoint, r"source\s+/opt/ros/jazzy/setup\.bash\s*\n\s*set -u")
        # Critical processes must be tracked and checked rather than backgrounded and forgotten.
        for variable in ("REVISION_AGENT_PID", "ALGORITHM_BRIDGE_PID", "PACKET_RUNTIME_PID"):
            self.assertIn(variable, entrypoint)
        self.assertTrue("wait -n" in entrypoint or "kill -0" in entrypoint)

    def test_compose_health_requires_packet_and_algorithm_bridge(self) -> None:
        compose = (ROOT / "Docker" / "compose" / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("snaas_packet_runtime_heartbeat.json", compose)
        self.assertIn("snaas_algorithm_runtime_heartbeat.json", compose)
        self.assertIn("netlab_researcher_algorithm_bridge", compose)


if __name__ == "__main__":
    unittest.main()
