"""Source recovery is a no-fit operation and never executes archived programs."""

import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from research_lab.core import LabError
from research_lab.source_recovery import recover_sources


class SourceRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.archive = self.root / "source.zip"
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("native/train.py", "raise RuntimeError('must never execute')\n")
            archive.writestr("native/PROTOCOL.json", '{"historical":true}')
            archive.writestr("native/final_labels.npz", b"not source; must never extract")
        self.catalog = {
            "schema": "research_lab.source_catalog.v1",
            "lanes": [
                {
                    "id": "PSN",
                    "archive": "source.zip",
                    "archive_sha256": self.pin(),
                    "library_file_id": "libfile-example",
                    "prefix": "native/",
                    "required": ["train.py", "PROTOCOL.json"],
                    "next_test": "Audit retrieval",
                },
                {"id": "SSA", "archive": None, "reason": "Exact source still required"},
            ],
        }

    def pin(self):
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def test_real_source_recovered_without_running_or_reading_binary_data(self):
        result = recover_sources(self.catalog, self.root, self.root / "recovered")
        first, second = result["lanes"]
        self.assertEqual(first["status"], "SOURCE_RECOVERED")
        self.assertEqual(first["fitted_models"], 0)
        self.assertFalse((self.root / "recovered/PSN/final_labels.npz").exists())
        self.assertEqual(second["status"], "SOURCE_MISSING")
        self.assertEqual(first["source_checks"]["python_syntax"], "PASS")
        repeat = recover_sources(self.catalog, self.root, self.root / "recovered")
        self.assertEqual(result, repeat)

    def test_archive_pin_and_existing_output_changes_fail_closed(self):
        self.catalog["lanes"][0]["archive_sha256"] = "0" * 64
        self.assertEqual(
            recover_sources(self.catalog, self.root, self.root / "out")["lanes"][0]["status"],
            "BLOCKED",
        )
        self.catalog["lanes"][0]["archive_sha256"] = self.pin()
        recover_sources(self.catalog, self.root, self.root / "out")
        (self.root / "out/PSN/train.py").write_text("changed")
        self.assertEqual(
            recover_sources(self.catalog, self.root, self.root / "out")["lanes"][0]["status"],
            "BLOCKED",
        )

    def test_missing_entrypoint_and_invalid_syntax_are_not_ready(self):
        self.catalog["lanes"][0]["required"].append("absent.py")
        self.assertEqual(
            recover_sources(self.catalog, self.root, self.root / "out")["lanes"][0]["status"],
            "BLOCKED",
        )
        self.catalog["lanes"][0]["required"].pop()
        with zipfile.ZipFile(self.archive, "w") as z:
            z.writestr("native/train.py", "def invalid(")
            z.writestr("native/PROTOCOL.json", "{}")
        self.catalog["lanes"][0]["archive_sha256"] = self.pin()
        self.assertEqual(
            recover_sources(self.catalog, self.root, self.root / "other")["lanes"][0]["status"],
            "BLOCKED",
        )

    def test_double_slash_after_prefix_cannot_create_an_absolute_extraction_path(self):
        escaped = self.root / "escaped.py"
        with zipfile.ZipFile(self.archive, "a") as archive:
            archive.writestr("native//" + str(escaped).lstrip("/"), "pass")
        self.catalog["lanes"][0]["archive_sha256"] = self.pin()
        result = recover_sources(self.catalog, self.root, self.root / "out")
        self.assertEqual(result["lanes"][0]["status"], "BLOCKED")
        self.assertFalse(escaped.exists())

    def test_unsafe_archive_and_unknown_catalog_fields_rejected(self):
        with zipfile.ZipFile(self.archive, "a") as z:
            z.writestr("../escape.py", "pass")
        self.catalog["lanes"][0]["archive_sha256"] = self.pin()
        self.assertEqual(
            recover_sources(self.catalog, self.root, self.root / "out")["lanes"][0]["status"],
            "BLOCKED",
        )
        with self.assertRaises(LabError):
            recover_sources({**self.catalog, "execute": True}, self.root, self.root / "out")


if __name__ == "__main__":
    unittest.main()
