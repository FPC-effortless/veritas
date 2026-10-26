"""No-network unit tests for honest NYC311 public acquisition evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from forge_data.nyc311_snapshot import (
    SnapshotError, _source_url, inspect_capture, make_snapshot,
)


def source_bytes():
    return json.dumps([
        {"unique_key":"fixture-1", "created_date":"2026-10-26T13:00:00.000",
         "agency":"DOT", "status":"Open"},
        {"unique_key":"fixture-2", "created_date":"2026-10-26T12:00:00.000",
         "closed_date":"2026-10-26T12:15:00.000", "status":"Closed"},
    ]).encode()


def clocks():
    return iter(["2026-10-26T14:00:00.000000Z", "2026-10-26T14:00:01.000000Z"])


class PublicSourceCaptureTests(unittest.TestCase):
    def capture(self, raw=None, status=200, content_type="application/json"):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        output = root / "capture"
        capture_clock = clocks()
        receipt = make_snapshot(
            output, limit=25,
            fetcher=lambda request, n: (status, content_type, "Mon, 26 Oct 2026 14:00:00 GMT",
                                        source_bytes() if raw is None else raw),
            clock=lambda: next(capture_clock),
        )
        return output, receipt

    def test_raw_bytes_receipt_no_claim_of_historical_availability(self):
        folder, receipt = self.capture()
        self.assertEqual(receipt["source_bytes_sha256"], hashlib.sha256(source_bytes()).hexdigest())
        self.assertFalse(receipt["historical_asof_fields_qualified"])
        self.assertFalse(receipt["allowed_for_model_fit_or_heldout_scoring"])
        out = inspect_capture(folder)
        self.assertEqual(out["capture_integrity"], "LOCAL_BYTES_AND_RECEIPT_MATCH")
        self.assertEqual(out["fit_or_scoring"], "PROHIBITED")
        self.assertEqual(out["historical_asof"], "NOT_QUALIFIED")

    def test_same_path_not_overwritten(self):
        folder, _ = self.capture()
        with self.assertRaisesRegex(SnapshotError, "overwrite"):
            make_snapshot(folder, fetcher=lambda *_: None)

    def test_minimal_columns_no_free_text_or_geo(self):
        url = _source_url(25)
        self.assertIn("erm2-nwe9", url)
        self.assertNotIn("descriptor", url)
        self.assertNotIn("latitude", url)
        self.assertNotIn("longitude", url)
        self.assertNotIn("incident_address", url)

    def test_reject_unexpected_sensitive_source_fields(self):
        raw = json.dumps([{"unique_key":"1","created_date":"2026-01-01",
                           "incident_address":"private"}]).encode()
        with self.assertRaisesRegex(SnapshotError, "unexpected or sensitive"):
            self.capture(raw=raw)

    def test_reject_duplicates(self):
        raw = json.dumps([{"unique_key":"same","created_date":"2026-01-01"}]*2).encode()
        with self.assertRaisesRegex(SnapshotError, "duplicate"):
            self.capture(raw=raw)

    def test_reject_nonfinite_json(self):
        with self.assertRaises(SnapshotError):
            self.capture(raw=b'[{"unique_key":"1","created_date":"2026-01-01","x":NaN}]')

    def test_status_error_not_accepted(self):
        with self.assertRaisesRegex(SnapshotError, "HTTP 200"):
            self.capture(status=429)

    def test_content_type_error_not_accepted(self):
        with self.assertRaisesRegex(SnapshotError, "HTTP 200"):
            self.capture(content_type="text/html")

    def test_acquired_source_bytes_tamper_rejected(self):
        folder, receipt = self.capture()
        (folder / "publisher-response.json").write_bytes(b"{}")
        with self.assertRaisesRegex(SnapshotError, "SHA|differ"):
            inspect_capture(folder)

    def test_self_promoted_training_flag_rejected(self):
        folder, _ = self.capture()
        path = folder / "acquisition-receipt.json"
        receipt = json.loads(path.read_text())
        receipt["allowed_for_model_fit_or_heldout_scoring"] = True
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(SnapshotError, "self-promote"):
            inspect_capture(folder)

    def test_self_promoted_asof_field_rejected(self):
        folder, _ = self.capture()
        path = folder / "acquisition-receipt.json"
        receipt = json.loads(path.read_text())
        receipt["historical_asof_fields_qualified"] = True
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(SnapshotError, "self-promote"):
            inspect_capture(folder)

    def test_invalid_source_limit(self):
        for limit in (0, 101, 1.5, True):
            with self.subTest(limit=limit):
                with self.assertRaises(SnapshotError):
                    _source_url(limit)

    def test_bogus_capture_url_rejected(self):
        folder, _ = self.capture()
        path = folder / "acquisition-receipt.json"
        receipt = json.loads(path.read_text())
        receipt["request_url"] = "https://evil.invalid/311.json?$limit=25"
        path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(SnapshotError, "not the approved"):
            inspect_capture(folder)

    def test_empty_source_list_rejected(self):
        with self.assertRaises(SnapshotError):
            self.capture(raw=b"[]")

    def test_nonmonotonic_acquisition_clock(self):
        reverse = iter(["2026-10-26T14:01:00.000000Z","2026-10-26T14:00:00.000000Z"])
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(SnapshotError, "non-monotonic"):
                make_snapshot(Path(root)/"capture",limit=2,
                    fetcher=lambda *_:(200,"application/json",None,source_bytes()),
                    clock=lambda:next(reverse))


if __name__ == "__main__":
    unittest.main()
