import copy
import unittest

from tools.aggregate_training_value_v3 import aggregate_reports
from tools.run_training_value_v3 import _paired_summary
from tools.training_value_diagnostics import content_identity, interpretation, score_by_id


def phase(ids, scores):
    return {
        "episodes": [{"episode_id": k, "score": v, "parsed": True} for k, v in zip(ids, scores)],
        "mean": sum(scores) / len(scores),
        "parse_failures": 0,
    }


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.ref = phase(["a", "b"], [1.0, 1.0])
        self.tb = phase(["a", "b"], [0.0, 0.0])
        self.ta = phase(["a", "b"], [1.0, 1.0])
        self.hb = phase(["c", "d"], [0.0, 0.0])
        self.ha = phase(["c", "d"], [0.5, 0.5])

    def run_case(self, threshold=0.9):
        return interpretation(
            self.ref, self.tb, self.ta, self.hb, self.ha, minimum_reference_score=threshold
        )

    def test_good_observations_never_qualify(self):
        r = self.run_case()
        self.assertEqual(r["diagnosis"], "observed_training_and_heldout_score_improvement")
        self.assertEqual(r["qualification"], "NOT_QUALIFIED")

    def test_missing_or_failing_sanity(self):
        self.assertEqual(self.run_case(None)["diagnosis"], "pipeline_sanity_unassessed")
        self.ref = phase(["a", "b"], [0.8, 1.0])
        self.assertEqual(self.run_case()["diagnosis"], "target_scorer_sanity_failed")
        self.ref = phase(["a", "b"], [1.0, 1.0])
        self.ref["parse_failures"] = 1
        self.ref["episodes"][0]["parsed"] = False
        self.assertEqual(self.run_case()["diagnosis"], "target_scorer_sanity_failed")

    def test_missing_parse_sanity_does_not_become_failure_or_pass(self):
        del self.ref["parse_failures"]
        self.assertEqual(self.run_case()["diagnosis"], "pipeline_sanity_unassessed")
        self.ref["parse_failures"] = False
        with self.assertRaises(ValueError):
            self.run_case()

    def test_reference_parse_flags_must_match_count(self):
        self.ref["episodes"][0]["parsed"] = False
        with self.assertRaisesRegex(ValueError, "parse count"):
            self.run_case()
        del self.ref["episodes"][0]["parsed"]
        self.assertEqual(self.run_case()["diagnosis"], "pipeline_sanity_unassessed")

    def test_ceiling_is_not_fit_failure(self):
        self.tb = copy.deepcopy(self.ta)
        self.assertEqual(self.run_case()["diagnosis"], "already_at_training_score_ceiling")

    def test_no_gain_is_scoped_and_overfit_does_not_transfer(self):
        self.ha = copy.deepcopy(self.hb)
        self.assertEqual(
            self.run_case()["diagnosis"], "training_score_improvement_without_detected_transfer"
        )
        self.ta = copy.deepcopy(self.tb)
        self.assertEqual(self.run_case()["diagnosis"], "no_detected_training_score_improvement")

    def test_duplicate_ids_rejected_before_heavy_import(self):
        duplicate = phase(["a", "a"], [0.0, 1.0])
        with self.assertRaisesRegex(ValueError, "unique"):
            _paired_summary(duplicate, duplicate)
        reports = [
            {
                "model": "x",
                "training_seed": seed,
                "train_panel_id": "t",
                "heldout_panel_id": "h",
                "train_absolute_improvement": 0.0,
                "heldout_absolute_improvement": 0.0,
                "paired_heldout": {
                    "mean_delta": 0.0,
                    "median_delta": 0.0,
                    "proportion_improved": 0.0,
                    "episode_deltas": [
                        {"episode_id": "a", "delta": 0.0},
                        {"episode_id": "a", "delta": 0.0},
                    ],
                },
            }
            for seed in (1, 2, 3)
        ]
        with self.assertRaisesRegex(ValueError, "unique"):
            aggregate_reports(reports)

    def test_bad_scores_population_and_summary(self):
        for value in (None, float("nan"), True, -1.0, 2.0):
            p = phase(["a"], [0.0])
            p["episodes"][0]["score"] = value
            with self.assertRaises(ValueError):
                score_by_id(p)
        self.ha["episodes"][0]["episode_id"] = "other"
        with self.assertRaises(ValueError):
            self.run_case()
        self.ha = copy.deepcopy(self.hb)
        self.ta["mean"] = 0.0
        with self.assertRaises(ValueError):
            self.run_case()

    def test_content_changes_under_same_id_change_hash(self):
        class Episode:
            episode_id = "a"

            def __init__(self, value):
                self.value = value

            def model_dump(self, mode):
                return {"value": self.value}

        self.assertNotEqual(content_identity([Episode(1)]), content_identity([Episode(2)]))
        with self.assertRaises(ValueError):
            content_identity([Episode(1), Episode(2)])

    def test_bad_threshold(self):
        for threshold in (True, 0, float("nan"), 1.1):
            with self.assertRaises(ValueError):
                self.run_case(threshold)


if __name__ == "__main__":
    unittest.main()
