import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from netlab.docker import CommandResult, ComposeProject


def result(argv, code=0, out="", err=""):
    return CommandResult(list(argv), code, out, err, 0.01)


class DockerResolutionTests(unittest.TestCase):
    def test_prefixed_container_name_is_resolved_from_compose(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            (path / "docker-compose.yml").write_text("services: {ros2-core: {image: test}}")
            project = ComposeProject(path)
            responses = [
                result([], out="b58785930298\n"),
                result([], out="/b58785930298_netlab-ros2-core\n"),
            ]
            with patch("netlab.docker.run", side_effect=responses):
                name = project.service_container_name("ros2-core", "netlab-ros2-core")
            self.assertEqual(name, "b58785930298_netlab-ros2-core")


if __name__ == "__main__":
    unittest.main()
