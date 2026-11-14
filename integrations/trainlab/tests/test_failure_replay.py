import tempfile
import unittest
from pathlib import Path

from trainlab.failure_replay import reduce_failure, replay
from trainlab.runner import LabError


def simulate(fixture, events, query, *, stale=False):
    state = fixture.get("values", {})
    for event in events:
        if event["op"] == "SET":
            state[event["key"]] = event["value"]
        elif event["op"] == "DELETE" and not stale:
            state.pop(event["key"], None)
    return state.get(query)


def stale(fixture, events, query):
    return simulate(fixture, events, query, stale=True)


class FailureReplayTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "repro"
        self.case = {
            "fixture": {"values": {"id": 7}, "unused": 9},
            "events": [{"op": "SET", "key": "other", "value": 8}, {"op": "DELETE", "key": "id"}],
            "query": "id",
        }
        self.implementations = {
            "candidate": {"sha256": "a" * 64, "simulate": stale},
            "reference": {"sha256": "b" * 64, "simulate": simulate},
        }

    def test_export_reopens_pinned_failure_in_a_fresh_call(self):
        result = reduce_failure(self.root, self.case, self.implementations)
        self.assertEqual(result["status"], "TESTED")
        self.assertTrue(result["one_deletion_minimal"])
        exported = replay(self.root, result["reproducer_sha256"], self.implementations)
        self.assertEqual(exported["status"], "FAILED")
        self.assertEqual(exported["fixture_fields"], 1)
        self.assertEqual(exported["events"], 1)
        self.assertEqual(self.case["fixture"], {"values": {"id": 7}, "unused": 9})
        stale_identity = {
            **self.implementations,
            "reference": {"sha256": "c" * 64, "simulate": simulate},
        }
        with self.assertRaisesRegex(LabError, "implementation"):
            replay(self.root, result["reproducer_sha256"], stale_identity)
        path = self.root / "reproducer.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(LabError, "pin"):
            replay(self.root, result["reproducer_sha256"], self.implementations)

    def test_expiring_budget_exports_last_witness(self):
        result = reduce_failure(self.root, self.case, self.implementations, max_calls=1)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["calls"], 1)
        self.assertFalse(result["one_deletion_minimal"])
        self.assertEqual(
            replay(self.root, result["reproducer_sha256"], self.implementations)["status"], "FAILED"
        )

    def test_reduction_rejects_a_symlink_parent_before_execution(self):
        link = self.root.with_name("link")
        destination = self.root.with_name("actual")
        destination.mkdir()
        link.symlink_to(destination, target_is_directory=True)
        with self.assertRaisesRegex(LabError, "symlinks"):
            reduce_failure(link / "repro", self.case, self.implementations)
        self.assertEqual(list(destination.iterdir()), [])

    def test_clean_and_unavailable_outcomes_have_no_reproducer(self):
        clean_case = {**self.case, "events": []}
        clean = reduce_failure(self.root, clean_case, self.implementations)
        self.assertEqual(clean["status"], "NO_FAILURE")
        self.assertIsNone(clean["reproducer_sha256"])

        def broken(*_args):
            raise ValueError("unsupported case")

        unavailable = {
            **self.implementations,
            "candidate": {"sha256": "c" * 64, "simulate": broken},
        }
        result = reduce_failure(self.root.with_name("unknown"), self.case, unavailable)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertIsNone(result["reproducer_sha256"])
