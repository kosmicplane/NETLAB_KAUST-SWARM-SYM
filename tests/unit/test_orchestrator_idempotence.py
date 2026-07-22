import tempfile
import unittest
from pathlib import Path
from unittest import mock

from netlab.orchestrator import Orchestrator


class OrchestratorIdempotenceTests(unittest.TestCase):
    def test_start_does_not_create_duplicate_runtime_when_observed_stack_is_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Docker" / "compose").mkdir(parents=True)
            (root / "Docker" / "workspace" / "results").mkdir(parents=True)
            (root / "Docker" / "workspace" / "shared").mkdir(parents=True)
            orchestrator = Orchestrator(root)
            observed = {
                "readiness": {"critical_ready": True},
                "revision": {"in_sync": True, "revision_id": "revision-1"},
                "state": {"phase": "READY", "telemetry_source": "LIVE", "run_id": "run-1"},
            }
            with mock.patch("netlab.orchestrator.system_diagnose", return_value=observed), mock.patch.object(
                orchestrator, "preflight"
            ) as preflight, mock.patch.object(orchestrator.compose, "command") as compose_command:
                result = orchestrator.start_stack(build=True)
            self.assertTrue(result["ok"])
            self.assertTrue(result["idempotent"])
            preflight.assert_not_called()
            compose_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
