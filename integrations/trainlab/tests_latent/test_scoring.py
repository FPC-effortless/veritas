import copy
import os
import unittest
from pathlib import Path

import numpy as np
from trainlab.latent.scoring import (
    additive_nll_decomposition,
    calibration,
    classification_metrics,
    competence_retention_gates,
    correctness_transition_masks,
    counterfactual_metrics,
    summarize_counterfactual,
)
from trainlab.runner import LabError


class LatentScoringTests(unittest.TestCase):
    def test_full_vocabulary_failure_is_not_candidate_success(self):
        logits = [[2.0, 1.0, 3.0], [1.0, 2.0, 3.0]]
        result = counterfactual_metrics(
            logits, [0, 1], [9, 9], [0, 1], candidate_ids=[[0, 1], [0, 1]]
        )
        self.assertEqual(result["pair"]["candidate_complete_pair"].tolist(), [1.0])
        self.assertEqual(result["pair"]["native_complete_pair"].tolist(), [0.0])
        self.assertEqual(result["pair"]["same_native_answer"].tolist(), [1.0])

    def test_ties_are_exposed_and_candidate_ties_fail(self):
        scored = counterfactual_metrics(
            np.zeros((2, 3)), [0, 1], [0, 0], [0, 1], candidate_ids=[[0, 1], [0, 1]]
        )
        self.assertEqual(scored["pair"]["candidate_complete_pair"].tolist(), [0.0])
        self.assertTrue(scored["row"]["native_tie"].all())
        self.assertEqual(scored["row"]["candidate_prediction"].tolist(), [-1, -1])

    def test_pair_is_complete_and_stratum_bootstrap_uses_families(self):
        x = np.eye(2)[[0, 1, 0, 0]]
        result = counterfactual_metrics(
            x, [0, 1, 0, 1], [1, 1, 2, 2], [0, 1, 0, 1], unit_ids=[3, 3, 3, 3]
        )
        summary = summarize_counterfactual(result, draws=30)
        self.assertEqual(summary["all"]["units"], 1)
        self.assertEqual(summary["all"]["metrics"]["native_complete_pair"]["ci95"], [0.5, 0.5])
        with self.assertRaises(LabError):
            counterfactual_metrics(x, [0, 1, 0, 1], [1, 1, 1, 2], [0, 1, 0, 1])

    def test_probability_metrics_and_ece_boundary_cases(self):
        result = classification_metrics(np.zeros((2, 4)), [0, 3], answer_ids=[0, 1])
        np.testing.assert_allclose(result["target_nll"], np.log(4))
        np.testing.assert_allclose(result["multiclass_brier"], 0.75)
        np.testing.assert_allclose(result["answer_probability_mass"], 0.5)
        reliability = calibration([0.0, 0.1, 1.0], [0, 1, 1])
        self.assertEqual([reliability["bins"][i]["positions"] for i in (0, 1, 9)], [1, 1, 1])
        self.assertAlmostEqual(reliability["ece"], 0.3)
        self.assertIsNone(reliability["bins"][3]["accuracy"])

    def test_decomposition_uses_unconditional_record_means(self):
        a, b = np.asarray([[5.0, 1.0], [1.0, 1.0]]), np.ones((2, 2))
        masks = {"rare": np.asarray([[1, 0], [0, 0]]), "other": np.asarray([[0, 1], [1, 1]])}
        result = additive_nll_decomposition(a, b, masks, record_ids=[4, 4])
        self.assertEqual(result["contributions"]["rare"].tolist(), [1.0])
        self.assertEqual(result["fractions"]["rare"].tolist(), [0.25])
        self.assertEqual(result["total_difference"].tolist(), [1.0])
        with self.assertRaises(LabError):
            additive_nll_decomposition(a, b, {"missing": masks["rare"]})
        transitions = correctness_transition_masks([1, 0, 1, 0], [1, 1, 0, 0])
        for index, name in enumerate(("CC", "CW", "WC", "WW")):
            self.assertEqual(np.flatnonzero(transitions[name]).tolist(), [index])

    def test_gates_are_inclusive_and_require_the_same_checkpoint(self):
        task = [
            {
                "checkpoint_id": "c",
                "metric": "native_complete_pair",
                "delay": d,
                "stratum": s,
                "mean": 0.8,
                "ci95": [0.7, 0.9],
            }
            for d in (0, 8)
            for s in ("all", "shared_first", "shared_second", "neither")
        ]
        retention = [
            {
                "checkpoint_id": "c",
                "metric": "delta_target_nll",
                "domain": d,
                "mean": 0.05,
                "ci95": [0, 0.1],
            }
            for d in ("Shakespeare", "Alice")
        ]
        args = dict(
            checkpoint_id="c",
            task_cells=task,
            copy_control={"checkpoint_id": "c", "metric": "native_complete_pair", "mean": 0.8},
            retention_cells=retention,
        )
        self.assertEqual(competence_retention_gates(**args)["status"], "PASS")
        missing = args | {"retention_cells": retention[:1]}
        self.assertEqual(competence_retention_gates(**missing)["status"], "UNKNOWN")
        broken = copy.deepcopy(args)
        broken["task_cells"][3]["mean"] = 0.799999999
        self.assertEqual(competence_retention_gates(**broken)["status"], "FAIL")
        broken["task_cells"][3]["checkpoint_id"] = "other"
        with self.assertRaises(LabError):
            competence_retention_gates(**broken)
        wrong_metric = copy.deepcopy(args)
        wrong_metric["task_cells"][0]["metric"] = "candidate_complete_pair"
        with self.assertRaises(LabError):
            competence_retention_gates(**wrong_metric)
        del wrong_metric["task_cells"][0]["metric"]
        self.assertEqual(competence_retention_gates(**wrong_metric)["status"], "UNKNOWN")

    def test_nonfinite_and_invalid_target_inputs_fail(self):
        with self.assertRaises(LabError):
            classification_metrics([[0, float("nan")]], [0])
        with self.assertRaises(LabError):
            classification_metrics([[0.0, 1.0]], [2])
        with self.assertRaises(LabError):
            classification_metrics([[0.0, 1.0]], [1.0])

    @unittest.skipUnless(
        os.environ.get("VERITAS_LATENT_ARCHIVE_ROOT"), "optional saved-study parity"
    )
    def test_cycle006_saved_logit_metrics_match_archived_measurements(self):
        path = (
            Path(os.environ["VERITAS_LATENT_ARCHIVE_ROOT"])
            / "latent_transfer_006/outputs/language/csm_seed11__balanced_replay.npz"
        )
        with np.load(path, allow_pickle=False) as archive:
            rows = archive["snapshot_rows"]
            result = classification_metrics(
                archive["snapshot_logits"],
                archive["target_ids"][rows],
                answer_ids=list(range(65, 73)),
            )
            np.testing.assert_array_equal(
                result["native_prediction"], archive["predicted_byte"][rows]
            )
            for new, saved in (
                ("target_nll", "target_nll"),
                ("answer_probability_mass", "A_H_probability_mass"),
                ("max_probability", "max_probability"),
                ("multiclass_brier", "multiclass_brier"),
            ):
                np.testing.assert_allclose(result[new], archive[saved][rows], rtol=0, atol=2e-14)


if __name__ == "__main__":
    unittest.main()
