import copy
import unittest

from trainlab.experiment_diagnostics import (
    PACKS,
    benchmark_diagnostics,
    classification_diagnostics,
    comparison_ledger,
    paired_statistics,
    quality_cost,
    training_diagnostics,
)
from trainlab.runner import LabError

THRESHOLDS = {
    "min_loss_drop": 0.5,
    "min_update_norm": 0.0,
    "min_gradient_norm": 0.0,
    "min_classes": 2,
    "acquired_score": 0.9,
    "max_regression": 0.05,
}


def events():
    return [
        {
            "step": i + 1,
            "loss": loss,
            "finite": True,
            "gradient_norm": 0.5,
            "update_norm": 0.1,
            "missing_gradients": 0,
            "learning_rate": 0.1,
            "predicted_classes": 2,
            "validation_score": score,
        }
        for i, (loss, score) in enumerate(zip([1.0, 0.4, 0.1], [0.2, 0.95, 0.96]))
    ]


def statuses(report):
    return {c["name"]: c["status"] for c in report["coverage"]}


def benchmark():
    return [
        {
            "id": str(i),
            "group": str(i),
            "original": 0,
            "intervened": 1,
            "reference_original": 0,
            "reference_intervened": 1,
            "expect_change": True,
            "deficient_original": 0,
            "deficient_intervened": 0,
        }
        for i in range(3)
    ]


def arms():
    return [
        {
            "id": name,
            "attributes": {"data": "a" * 64, "route_labels": False},
            "seeds": [{"seed": n, "status": "succeeded"} for n in [1, 2]],
            "competence": {"status": "supported", "evidence_sha256": "b" * 64},
            "selection": {"split": "validation", "trials": 3, "rule": "lowest dev loss"},
        }
        for name in ("candidate", "baseline")
    ]


