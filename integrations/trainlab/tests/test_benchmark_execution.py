import tempfile
import unittest
from pathlib import Path

from trainlab.benchmark_execution import execute, freeze_panel
from trainlab.research_diagnostics import BudgetExceeded
from trainlab.runner import LabError


class BenchmarkExecutionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "bench"
        self.rows = [
            {
                "id": "changes",
                "group": "a",
                "original": {"value": 1},
                "intervened": {"value": 2},
                "expected_original": 1,
                "expected_intervened": 2,
                "expect_change": True,
            },
            {
                "id": "preserves",
                "group": "b",
                "original": {"value": 3},
                "intervened": {"value": 3, "unused": 7},
                "expected_original": 3,
                "expected_intervened": 3,
                "expect_change": False,
            },
        ]
        self.arms = {
            "reference_a": lambda row: row.get("value"),
            "reference_b": lambda row: next(v for k, v in row.items() if k == "value"),
            "shortcut": lambda row: None,
        }
        self.artifact = freeze_panel(
            self.rows,
            source_sha256={"reference_a": "a" * 64, "reference_b": "b" * 64, "shortcut": "c" * 64},
            minimum_changed_groups=1,
            minimum_invariant_groups=1,
            maximum_shortcut_accuracy=0.75,
        )

    def test_executes_both_references_and_scores_deficient_control(self):
        report = execute(self.root, self.arms, **self.artifact)
        self.assertEqual(report["status"], "TESTED")
        self.assertEqual(report["summary"]["observed_invocations"], 12)
        self.assertEqual(report["summary"]["shortcut_accuracy"], 0.0)
        self.assertEqual(report["findings"], [])

    def test_recorded_disagreement_survives_remaining_budget_loss(self):
        self.arms["reference_a"] = lambda row: -1
        report = execute(self.root, self.arms, max_calls=2, **self.artifact)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["summary"]["observed_invocations"], 2)
        self.assertEqual(report["summary"]["expected_invocations"], 12)
        self.assertIsNone(report["summary"]["shortcut_accuracy"])
        self.assertEqual(
            [finding["kind"] for finding in report["findings"]],
            ["REFERENCE_PARITY", "REFERENCE_EXPECTATION", "INSUFFICIENT_CHANGED_GROUPS"],
        )

    def test_mutation_and_pinned_panel_change(self):
        def corrupt(value):
            return value.pop("value")

        self.arms["reference_a"] = corrupt
        report = execute(self.root, self.arms, **self.artifact)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["summary"]["observed_invocations"], 8)
        self.assertEqual(report["observations"][0]["state"], "INVALID_OUTPUT_OR_MUTATION")
        self.assertEqual(self.artifact["panel"]["rows"], self.rows)
        self.artifact["panel"]["rows"][0]["original"]["value"] = 5
        with self.assertRaisesRegex(LabError, "panel pin"):
            execute(self.root.with_name("other"), self.arms, **self.artifact)

    def test_malformed_unicode_output_is_unobserved(self):
        self.arms["reference_a"] = lambda _row: chr(0xD83D)
        report = execute(self.root, self.arms, **self.artifact)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["observations"][0]["state"], "INVALID_OUTPUT_OR_MUTATION")

    def test_callback_budget_exception_is_a_failed_call(self):
        def fail(_row):
            raise BudgetExceeded("callback failure")

        self.arms["reference_a"] = fail
        report = execute(self.root, self.arms, **self.artifact)
        self.assertEqual(report["summary"]["observed_invocations"], 8)
        self.assertEqual(report["observations"][0]["state"], "CALL_FAILED")
        self.assertEqual(report["observations"][-1]["state"], "OBSERVED")

    def test_object_input_order_is_canonical_for_the_same_pin(self):
        self.arms["reference_a"] = lambda row: list(row.values())
        first = execute(self.root, self.arms, **self.artifact)
        row = self.artifact["panel"]["rows"][1]
        row["intervened"] = dict(reversed(list(row["intervened"].items())))
        second = execute(self.root.with_name("same"), self.arms, **self.artifact)
        self.assertEqual(first["observations"], second["observations"])

    def test_impossible_coverage_is_failed_when_a_shortcut_crashes(self):
        def fail(_row):
            raise RuntimeError("unavailable shortcut")

        self.arms["shortcut"] = fail
        frozen = freeze_panel(
            self.rows[:1],
            source_sha256=self.artifact["panel"]["source_sha256"],
            minimum_changed_groups=2,
            minimum_invariant_groups=1,
            maximum_shortcut_accuracy=0.75,
        )
        report = execute(self.root, self.arms, **frozen)
        self.assertEqual(report["status"], "FAILED")
        self.assertFalse(report["summary"]["complete"])
        self.assertEqual(report["summary"]["possible_changed_groups"], 1)
        self.assertEqual(report["summary"]["possible_invariant_groups"], 0)

    def test_suspicious_control_and_insufficient_group_support(self):
        self.arms["shortcut"] = lambda row: row["value"]
        report = execute(self.root, self.arms, **self.artifact)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["findings"][0]["kind"], "SHORTCUT_ABOVE_CEILING")
        frozen = freeze_panel(
            self.rows[:1],
            source_sha256=self.artifact["panel"]["source_sha256"],
            minimum_changed_groups=2,
            minimum_invariant_groups=1,
            maximum_shortcut_accuracy=0.75,
        )
        result = execute(self.root.with_name("narrow"), self.arms, **frozen)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("INSUFFICIENT_CHANGED_GROUPS", [f["kind"] for f in result["findings"]])
        self.assertIn("INSUFFICIENT_INVARIANT_GROUPS", [f["kind"] for f in result["findings"]])
