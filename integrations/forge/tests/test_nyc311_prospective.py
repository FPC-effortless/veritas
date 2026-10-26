"""Constructed hostile source/cutoff tests. Absolutely NO live FIT/label scoring."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import subprocess
import sys
import os
import json
from pathlib import Path
import tempfile
import unittest

from forge_data.nyc311_prospective import (
    _request_url, enroll_candidate, followup_fixed_ids, inspect_candidate, inspect_followup,
    SnapshotError, SCHEMA
)


def initial_rows():
    return [
        {"unique_key": "101", "created_date": "2026-10-26T11:00:00.000",
         "agency": "DOT", "complaint_type": "Pothole", "status": "Open"},
        {"unique_key": "102", "created_date": "2026-10-26T10:00:00.000",
         "agency": "DEP", "complaint_type": "Water", "status": "Open"},
        {"unique_key": "103", "created_date": "2026-10-26T09:00:00.000",
         "agency": "DOT", "complaint_type": "Road", "status": "Open"},
    ]


def fixture(*, rows=None, assert_url=None):
    raw = json.dumps(initial_rows() if rows is None else rows).encode()
    def fetch(request, max_bytes):
        if assert_url:
            assert_url(request.full_url)
        return (200, "application/json", "Untrusted HTTP Date", raw)
    return fetch


def times(*values):
    seq = iter(values)
    return lambda: next(seq)


DAY0 = "2026-10-26T14:00:00.000000Z"
DAY0_END = "2026-10-26T14:00:01.000000Z"
DAY7 = "2026-11-02T14:00:01.000000Z"
DAY7_END = "2026-11-02T14:00:02.000000Z"


class ProspectiveCohortTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "cohort"

    def enroll(self, rows=None, assert_url=None):
        return enroll_candidate(
            self.root, limit=3, fetcher=fixture(rows=rows, assert_url=assert_url),
            clock=times(DAY0, DAY0_END),
        )

    def test_immutable_first_observed_open_source_candidate(self):
        result = self.enroll()
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["enrolled_case_count"], 3)
        self.assertEqual(result["scientific_evidence_tier"], "PUBLIC_SOURCE_COHORT_CANDIDATE_ONLY")
        self.assertNotIn("case_ids", result)
        self.assertFalse(result["fit_or_report_scoring_authorized"])
        report = inspect_candidate(self.root)
        self.assertEqual(report["case_ids"], ("101", "102", "103"))
        self.assertEqual(report["cohort_sha256"], hashlib.sha256(b"101\n102\n103\n").hexdigest())
        self.assertEqual(report["capture"]["acquisition_end_utc"], DAY0_END)

    def test_open_only_no_label_at_cohort_initialization(self):
        self.enroll(assert_url=lambda url: (
            self.assertIn("status%3D%27Open%27", url),
            self.assertNotIn("closed_date", url),
            self.assertNotIn("incident_address", url),
        ))
        original = json.loads((self.root/"enrollment-source.json").read_text())
        self.assertTrue(all("closed_date" not in x for x in original))

    def test_mixed_closed_member_rejected(self):
        rows = initial_rows()
        rows[1]["status"] = "Closed"
        with self.assertRaisesRegex(SnapshotError, "open"):
            self.enroll(rows=rows)
        self.assertFalse(self.root.exists())

    def test_unexpected_personal_details_rejected(self):
        rows = initial_rows()
        rows[0]["incident_address"] = "restricted"
        with self.assertRaisesRegex(SnapshotError, "non-allowlisted"):
            self.enroll(rows=rows)

    def test_duplicate_identity_rejected(self):
        rows = initial_rows()
        rows[2]["unique_key"] = "102"
        with self.assertRaisesRegex(SnapshotError, "duplicate"):
            self.enroll(rows=rows)

    def test_unsafe_nonnumeric_injection_rejected(self):
        rows = initial_rows()
        rows[0]["unique_key"] = "101') or true"
        with self.assertRaisesRegex(SnapshotError, "non-numeric"):
            self.enroll(rows=rows)

    def test_capture_cannot_be_overwritten(self):
        self.enroll()
        with self.assertRaisesRegex(SnapshotError, "overwrite"):
            self.enroll()

    def test_tampered_original_source_rejected(self):
        self.enroll()
        (self.root/"enrollment-source.json").write_text("[]")
        with self.assertRaisesRegex(SnapshotError, "hash"):
            inspect_candidate(self.root)

    def test_membership_tampering_rejected(self):
        self.enroll()
        manifest_path = self.root/"candidate-manifest.json"
        m=json.loads(manifest_path.read_text())
        m["case_ids"] = ["101", "102"]
        manifest_path.write_text(json.dumps(m))
        with self.assertRaisesRegex(SnapshotError, "digest/count"):
            inspect_candidate(self.root)

    def test_unqualified_source_cannot_self_promote_fit(self):
        self.enroll()
        manifest_path = self.root/"candidate-manifest.json"
        m=json.loads(manifest_path.read_text())
        m["fit_or_report_scoring_authorized"] = True
        manifest_path.write_text(json.dumps(m))
        with self.assertRaisesRegex(SnapshotError, "self-promote"):
            inspect_candidate(self.root)

    def test_future_eligibility_cannot_be_inferred_from_event_created_date(self):
        rows = initial_rows()
        rows[0]["created_date"] = "2022-01-01T01:00:00.000"  # old case created != old knowledge time
        self.enroll(rows=rows)
        self.assertEqual(inspect_candidate(self.root)["capture"]["acquisition_end_utc"], DAY0_END)

    def test_followup_response_is_received_before_acquisition_end_clock(self):
        self.enroll()
        events = []
        ticks = iter([DAY7, DAY7_END])
        def clock():
            events.append("clock")
            return next(ticks)
        def fetcher(request, byte_limit):
            events.append("fetch")
            return (200, "application/json", "untrusted", b"[]")
        result = followup_fixed_ids(
            self.root, self.base / "followup", fetcher=fetcher, clock=clock)
        self.assertEqual(events, ["clock", "fetch", "clock"])
        self.assertEqual(result["capture"]["acquisition_end_utc"], DAY7_END)
        self.assertEqual(inspect_followup(self.root, self.base / "followup")["report_scoring"],
                         "PROHIBITED")

    def test_seven_day_followup_bounded_before_fetch(self):
        self.enroll()
        called = []
        def no_fetch(*args):
            called.append(True)
            raise AssertionError("must not fetch future outcomes")
        with self.assertRaisesRegex(SnapshotError, "not yet due"):
            followup_fixed_ids(self.root, self.base/"followup", fetcher=no_fetch,
                clock=times("2026-10-27T14:00:00.000000Z"))
        self.assertEqual(called, [])

    def test_followup_id_membership_and_unknown_outcome(self):
        self.enroll()
        followup_rows=[{"unique_key":"103", "status":"Closed"},
                       {"unique_key":"101", "status":"Open"}]
        seen = []
        def follow_fetch(request, size):
            seen.append(request.full_url)
            return (200, "application/json", "No signature", json.dumps(followup_rows).encode())
        out=followup_fixed_ids(self.root, self.base/"followup", fetcher=follow_fetch,
            clock=times(DAY7, DAY7_END))
        self.assertEqual(out["present_case_count"], 2)
        self.assertEqual(out["missing_case_count"], 1)
        self.assertFalse(out["actual_status_labels_verified"])
        self.assertFalse(out["fit_or_scoring_authorized"])
        self.assertIn("unique_key+in%28%27101%27%2C%27102%27%2C%27103%27%29", seen[0])
        receipt=json.loads((self.base/"followup"/"followup-receipt.json").read_text())
        self.assertEqual(receipt["missing_case_ids"], ["102"])
        self.assertEqual(receipt["outcome_status"], "PUBLISHER_SNAPSHOT_UNVERIFIED_NO_LABELS")

    def test_followup_cannot_substitute_new_latest_case(self):
        self.enroll()
        with self.assertRaisesRegex(SnapshotError, "unexpected/injected"):
            followup_fixed_ids(self.root,self.base/"followup",
                fetcher=fixture(rows=[{"unique_key":"999", "status":"Closed"}]),
                clock=times(DAY7,DAY7_END))

    def test_empty_followup_not_labeled_negative(self):
        self.enroll()
        report=followup_fixed_ids(self.root,self.base/"followup",
            fetcher=fixture(rows=[]),clock=times(DAY7,DAY7_END))
        self.assertEqual(report["missing_case_count"], 3)
        self.assertEqual(report["present_case_count"], 0)

    def test_nonmonotonic_recovery_clock_rejected(self):
        self.enroll()
        with self.assertRaisesRegex(SnapshotError, "reversed"):
            followup_fixed_ids(self.root,self.base/"followup",
                fetcher=fixture(rows=[]), clock=times(DAY7_END,DAY7))

    def test_followup_duplicate_rows_rejected(self):
        self.enroll()
        bad=[{"unique_key":"101","status":"Open"},
             {"unique_key":"101","status":"Closed"}]
        with self.assertRaisesRegex(SnapshotError,"duplicate"):
            followup_fixed_ids(self.root,self.base/"followup",
                fetcher=fixture(rows=bad),clock=times(DAY7,DAY7_END))

    def test_followup_only_publisher_status_no_direct_physical_closure(self):
        self.enroll()
        bad=[{"unique_key":"101","status":"Closed", "closed_date":"2026-10-30"}]
        with self.assertRaisesRegex(SnapshotError,"non-allowlisted"):
            followup_fixed_ids(self.root,self.base/"followup",
                fetcher=fixture(rows=bad),clock=times(DAY7,DAY7_END))

    def test_saved_followup_original_bytes_and_missingness_are_verified(self):
        self.enroll()
        response = followup_fixed_ids(
            self.root, self.base / "followup",
            fetcher=fixture(rows=[{"unique_key":"101","status":"Closed"}]),
            clock=times(DAY7, DAY7_END))
        verified = inspect_followup(self.root, self.base / "followup")
        self.assertEqual(verified["status"], "SOURCE_BYTES_MATCH_ONLY_NO_LABELS")
        self.assertEqual(verified["present_case_count"], 1)
        self.assertEqual(verified["missing_case_count"], 2)
        self.assertEqual(verified["report_scoring"], "PROHIBITED")
        self.assertEqual(verified["original_response_sha256"],
                         response["capture"]["original_response_sha256"])

    def test_followup_original_bytes_tamper_denied(self):
        self.enroll()
        folder = self.base / "followup"
        followup_fixed_ids(self.root, folder, fetcher=fixture(rows=[]),
                           clock=times(DAY7, DAY7_END))
        (folder / "followup-source.json").write_bytes(b"[] ")
        with self.assertRaisesRegex(SnapshotError, "hash"):
            inspect_followup(self.root, folder)

    def test_followup_cannot_forge_missingness_or_independent_label(self):
        self.enroll()
        folder = self.base / "followup"
        followup_fixed_ids(self.root, folder, fetcher=fixture(rows=[]),
                           clock=times(DAY7, DAY7_END))
        receipt_path = folder / "followup-receipt.json"
        original = json.loads(receipt_path.read_text())
        altered = dict(original, missing_case_count=0)
        receipt_path.write_text(json.dumps(altered))
        with self.assertRaisesRegex(SnapshotError, "missingness"):
            inspect_followup(self.root, folder)
        altered = dict(original, actual_status_labels_verified=True)
        receipt_path.write_text(json.dumps(altered))
        with self.assertRaisesRegex(SnapshotError, "promote"):
            inspect_followup(self.root, folder)

    def test_followup_must_query_exact_original_id_list(self):
        self.enroll()
        folder = self.base / "followup"
        followup_fixed_ids(self.root, folder, fetcher=fixture(rows=[]),
                           clock=times(DAY7, DAY7_END))
        receipt_path = folder / "followup-receipt.json"
        altered = json.loads(receipt_path.read_text())
        altered["capture"]["request_url"] = _request_url("followup", ids=("999",))
        receipt_path.write_text(json.dumps(altered))
        with self.assertRaisesRegex(SnapshotError, "exactly the fixed"):
            inspect_followup(self.root, folder)

    def test_cli_inspection_offline_has_no_labels_or_private_ids(self):
        self.enroll()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
        p = subprocess.run([
            sys.executable, "-m", "forge_data.nyc311_prospective",
            "inspect-candidate", "--candidate", str(self.root)],
            env=env, capture_output=True, text=True, check=False, timeout=15)
        self.assertEqual(p.returncode, 0, p.stderr)
        result = json.loads(p.stdout)
        self.assertEqual(result["case_count"], 3)
        self.assertEqual(result["fit_or_scoring"], "PROHIBITED")
        self.assertNotIn("case_ids", result)

    def test_numeric_fixed_id_sql_safety(self):
        with self.assertRaisesRegex(SnapshotError,"numeric"):
            _request_url("followup", ids=("1') or true",))


if __name__=="__main__":
    unittest.main()
