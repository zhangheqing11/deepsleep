"""The optional snapshot must match its declared sources and file manifest."""
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from api.integration_backend import OfflineEngineBackend
from api.prepare_integration import MARKER, prepare, specification, verify_snapshot


class IntegrationSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.temp) / "snapshot"
        self.root.mkdir()
        self.source = self.root / "engine/__init__.py"
        self.source.parent.mkdir()
        self.source.write_text("# pinned fixture", encoding="utf-8")
        self.metadata = {"sources": specification(), "files": {
            "engine/__init__.py": hashlib.sha256(self.source.read_bytes()).hexdigest()}}
        self.marker = self.root / MARKER
        self.marker.write_text(json.dumps(self.metadata), encoding="utf-8")

    def test_verification_rejects_edited_missing_and_extra_files(self):
        self.assertEqual(verify_snapshot(self.root), self.metadata)
        self.source.write_text("# changed", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "modified"):
            verify_snapshot(self.root)
        self.source.unlink()
        with self.assertRaisesRegex(RuntimeError, "missing"):
            verify_snapshot(self.root)
        self.source.write_text("# pinned fixture", encoding="utf-8")
        (self.root / "unexpected.py").write_text("pass", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Unexpected"):
            verify_snapshot(self.root)

    def test_verification_rejects_wrong_sources_and_escaping_paths(self):
        self.metadata["sources"]["engine"]["ref"] = "wrong"
        self.marker.write_text(json.dumps(self.metadata), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "sources differ"):
            verify_snapshot(self.root)
        self.metadata["sources"] = specification()
        self.metadata["files"] = {"../outside.py": "ignored"}
        self.marker.write_text(json.dumps(self.metadata), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Invalid"):
            verify_snapshot(self.root)

    def test_imported_module_outside_snapshot_is_rejected(self):
        backend = OfflineEngineBackend.__new__(OfflineEngineBackend)
        backend.root = self.root.resolve()
        fake = types.ModuleType("engine.outside_test")
        fake.__file__ = str(Path(self.temp) / "wrong_engine.py")
        with patch.dict("sys.modules", {"engine.outside_test": fake}):
            with self.assertRaisesRegex(RuntimeError, "outside the pinned snapshot"):
                backend._check_origins()

    def test_export_cannot_write_outside_project_var(self):
        project = Path(self.temp) / "project"
        with self.assertRaisesRegex(ValueError, "var/"):
            prepare(root=project, destination=Path(self.temp) / "outside")


if __name__ == "__main__":
    unittest.main()
