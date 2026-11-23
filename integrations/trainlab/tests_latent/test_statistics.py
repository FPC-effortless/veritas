import json
import os
import unittest
from pathlib import Path

import numpy as np
from trainlab.latent.statistics import cluster_means, fixed_seed_mean, make_bootstrap, record_means
from trainlab.runner import LabError


class LatentStatisticsTests(unittest.TestCase):
    def test_paired_identity_and_constant_shift_have_exact_intervals(self):
        plan = make_bootstrap(["a", "b", "c"], draws=100, seed=12)
        values = np.asarray([0.0, 1.0, 4.0])
        self.assertEqual(plan.paired(values, values)["ci95"], [0.0, 0.0])
        self.assertEqual(plan.paired(values + 2, values)["ci95"], [2.0, 2.0])
        self.assertEqual(
            plan.difference_in_differences(values, values, values, values)["mean"], 0.0
        )
        with self.assertRaises(LabError):
            plan.paired(values, values, right_ids=["b", "a", "c"])

    def test_stratum_quotas_are_preserved_and_archived_draws_validated(self):
        plan = make_bootstrap([1, 2, 3], strata=[0, 1, 1], draws=50, seed=4)
        labels = np.asarray([0, 1, 1])
        self.assertTrue(np.all((labels[plan.indices] == 0).sum(axis=1) == 1))
        restored = make_bootstrap([1, 2, 3], strata=labels, draws=50, seed=4, indices=plan.indices)
        self.assertEqual(plan.manifest(), restored.manifest())
        broken = plan.indices.copy()
        broken[0] = 0
        with self.assertRaises(LabError):
            make_bootstrap([1, 2, 3], strata=labels, draws=50, indices=broken)
        with self.assertRaises(ValueError):
            plan.indices[0, 0] = 1

    def test_records_are_not_weighted_by_window_count(self):
        ids, means = record_means([[0.0, 0.0], [0.0, 0.0], [1.0, 1.0]], [10, 10, 20])
        np.testing.assert_array_equal(ids, [10, 20])
        np.testing.assert_array_equal(means, [0.0, 1.0])
        self.assertEqual(make_bootstrap(ids, draws=20).estimate(means)["mean"], 0.5)
        np.testing.assert_array_equal(cluster_means([1, 3, 8], [1, 1, 2])[1], [2, 8])

    def test_fixed_seeds_are_averaged_before_resampling(self):
        values = np.asarray([[0, 4], [4, 0]])
        means = fixed_seed_mean(values, [23, 11], [11, 23])
        self.assertEqual(make_bootstrap([1, 2], draws=20).estimate(means)["ci95"], [2.0, 2.0])
        with self.assertRaises(LabError):
            fixed_seed_mean(values, [11, 11], [11, 23])

    def test_invalid_and_missing_values_are_not_imputed(self):
        for values in ([1, float("nan")], [1, float("inf")]):
            with self.assertRaises(LabError):
                make_bootstrap([1, 2], draws=20).estimate(values)
        with self.assertRaises(LabError):
            make_bootstrap([1, 1])
        with self.assertRaises(LabError):
            make_bootstrap([1, "2"])
        with self.assertRaises(LabError):
            cluster_means(np.empty((2, 0)), [1, 2])
        with self.assertRaises(LabError):
            make_bootstrap([1, 2], draws=20).contrast({"a": [0, 1]}, {"missing": 1})

    @unittest.skipUnless(
        os.environ.get("VERITAS_LATENT_ARCHIVE_ROOT"), "optional saved-study parity"
    )
    def test_cycle006_archived_family_statistics_are_exact(self):
        root = Path(os.environ["VERITAS_LATENT_ARCHIVE_ROOT"]) / "latent_transfer_006"
        with np.load(root / "analysis/position/family_values.npz", allow_pickle=False) as saved:
            values = saved["values"][0, 0]
            ids, labels = saved["family_ids"], saved["family_strata"]
            model, condition = str(saved["model_ids"][0]), str(saved["condition_names"][0])
            metrics = saved["metric_names"].tolist()
        with np.load(
            root / "analysis/position/family_bootstrap_draws.npz", allow_pickle=False
        ) as saved:
            plan = make_bootstrap(ids, strata=labels, indices=saved["all"])
        result = plan.estimate(values)
        expected = json.loads((root / "analysis/position/condition_summaries.json").read_text())[
            "models"
        ][model]["conditions"][condition]["estimates"]["all"]
        for i, metric in enumerate(metrics):
            self.assertEqual(result["mean"][i], expected[metric]["mean"])
            self.assertEqual([result["ci95"][0][i], result["ci95"][1][i]], expected[metric]["ci95"])


if __name__ == "__main__":
    unittest.main()
