import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from apps.mission_control.backend.server import MissionControlApplication, MissionControlServer
from netlab.config import default_experiment

ROOT = Path(__file__).resolve().parents[2]


class MissionControlApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        # Minimal static tree for the server under test.
        frontend = cls.root / "apps" / "mission_control" / "frontend"
        frontend.mkdir(parents=True)
        (frontend / "index.html").write_text("<!doctype html><title>NETLAB</title>")
        plugins = cls.root / "plugins" / "controllers"
        plugins.mkdir(parents=True)
        # Researcher algorithms are executed from the temporary product root.
        (cls.root / "netlab").symlink_to(ROOT / "netlab", target_is_directory=True)
        source_algorithm = ROOT / "plugins" / "research" / "researcher_chain_spacing"
        target_algorithm = cls.root / "plugins" / "research" / "researcher_chain_spacing"
        target_algorithm.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_algorithm, target_algorithm)
        app = MissionControlApplication(cls.root)
        app.save_config(default_experiment(), sync=False)
        cls.server = MissionControlServer(("127.0.0.1", 0), app)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_health_config_and_topology(self):
        for path in ("/api/health", "/api/config", "/api/topology", "/api/telemetry", "/api/guide", "/api/plugins", "/api/actions"):
            with self.subTest(path=path):
                status, payload = self.request(path)
                self.assertEqual(status, 200)
                self.assertTrue(payload["ok"])


    def test_telemetry_sse_once(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/telemetry/stream?once=1")
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("text/event-stream", response.headers.get("Content-Type", ""))
            self.assertIn("event: telemetry", body)
            self.assertIn("data:", body)

    def test_link_preview_and_validation(self):
        status, payload = self.request("/api/link/preview", {"src":"station","dst":"drone_1","tx_position":[0,0,1.5],"rx_position":[30,0,30]})
        self.assertEqual(status, 200)
        self.assertIn("decision", payload)
        cfg = default_experiment()
        status, payload = self.request("/api/config/validate", {"config":cfg})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])

    def test_revision_and_synchronization_api_contract(self):
        status, payload = self.request("/api/synchronization")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("synchronization", payload)
        status, payload = self.request("/api/revisions")
        self.assertEqual(status, 200)
        self.assertIn("revisions", payload)

    def test_offline_runtime_save_is_durable_but_not_falsely_committed(self):
        cfg = default_experiment()
        cfg["experiment"]["name"] = "Offline Durable Draft"
        status, payload = self.request("/api/config", {"config": cfg, "sync": True})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["durable_saved"])
        self.assertFalse(payload["committed"])
        self.assertEqual(payload["command"]["status"], "PARTIALLY_APPLIED")
        self.assertTrue(str(payload["synchronization"]["state"]).startswith("PENDING_"))


    def test_topology_inventory_replacement_is_atomic_and_durable(self):
        cfg = default_experiment()
        drones = cfg["swarm"]["drones"][:-1]
        drones[0]["position"] = [30.0, 2.0, 30.0]
        topology = dict(cfg["topology"])
        status, payload = self.request(
            "/api/topology",
            {
                "topology": topology,
                "drones": drones,
                "station": cfg["station"],
                "replace_inventory": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["config"]["swarm"]["drone_count"], len(drones))
        self.assertEqual(payload["config"]["swarm"]["drones"][0]["position"], [30.0, 2.0, 30.0])
        self.assertIn("link_preview", payload["topology_validation"])
        self.assertFalse(payload["committed"])  # no live ROS/Sionna/Isaac participants in this test

    def test_topology_and_coordinate_edit_share_one_revision_contract(self):
        cfg = default_experiment()
        drones = cfg["swarm"]["drones"]
        drones[0]["position"] = [31.0, 3.0, 30.0]
        status, payload = self.request("/api/topology", {"topology": cfg["topology"], "drones": drones})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("synchronization", payload)
        self.assertNotIn("ROS 2 is offline", json.dumps(payload))

    def test_researcher_algorithm_api_end_to_end_contract(self):
        status, registry = self.request("/api/algorithms")
        self.assertEqual(status, 200)
        self.assertTrue(registry["ok"])
        self.assertEqual(registry["api_version"], "2.0")
        self.assertEqual(registry["valid_count"], 1)

        status, package = self.request("/api/algorithms/researcher_chain_spacing")
        self.assertEqual(status, 200)
        self.assertTrue(package["algorithm"]["valid"])

        status, source = self.request("/api/algorithm/source?algorithm_id=researcher_chain_spacing")
        self.assertEqual(status, 200)
        self.assertIn("def step", source["source"])

        status, validated = self.request("/api/algorithm/validate", {"algorithm_id": "researcher_chain_spacing"})
        self.assertEqual(status, 200)
        self.assertTrue(validated["ok"])

        status, dry = self.request(
            "/api/algorithm/dry-run",
            {"algorithm_id": "researcher_chain_spacing", "parameters": {"spacing_m": 28.0, "altitude_m": 30.0}},
        )
        self.assertEqual(status, 200)
        self.assertTrue(dry["ok"], dry)
        self.assertTrue(dry["shield"]["accepted"])

        status, negative = self.request(
            "/api/algorithm/dry-run",
            {"algorithm_id": "researcher_chain_spacing", "negative_test": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(negative["negative_test_passed"])
        self.assertFalse(negative["shield"]["accepted"])

        status, activated = self.request(
            "/api/algorithm/activate",
            {"algorithm_id": "researcher_chain_spacing", "parameters": {"spacing_m": 28.0}, "sync": False},
        )
        self.assertEqual(status, 200)
        self.assertTrue(activated["ok"])
        self.assertFalse(activated["committed"])
        self.assertEqual(activated["activation"]["selection"]["algorithm_id"], "researcher_chain_spacing")

        status, selection = self.request("/api/algorithm/selection")
        self.assertEqual(status, 200)
        self.assertEqual(selection["selection"]["algorithm_id"], "researcher_chain_spacing")

        status, comparison = self.request(
            "/api/algorithm/compare",
            {"algorithm_ids": ["researcher_chain_spacing"], "replications": 2, "seed": 77},
        )
        self.assertEqual(status, 200)
        self.assertTrue(comparison["ok"])
        self.assertEqual(comparison["paired_seeds"], [77, 78])


if __name__ == "__main__":
    unittest.main()
