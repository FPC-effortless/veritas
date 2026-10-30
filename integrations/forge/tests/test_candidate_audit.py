"""Constructed-only CLI candidate audit checks. No real source or model qualification."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge_data.candidate_audit import MAX_CANDIDATE_BYTES, audit_woyengi_candidate
from forge_data.core import ForgeError

from test_woyengi import constructed_export


class CandidateAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "candidate.json"
        self.path.write_text(json.dumps(constructed_export()), encoding="utf-8")

    def audit(self, cutoff="2026-02-15T00:00:00Z"):
        return audit_woyengi_candidate(self.path, as_of=cutoff)

    def test_available_snapshot_is_structural_only_and_redacted(self):
        result = self.audit()
        self.assertEqual(result["records_total"], 2)
        self.assertEqual(result["records_visible_as_of"], 2)
        self.assertEqual(result["model_training_release"], "PROHIBITED")
        self.assertEqual(result["model_inference"], "NOT_PERFORMED")
        self.assertEqual(result["device_offline_qualification"], "NOT_RUN")
        self.assertEqual(result["publisher_authenticity"], "NOT_VERIFIED")
        self.assertEqual(result["source_rights"], "NOT_VERIFIED")
        serialized = json.dumps(result)
        self.assertNotIn("claim:fixture", serialized)
        self.assertNotIn("entity:one", serialized)
        self.assertNotIn("features", serialized)

    def test_later_selection_not_visible_before_full_snapshot(self):
        result = self.audit("2026-02-14T23:59:59Z")
        self.assertEqual(result["records_visible_as_of"], 0)
        self.assertEqual(result["records_not_yet_available"], 2)

    def test_audit_is_local_read_only_and_emits_no_release(self):
        with patch("socket.socket", side_effect=AssertionError("network access forbidden")):
            self.assertEqual(self.audit()["qualification"], "STRUCTURAL_ONLY")
        self.assertEqual({p.name for p in self.root.iterdir()}, {"candidate.json"})

    def test_rejects_duplicate_json_keys(self):
        self.path.write_text('{"kind":"one","kind":"two"}', encoding="utf-8")
        with self.assertRaisesRegex(ForgeError, "duplicate JSON"):
            self.audit()

    def test_rejects_nonfinite_json_numbers(self):
        self.path.write_text('{"kind":NaN}', encoding="utf-8")
        with self.assertRaisesRegex(ForgeError, "nonfinite"):
            self.audit()

    def test_rejects_oversize_input_without_writing_output(self):
        self.path.write_bytes(b" " * (MAX_CANDIDATE_BYTES + 1))
        with self.assertRaisesRegex(ForgeError, "size limit"):
            self.audit()
        self.assertEqual({p.name for p in self.root.iterdir()}, {"candidate.json"})

    def test_rejects_invalid_as_of_time(self):
        with self.assertRaisesRegex(ForgeError, "cutoff"):
            self.audit("2026-02-15T00:00:00")


if __name__ == "__main__":
    unittest.main()
