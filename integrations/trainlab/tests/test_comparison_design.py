import copy
import unittest

from trainlab.comparison_design import analyze, freeze_design
from trainlab.runner import LabError

CONTEXT = "a" * 64
WINDOW = "b" * 64


class ComparisonDesignTests(unittest.TestCase):
    def plan(self, **changes):
        inputs = {
            "units": ["a", "b", "c"],
            "seeds": [10, 20, 30],
            "comparisons": ["first", "second"],
            "context_sha256": CONTEXT,
            "analysis_window": WINDOW,
            "selection": "FIXED",
        }
        return freeze_design(**(inputs | changes))

    def rows(self):
        return [
            {
                "comparison": comparison,
                "unit": unit,
                "seed": seed,
                "status": "OBSERVED",
                "candidate": float(seed) if comparison == "first" else float(ui),
                "baseline": 0.0,
            }
            for comparison in ("first", "second")
            for ui, unit in enumerate(("a", "b", "c"))
            for seed in (10, 20, 30)
        ]

    def run_report(self, rows=None, **changes):
        frozen = self.plan(**changes)
        return analyze(rows=self.rows() if rows is None else rows, context_sha256=CONTEXT, **frozen)

    def test_resamples_the_axes_that_vary(self):
        report = self.run_report()
        self.assertEqual(report["status"], "TESTED")
        a = report["comparisons"]["first"]
        b = report["comparisons"]["second"]
        self.assertEqual(a["effect"], 20)
        self.assertEqual(a["intervals"]["unit_only"], [20, 20])
        self.assertLess(a["intervals"]["seed_only"][0], 20)
        self.assertEqual(b["effect"], 1)
        self.assertEqual(b["intervals"]["seed_only"], [1, 1])
        self.assertLess(b["intervals"]["unit_only"][0], 1)
        self.assertEqual(report["tail_probability"], 0.0125)

    def test_observation_order_does_not_change_result(self):
        self.assertEqual(self.run_report(), self.run_report(list(reversed(self.rows()))))

    def test_a_failed_cell_prevents_family_intervals_without_imputing(self):
        rows = self.rows()
        rows[0].update(status="FAILED", candidate=None, baseline=None)
        del rows[1]
        report = self.run_report(rows)
        a = report["comparisons"]["first"]
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual((a["failed"], a["missing"], a["observed"]), (1, 1, 7))
        self.assertIsNone(a["effect"])
        self.assertIsNone(report["comparisons"]["second"]["intervals"])

    def test_no_interval_under_adaptive_selection_or_unresolved_tail(self):
        for changes in (
            {"selection": "ADAPTIVE"},
            {"selection": "UNKNOWN"},
            {"alpha": 0.001, "draws": 100},
        ):
            with self.subTest(changes=changes):
                result = self.run_report(**changes)
                self.assertEqual(result["status"], "INCONCLUSIVE")
                self.assertEqual(result["comparisons"]["first"]["effect"], 20)
                self.assertIsNone(result["comparisons"]["first"]["intervals"])

    def test_pin_context_and_duplicate_validation(self):
        plan = self.plan()
        with self.assertRaises(LabError):
            analyze(rows=self.rows(), context_sha256="d" * 64, **plan)
        changed = copy.deepcopy(plan)
        changed["design"]["alpha"] = 0.2
        with self.assertRaises(LabError):
            analyze(rows=self.rows(), context_sha256=CONTEXT, **changed)
        with self.assertRaises(LabError):
            self.run_report(self.rows() + self.rows()[:1])

    def test_constant_panel_uses_identical_bounds(self):
        rows = self.rows()
        for row in rows:
            row["candidate"] = 0.1
            row["baseline"] = 0
        result = self.run_report(rows)
        for report in result["comparisons"].values():
            self.assertEqual(report["effect"], 0.1)
            self.assertTrue(all(v == [0.1, 0.1] for v in report["intervals"].values()))

    def test_exact_integer_cancellation_and_result_ownership(self):
        rows = self.rows()
        for index, row in enumerate(rows):
            row["candidate"] = (10**20 + 1, -(10**20))[index] if index < 2 else 0
        result = self.run_report(rows)
        self.assertEqual(result["comparisons"]["first"]["effect"], 1 / 9)
        raw = result["comparisons"]["first"]["cells"][0]
        rows[0]["candidate"] = 0
        self.assertEqual(raw["candidate"], 10**20 + 1)

    def test_crossed_interaction_survives_both_flat_marginals(self):
        plan = self.plan(units=["x", "y"], seeds=[1, 2], comparisons=["interaction"])
        rows = [
            {
                "comparison": "interaction",
                "unit": u,
                "seed": seed,
                "status": "OBSERVED",
                "candidate": 1 if (u, seed) in (("x", 1), ("y", 2)) else -1,
                "baseline": 0,
            }
            for u in ("x", "y")
            for seed in (1, 2)
        ]
        report = analyze(rows=rows, context_sha256=CONTEXT, **plan)["comparisons"]["interaction"]
        self.assertEqual(
            report["intervals"],
            {
                "crossed": [-1, 1],
                "unit_only": [0, 0],
                "seed_only": [0, 0],
            },
        )

    def test_float_effect_cancellation_before_sum(self):
        rows = self.rows()
        for row in rows:
            row.update(candidate=0.0, baseline=0.0)
        rows[0].update(candidate=1e16, baseline=1.0)
        rows[1].update(candidate=-1e16)
        self.assertEqual(self.run_report(rows)["comparisons"]["first"]["effect"], -1 / 9)
