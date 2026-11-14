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

    def test_regression_at_exact_threshold(self):
        panel = freeze_slices(
            [{"id": str(i), "slice": "fixed", "label": "one"} for i in range(10)],
            acquired_score=0.9,
            max_regression=0.3,
        )
        result = slice_trajectory(
            checkpoints=[
                {
                    "step": step,
                    "predictions": {str(i): "one" if i < hits else "two" for i in range(10)},
                }
                for step, hits in enumerate((9, 6, 5))
            ],
            expected_steps=[0, 1, 2],
            **panel,
        )
        self.assertEqual(result["slices"]["fixed"]["first_regression"], 2)


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
        return train_step(
            model, opt, self.batch, step=2, task="classification", classes=2, **kwargs
        )

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

    def test_invalid_labels_do_not_run_forward_or_clear_existing_gradients(self):
        torch = self.t
        model = torch.nn.Linear(2, 2)
        param = model.weight
        param.grad = torch.ones_like(param)
        called = []
        handle = model.register_forward_hook(lambda *_args: called.append(True))
        self.addCleanup(handle.remove)
        self.batch["labels"][0] = 2
        with self.assertRaisesRegex(LabError, "declared vocabulary"):
            self.fit(model)
        self.assertEqual(called, [])
        self.assertTrue(torch.equal(param.grad, torch.ones_like(param)))

    def test_detached_logits_and_unvisited_module_are_visible(self):
        torch = self.t

        class Detached(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.used = torch.nn.Linear(2, 2)
                self.unvisited = torch.nn.Linear(2, 2)
                self.unvisited.requires_grad_(False)

            def forward(self, inputs):
                return self.used(inputs).detach()

        result = self.fit(Detached(), module_names=["used", "unvisited"])
        self.assertEqual(result["first_anomaly"]["kind"], "MISSING_GRADIENT")
        observed = result["observations"]
        self.assertEqual(observed["missing_gradients"], ["used.weight", "used.bias"])
        self.assertEqual(observed["outputs_by_module"], {"used": 1, "unvisited": 0})
        self.assertEqual(observed["frozen_parameters"], 2)
        self.assertIsNone(observed["updated_parameters"])

    def test_first_gradient_uses_callback_order(self):
        torch = self.t

        class BadBackward(torch.autograd.Function):
            @staticmethod
            def forward(ctx, tensor):
                return tensor

            @staticmethod
            def backward(ctx, gradient):
                return gradient * float("nan")

        class Broken(torch.nn.Sequential):
            def forward(self, inputs):
                return BadBackward.apply(super().forward(inputs))

        model = Broken(torch.nn.Linear(2, 2), torch.nn.Linear(2, 2))
        order = []
        for name, parameter in model.named_parameters():
            handle = parameter.register_hook(lambda _gradient, name=name: order.append(name))
            self.addCleanup(handle.remove)
        result = self.fit(model)
        self.assertEqual(result["first_anomaly"]["location"], order[0])
        self.assertNotEqual(order[0], next(iter(dict(model.named_parameters()))))

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
            train_step(model, opt, batch, step=1, task="next_token", classes=5)["status"], "TESTED"
        )
        batch["labels"][0, 0] = 3
        with self.assertRaises(LabError):
            train_step(model, opt, batch, step=2, task="next_token", classes=5)
