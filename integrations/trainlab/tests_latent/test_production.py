"""Failure cases for private evidence publication and bounded numerical work."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from trainlab.latent import geometry
from trainlab.latent.artifacts import seal_bundle
from trainlab.latent.suite import export_bundle
from trainlab.runner import LabError, contained_file


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "bundle"
        self.source.mkdir(mode=0o700)
        (self.source / "observation.json").write_text('{"constructed":true}')
        self.pin = seal_bundle(
            self.source, plan_sha256="a" * 64, implementation={}, state="COMPLETE"
        )

    @unittest.skipUnless(os.name == "posix", "POSIX file permission contract")
    def test_export_remains_private_under_permissive_umask(self):
        previous = os.umask(0o022)
        try:
            destination = self.root / "evidence.zip"
            result = export_bundle(self.source, self.pin, destination)
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(result["files"], 3)
        self.assertFalse(list(self.root.glob(".latent-export-*")))

    def test_changed_capture_never_publishes_final_archive(self):
        destination = self.root / "evidence.zip"

        def mutate(root, name):
            path = contained_file(root, name)
            if name == "observation.json":
                path.write_text('{"constructed":false}')
            return path

        with patch("trainlab.latent.suite.contained_file", side_effect=mutate):
            with self.assertRaisesRegex(LabError, "pinned evidence"):
                export_bundle(self.source, self.pin, destination)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob(".latent-export-*")))

    def test_export_never_overwrites_a_racing_destination(self):
        destination = self.root / "evidence.zip"
        link = os.link

        def compete(source, target):
            Path(target).write_bytes(b"other owner's archive")
            return link(source, target)

        with patch("trainlab.latent.suite.os.link", side_effect=compete):
            with self.assertRaises(FileExistsError):
                export_bundle(self.source, self.pin, destination)
        self.assertEqual(destination.read_bytes(), b"other owner's archive")
        self.assertFalse(list(self.root.glob(".latent-export-*")))

    def test_wide_pca_rejects_before_full_basis_allocation(self):
        with patch(
            "trainlab.latent.geometry.np.linalg.svd", side_effect=AssertionError("allocation")
        ):
            with self.assertRaisesRegex(LabError, "workspace"):
                geometry.pca_fit(np.zeros((2, 10_000)))

    def test_large_random_basis_rejects_before_allocation(self):
        with patch(
            "trainlab.latent.geometry.np.random.default_rng",
            side_effect=AssertionError("allocation"),
        ):
            with self.assertRaisesRegex(LabError, "workspace"):
                geometry.random_subspace(10_000)

    def test_cka_draws_and_representation_pairs_share_workspace_budget(self):
        values = {f"view{i}": [[0.0], [1.0], [2.0]] for i in range(1000)}
        with patch(
            "trainlab.latent.statistics.make_bootstrap", side_effect=AssertionError("allocation")
        ):
            with self.assertRaisesRegex(LabError, "workspace"):
                geometry.cka_bootstrap(values, ["a", "b", "c"], draws=5000)

    def test_permutation_draws_reject_before_allocation(self):
        with patch("trainlab.latent.geometry.np.tile", side_effect=AssertionError("allocation")):
            with self.assertRaisesRegex(LabError, "workspace"):
                geometry.conditional_permutations([1, 1], ["d", "d"], draws=10**12)

    def test_wide_cka_matches_feature_space_estimand(self):
        rng = np.random.default_rng(37)
        left, right = rng.normal(size=(7, 128)), rng.normal(size=(7, 96))
        a, b = left - left.mean(axis=0), right - right.mean(axis=0)
        expected = np.square(a.T @ b).sum() / (np.linalg.norm(a.T @ a) * np.linalg.norm(b.T @ b))
        self.assertAlmostEqual(geometry.linear_cka(left, right), expected, places=13)

    def test_numerical_budget_rejects_small_integer_arrays_before_float_conversion(self):
        with patch("trainlab.latent.geometry.MAX_WORKSPACE_ELEMENTS", 5):
            with self.assertRaisesRegex(LabError, "workspace"):
                geometry.pca_fit(np.zeros((2, 3), dtype=np.uint8))

    def test_export_budget_is_checked_before_creating_an_archive(self):
        destination = self.root / "evidence.zip"
        with patch("trainlab.latent.suite.MAX_EXPORT_BYTES", 1):
            with self.assertRaisesRegex(LabError, "byte limit"):
                export_bundle(self.source, self.pin, destination)
        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob(".latent-export-*")))


if __name__ == "__main__":
    unittest.main()
