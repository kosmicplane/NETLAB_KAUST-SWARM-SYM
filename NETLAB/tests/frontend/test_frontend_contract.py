import re
import unittest
from pathlib import Path


class FrontendContractTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[2]
        self.frontend = self.root / "apps" / "mission_control" / "frontend"
        self.text = "\n".join(path.read_text() for path in self.frontend.glob("modules/*.js"))

    def test_required_research_modules_exist(self):
        required = {"overview","guided_demo","mission_designer","experiment_manager","swarm_control","topology_studio","antenna_lab","world_lab","algorithm_lab","traffic_services","fault_recovery","live_telemetry","synchronization","evidence","diagnostics","settings"}
        present = {path.stem for path in self.frontend.glob("modules/*.js")}
        self.assertFalse(required - present)

    def test_guided_demo_is_english_only(self):
        guided = (self.frontend / "modules" / "guided_demo.js").read_text().lower()
        # Construct historical non-English labels from code points so the release
        # source remains English-only while retaining a regression check.
        forbidden_codepoints = (
            (100, 101, 109, 111, 32, 99, 111, 110, 32, 117, 115, 101, 114),
            (101, 106, 101, 99, 117, 116, 97, 114),
            (115, 105, 109, 117, 108, 97, 99, 105, 243, 110),
            (102, 97, 108, 108, 111, 32, 100, 101, 108, 32, 100, 114, 111, 110),
            (114, 101, 99, 117, 112, 101, 114, 97, 99, 105, 243, 110),
        )
        for values in forbidden_codepoints:
            self.assertNotIn("".join(map(chr, values)), guided)

    def test_primary_actions_are_api_backed(self):
        for endpoint in ("/api/command", "/api/config", "/api/swarm", "/api/topology", "/api/telemetry", "/api/guided-demo"):
            self.assertIn(endpoint, self.text)

    def test_live_telemetry_uses_stream_with_polling_fallback(self):
        telemetry = (self.frontend / "modules" / "live_telemetry.js").read_text()
        self.assertIn("EventSource", telemetry)
        self.assertIn("/api/telemetry/stream", telemetry)
        self.assertIn("startPolling", telemetry)

    def test_no_raw_latest_status_dump_in_overview(self):
        overview = (self.frontend / "modules" / "overview.js").read_text()
        self.assertNotRegex(overview, r"JSON\.stringify\([^)]*status[^)]*,\s*null\s*,\s*2")

    def test_transactional_synchronization_is_first_class(self):
        sync = (self.frontend / "modules" / "synchronization.js").read_text()
        app = (self.frontend / "modules" / "app.js").read_text()
        topology = (self.frontend / "modules" / "topology_studio.js").read_text()
        self.assertIn("Participant acknowledgements", sync)
        self.assertIn("readiness?.readiness", app)
        self.assertNotIn("result.ros?.ok", self.text)
        self.assertNotIn("ROS 2 is offline", topology)
        self.assertIn("result.committed", topology)

    def test_topology_coordinates_and_graph_are_submitted_atomically(self):
        topology = (self.frontend / "modules" / "topology_studio.js").read_text()
        self.assertIn("api.saveTopology(topology, drones, station, true)", topology)
        self.assertNotIn("await api.saveSwarm(drones);", topology)


if __name__ == "__main__":
    unittest.main()
