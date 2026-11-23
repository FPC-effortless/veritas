import unittest

import numpy as np
from trainlab.latent.data import (
    hierarchical_means,
    language_overlap,
    language_panel,
    prepare_token_rows,
    source_record_folds,
)
from trainlab.runner import LabError


class DataTests(unittest.TestCase):
    def test_same_source_cannot_cross_folds_or_domains(self):
        result = source_record_folds(["a", "a", "b", "c", "d"], ["x"] * 5)
        self.assertEqual(result["folds"][0], result["folds"][1])
        with self.assertRaisesRegex(LabError, "crosses"):
            source_record_folds(["a", "a"], ["x", "y"])

    def test_native_rows_preserve_masked_decoder_context_and_source_identity(self):
        from trainlab.latent.native import _input_digest

        x = np.arange(6).reshape(2, 3)
        h = np.arange(24).reshape(2, 3, 4)
        capture = {
            "input_sha256": _input_digest(x),
            "hidden": h,
            "logits": h,
            "views": {"stage": h + 1},
            "context": {"successor_ids": x - 1},
            "readout_kind": "log_probabilities",
        }
        mask = np.array([[False, True, True], [True, True, True]])
        result = prepare_token_rows(
            capture,
            x,
            record_ids=["a", "b"],
            domains=["d", "d"],
            target_ids=np.zeros_like(x),
            lengths=[3, 2],
            row_mask=mask,
            position_ids=[5, 6, 7],
        )
        np.testing.assert_array_equal(result["capture_row_indices"], [1, 2, 3, 4])
        np.testing.assert_array_equal(result["hidden"], h.reshape(6, 4)[[1, 2, 3, 4]])
        np.testing.assert_array_equal(result["context"]["successor_ids"], [0, 1, 2, 3])
        np.testing.assert_array_equal(result["record_ids"], ["a", "a", "b", "b"])
        np.testing.assert_array_equal(result["positions"], [6, 7, 5, 6])
        self.assertEqual(result["rows"][2]["id"], 3)
        with self.assertRaisesRegex(LabError, "exact input"):
            prepare_token_rows(capture, x + 1, record_ids=["a", "b"], domains=["d", "d"])
        capture["context"]["successor_ids"] = np.arange(6)
        with self.assertRaisesRegex(LabError, "align"):
            prepare_token_rows(capture, x, record_ids=["a", "b"], domains=["d", "d"])

    def test_language_windows_have_no_boundary_separator_and_short_records_are_explicit(self):
        records = [{"id": "r", "domain": "d", "text": "abcdefghijk"}]
        panel = language_panel(records, context=3, windows_per_record=2)
        np.testing.assert_array_equal(panel["input_ids"], [[97, 98, 99], [101, 102, 103]])
        with self.assertRaisesRegex(LabError, "short"):
            language_panel(records, context=100)

    def test_overlap_checks_non_window_aligned_training_positions(self):
        train = [{"id": "t", "domain": "d", "text": "abcdefghijk"}]
        evaluation = [{"id": "e", "domain": "d", "text": "xxx"}]
        overlap = language_overlap(train, evaluation, evaluation_windows=[[99, 100, 101]])
        self.assertEqual(overlap["status"], "FAILED")
        self.assertEqual(overlap["window_training_substring_overlap"], [0])

    def test_equal_domains_and_equal_records_do_not_pool_long_records(self):
        result = hierarchical_means([1, 1, 9, 3], ["a", "a", "b", "c"], ["X", "X", "X", "Y"])
        self.assertEqual(result["domain_means"], {"X": 5.0, "Y": 3.0})
        self.assertEqual(result["equal_domain_mean"], 4.0)

    def test_mixed_record_domain_or_window_ids_cannot_merge_observations(self):
        with self.assertRaisesRegex(LabError, "mixed"):
            hierarchical_means([0, 100, 100], [1, "1", "b"], ["X"] * 3)
        with self.assertRaisesRegex(LabError, "mixed"):
            source_record_folds([1, "1", "b"], ["X"] * 3)
        with self.assertRaisesRegex(LabError, "mixed"):
            hierarchical_means([0, 100], ["a", "b"], [1, "1"])
        with self.assertRaisesRegex(LabError, "mixed"):
            hierarchical_means([0, 100], ["a", "a"], ["X", "X"], window_ids=[1, "1"])


if __name__ == "__main__":
    unittest.main()
