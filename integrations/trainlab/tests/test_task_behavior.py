import unittest

from trainlab.runner import LabError
from trainlab.task_behavior import regression, retrieval, sequence


def row(id_, label, prediction, *, slice_="validation", **extra):
    return {"id": id_, "slice": slice_, "label": label, "prediction": prediction, **extra}


class BehaviorTests(unittest.TestCase):
    def test_regression_reports_missing_coverage_and_intervals_separately(self):
        result = regression(
            [
                row("one", 1, 2, interval=[1, 3]),
                row("two", 3, 1, interval=[0, 2]),
                row("three", None, 1, interval=[1, 2], slice_="partial"),
            ],
            intervals=True,
        )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIsNone(result["overall"]["metrics"])
        expected = {
            "mae": 1.5,
            "rmse": (2.5) ** 0.5,
            "mean_signed_error": -0.5,
        }
        self.assertEqual(result["slices"]["validation"]["metrics"], expected)
        self.assertEqual(result["overall"]["observed_metrics"], expected)
        self.assertEqual(result["slices"]["validation"]["intervals"]["coverage"], 0.5)
        self.assertIsNone(result["overall"]["intervals"]["coverage"])
        self.assertEqual(result["overall"]["intervals"]["observed_coverage"], 0.5)
        incomplete = regression([row("int", 0, 0, interval=None)], intervals=True)
        self.assertEqual(incomplete["status"], "PARTIAL")
        self.assertEqual(incomplete["overall"]["metrics"]["mae"], 0)

    def test_rmse_preserves_small_finite_errors(self):
        result = regression([row("tiny", 0, 1e-200)])
        self.assertEqual(result["overall"]["metrics"]["rmse"], 1e-200)

    def test_sequence_order_edit_empty_and_partial(self):
        result = sequence(
            [
                row("a", ["red", "blue"], ["blue", "red"]),
                row("b", [], []),
                row("c", ["red", "blue"], ["red", "other", "blue"]),
                row("d", ["green"], None, slice_="partial"),
            ]
        )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIsNone(result["overall"]["metrics"])
        metrics = result["slices"]["validation"]["metrics"]
        self.assertEqual(metrics["exact_match"], 1 / 3)
        self.assertEqual(metrics["target_position_accuracy"], 0.25)
        self.assertEqual(metrics["mean_edit_distance"], 1)
        self.assertEqual(result["overall"]["observed_target_positions"], 4)
        self.assertIsNone(
            sequence([row("e", [], [])])["overall"]["metrics"]["target_position_accuracy"]
        )

    def test_ranking_order_and_incomplete_judgments(self):
        result = retrieval(
            [
                row("one", {"a": True, "b": False, "c": True}, ["a", "c"]),
                row("two", {"a": True, "b": False, "c": True}, ["b", "a"]),
                row("three", {"a": True, "b": None}, ["a", "b"], slice_="partial"),
                row("four", {"a": False}, ["a"], slice_="no-positives"),
            ],
            cutoff=2,
        )
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIsNone(result["overall"]["metrics"])
        expected = {"average_precision": 0.625, "recall": 0.75, "reciprocal_rank": 0.75}
        self.assertEqual(result["overall"]["observed_metrics"], expected)
        self.assertEqual(result["slices"]["validation"]["metrics"], expected)
        self.assertEqual(result["slices"]["no-positives"]["inapplicable"], 1)
        self.assertEqual(result["slices"]["partial"]["unobserved"], 1)

    def test_hash_cannot_alias_surrogates_and_unicode_scalars(self):
        scalar = chr(0x1F600)
        surrogates = chr(0xD83D) + chr(0xDE00)
        report = sequence([row(scalar, [scalar], [scalar])])
        self.assertEqual(report["overall"]["metrics"]["exact_match"], 1)
        controls = (
            (sequence, row(surrogates, [scalar], [scalar]), {}),
            (sequence, row(scalar, [scalar], [surrogates]), {}),
            (regression, row("a", 0, 0, slice_=surrogates), {}),
            (retrieval, row("a", {surrogates: True}, [surrogates]), {"cutoff": 1}),
        )
        for scorer, candidate, opts in controls:
            with self.assertRaises(LabError):
                scorer([candidate], **opts)

    def test_invalid_values_ids_and_ranks(self):
        controls = (
            (regression, [row("a", True, 1)], {}),
            (regression, [row("a", 1, 1), row("a", 1, 1)], {}),
            (regression, [row("a", 1, 1, interval=[2, 1])], {"intervals": True}),
            (sequence, [row("a", "one", ["one"])], {}),
            (sequence, [row("a", [0], ["0"])], {}),
            (retrieval, [row("a", {"c": True, "d": True}, ["c", "c"])], {"cutoff": 2}),
            (retrieval, [row("a", {"c": True}, ["x"])], {"cutoff": 1}),
            (retrieval, [row("a", {"c": 1}, ["c"])], {"cutoff": 1}),
        )
        for scorer, rows, opts in controls:
            with self.subTest(scorer=scorer.__name__, rows=rows), self.assertRaises(LabError):
                scorer(rows, **opts)