class ExperimentTests(unittest.TestCase):
    def test_benchmark_cannot_disable_perfect_shortcut_detection(self):
        with self.assertRaises(LabError):
            benchmark_diagnostics(benchmark(), max_control_accuracy=1)
        data = benchmark()
        for row in data:
            row["deficient_intervened"] = row["intervened"]
        self.assertEqual(statuses(benchmark_diagnostics(data))["deficient_control"], "FAILED")

    def test_partial_companion_channel_does_not_hide_known_fault(self):
        for event, check in [
            ({"missing_gradients": 3}, "gradients"),
            ({"gradient_norm": 0}, "gradients"),
            ({"update_norm": 0}, "updates"),
            ({"learning_rate": 0}, "updates"),
        ]:
            report = training_diagnostics(
                [{"step": 1, **event}], expected_steps=[1], thresholds=THRESHOLDS
            )
            self.assertEqual(statuses(report)[check], "FAILED")
            self.assertEqual(report["findings"][0]["step"], 1)

    def test_equal_null_attributes_are_unknown_not_matched(self):
        data = arms()
        for arm in data:
            arm["attributes"]["data"] = None
        report = comparison_ledger(data, required_seeds=[1, 2], matched_fields=["data"])
        self.assertEqual(statuses(report)["matched_information"], "INCONCLUSIVE")

    def test_pack_catalog_is_versioned_and_limited(self):
        self.assertEqual(len(PACKS), 6)
        for pack in PACKS.values():
            self.assertEqual(pack["version"], "1")
            self.assertTrue(pack["limitations"])

    def test_training_clean_and_earliest_faults(self):
        report = training_diagnostics(events(), expected_steps=[1, 2, 3], thresholds=THRESHOLDS)
        self.assertEqual(set(statuses(report).values()), {"TESTED"})
        bad = events()
        bad[1].update(finite=False, loss=None, update_norm=0, missing_gradients=1)
        report = training_diagnostics(bad, expected_steps=[1, 2, 3], thresholds=THRESHOLDS)
        self.assertEqual(statuses(report)["numerics"], "FAILED")
        self.assertEqual(statuses(report)["updates"], "FAILED")
        self.assertEqual(statuses(report)["gradients"], "FAILED")
        self.assertEqual(report["findings"][0]["step"], 2)

    def test_training_collapse_and_post_acquisition_regression(self):
        bad = events()
        bad[-1].update(predicted_classes=1, validation_score=0.5)
        status = statuses(
            training_diagnostics(bad, expected_steps=[1, 2, 3], thresholds=THRESHOLDS)
        )
        self.assertEqual(status["prediction_diversity"], "FAILED")
        self.assertEqual(status["retention"], "FAILED")

    def test_training_missing_channels_and_steps_do_not_pass(self):
        status = statuses(
            training_diagnostics(
                [{"step": 1}, {"step": 3}], expected_steps=[1, 2, 3], thresholds=THRESHOLDS
            )
        )
        self.assertEqual(status["step_coverage"], "INCONCLUSIVE")
        self.assertEqual(status["numerics"], "UNSUPPORTED")
        self.assertEqual(status["updates"], "UNSUPPORTED")

    def test_training_never_acquired_does_not_claim_forgetting(self):
        trace = events()
        for event in trace:
            event["validation_score"] = 0.1
        status = statuses(
            training_diagnostics(trace, expected_steps=[1, 2, 3], thresholds=THRESHOLDS)
        )
        self.assertEqual(status["acquisition"], "FAILED")
        self.assertEqual(status["retention"], "INCONCLUSIVE")

    def test_training_bad_order_and_nonfinite_input_rejected(self):
        for trace in (
            events()[::-1],
            events() + [events()[0]],
            [{"step": 1, "loss": float("nan")}],
        ):
            with self.assertRaises(LabError):
                training_diagnostics(trace, expected_steps=[1, 2, 3], thresholds=THRESHOLDS)

    def test_training_partial_progress_and_no_post_acquisition_observation(self):
        report = training_diagnostics(events()[:1], expected_steps=[1, 2, 3], thresholds=THRESHOLDS)
        self.assertEqual(statuses(report)["acquisition"], "INCONCLUSIVE")
        trace = events()
        trace[1]["validation_score"] = 0.2
        report = training_diagnostics(trace, expected_steps=[1, 2, 3], thresholds=THRESHOLDS)
        self.assertEqual(statuses(report)["retention"], "INCONCLUSIVE")

    def test_benchmark_clean_and_nonobservable_control(self):
        self.assertEqual(set(statuses(benchmark_diagnostics(benchmark())).values()), {"TESTED"})
        data = benchmark()
        for row in data:
            row.update(intervened=0, reference_intervened=0)
        status = statuses(benchmark_diagnostics(data))
        self.assertEqual(status["sensitivity"], "FAILED")
        self.assertEqual(status["intervention_expectations"], "FAILED")
        self.assertEqual(status["deficient_control"], "FAILED")

    def test_benchmark_oracle_disagreement_and_correlated_groups(self):
        data = benchmark()
        for row in data:
            row["group"] = "one"
        data[1]["reference_original"] = 7
        status = statuses(benchmark_diagnostics(data))
        self.assertEqual(status["oracle_parity"], "FAILED")
        self.assertEqual(status["sensitivity"], "FAILED")

    def test_benchmark_typed_values_are_not_python_equal(self):
        data = benchmark()
        data[0]["reference_original"] = False
        self.assertEqual(statuses(benchmark_diagnostics(data))["oracle_parity"], "FAILED")

    def test_ledger_retains_mismatches_missing_failed_seeds_and_unknown_competence(self):
        good = arms()
        kwargs = {"required_seeds": [1, 2], "matched_fields": ["data", "route_labels"]}
        self.assertEqual(set(statuses(comparison_ledger(good, **kwargs)).values()), {"TESTED"})
        bad = arms()
        bad[0]["attributes"]["route_labels"] = True
        bad[1]["seeds"] = [{"seed": 1, "status": "failed"}]
        bad[1]["competence"] = {"status": "unknown", "evidence_sha256": None}
        report = comparison_ledger(bad, **kwargs)
        self.assertEqual(statuses(report)["matched_information"], "FAILED")
        self.assertEqual(statuses(report)["seed_completion"], "FAILED")
        self.assertEqual(statuses(report)["competence_evidence"], "INCONCLUSIVE")
        self.assertEqual(report["observations"]["arms"], bad)

    def test_ledger_hidden_selection_and_missing_dimensions(self):
        bad = arms()
        bad[0]["selection"]["split"] = "test"
        del bad[1]["attributes"]["route_labels"]
        status = statuses(
            comparison_ledger(bad, required_seeds=[1, 2], matched_fields=["data", "route_labels"])
        )
        self.assertEqual(status["selection"], "FAILED")
        self.assertEqual(status["matched_information"], "INCONCLUSIVE")

    def test_ledger_arm_with_no_executions_is_retained_as_incomplete(self):
        data = arms()
        data[1]["seeds"] = []
        report = comparison_ledger(data, required_seeds=[1, 2], matched_fields=["data"])
        self.assertEqual(statuses(report)["seed_completion"], "FAILED")
        self.assertEqual(report["observations"]["arms"][1]["seeds"], [])

    def paired(self):
        return [
            {"unit": unit, "seed": seed, "candidate": value, "baseline": value - 0.1}
            for unit, value in zip(["a", "b", "c"], [0.4, 0.6, 0.8])
            for seed in [1, 2]
        ]

    def test_paired_bootstrap_preserves_pairs_and_seed_panel(self):
        report = paired_statistics(
            self.paired(),
            required_units=["a", "b", "c"],
            required_seeds=[1, 2],
            draws=200,
            rng_seed=3,
        )
        self.assertAlmostEqual(report["observations"]["effect"], 0.1)
        for value in report["observations"]["interval"]:
            self.assertAlmostEqual(value, 0.1)
        self.assertEqual(
            report,
            paired_statistics(
                self.paired(),
                required_units=["a", "b", "c"],
                required_seeds=[1, 2],
                draws=200,
                rng_seed=3,
            ),
        )

    def test_paired_missing_duplicate_or_single_unit_not_qualified(self):
        for rows in (self.paired()[:-1], self.paired() + [self.paired()[0]]):
            with self.assertRaises(LabError):
                paired_statistics(
                    rows, required_units=["a", "b", "c"], required_seeds=[1, 2], draws=200
                )
        report = paired_statistics(
            self.paired()[:2], required_units=["a"], required_seeds=[1, 2], draws=200
        )
        self.assertEqual(statuses(report)["uncertainty"], "INCONCLUSIVE")
        self.assertIsNone(report["observations"]["interval"])

    def test_paired_adjustment_and_reorder_invariance(self):
        rows = self.paired()
        rows[-1]["candidate"] += 0.3
        first = paired_statistics(
            rows, required_units=["a", "b", "c"], required_seeds=[1, 2], draws=200, comparisons=3
        )
        second = paired_statistics(
            rows[::-1],
            required_units=["a", "b", "c"],
            required_seeds=[1, 2],
            draws=200,
            comparisons=3,
        )
        self.assertEqual(first["observations"], second["observations"])
        self.assertAlmostEqual(first["observations"]["interval_alpha"], 0.05 / 3)

    def test_paired_absent_whole_unit_and_unresolved_tail(self):
        with self.assertRaises(LabError):
            paired_statistics(
                self.paired()[:4], required_units=["a", "b", "c"], required_seeds=[1, 2]
            )
        report = paired_statistics(
            self.paired(),
            required_units=["a", "b", "c"],
            required_seeds=[1, 2],
            draws=100,
            comparisons=100,
        )
        self.assertEqual(statuses(report)["uncertainty"], "INCONCLUSIVE")

    def test_classification_metrics_and_slice_errors(self):
        rows = [
            {
                "id": "a",
                "label": "yes",
                "prediction": "yes",
                "probabilities": [0.2, 0.8],
                "slice": "one",
            },
            {
                "id": "b",
                "label": "no",
                "prediction": "yes",
                "probabilities": [0.3, 0.7],
                "slice": "two",
            },
        ]
        report = classification_diagnostics(rows, classes=["no", "yes"], bins=2)
        self.assertEqual(report["observations"]["accuracy"], 0.5)
        self.assertAlmostEqual(report["observations"]["brier"], 0.53)
        self.assertAlmostEqual(report["observations"]["ece"], 0.25)
        self.assertEqual(report["observations"]["slices"]["two"]["accuracy"], 0)
        self.assertEqual(report["observations"]["error_ids"], ["b"])

    def test_classification_missing_probability_and_zero_true_probability(self):
        rows = [{"id": "a", "label": "no", "prediction": "yes"}]
        report = classification_diagnostics(rows, classes=["no", "yes"])
        self.assertEqual(statuses(report)["calibration"], "UNSUPPORTED")
        rows[0]["probabilities"] = [0, 1]
        report = classification_diagnostics(rows, classes=["no", "yes"])
        self.assertIsNone(report["observations"]["nll"])
        self.assertEqual(report["observations"]["zero_true_probability"], 1)
        rows[0]["probabilities"] = [0.5, 0.8]
        with self.assertRaises(LabError):
            classification_diagnostics(rows, classes=["no", "yes"])

    def test_classification_unknown_labels_are_visible(self):
        report = classification_diagnostics(
            [{"id": "a", "prediction": "yes"}], classes=["no", "yes"]
        )
        self.assertEqual(statuses(report)["performance"], "UNSUPPORTED")
        self.assertIsNone(report["observations"]["accuracy"])

    def costs(self):
        return [
            {
                "id": name,
                "quality": quality,
                "session_seconds": seconds,
                "workload_sha256": "a" * 64,
                "hardware_sha256": "b" * 64,
                "boundary_sha256": "c" * 64,
                "cost_status": "MEASURED",
            }
            for name, quality, seconds in [("a", 0.8, 1), ("b", 0.9, 2), ("c", 0.7, 3)]
        ]

    def test_quality_cost_front_and_context_mismatch(self):
        report = quality_cost(self.costs())
        self.assertEqual(report["observations"]["pareto_ids"], ["a", "b"])
        bad = self.costs()
        bad[0]["boundary_sha256"] = "d" * 64
        report = quality_cost(bad)
        self.assertEqual(statuses(report)["matched_context"], "FAILED")
        self.assertIsNone(report["observations"]["pareto_ids"])

    def test_quality_cost_incomplete_measurement_cannot_win(self):
        bad = self.costs()
        bad[0].update(cost_status="INCOMPLETE", session_seconds=None)
        report = quality_cost(bad)
        self.assertEqual(statuses(report)["cost_coverage"], "INCONCLUSIVE")
        self.assertIsNone(report["observations"]["pareto_ids"])

    def test_reports_bind_input_and_do_not_alias_it(self):
        original = arms()
        report = comparison_ledger(original, required_seeds=[1, 2], matched_fields=["data"])
        preserved = copy.deepcopy(report)
        original[0]["attributes"]["data"] = "changed"
        self.assertEqual(report, preserved)
        self.assertEqual(report["scientific_qualification"], "NOT_QUALIFIED")


if __name__ == "__main__":
    unittest.main()
