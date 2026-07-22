import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from netlab.io import atomic_write_json, permission_diagnostic, read_json, repair_shared_tree


class SharedIoTests(unittest.TestCase):
    def test_atomic_replace_preserves_shared_mode(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(os.environ, {"NETLAB_SHARED_FILE_MODE": "664", "NETLAB_SHARED_DIR_MODE": "2775"}, clear=False):
            path = Path(td) / "results" / "heartbeat.json"
            atomic_write_json(path, {"sequence": 1})
            atomic_write_json(path, {"sequence": 2})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o664)
            self.assertEqual(read_json(path)["sequence"], 2)
            self.assertTrue(permission_diagnostic(path)["readable"])

    def test_concurrent_readers_never_observe_partial_json(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            atomic_write_json(path, {"sequence": 0, "payload": "x" * 1024})
            errors = []
            stop = threading.Event()

            def reader():
                while not stop.is_set():
                    try:
                        with path.open("r", encoding="utf-8") as handle:
                            value = json.load(handle)
                        if "sequence" not in value:
                            errors.append("missing sequence")
                    except Exception as exc:  # pragma: no cover - failure captured below
                        errors.append(str(exc))

            threads = [threading.Thread(target=reader) for _ in range(4)]
            for thread in threads:
                thread.start()
            for sequence in range(1, 80):
                atomic_write_json(path, {"sequence": sequence, "payload": "y" * 2048})
            stop.set()
            for thread in threads:
                thread.join(timeout=2)
            self.assertEqual(errors, [])

    def test_repair_shared_tree_restores_readability(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "results"
            root.mkdir()
            path = root / "private.json"
            path.write_text("{}")
            path.chmod(0o600)
            result = repair_shared_tree(root, file_mode=0o664, dir_mode=0o2775)
            self.assertTrue(result["ok"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o664)


if __name__ == "__main__":
    unittest.main()
