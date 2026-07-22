import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path


class SionnaServiceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        path = root / "Docker" / "workspace" / "sionna" / "realtime_link_server.py"
        spec = importlib.util.spec_from_file_location("netlab_test_sionna_service", path)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.module.HEARTBEAT_PATH = Path(cls.tmp.name) / "heartbeat.json"
        cls.server = cls.module.ThreadingHTTPServer(("127.0.0.1", 0), cls.module.Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.tmp.cleanup()

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_health_models_and_link(self):
        for path in ("/health", "/ready", "/models"):
            status, payload = self.request(path)
            self.assertEqual(status, 200)
            self.assertTrue(payload["ok"])
        status, payload = self.request("/link", {"src":"station","dst":"drone_1","tx_position":[0,0,1.5],"rx_position":[30,0,30],"frequency_hz":3.5e9,"bandwidth_hz":20e6,"tx_power_dbm":23,"thresholds":{"operational_range_m":90,"hard_outage_distance_m":220,"min_snr_db":3,"min_capacity_mbps":1}})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("gate_reason", payload)
        self.assertIn("model_source", payload)


if __name__ == "__main__":
    unittest.main()
