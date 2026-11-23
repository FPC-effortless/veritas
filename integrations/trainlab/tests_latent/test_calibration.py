import json
import unittest
from pathlib import Path

import numpy as np
from trainlab.latent import calibration as c
from trainlab.runner import LabError


class CalibrationTests(unittest.TestCase):
    def test_native_probability_metrics_and_temperature_semantics(self):
        lp = c.log_softmax([[2.0, 0.0], [-1.0, 2.0]])
        scaled = c.temperature_scale(lp, 2.0)
        np.testing.assert_array_equal(scaled.argmax(1), lp.argmax(1))
        report, arrays = c.probability_metrics(lp, [0, 1], reference_logp=lp)
        self.assertEqual(report["accuracy"], 1.0)
        np.testing.assert_array_equal(arrays["kl"], [0.0, 0.0])
        self.assertAlmostEqual(report["brier"], np.square(np.exp(lp) - np.eye(2)).sum(1).mean())
        self.assertEqual(len(report["reliability"]), 10)
        json.dumps(report, allow_nan=False)
        with self.assertRaises(LabError):
            c.temperature_scale(lp, 0)
        with self.assertRaises(LabError):
            c.probability_metrics([[0.0, 0.0]], [0])

    def test_equal_record_domain_weights_do_not_reward_long_records(self):
        weights = c.record_domain_weights(["a", "a", "a", "b", "c"], ["x", "x", "x", "x", "y"])
        np.testing.assert_allclose(weights, [1 / 12, 1 / 12, 1 / 12, 1 / 4, 1 / 2])

    def test_selection_only_sees_calibration_rows_and_ties_prefer_native(self):
        conditions = [
            {
                "name": "zero",
                "gain": 0.0,
                "temperature": 1.0,
                "gate_mode": "adaptive",
                "vector_mode": "gain",
            },
            {
                "name": "native",
                "gain": 1.0,
                "temperature": 1.0,
                "gate_mode": "adaptive",
                "vector_mode": "gain",
            },
            {
                "name": "negative",
                "gain": -1.0,
                "temperature": 1.0,
                "gate_mode": "adaptive",
                "vector_mode": "gain",
            },
        ]
        result = c.select_calibration_settings(
            np.array([[2.0, 2.0], [2.0, 2.0], [1.0, 1.0]]), conditions, ["a", "b"]
        )
        self.assertEqual(result["selections"]["nonnegative_gain"]["name"], "native")
        self.assertEqual(result["selections"]["signed_gain"]["name"], "negative")
        self.assertFalse(result["uses_evaluation_rows"])

    def test_native_replay_rejects_wrong_decoder(self):
        x = np.array([[1.0, 0.0], [0.0, 1.0]])

        def decoder(h, row_indices):
            return h + np.array([0.5, 0.0])

        report, arrays = c.native_readout_contrast(
            x,
            {"removed": np.zeros_like(x)},
            [0, 1],
            decoder,
            observed_native_scores=decoder(x, np.arange(2)),
        )
        self.assertTrue(report["native_replay"]["passed"])
        self.assertEqual(arrays["nll"].shape, (2, 2))
        with self.assertRaises(LabError):
            c.native_readout_contrast(
                x, {}, [0, 1], decoder, observed_native_scores=np.zeros_like(x)
            )

    def test_component_controls_really_separate_head_gate_and_successor(self):
        prebank = np.array([[0.2, -0.1], [-0.3, 0.1], [0.1, 0.2], [-0.1, -0.2]])
        bank = np.array([[1.0, -0.2], [-0.3, 1.0], [0.4, 0.1], [-0.1, 0.4]])
        calls = []

        def decoder(
            h, row_indices, gate_hidden=None, gate_mode="adaptive", no_mixture=False, context=None
        ):
            gate_h = h if gate_hidden is None else gate_hidden
            calls.append((h.copy(), gate_h.copy(), no_mixture))
            lp = c.log_softmax(h)
            if no_mixture:
                return lp
            gate = 1 / (1 + np.exp(-gate_h[:, 0]))
            if gate_mode == "native":
                gate = context["gate"][row_indices]
            p = (1 - gate[:, None]) * np.exp(lp)
            p[:, 0] += gate
            return np.log(p)

        report, arrays = c.component_readout_diagnostics(
            prebank,
            bank,
            [0, 1, 0, 1],
            decoder,
            donor_indices=[1, 0, 3, 2],
            clusters=["a", "b", "c", "d"],
            domains=["x"] * 4,
            readout_kind="log_probabilities",
        )
        names = arrays["condition_names"].tolist()
        h, gate_h, _ = calls[names.index("head_only_bank_removed")]
        np.testing.assert_array_equal(h, prebank)
        np.testing.assert_array_equal(gate_h, prebank + bank)
        h, gate_h, _ = calls[names.index("gate_only_bank_removed")]
        np.testing.assert_array_equal(h, prebank + bank)
        np.testing.assert_array_equal(gate_h, prebank)
        self.assertIn("factorial_nll_interaction", arrays)
        self.assertIn("prediction_path_only", report["scope"])

    def test_bank_calibration_rejects_source_leakage(self):
        x = np.array([[0.1, 0.2], [0.2, 0.3], [0.3, 0.4], [0.4, 0.5]])

        def decoder(h, row_indices, **kwargs):
            return h

        with self.assertRaises(LabError):
            c.bank_gain_diagnostics(
                x,
                x,
                [0, 1, 0, 1],
                decoder,
                calibration_indices=[0, 1],
                evaluation_indices=[2, 3],
                clusters=["a", "b", "a", "c"],
            )

    def test_bank_selection_mean_and_quartiles_do_not_use_evaluation(self):
        base = np.array(
            [[0.2, -0.1], [-0.3, 0.1], [0.1, 0.2], [-0.1, -0.2], [0.5, 0.1], [-0.3, 0.5]]
        )
        bank = np.array([[1.0, -0.2], [-0.3, 1.0], [0.4, 0.1], [-0.1, 0.4], [1.0, 0.5], [0.2, 0.7]])
        successor = np.array([0, 1, -1, 0, -1, 1])
        native_gate = 1 / (1 + np.exp(-(base + bank)[:, 0]))

        def decoder(
            h, row_indices, gate_hidden=None, gate_mode="adaptive", no_mixture=False, context=None
        ):
            lp = c.log_softmax(h)
            gate = 1 / (1 + np.exp(-gate_hidden[:, 0]))
            if gate_mode == "native":
                gate = context["gates"][row_indices]
            ids = successor[row_indices]
            gate = np.where(ids < 0, 0.0, gate)
            p = (1 - gate[:, None]) * np.exp(lp)
            p[np.arange(len(p)), np.maximum(ids, 0)] += gate
            return np.log(p)

        kwargs = dict(
            calibration_indices=[0, 1],
            evaluation_indices=[2, 3, 4, 5],
            clusters=["a", "b", "c", "d", "e", "f"],
            domains=["x"] * 6,
            successor_ids=successor,
            gains=[0, 1],
            temperatures=[1, 2],
            readout_kind="log_probabilities",
            readout_kwargs={"context": {"gates": native_gate}},
            selection_draws=16,
        )
        report, arrays = c.bank_gain_diagnostics(base, bank, [0, 1, 0, 1, 1, 0], decoder, **kwargs)
        changed = bank.copy()
        changed[2:] *= 50
        # Recompute native context for the changed held-out rows; calibration stays untouched.
        kwargs["readout_kwargs"] = {"context": {"gates": 1 / (1 + np.exp(-(base + changed)[:, 0]))}}
        changed_report, changed_arrays = c.bank_gain_diagnostics(
            base, changed, [0, 1, 1, 0, 0, 1], decoder, **kwargs
        )
        self.assertEqual(report["selection"], changed_report["selection"])
        self.assertEqual(
            report["calibration_native_confidence_quartile_edges"],
            changed_report["calibration_native_confidence_quartile_edges"],
        )
        np.testing.assert_array_equal(
            arrays["calibration_mean_bank"], changed_arrays["calibration_mean_bank"]
        )
        self.assertTrue(report["unavailable_successor_gate_invariance"]["passed"])
        self.assertEqual(len(report["primary_contrasts"]), 3)
        json.dumps(report, allow_nan=False)

    def test_saved_bank_selections_and_stability_when_study_is_available(self):
        root = Path(__file__).resolve().parents[4] / "latent_diagnostics_002/lanes/bank_calibration"
        files = [
            root / name
            for name in (
                "protocol.json",
                "selected_windows.json",
                "selected_settings.json",
                "calibration_outcomes.npz",
            )
        ]
        if not all(path.is_file() for path in files):
            self.skipTest("archived study is not part of the installed package")
        protocol = json.loads(files[0].read_text())
        windows = [
            w for w in json.loads(files[1].read_text())["windows"] if w["split"] == "calibration"
        ]
        saved = json.loads(files[2].read_text())
        with np.load(files[3], allow_pickle=False) as data:
            losses = data["loss"]
            conditions = protocol["conditions"]
            self.assertEqual([row["name"] for row in conditions], data["condition_names"].tolist())
        records = np.repeat([w["record_id"] for w in windows], losses.shape[2])
        domains = np.repeat([w["domain"] for w in windows], losses.shape[2])
        result = c.select_calibration_settings(
            losses.reshape(len(conditions), -1),
            conditions,
            records,
            domains,
            draws=5000,
            seed=20261123,
        )
        # The original selector froze seed=20261123 and 5,000 x 11 record
        # draws. Bind the regenerated indices, not only the selected settings.
        self.assertEqual(result["bootstrap_plans"][0]["unit_ids"], sorted(set(records.tolist())))
        self.assertEqual(
            result["bootstrap_plans"][0]["indices_sha256"],
            "f4691cdc77ef5720da0ac5175a34a64872c8b717c3e45a0177fd62bbc8aed560",
        )
        for name, actual in result["selections"].items():
            expected = saved["selections"][name]
            self.assertEqual(actual["condition"], expected["condition"])
            self.assertAlmostEqual(
                actual["calibration_nll"], expected["calibration_mean_nll"], places=12
            )
            self.assertEqual(
                {k: v for k, v in actual["bootstrap_selection_counts"].items() if v},
                expected["calibration_bootstrap_selection_counts"],
            )


if __name__ == "__main__":
    unittest.main()
