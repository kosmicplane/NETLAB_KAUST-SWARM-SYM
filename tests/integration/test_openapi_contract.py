import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class OpenApiContractTests(unittest.TestCase):
    def test_machine_readable_api_covers_runtime_critical_routes(self):
        root = Path(__file__).resolve().parents[2]
        spec = yaml.safe_load((root / "schemas" / "api" / "openapi-v1.yaml").read_text(encoding="utf-8"))
        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertEqual(spec["info"]["version"], "9.0.0")
        paths = spec["paths"]
        required = {
            "/api/health", "/api/readiness", "/api/status", "/api/config",
            "/api/swarm", "/api/topology", "/api/synchronization",
            "/api/reconcile", "/api/telemetry", "/api/telemetry/stream",
            "/api/command", "/api/diagnostics", "/api/packet-doctor",
            "/api/smoke-test", "/api/support-bundle",
        }
        self.assertFalse(required - set(paths), required - set(paths))
        server = (root / "apps" / "mission_control" / "backend" / "server.py").read_text(encoding="utf-8")
        for route in required:
            self.assertIn(route, server)


if __name__ == "__main__":
    unittest.main()
