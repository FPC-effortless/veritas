import importlib.util
import unittest

from trainlab.runner import LabError
from trainlab.training_observer import freeze_slices, slice_trajectory, train_step


class SliceTrajectoryTests(unittest.TestCase):
    def test_fixed_panel_acquisition_regression_and_missing_coverage(self):
        panel = freeze_slices(
            [
                {"id": "a", "slice": "first", "label": "one"},
                {"id": "b", "slice": "other", "label": "two"},
            ],
            acquired_score=1,
            max_regression=0.25,
        )
        result = slice_trajectory(
            checkpoints=[
                {"step": 1, "predictions": {"a": "one", "b": "two"}},
                {"step": 2, "predictions": {"a": "two"}},
            ],
            expected_steps=[1, 2],
            **panel,
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["slices"]["first"]["first_acquired"], 1)
        self.assertEqual(result["slices"]["first"]["first_regression"], 2)
        self.assertIsNone(result["slices"]["other"]["points"][1]["accuracy"])
        self.assertFalse(result["complete"])


@unittest.skipUnless(importlib.util.find_spec("torch"), "optional CPU PyTorch runtime")
class NativeStepTests(unittest.TestCase):
    def setUp(self):
        import torch

        self.t = torch
        torch.manual_seed(31)
        self.batch = {
            "inputs": torch.tensor([[1.0, 0], [0.0, 1.0]]),
            "labels": torch.tensor([0, 1]),
            "mask": None,
        }

    def fit(self, model, lr=0.1, **kwargs):
        opt = self.t.optim.SGD(model.parameters(), lr=lr)
        return train_step(model, opt, self.batch, step=2, task="classification", **kwargs)

    def test_actual_update_and_frozen_update(self):
        model = self.t.nn.Linear(2, 2)
        self.assertGreater(self.fit(model)["observations"]["updated_parameters"], 0)
        frozen = self.fit(model, lr=0.0)
        self.assertTrue(frozen["unchanged_update"])
        self.assertEqual(frozen["status"], "FAILED")

    def test_nonfinite_activation_localization_and_cleanup(self):
        torch = self.t

        class Broken(torch.nn.Module):
            def forward(self, x):
                return x * float("nan")

        model = torch.nn.Sequential(torch.nn.Linear(2, 2), Broken())
        result = self.fit(model)
        self.assertEqual(result["first_anomaly"]["location"], "1")
        self.assertFalse(model[1]._forward_hooks)
        self.assertIsNone(result["observations"]["updated_parameters"])

    def test_next_token_shift_and_label_scope(self):
        torch = self.t
        model = torch.nn.Embedding(5, 5)
        opt = torch.optim.Adam(model.parameters())
        batch = {
            "inputs": torch.tensor([[0, 1, 2]]),
            "labels": torch.tensor([[1, 2, -100]]),
            "mask": torch.tensor([[True, True, False]]),
        }
        self.assertEqual(
            train_step(model, opt, batch, step=1, task="next_token")["status"], "TESTED"
        )
        batch["labels"][0, 0] = 3
        with self.assertRaises(LabError):
            train_step(model, opt, batch, step=2, task="next_token")
