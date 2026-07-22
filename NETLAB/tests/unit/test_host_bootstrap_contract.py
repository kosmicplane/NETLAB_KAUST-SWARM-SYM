import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class HostBootstrapContractTests(unittest.TestCase):
    def setUp(self):
        self.script = (ROOT / "scripts" / "bootstrap_host.sh").read_text(encoding="utf-8")

    def test_existing_docker_is_never_replaced_or_mixed_with_containerd_io(self):
        self.assertIn("command -v docker", self.script)
        self.assertIn("docker info", self.script)
        self.assertNotRegex(self.script, r"apt(?:-get)?\s+install[^\n]*\bcontainerd\.io\b")
        self.assertIn("docker.io", self.script)

    def test_bootstrap_delegates_to_authoritative_cli(self):
        self.assertRegex(self.script, r'exec\s+"\$ROOT/scripts/netlab"\s+"\$\{args\[@\]\}"')
        self.assertIn("bootstrap --non-interactive", self.script)


if __name__ == "__main__":
    unittest.main()
