"""Optional real-PyTorch falsifiers, never a hardware qualification suite."""

import unittest

import torch
from torch import nn
from trainlab.pytorch import (
    check_activations,
    check_model,
    check_tensor,
    profile_modules,
    resolve_device,
)
from trainlab.runner import LabError


class BackendTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(7)
        torch.set_num_threads(1)
        self.model = nn.Sequential(nn.Linear(2, 4), nn.Tanh(), nn.Linear(4, 1))
        self.inputs = torch.ones(3, 2)

    def assert_no_hooks(self):
        for module in self.model.modules():
            self.assertFalse(module._forward_hooks)
            self.assertFalse(module._forward_pre_hooks)

    def test_finite_parameters_gradients_and_activations(self):
        with check_activations(self.model) as checked:
            loss = self.model(self.inputs).square().mean()
            check_tensor("loss", loss)
            loss.backward()
        self.assertGreater(checked["tensor_outputs_checked"], 0)
        self.assertGreater(check_model(self.model, gradients=True)["gradient_values"], 0)
        self.assert_no_hooks()
        self.model[0].weight.grad[0, 0] = float("nan")
        with self.assertRaisesRegex(LabError, "gradient.*0.weight"):
            check_model(self.model, gradients=True)
        self.model[0].weight.grad = None
        with self.assertRaisesRegex(LabError, "missing gradient"):
            check_model(self.model, gradients=True)

    def test_nested_outputs_keywords_and_frozen_parameters(self):
        class Nested(nn.Module):
            def forward(self, *, inputs):
                return {"prediction": inputs, "auxiliary": [inputs + 1, None]}

        nested = Nested()
        with check_activations(nested) as checked:
            with profile_modules(nested, device="cpu") as profile:
                nested(inputs=self.inputs)
        self.assertEqual(checked["tensor_outputs_checked"], 2)
        self.assertEqual(profile.report()["modules"]["<root>"]["calls"], 1)
        self.model[0].requires_grad_(False)
        self.model(self.inputs).sum().backward()
        self.assertGreater(check_model(self.model, gradients=True)["gradient_values"], 0)

    def test_numpy_tensor_interoperability(self):
        import numpy as np

        source = np.array([[1.0, 2.0]], dtype=np.float32)
        tensor = torch.from_numpy(source)
        tensor.add_(1)
        np.testing.assert_array_equal(source, [[2.0, 3.0]])
        np.testing.assert_array_equal(tensor.numpy(), source)

    def test_nonfinite_activation_and_empty_tensor_fail_and_cleanup(self):
        with torch.no_grad():
            self.model[0].weight[0, 0] = float("inf")
        with self.assertRaisesRegex(LabError, "activation"), check_activations(self.model):
            self.model(self.inputs)
        self.assert_no_hooks()
        with self.assertRaises(LabError):
            check_tensor("empty", torch.empty(0))
        with self.assertRaises(LabError), check_activations(self.model):
            pass

    def test_automatic_module_profile_counts_and_cleanup(self):
        with profile_modules(self.model, device="cpu") as profile:
            for _ in range(3):
                self.model(self.inputs)
        report = profile.report()
        self.assertEqual(set(report["modules"]), {"0", "1", "2"})
        self.assertTrue(all(row["calls"] == 3 for row in report["modules"].values()))
        self.assertTrue(all(row["total_seconds"] >= 0 for row in report["modules"].values()))
        self.assertFalse(report["synchronized"])
        self.assert_no_hooks()

    def test_profile_errors_cleanup_and_caught_errors_invalidate_profile(self):
        with self.assertRaises(RuntimeError), profile_modules(self.model, device="cpu"):
            self.model(torch.ones(3, 5))
        self.assert_no_hooks()
        with self.assertRaisesRegex(LabError, "did not complete"):
            with profile_modules(self.model, device="cpu"):
                try:
                    self.model(torch.ones(3, 5))
                except RuntimeError:
                    pass
        self.assert_no_hooks()
        with profile_modules(self.model, device="cpu", names=["0"]) as profile:
            self.model(self.inputs)
        self.assertEqual(set(profile.report()["modules"]), {"0"})
        self.assert_no_hooks()

    def test_device_and_module_selection_fail_closed(self):
        self.assertEqual(resolve_device("cpu"), torch.device("cpu"))
        for device in ("magic", "meta", "cpu:1"):
            with self.subTest(device=device), self.assertRaises(LabError):
                resolve_device(device)
        for names in ([], ["missing"], ["0", "0"], "0"):
            with self.subTest(names=names), self.assertRaises(LabError):
                with profile_modules(self.model, device="cpu", names=names):
                    pass
        self.assert_no_hooks()
        if not torch.cuda.is_available():
            with self.assertRaisesRegex(LabError, "CUDA.*unavailable"):
                resolve_device("cuda")

    def test_caught_hook_failures_invalidate_contexts(self):
        with self.assertRaisesRegex(LabError, "inspection failed"):
            with check_activations(self.model):
                self.model(self.inputs)
                with torch.no_grad():
                    self.model[0].weight[0, 0] = float("nan")
                try:
                    self.model(self.inputs)
                except LabError:
                    pass
        self.assert_no_hooks()

        class WrongDevice(nn.Module):
            def forward(self, inputs):
                return inputs.to("meta")

        wrong = WrongDevice()
        with self.assertRaisesRegex(LabError, "did not complete"):
            with profile_modules(wrong, device="cpu"):
                try:
                    wrong(self.inputs)
                except LabError:
                    pass
        self.assertFalse(wrong._forward_hooks)
        self.assertFalse(wrong._forward_pre_hooks)

    @unittest.skipUnless(torch.cuda.is_available(), "CUDA hardware is unavailable")
    def test_cuda_sync_and_device_mismatch(self):
        self.model.cuda()
        with profile_modules(self.model, device="cuda") as profile:
            self.model(self.inputs.cuda())
        self.assertTrue(profile.report()["synchronized"])
        with self.assertRaises(LabError), profile_modules(self.model, device="cpu"):
            self.model(self.inputs.cuda())
        self.assert_no_hooks()
