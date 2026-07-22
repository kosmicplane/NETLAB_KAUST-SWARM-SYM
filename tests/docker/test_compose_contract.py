import unittest
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@unittest.skipIf(yaml is None, "PyYAML is not installed")
class ComposeContractTests(unittest.TestCase):
    def test_complete_stack_autostarts_runtime_components(self):
        root = Path(__file__).resolve().parents[2]
        data = yaml.safe_load((root / "Docker" / "compose" / "docker-compose.yml").read_text())
        services = data["services"]
        self.assertEqual(set(("isaac","ros2-core","sionna-engine")) - set(services), set())
        self.assertIn("realtime_link_server.py", " ".join(services["sionna-engine"]["command"]))
        self.assertIn("runtime_entrypoint.sh", " ".join(services["ros2-core"]["command"]))
        self.assertIn("healthcheck", services["isaac"])
        self.assertIn("healthcheck", services["ros2-core"])
        self.assertIn("healthcheck", services["sionna-engine"])

    def test_legacy_brev_setup_delegates_to_canonical_bootstrap(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / "scripts" / "netlab_brev_webrtc.sh").read_text(encoding="utf-8")
        self.assertIn('"$PROJECT_ROOT/scripts/netlab" bootstrap --no-start --non-interactive', text)



if __name__ == "__main__":
    unittest.main()
