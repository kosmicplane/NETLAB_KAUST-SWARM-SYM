import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from netlab.bootstrap import Bootstrapper
from netlab.config import default_experiment, emit_legacy_config, load_experiment, save_experiment


class FakeCompose:
    def __init__(self, compose_dir):
        self.compose_dir = Path(compose_dir)
        self.env_file = ".env"

    def validate(self):
        class Result:
            ok = True
            def as_dict(self): return {"ok": True}
        return Result()

    def services(self): return ["sionna-engine", "ros2-core", "isaac"]
    def available(self): return False


class BootstrapTests(unittest.TestCase):
    def make_root(self, td):
        root = Path(td)
        (root / "Docker" / "compose").mkdir(parents=True)
        (root / "Docker" / "compose" / ".env.example").write_text("NETLAB_SHARED_UID=1000\nNETLAB_SHARED_GID=1000\nISAACSIM_HOST=127.0.0.1\n")
        (root / "Docker" / "workspace" / "shared").mkdir(parents=True)
        (root / "Docker" / "workspace" / "results").mkdir(parents=True)
        (root / "scripts").mkdir()
        return root

    def test_repair_preserves_valid_experiment(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            path = root / "Docker" / "workspace" / "shared" / "snaas_relay_config.json"
            save_experiment(path, default_experiment(), emit_legacy=True)
            before = path.read_text()
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            result = bootstrap.repair(repair_invalid_config=True)
            self.assertTrue(result["ok"])
            self.assertEqual(path.read_text(), before)

    def test_repair_replaces_only_invalid_generated_configuration(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            path = root / "Docker" / "workspace" / "shared" / "snaas_relay_config.json"
            invalid = emit_legacy_config(default_experiment())
            invalid["v5"]["antennas"]["definitions"] = []
            path.write_text(json.dumps(invalid))
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            result = bootstrap.repair(repair_invalid_config=True)
            self.assertTrue(result["ok"])
            self.assertTrue(load_experiment(path)["antennas"]["definitions"])
            self.assertTrue(list(path.parent.glob("snaas_relay_config.invalid_*.json")))

    def test_repair_creates_reference_when_active_config_is_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            path = root / "Docker" / "workspace" / "shared" / "snaas_relay_config.json"
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            result = bootstrap.repair(repair_invalid_config=True)
            self.assertTrue(result["ok"])
            self.assertTrue(path.exists())
            self.assertEqual(load_experiment(path)["experiment"]["id"], "first_feasible_relay_chain")
            action = next(item for item in result["actions"] if item["action"] == "CREATE_VALID_REFERENCE_CONFIG")
            self.assertTrue(action["ok"])

    def test_repair_preserves_invalid_researcher_configuration(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            path = root / "Docker" / "workspace" / "shared" / "snaas_relay_config.json"
            invalid = default_experiment()
            invalid["experiment"]["id"] = "researcher_custom_trial"
            invalid["experiment"]["author"] = "Researcher"
            invalid["experiment"]["tags"] = ["custom"]
            invalid["compatibility"]["generated_reference"] = False
            invalid["antennas"]["definitions"] = []
            path.write_text(json.dumps(invalid), encoding="utf-8")
            before = path.read_text(encoding="utf-8")
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            result = bootstrap.repair(repair_invalid_config=True)
            self.assertFalse(result["ok"])
            self.assertEqual(path.read_text(encoding="utf-8"), before)
            action = next(item for item in result["actions"] if item["action"] == "PRESERVE_INVALID_USER_CONFIGURATION")
            self.assertTrue(action["preserved"])
            self.assertTrue(action["requires_operator_action"])

    def test_environment_generation_records_host_identity(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {}, clear=False):
            root = self.make_root(td)
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            with mock.patch.object(bootstrap, "detect_host_address", return_value="100.64.0.1"):
                result = bootstrap.prepare_env()
            self.assertTrue(result["ok"])
            text = (root / "Docker" / "compose" / ".env").read_text()
            self.assertIn("ISAACSIM_HOST=100.64.0.1", text)
            self.assertIn(f"NETLAB_SHARED_UID={os.getuid()}", text)
            self.assertIn(f"NETLAB_SHARED_GID={os.getgid()}", text)

    def test_host_requirements_are_reported_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            result = bootstrap.host_requirements()
            self.assertIn("platform", result)
            self.assertIn("python", result)
            self.assertIn("commands", result)
            self.assertIn("disk", result)
            self.assertGreater(result["disk"]["free_bytes"], 0)
            self.assertIn("ports", result)

    def test_bootstrap_starts_mission_control_through_canonical_wrapper(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            launcher = root / "scripts" / "netlab_mission_control.sh"
            launcher.write_text("#!/usr/bin/env bash\nexit 0\n")
            launcher.chmod(0o755)
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            with mock.patch("netlab.bootstrap.subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout="started\n", stderr="")
                result = bootstrap._start_mission_control()
            self.assertTrue(result["ok"])
            self.assertEqual(result["url"], "http://127.0.0.1:8765")
            run_mock.assert_called_once()
            self.assertEqual(run_mock.call_args.args[0][-1], "start")

    def test_smoke_test_requires_live_feasible_packet_progress(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            system = {
                "readiness": {"critical_ready": True},
                "state": {"telemetry_source": "LIVE"},
            }
            packet = {
                "heartbeat_freshness": {"fresh": True},
                "heartbeat": {
                    "ready": True,
                    "sequence": 3,
                    "packet_advancing": True,
                    "connectivity_paused": False,
                    "operator_paused": False,
                    "gate_reason": "FEASIBLE",
                },
                "latest_gate": {"gate_reason": "FEASIBLE"},
            }
            with mock.patch("netlab.bootstrap.system_diagnose", return_value=system), mock.patch(
                "netlab.bootstrap.packet_diagnose", return_value=packet
            ):
                result = bootstrap.smoke_test()
            self.assertTrue(result["ok"])
            self.assertEqual(result["observed"]["packet_sequence"], 3)
            self.assertEqual(result["observed"]["telemetry_source"], "LIVE")

    def test_smoke_test_rejects_preview_or_non_feasible_flow(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_root(td)
            bootstrap = Bootstrapper(root, FakeCompose(root / "Docker" / "compose"))
            system = {
                "readiness": {"critical_ready": True},
                "state": {"telemetry_source": "PREVIEW"},
            }
            packet = {
                "heartbeat_freshness": {"fresh": True},
                "heartbeat": {
                    "ready": True,
                    "sequence": 0,
                    "packet_advancing": False,
                    "connectivity_paused": True,
                    "gate_reason": "OUT_OF_RANGE",
                },
                "latest_gate": {"gate_reason": "OUT_OF_RANGE"},
            }
            with mock.patch("netlab.bootstrap.system_diagnose", return_value=system), mock.patch(
                "netlab.bootstrap.packet_diagnose", return_value=packet
            ):
                result = bootstrap.smoke_test()
            self.assertFalse(result["ok"])
            self.assertFalse(result["checks"]["reference_gate_feasible"])
            self.assertFalse(result["checks"]["telemetry_live"])


if __name__ == "__main__":
    unittest.main()
