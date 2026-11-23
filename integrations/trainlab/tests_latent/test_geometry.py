import json
import unittest
from pathlib import Path

import numpy as np
from trainlab.latent import geometry as g
from trainlab.runner import LabError


class GeometryTests(unittest.TestCase):
    def test_pca_full_rank_and_extra_norm_scalar(self):
        x = np.array([[1.0, 8.0, 2.0], [2.0, -4.0, 1.0], [7.0, 1.0, -3.0], [-2.0, 0.0, 4.0]])
        report, fit = g.pca_fit(x)
        np.testing.assert_allclose(g.pca_reconstruct(x, fit, 3), x, atol=1e-12)
        matched = g.pca_reconstruct(x, fit, 1, norm_match=True)
        np.testing.assert_allclose(
            np.linalg.norm(matched - fit["mean"], axis=1),
            np.linalg.norm(x - fit["mean"], axis=1),
            atol=1e-12,
        )
        self.assertEqual(report["dimensions"], 3)
        self.assertEqual(g.pca_reconstruct(x, fit, 0).shape, x.shape)
        np.testing.assert_allclose(
            g.random_subspace(3, seed=2).T @ g.random_subspace(3, seed=2), np.eye(3), atol=1e-12
        )

    def test_decoder_aware_same_rank_preserves_low_variance_signal(self):
        cal = np.array([[a, b] for a in [-10.0, -9.0, 9.0, 10.0] for b in [-0.1, 0.1]])
        weights = np.array([[0.0, 100.0], [0.0, -100.0]])
        _, plain = g.pca_fit(cal)
        report, aware = g.decoder_metric_fit(cal, weights, 1)
        p = g.pca_reconstruct(cal, plain, 1)
        a = g.decoder_metric_reconstruct(cal, aware)
        self.assertLess(
            np.square((a - cal) @ weights.T).sum(), np.square((p - cal) @ weights.T).sum() * 1e-8
        )
        self.assertLess(report["calibration_objective"], report["plain_pca_objective"])
        self.assertEqual(report["rank"], 1)
        _, full = g.decoder_metric_fit(cal, weights, 2)
        np.testing.assert_allclose(g.decoder_metric_reconstruct(cal, full), cal, atol=1e-10)

    def test_cka_invariance_and_degeneracy(self):
        x = np.random.default_rng(3).normal(size=(30, 4))
        q = g.random_subspace(4, seed=4)
        self.assertAlmostEqual(g.linear_cka(x, 7 * x @ q + 5), 1.0)
        self.assertIsNone(g.linear_cka(x, np.ones((30, 1))))
        self.assertIsNone(g.linear_cka(x, np.tile([0.1, 0.7], (30, 1))))
        with self.assertRaises(LabError):
            g.linear_cka(x, x[:-1])

    def test_neighborhood_ties_are_deterministic(self):
        x = np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [4.0, 4.0], [5.0, 5.0]])
        report = g.neighborhood_quality(x, x[:, :1], ks=(1, 2))
        self.assertEqual(report["k1"]["trustworthiness"], 1.0)
        self.assertEqual(report["k2"]["neighbor_overlap"], 1.0)
        self.assertIn("stable", report["tie_breaking"])

    def test_conditioning_uses_only_supported_calibration_records(self):
        tokens = np.array([0, 0, 1, 0, 0, 2])
        clusters = np.array(["a", "b", "a", "c", "d", "c"])
        folds = np.array([0, 0, 0, 1, 1, 1])
        x = np.array([[1.0, 0.0], [3.0, 0.0], [90.0, 2.0], [2.0, 1.0], [4.0, 1.0], [-90.0, 3.0]])
        report, arrays = g.token_conditioned_geometry(
            {"a": x, "b": 2 * x},
            tokens,
            ["d"] * 6,
            clusters,
            folds,
            positions=[1, 1, 2, 1, 1, 2],
            bootstrap_draws=16,
            permutation_draws=3,
        )
        self.assertEqual(report["folds"][1]["coverage"]["eligible_rows"], 2)
        self.assertEqual(report["folds"][1]["coverage"]["unseen_rows"], 1)
        np.testing.assert_array_equal(arrays["fold_1_eligible_indices"], [3, 4])
        np.testing.assert_allclose(
            arrays["fold_1_a_token_component"][:, 0], [2 - x[:3, 0].mean()] * 2
        )
        self.assertIn("token_only_reconstruction_r2_ci95", report["folds"][1])
        json.dumps(report, allow_nan=False)
        with self.assertRaises(LabError):
            g.token_conditioned_geometry({"a": x}, tokens, ["d"] * 6, ["a"] * 6, folds)

    def test_shuffle_and_matched_pairs_preserve_declared_nuisances(self):
        tokens = np.array([1, 1, 1, 1, 2, 2])
        domains = np.array(["x"] * 6)
        records = np.array(["a", "a", "b", "b", "a", "b"])
        positions = np.array([1, 2, 1, 2, 3, 3])
        report, arrays = g.conditional_permutations(
            tokens, domains, records, positions=positions, position_bin=1, draws=5, seed=2
        )
        for p in arrays["permutations"]:
            np.testing.assert_array_equal(np.sort(p), np.arange(6))
            np.testing.assert_array_equal(tokens[p], tokens)
            np.testing.assert_array_equal(positions[p], positions)
        self.assertFalse(report["provides_p_value"])
        _, arrays = g.matched_context_pairs(
            tokens, domains, records, positions, position_bin=1, seed=2
        )
        pairs = arrays["pairs"]
        self.assertEqual(len(np.unique(pairs)), pairs.size)
        self.assertTrue(np.all(records[pairs[:, 0]] != records[pairs[:, 1]]))

    def test_whole_window_derangement_preserves_position_and_domain(self):
        sequence = ["a", "b", "a", "b", "c", "c"]
        domains = np.array(["x", "x", "x", "x", "y", "y"])
        positions = np.array([1, 1, 0, 0, 0, 1])
        report, arrays = g.window_derangement(sequence, domains, positions, seed=2)
        permutation = arrays["permutation"]
        np.testing.assert_array_equal(positions[permutation], positions)
        np.testing.assert_array_equal(domains[permutation], domains)
        self.assertAlmostEqual(report["fraction_fixed_rows"], 1 / 3)

    def test_bootstrap_cka_equals_expanded_records_including_recentering(self):
        x = np.array([[1.0, 2.0], [3.0, 5.0], [6.0, 2.0], [9.0, -1.0], [2.0, 4.0]])
        y = np.array([[2.0, 1.0], [-2.0, 5.0], [4.0, 1.0], [1.0, 8.0], [-3.0, 1.0]])
        clusters = np.array(["a", "a", "b", "b", "c"])
        report, arrays = g.cka_bootstrap({"x": x, "y": y}, clusters, draws=32, seed=3)
        for i, draw in enumerate(arrays["cluster_draws"]):
            rows = np.concatenate([np.flatnonzero(clusters == ["a", "b", "c"][j]) for j in draw])
            expected = g.linear_cka(x[rows], y[rows])
            if expected is not None:
                self.assertTrue(arrays["valid"][i, 0, 1])
                self.assertAlmostEqual(arrays["bootstrap"][i, 0, 1], expected, places=10)
            else:
                self.assertFalse(arrays["valid"][i, 0, 1])
        json.dumps(report, allow_nan=False)

    def test_degenerate_bootstrap_is_masked_not_reported_as_similarity(self):
        _, arrays = g.cka_bootstrap(
            {"x": [[0.0], [1.0]], "y": [[1.0], [0.0]]}, ["a", "b"], draws=32, seed=3
        )
        repeated = arrays["cluster_draws"][:, 0] == arrays["cluster_draws"][:, 1]
        self.assertTrue(repeated.any())
        self.assertFalse(arrays["valid"][repeated].any())

    def test_crossfit_compression_retains_native_decoder_and_split_integrity(self):
        x = np.array([[a, b] for a in [-10.0, -9.0, 9.0, 10.0] for b in [-0.1, 0.1]])
        y = (x[:, 1] < 0).astype(int)
        weights = np.array([[0.0, 100.0], [0.0, -100.0]])
        seen = []

        def decode(h, row_indices):
            seen.append(row_indices.copy())
            return 15 * np.tanh((h @ weights.T + np.array([0.3, -0.3])) / 15)

        folds = [0, 0, 1, 1, 0, 0, 1, 1]
        report, arrays = g.compression_diagnostic(
            x,
            y,
            decode,
            folds=folds,
            clusters=np.arange(8),
            ranks=(0, 1, 2),
            random_seeds=(11,),
            decoder_weights=weights,
        )
        self.assertTrue(report["full_rank_replay"]["passed"])
        self.assertTrue(report["fit_targets_used"] is False)
        self.assertEqual(arrays["nll"].shape[1], 8)
        self.assertTrue(any(len(ix) == 4 for ix in seen))
        self.assertTrue(all(isinstance(i, np.ndarray) for i in seen))
        json.dumps(report, allow_nan=False)
        with self.assertRaises(LabError):
            g.compression_diagnostic(x, y, decode, folds=folds, clusters=["a"] * 8)

    def test_nonfinite_and_invalid_rank_fail_closed(self):
        with self.assertRaises(LabError):
            g.pca_fit([[1.0, np.nan], [2.0, 1.0]])
        _, fit = g.pca_fit([[1.0, 2.0], [2.0, 1.0]])
        with self.assertRaises(LabError):
            g.pca_reconstruct([[1.0, 2.0]], fit, 3)
        with self.assertRaises(LabError):
            g.pca_fit([[1 + 2j, 2], [3, 4]])

    def test_optional_tsne_records_original_space_fidelity(self):
        try:
            import sklearn  # noqa: F401
        except ImportError:
            self.skipTest("optional projection dependency is not installed")
        x = np.random.default_rng(5).normal(size=(12, 3))
        report, arrays = g.tsne_projection(x, perplexity=3, iterations=300, neighbors=(2,))
        self.assertEqual(arrays["coordinates"].shape, (12, 2))
        self.assertEqual(report["quality"]["metric"], "euclidean_original_dimensions")
        self.assertTrue(np.isfinite(report["kl_divergence"]))

    def test_saved_csm_cka_when_study_is_available(self):
        root = Path(__file__).resolve().parents[4] / "latent_atlas"
        reference = root / "output/csm_cka.json"
        a = root / "work/csm/csm_seed11.npz"
        b = root / "work/csm/csm_seed23.npz"
        if not all(p.is_file() for p in (reference, a, b)):
            self.skipTest("archived study is not part of the installed package")
        saved = json.loads(reference.read_text())
        with np.load(a, allow_pickle=False) as za, np.load(b, allow_pickle=False) as zb:
            actual = g.linear_cka(za["hidden"], zb["hidden"])
        ia, ib = saved["model_ids"].index("csm_seed11"), saved["model_ids"].index("csm_seed23")
        self.assertAlmostEqual(actual, saved["linear_cka"][ia][ib], places=12)


if __name__ == "__main__":
    unittest.main()
