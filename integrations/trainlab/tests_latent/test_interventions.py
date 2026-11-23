"""Falsifiers for the latent intervention execution and analysis contract."""

import unittest

import numpy as np
from trainlab.latent.interventions import (
    analyze_future_access,
    position_ids,
    read_footprint,
    response_metrics,
    state_distances,
    suffix_intervention,
)
from trainlab.runner import LabError


class InterventionTests(unittest.TestCase):
    def test_suffix_patch_preserves_current_suffix_and_future(self):
        x = np.arange(24).reshape(3, 8)
        edited = suffix_intervention(x, [5, 6, 7], 2, donor_indices=[1, 2, 0])
        for row, anchor in enumerate([5, 6, 7]):
            np.testing.assert_array_equal(
                edited["input_ids"][row, anchor - 2 :], x[row, anchor - 2 :]
            )
            np.testing.assert_array_equal(
                edited["input_ids"][row, : anchor - 2], x[(row + 1) % 3, : anchor - 2]
            )
        with self.assertRaises(LabError):
            suffix_intervention(x, [5, 6, 7], 2, donor_indices=[0, 1, 8])

    def test_shuffle_is_frozen_and_preserves_histogram(self):
        x = np.arange(20).reshape(2, 10)
        first = suffix_intervention(x, [9, 8], 2, seed=7, shuffle=True)
        second = suffix_intervention(x, [9, 8], 2, permutations=first["permutations"], shuffle=True)
        np.testing.assert_array_equal(first["input_ids"], second["input_ids"])
        np.testing.assert_array_equal(np.sort(first["input_ids"], 1), x)
        bad = first["permutations"].copy()
        bad[0, 0] = 9
        with self.assertRaises(LabError):
            suffix_intervention(x, [9, 8], 2, permutations=bad, shuffle=True)

    def test_positions_only_change_named_lookup_ids(self):
        ids = position_ids(
            50,
            query_positions=[48, 49],
            query_reset=[16, 17],
            filler_range=(8, 48),
            filler_wrap=(8, 8),
            table_size=64,
        )
        np.testing.assert_array_equal(ids[:8], np.arange(8))
        np.testing.assert_array_equal(ids[8:48], 8 + np.arange(40) % 8)
        np.testing.assert_array_equal(ids[48:], [16, 17])
        with self.assertRaises(LabError):
            position_ids(50, offset=32, table_size=64)

    def test_footprint_includes_cursor_and_destination(self):
        got = read_footprint({"cursor": [0], "first": [1], "second": [1], "destination": [3]}, 5)
        np.testing.assert_array_equal(got, [[True, True, False, True, False]])
        with self.assertRaises(LabError):
            read_footprint({"cursor": [0], "first": [1], "second": [1]}, 5)

    def test_no_effect_before_changed_row_access_fails(self):
        native = np.zeros((1, 3, 2))
        changed = native.copy()
        changed[:, 0, 0] = 1
        trace = {key: np.array([[0, 0, 1]]) for key in ("cursor", "first", "second", "destination")}
        out = analyze_future_access(native, changed, trace, trace, [[False, True]])
        self.assertEqual(out["status"], "FAILED")
        self.assertEqual(out["first_access"].tolist(), [2])
        self.assertEqual(out["first_output_change"].tolist(), [0])
        self.assertEqual(out["preaccess_violation_count"], 1)
        changed[:] = native
        changed[:, 2, 0] = 1
        self.assertEqual(
            analyze_future_access(native, changed, trace, trace, [[False, True]])["status"],
            "TESTED",
        )

    def test_no_access_is_not_zero_time(self):
        native = np.zeros((2, 3, 2))
        trace = {
            key: np.zeros((2, 3), dtype=int) for key in ("cursor", "first", "second", "destination")
        }
        result = analyze_future_access(native, native, trace, trace, [[False, True], [False, True]])
        self.assertEqual(result["first_access"].tolist(), [-1, -1])
        self.assertEqual(result["first_output_change"].tolist(), [-1, -1])

    def test_metrics_use_unconditional_flips_and_full_vocabulary(self):
        a = np.array([[2.0, 0.0, 0.0], [0.0, 2.0, 0.0]])
        b = np.array([[0.0, 2.0, 0.0], [0.0, 2.0, 0.0]])
        result = response_metrics(a, b, targets=[0, 0], alternate_targets=[1, 1])
        self.assertEqual(result["correct_to_alternate_rate"], 0.5)
        self.assertEqual(result["prediction_change_rate"], 0.5)
        self.assertTrue(np.all(result["kl"] >= 0))
        np.testing.assert_array_equal(response_metrics(a, a)["kl"], [0.0, 0.0])

    def test_retention_reports_fields_and_exact_identity(self):
        left = {"values": np.zeros((2, 2, 3)), "links": np.eye(2)[None].repeat(2, 0), "position": 4}
        right = {
            key: value.copy() if isinstance(value, np.ndarray) else value
            for key, value in left.items()
        }
        right["values"][0, 1, 2] = 2
        result = state_distances(left, right)
        self.assertFalse(result["exact"])
        np.testing.assert_array_equal(result["fields"]["values"]["l2"], [2.0, 0.0])
        self.assertTrue(result["fields"]["links"]["exact"])


if __name__ == "__main__":
    unittest.main()
