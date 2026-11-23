"""Cheap constructed native-hook conformance; no research checkpoint is bundled."""

import hashlib
import importlib.util
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from trainlab.runner import LabError

try:
    import torch
    from torch import nn
except ImportError:
    torch = None


if torch is not None:

    @dataclass
    class TinyState:
        values: object
        links: object
        cursor: object
        history: object
        position: int

    class TinyRecord(nn.Module):
        """Constructed learned hard-read interface fixture, not the CSM source."""

        def __init__(self):
            super().__init__()
            self.config = SimpleNamespace(width=2, slots=5)
            self.embedding = nn.Embedding(8, 2)
            self.frontend = nn.Linear(6, 2)
            self.controller = nn.Linear(4, 2)
            self.transform = nn.Linear(8, 2)
            self.output = nn.Linear(2, 8)

        def init_state(self, batch, device):
            return TinyState(
                torch.zeros(batch, 5, 2, device=device),
                torch.eye(5, device=device)[None].repeat(batch, 1, 1),
                torch.nn.functional.one_hot(torch.zeros(batch, dtype=torch.long), 5).float(),
                torch.zeros(batch, 2, 2, device=device),
                0,
            )

        def step(self, tokens, state, interventions=None, return_trace=False):
            b = len(tokens)
            first, second, destination = ((state.position + j) % 5 for j in (1, 2, 3))
            raw = self.embedding(tokens)
            front = self.frontend(torch.cat((state.history.flatten(1), raw), -1)).tanh()
            active = (state.cursor[..., None] * state.values).sum(1)
            control = self.controller(torch.cat((front, active), -1)).tanh()
            proposed = self.transform(
                torch.cat((front, state.values[:, first], state.values[:, second], control), -1)
            ).tanh()
            updated = 0.5 * (state.values[:, destination] + proposed)
            values = state.values.clone()
            values[:, destination] = updated
            cursor = torch.nn.functional.one_hot(torch.full((b,), destination), 5).float()
            following = TinyState(
                values,
                state.links.clone(),
                cursor,
                torch.stack((state.history[:, 1], raw), 1),
                state.position + 1,
            )
            logits = self.output(updated)
            if return_trace:
                return (
                    logits,
                    following,
                    {
                        name: torch.full((b,), value)
                        for name, value in (
                            ("first", first),
                            ("second", second),
                            ("destination", destination),
                        )
                    },
                )
            return logits, following

        def forward(self, x):
            state = self.init_state(len(x), x.device)
            outputs = []
            for token in x.T:
                out, state = self.step(token, state)
                outputs.append(out)
            return torch.stack(outputs, 1)

    class TinyLanguage(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(8, 4)
            self.pos = nn.Embedding(16, 4)
            self.layers = nn.ModuleList([nn.Linear(4, 4)])
            self.out = nn.Linear(4, 8)

        def forward(self, tokens):
            h = self.emb(tokens) + self.pos(torch.arange(tokens.shape[1]))
            for layer in self.layers:
                h = torch.tanh(layer(h))
            return self.out(h)


class Context:
    def __init__(self, adapter):
        self.adapter = adapter
        self.calls = []

    def invoke(self, operation, *args, phase, condition="unspecified", **kwargs):
        self.calls.append((operation, phase))
        return self.adapter.operations[operation](*args, **kwargs)


@unittest.skipIf(torch is None, "optional PyTorch backend is not installed")
class NativeTests(unittest.TestCase):
    def setUp(self):
        from trainlab.latent.native import language_adapter

        torch.manual_seed(29)
        self.model = TinyLanguage().eval()
        self.adapter = language_adapter(self.model, "transformer")
        self.ctx = Context(self.adapter)
        self.x = np.array([[1, 2, 3], [2, 1, 3]])

    def test_native_readout_and_instrumentation_are_exact(self):
        from trainlab.latent.interventions import native_parity

        result = native_parity(self.ctx, input_ids=self.x)
        self.assertEqual(result["status"], "TESTED")
        self.assertTrue(result["weights_unchanged"])
        self.assertTrue(result["readout_exact"])
        self.assertFalse(self.model.out._forward_pre_hooks)
        self.assertFalse(self.model.layers[0]._forward_hooks)

    def test_custom_softcap_and_vocab_slice_must_be_replayed(self):
        from trainlab.latent.interventions import native_parity
        from trainlab.latent.native import torch_hook_adapter

        model = self.model

        def decode(h):
            return 2 * torch.tanh(model.out(h)[..., :6] / 2)

        adapter = torch_hook_adapter(
            model,
            forward=lambda x: 2 * torch.tanh(model(x)[..., :6] / 2),
            head=model.out,
            embedding=model.emb,
            readout=decode,
        )
        self.assertEqual(native_parity(Context(adapter), input_ids=self.x)["status"], "TESTED")
        wrong = torch_hook_adapter(
            model,
            forward=lambda x: 2 * torch.tanh(model(x)[..., :6] / 2),
            head=model.out,
            embedding=model.emb,
            readout=lambda h: model.out(h)[..., :6],
        )
        self.assertEqual(native_parity(Context(wrong), input_ids=self.x)["status"], "FAILED")

    def test_position_lookup_changes_without_changing_tokens(self):
        from trainlab.latent.interventions import position_sweep

        result = position_sweep(
            self.ctx, input_ids=self.x, conditions={"identity": [0, 1, 2], "offset": [8, 9, 10]}
        )
        self.assertFalse(result["conditions"]["identity"]["metrics"]["exact_output_changed"].any())
        self.assertTrue(result["conditions"]["offset"]["metrics"]["exact_output_changed"].any())
        self.assertFalse(self.model.pos._forward_pre_hooks)

    def test_recurrent_position_condition_is_alias_without_extra_forward(self):
        from trainlab.latent.interventions import position_sweep
        from trainlab.latent.native import module_adapter

        adapter = module_adapter(
            self.model,
            name="declared-absent",
            head=self.model.out,
            embedding=self.model.emb,
            position_absent=True,
        )
        # The contract is caller-declared; this checks no-op execution, not that
        # this constructed model genuinely lacks positions.
        result = position_sweep(
            Context(adapter), input_ids=self.x, conditions={"offset": [8, 9, 10]}
        )
        self.assertEqual(result["conditions"]["offset"]["alias_of"], "native")
        self.assertFalse(result["conditions"]["offset"]["metrics"]["exact_output_changed"].any())
        with self.assertRaises(LabError):
            adapter.operations["position_forward"](
                self.x, [8, 9, 10], native={"input_sha256": "stale"}
            )

    def test_cleanup_after_native_failure_and_unknown_capability(self):
        from trainlab.latent.native import module_adapter

        adapter = module_adapter(
            self.model,
            name="bad",
            head=self.model.out,
            forward_fn=lambda x: (_ for _ in ()).throw(RuntimeError("fault")),
        )
        with self.assertRaises(RuntimeError):
            adapter.operations["forward"](self.x)
        self.assertFalse(self.model.out._forward_pre_hooks)
        self.assertNotIn("position_forward", adapter.operations)
        self.model.train()
        with self.assertRaises(LabError):
            self.adapter.operations["forward"](self.x)

    def test_stage_capture_preserves_transformer_fused_dispatch(self):
        from trainlab.latent.interventions import native_parity
        from trainlab.latent.native import module_adapter

        class Encoder(nn.Module):
            def __init__(self):
                super().__init__()
                self.emb = nn.Embedding(8, 8)
                self.stage = nn.TransformerEncoderLayer(
                    8, 2, 16, dropout=0.0, batch_first=True, norm_first=True
                )
                self.out = nn.Linear(8, 8)

            def forward(self, tokens):
                mask = torch.ones(tokens.shape[1], tokens.shape[1], dtype=torch.bool).triu(1)
                return self.out(self.stage(self.emb(tokens), src_mask=mask))

        model = Encoder().eval()
        self.assertNotIn("forward", model.stage.__dict__)
        adapter = module_adapter(model, name="fused", head=model.out, views={"layer": model.stage})
        self.assertEqual(native_parity(Context(adapter), input_ids=self.x)["status"], "TESTED")
        self.assertNotIn("forward", model.stage.__dict__)

    def test_reused_stage_calls_and_tuple_selectors_are_explicit(self):
        from trainlab.latent.native import module_adapter

        model = self.model
        layer = model.layers[0]

        def forward(tokens):
            h = model.emb(tokens)
            h = layer(h)
            h = layer(h)
            return model.out(h)

        adapter = module_adapter(
            model,
            name="reused",
            head=model.out,
            forward_fn=forward,
            views={"repeat": layer, "prehead": {"module": model.out, "capture": "input"}},
        )
        result = adapter.operations["forward"](self.x)
        self.assertEqual(set(result["views"]), {"repeat_call_01", "repeat_call_02", "prehead"})
        np.testing.assert_array_equal(result["views"]["prehead"], result["hidden"])
        self.assertNotIn("forward", layer.__dict__)

    def test_existing_workbench_preserves_operation_accounting(self):
        from trainlab.latent.interventions import native_parity
        from trainlab.research_diagnostics import Diagnostic, Workbench

        def check(ctx):
            result = native_parity(ctx, input_ids=self.x)
            return {
                "status": result["status"],
                "summary": "Constructed native hook parity",
                "metrics": {"max_delta": result["readout_max_abs_delta"]},
            }

        with tempfile.TemporaryDirectory() as tmp:
            report = Workbench(
                self.adapter,
                dict.fromkeys(("model", "dataset", "code", "configuration"), "a" * 64),
                Path(tmp) / "new",
            ).run(
                [
                    Diagnostic(
                        "parity",
                        "v1",
                        ("native_forward", "forward", "readout"),
                        check,
                        "Constructed interface conformance",
                    )
                ]
            )
        self.assertEqual(report["coverage"][0]["status"], "TESTED")
        self.assertEqual(len(report["attempts"]), 5)

    def test_native_latency_quality_and_repeat_checks_are_separate(self):
        from trainlab.latent.interventions import latency_sweep
        from trainlab.research_diagnostics import Adapter

        result = latency_sweep(self.ctx, input_ids=self.x, warmups=2, repeats=5)
        self.assertEqual(result["status"], "TESTED")
        self.assertEqual(len(result["seconds"]), 5)
        self.assertTrue(result["weights_unchanged"])
        self.assertFalse(result["quality_cost_eligible"])
        self.assertEqual(result["quality_gate"], "UNASSESSED")
        self.assertIn("EXCLUDING_LEDGER_IO", result["measurement_scope"])
        self.assertEqual(sum(name == "timed_native_forward" for name, _ in self.ctx.calls), 7)
        original = self.adapter.operations["timed_native_forward"]

        def corrupt(x):
            value = original(x)
            value["logits"] += 1
            return value

        operations = dict(self.adapter.operations, timed_native_forward=corrupt)
        bad = Adapter(self.adapter.name, operations, self.adapter.state_semantics)
        failed = latency_sweep(
            Context(bad), input_ids=self.x, warmups=0, repeats=2, quality_gate=True
        )
        self.assertEqual(failed["status"], "FAILED")
        self.assertFalse(failed["quality_cost_eligible"])

    def test_record_components_clone_reset_and_future_access(self):
        from trainlab.latent.interventions import component_lesions, native_parity, retrieval_sweep
        from trainlab.latent.native import language_adapter

        model = TinyRecord().eval()
        adapter = language_adapter(model, "csm")
        context = Context(adapter)
        x = np.array([[1, 2, 3, 4, 5, 2, 3, 4], [2, 1, 3, 4, 5, 2, 3, 4]])
        self.assertEqual(native_parity(context, input_ids=x)["status"], "TESTED")
        native = adapter.operations["initial_state"](2)
        clone = adapter.operations["clone_state"](native)
        clone.values[:, 4] = 5
        self.assertFalse(torch.equal(clone.values, native.values))
        zeroed = adapter.operations["edit_state"](clone, "persistent_reset")
        self.assertTrue(torch.equal(zeroed.values, native.values))
        self.assertTrue(torch.equal(zeroed.history, clone.history))
        condition = {
            "controller": ["controller_active_zero"],
            "proposal": ["proposal_values_zero"],
            "history": ["history_zero"],
            "memory": ["prior_values_zero"],
            "foreign": {"state_operation": "foreign_record_memory", "donor_indices": [1, 0]},
        }
        for mode in ("one_step", "persistent"):
            result = component_lesions(context, input_ids=x, conditions=condition, mode=mode)
            self.assertEqual(set(result["conditions"]), set(condition))
            for item in result["conditions"].values():
                np.testing.assert_array_equal(item["logits"][:, 0], result["native_logits"][:, 0])
        future = retrieval_sweep(
            context, input_ids=x, anchor=4, donor_indices=[1, 0], horizon=4, trained_horizon=6
        )
        self.assertEqual(future["status"], "TESTED")
        self.assertTrue(future["local_history_exact"])
        self.assertTrue(future["checks"]["full_persistent_counterpart_exact"])
        self.assertEqual(
            future["unread_conditions"]["zero_unread"]["within_trained_horizon"].tolist(),
            [True, True, False, False],
        )
        self.assertTrue(future["unread_conditions"]["transplant_unread"]["sham_final_state_exact"])
        external = retrieval_sweep(
            context,
            input_ids=x,
            anchor=4,
            donor_input_ids=x[::-1],
            horizon=2,
            operations=(),
            frozen_state_operations=("identity", "paired_persistent"),
        )
        self.assertEqual(external["status"], "TESTED")

    def test_pinned_factory_strict_load_and_changed_source_rejection(self):
        from trainlab.latent.interventions import native_parity

        path = Path(__file__).resolve().parents[1] / "examples/latent_native_factory.py"
        specification = importlib.util.spec_from_file_location("latent_factory_test", path)
        factory = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(factory)
        model = nn.Module()
        model.emb, model.out = nn.Embedding(8, 4), nn.Linear(4, 8)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "model.py").write_text(
                "import torch\nfrom torch import nn\nimport native_csm\n"
                "class M(nn.Module):\n def __init__(self):\n  super().__init__(); "
                "self.emb=nn.Embedding(8,4); self.out=nn.Linear(4,8)\n"
                " def forward(self,x): return self.out(self.emb(x))\n"
                "def make(arm): return M()\n"
            )
            (root / "native.py").write_text("SOURCE_ID = 'constructed-fixture'\n")
            torch.save(
                {"state_dict": model.state_dict(), "arm": "gated_delta_reference"},
                root / "checkpoint.pt",
            )
            artifacts = {
                name: {
                    "path": name,
                    "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
                    "kind": "opaque",
                }
                for name in ("model.py", "native.py", "checkpoint.pt")
            }
            plan = {
                "artifacts": artifacts,
                "identities": {"model": artifacts["checkpoint.pt"]["sha256"]},
                "provenance": {
                    "native": {
                        "architecture": "gated_delta_reference",
                        "model_source": "model.py",
                        "native_source": "native.py",
                        "checkpoint": "checkpoint.pt",
                        "cpu_threads": 1,
                    }
                },
            }
            adapter = factory.build_adapter(plan, root)
            self.assertEqual(native_parity(Context(adapter), input_ids=self.x)["status"], "TESTED")
            double_weights = {
                key: torch.full_like(value, 1 + 2**-30, dtype=torch.float64)
                for key, value in model.state_dict().items()
            }
            torch.save(
                {"state_dict": double_weights, "arm": "gated_delta_reference"},
                root / "checkpoint.pt",
            )
            checkpoint_hash = hashlib.sha256((root / "checkpoint.pt").read_bytes()).hexdigest()
            plan["identities"]["model"] = checkpoint_hash
            plan["artifacts"]["checkpoint.pt"]["sha256"] = checkpoint_hash
            with self.assertRaisesRegex(LabError, "dtypes.*without casting"):
                factory.build_adapter(plan, root)
            (root / "model.py").write_text(
                "raise RuntimeError('modified source must never execute')\n"
            )
            with self.assertRaises(LabError):
                factory.build_adapter(plan, root)


if __name__ == "__main__":
    unittest.main()
