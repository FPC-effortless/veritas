"""Constructed department council tests. No remote agents or research fits."""

import copy
import io
import json
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from research_lab import council
from research_lab.__main__ import main
from research_lab.core import Controller, LabError


def note(department, note_id):
    return {
        "schema": "research_lab.department_note.v1",
        "id": note_id,
        "department": department,
        "head_role": "head." + department,
        "reporter_principal": "asserted.operator",
        "source_pin": "a" * 40,
        "stage": "SOURCE_RECOVERY",
        "summary": "Source-level inspection only; no learned-model claim.",
        "negative_results": ["No native execution evidence."],
        "blocker": "Independent review is pending.",
        "help_requests": [],
        "shares": [],
        "responses": [],
        "next_action": "Review frozen source closure.",
        "observed_execution_id": "NONE",
        "review_receipt": "NONE",
    }


class ResearchCouncilTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.lab = Controller(self.tmp / "lab")

    def test_roster_agrees_with_18_lane_canonical_manifest(self):
        manifest = Path(__file__).resolve().parents[1] / "examples/frontier_unified_program.json"
        lanes = {x["id"] for x in json.loads(manifest.read_text())["lanes"]}
        roster = council.roster()
        self.assertEqual(lanes, set(council.DEPARTMENTS))
        self.assertEqual(len(roster["departments"]), 18)
        self.assertEqual({x["id"] for x in roster["departments"]}, lanes)
        self.assertIn("NO_EXECUTING_HEADS_ATTESTED", roster["authority"])

    def test_empty_meeting_is_not_real_attendance_or_workers(self):
        minutes = council.convene(self.lab, "20261105.early")
        self.assertEqual(minutes["expected_departments"], 18)
        self.assertEqual(minutes["reported_departments"], 0)
        self.assertEqual(sum(x["report"] == "NO_SUBMISSION" for x in minutes["departments"]), 18)
        self.assertIn("NOT_LIVE_HEAD_MEETING", minutes["meeting_type"])
        self.assertIn("NO_INDEPENDENT_HEAD", minutes["attendance"])
        self.assertEqual(self.lab.status()["tasks"], [])
        self.assertEqual(self.lab.status()["workers"], [])
        self.assertEqual(council.convene(self.lab, "20261105.early"), minutes)
        self.assertEqual(council.latest_minutes(self.lab), minutes)

    def test_reported_head_can_ask_and_target_can_respond_without_claiming_acceptance(self):
        a = note("FLOCK_COLLECT", "flock.001")
        a["help_requests"] = [{
            "id": "FLOCK_COLLECT.addresscheck", "target": "PSN",
            "question": "Can selective write prevent wrong-value binding?",
            "expected_artifact": "Read-only source review",
            "evidence_ref": "source:abc",
        }]
        a["shares"] = [{
            "target": "ALL",
            "finding": "Negative multi-key retrieval evidence",
            "evidence_ref": "evidence:fail-r9",
        }]
        b = note("PSN", "psn.001")
        b["responses"] = [{
            "request_id": "FLOCK_COLLECT.addresscheck",
            "response": "Can inspect the frozen selective-write source",
            "evidence_ref": "source:psn",
        }]
        self.assertTrue(council.post_note(self.lab, a)["created"])
        self.assertTrue(council.post_note(self.lab, b)["created"])
        minutes = council.convene(self.lab, "20261105.evening")
        self.assertEqual(minutes["reported_departments"], 2)
        flock = next(x for x in minutes["departments"] if x["id"] == "FLOCK_COLLECT")
        self.assertIn("No native execution", flock["negative_results"][0])
        self.assertEqual(flock["next_action"], "Review frozen source closure.")
        self.assertTrue(flock["all_report_content_unverified"])
        self.assertEqual(len(minutes["help_exchanges"]), 1)
        request = minutes["help_exchanges"][0]
        self.assertEqual(request["origin"], "FLOCK_COLLECT")
        self.assertEqual(request["status"], "RESPONSE_REPORTED_UNVERIFIED")
        self.assertEqual(request["responses"][0]["by"], "PSN")
        self.assertIn("NO_WORK_OR_COMPUTE_AUTHORIZED", request["authority"])
        self.assertEqual(len(minutes["shared_findings"]), 1)
        self.assertEqual(self.lab.status()["tasks"], [])

    def test_wrong_department_response_does_not_acknowledge_request(self):
        a = note("PSN", "psn.002")
        a["help_requests"] = [{
            "id": "PSN.please_help", "target": "GPU_KERNELS",
            "question": "Review source-level kernel compatibility",
            "expected_artifact": "Source-only matrix",
            "evidence_ref": "source:123",
        }]
        b = note("SSA", "ssa.002")
        b["responses"] = [{
            "request_id": "PSN.please_help",
            "response": "Unrelated response",
            "evidence_ref": "source:456",
        }]
        council.post_note(self.lab, a)
        council.post_note(self.lab, b)
        minutes = council.convene(self.lab, "20261105.wrong")
        self.assertEqual(minutes["help_exchanges"][0]["status"], "AWAITING_TARGET_REPORT")
        self.assertEqual(len(minutes["unmatched_responses"]), 1)

    def test_immutable_note_id_and_immutable_meeting_snapshot(self):
        a = note("PSN", "psn.003")
        r = council.post_note(self.lab, a)
        self.assertFalse(council.post_note(self.lab, a)["created"])
        self.assertEqual(r["pin"], council.post_note(self.lab, a)["pin"])
        altered = copy.deepcopy(a)
        altered["summary"] = "Different conclusion"
        with self.assertRaisesRegex(LabError, "immutable"):
            council.post_note(self.lab, altered)
        frozen = council.convene(self.lab, "20261105.frozen")
        council.post_note(self.lab, note("SSA", "ssa.003"))
        self.assertEqual(council.convene(self.lab, "20261105.frozen"), frozen)
        self.assertEqual(council.convene(self.lab, "20261105.next")["reported_departments"], 2)

    def test_reject_unrecognized_department_forged_head_and_invalid_pins(self):
        base = note("PSN", "psn.004")
        variants = [
            {"department": "MISSING"},
            {"head_role": "head.TAC_CORE"},
            {"source_pin": "not-hash"},
            {"stage": "PUBLISHED_FRONTIER"},
            {"stage": ["REVIEWED_REPORTED"]},
            {"reporter_principal": "not a safe id"},
        ]
        for change in variants:
            with self.subTest(change=change), self.assertRaises(LabError):
                council.post_note(self.lab, {**base, **change})

    def test_reject_self_target_and_undifferentiated_request_id(self):
        base = note("PSN", "psn.005")
        sample = {"id": "PSN.reuse", "target": "PSN",
                  "question": "wrong target", "expected_artifact": "none",
                  "evidence_ref": "x"}
        for change in ({"id": "unscoped", "target": "SSA"}, sample):
            with self.subTest(change=change), self.assertRaises(LabError):
                council.post_note(self.lab, {**base, "help_requests": [change]})

    def test_stale_note_is_not_current_head_participation(self):
        council.post_note(self.lab, note("GPU_KERNELS", "kernels.old"))
        with self.lab.transaction() as db:
            db.execute(
                "UPDATE department_notes SET recorded_at=? WHERE id=?",
                (time.time() - 8 * 86400, "kernels.old"),
            )
        minutes = council.convene(self.lab, "20261105.stale")
        self.assertEqual(minutes["reported_departments"], 1)
        self.assertEqual(minutes["freshly_reporting_departments"], 0)
        department = next(x for x in minutes["departments"] if x["id"] == "GPU_KERNELS")
        self.assertEqual(department["report"], "STALE_NOTE_NOT_CURRENT_SUBMISSION")
        self.assertIn("NO_INDEPENDENT_HEAD", minutes["attendance"])

    def test_cli_roster_post_meet_latest_is_durable(self):
        root = str(self.tmp / "cli")
        note_path = self.tmp / "note.json"
        note_path.write_text(json.dumps(note("TAC_CORE", "tac.007")))
        cases = [
            (["council", "roster"], "research_lab.department_roster.v1"),
            (["council", "post", str(note_path)], None),
            (["council", "meet", "20261105.cli"], "research_lab.council_minutes.v1"),
            (["council", "latest"], "research_lab.council_minutes.v1"),
        ]
        for args, expected_schema in cases:
            with self.subTest(args=args):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    self.assertEqual(main(["--root", root, *args]), 0)
                result = json.loads(buffer.getvalue())
                if expected_schema:
                    self.assertEqual(result["schema"], expected_schema)
        self.assertEqual(result["reported_departments"], 1)

    def request_note(self, note_id="psn.request1"):
        result = note("PSN", note_id)
        result["help_requests"] = [{
            "id": "PSN.revision_a", "target": "DPSL",
            "question": "Review revision A", "expected_artifact": "Source review",
            "evidence_ref": "revision-A",
        }]
        return result

    def test_request_identity_is_immutable_across_note_history(self):
        original = self.request_note()
        council.post_note(self.lab, original)
        # A later note omitting the request must not erase its identity.
        council.post_note(self.lab, note("PSN", "psn.intervening"))
        for field, value in (
            ("question", "Review revision B"),
            ("expected_artifact", "Different artifact"),
            ("evidence_ref", "revision-B"),
            ("target", "SSA"),
        ):
            changed = copy.deepcopy(original)
            changed["id"] = "psn.changed." + field
            changed["help_requests"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(LabError, "request.*immutable"):
                council.post_note(self.lab, changed)
        with self.lab.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM department_notes").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)

    def test_unchanged_request_can_be_carried_forward_without_rebinding_response(self):
        original = self.request_note()
        council.post_note(self.lab, original)
        response = note("DPSL", "dpsl.response")
        response["responses"] = [{
            "request_id": "PSN.revision_a", "response": "Reviewed revision A",
            "evidence_ref": "revision-A",
        }]
        council.post_note(self.lab, response)
        first = council.convene(self.lab, "meeting.original")
        carried = copy.deepcopy(original)
        carried.update(id="psn.request2", summary="A new unrelated department update")
        council.post_note(self.lab, carried)
        self.assertEqual(council.convene(self.lab, "meeting.carried")["help_exchanges"], first["help_exchanges"])
        changed = copy.deepcopy(carried)
        changed["id"] = "psn.request3"
        changed["help_requests"][0].update(id="PSN.revision_b", question="Review revision B", evidence_ref="revision-B")
        council.post_note(self.lab, changed)
        latest = council.convene(self.lab, "meeting.changed")
        self.assertEqual(latest["help_exchanges"][0]["status"], "AWAITING_TARGET_REPORT")
        self.assertEqual(len(latest["unmatched_responses"]), 1)
        self.assertEqual(council.convene(self.lab, "meeting.original"), first)

    def test_legacy_ambiguous_request_blocks_new_minutes_until_new_id(self):
        original = self.request_note()
        council.post_note(self.lab, original)
        frozen = council.convene(self.lab, "meeting.historical")
        changed = copy.deepcopy(original)
        changed["id"] = "psn.legacy"
        changed["help_requests"][0]["question"] = "Review revision B"
        # Simulate a note accepted by the old implementation without rewriting history.
        from research_lab.core import canonical, identity
        with self.lab.transaction() as db:
            db.execute("INSERT INTO department_notes VALUES (?,?,?,?,?)", (
                changed["id"], changed["department"], identity(changed), canonical(changed), time.time(),
            ))
        with self.assertRaisesRegex(LabError, "request.*immutable"):
            council.convene(self.lab, "meeting.ambiguous")
        with self.lab.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM council_meetings").fetchone()[0], 1)
        self.assertEqual(council.convene(self.lab, "meeting.historical"), frozen)
        repaired = copy.deepcopy(changed)
        repaired["id"] = "psn.repaired"
        repaired["help_requests"][0]["id"] = "PSN.revision_b"
        council.post_note(self.lab, repaired)
        self.assertEqual(council.convene(self.lab, "meeting.repaired")["help_exchanges"][0]["status"], "AWAITING_TARGET_REPORT")

    def test_malformed_department_types_fail_with_domain_error(self):
        for department in ([], {}, None, True, 123):
            malformed = note("PSN", "psn.invalid")
            malformed["department"] = department
            with self.subTest(department=department), self.assertRaises(LabError):
                council.post_note(self.lab, malformed)

    def test_cli_malformed_department_is_handled_without_traceback(self):
        path = self.tmp / "malformed.json"
        malformed = note("PSN", "psn.invalid")
        malformed["department"] = []
        path.write_text(json.dumps(malformed))
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["--root", str(self.tmp / "cli-invalid"), "council", "post", str(path)]), 1)
        self.assertIn("Research Lab OS:", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main()
