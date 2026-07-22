import csv
import tempfile
import time
import unittest
from pathlib import Path

from netlab.state import StateStore, atomic_write_json, read_json
from netlab.telemetry import TelemetryReader


class StateTelemetryTests(unittest.TestCase):
    def test_state_sequence_and_sync_ack(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = StateStore(root)
            first = store.update({"phase":"READY"})
            second = store.update({"phase":"RUNNING"})
            self.assertGreater(second["sequence"], first["sequence"])
            signal = store.write_sync_signal("test", config_hash="abc")
            atomic_write_json(store.paths.isaac_heartbeat, {"scene_ready": True, "timestamp": time.time()})
            atomic_write_json(store.paths.isaac_ack, {"revision": signal["revision"], "applied_config_hash":"abc"})
            self.assertTrue(store.sync_status()["acknowledged"])

    def test_telemetry_never_labels_empty_data_live(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reader = TelemetryReader(root)
            snapshot = reader.snapshot()
            self.assertEqual(snapshot["source"]["source"], "OFFLINE")

    def test_fresh_csv_is_live_and_aggregated(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            results = root / "Docker" / "workspace" / "results"
            results.mkdir(parents=True)
            path = results / "snaas_link_metrics.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["timestamp","branch_id","src","dst","link_ok","gate_reason","snr_db","capacity_mbps","distance_m"])
                writer.writeheader()
                writer.writerow({"timestamp":time.time(),"branch_id":"branch_0","src":"station","dst":"drone_1","link_ok":"true","gate_reason":"FEASIBLE","snr_db":15,"capacity_mbps":20,"distance_m":30})
            snapshot = TelemetryReader(root).snapshot()
            self.assertEqual(snapshot["source"]["source"], "LIVE")
            self.assertEqual(snapshot["analytics"]["samples"], 1)
            self.assertEqual(snapshot["analytics"]["feasible_samples"], 1)
            self.assertIn("packet_advancement_rate_hz", snapshot["analytics"])
            self.assertIn("event_timeline", snapshot["analytics"])
            self.assertIn("sample_rate_hz", snapshot["analytics"])


if __name__ == "__main__":
    unittest.main()
