"""FULLCYCLE-003 falsifier: actual four-layer width, independently learned depth."""

import unittest


class DeepBlueprintContract(unittest.TestCase):
    def test_deep_tac_bpe_backend_exists(self):
        from trainlab.fullcycle.backends import ModelConfig, configuration, create_model

        model = create_model(
            ModelConfig(
                backend="tac104", width=120, layers=40, heads=4, vocab_size=3072, context=512
            )
        )
        parameters = sum(p.numel() for p in model.parameters())
        self.assertTrue(9_900_000 <= parameters <= 10_100_000, parameters)
        self.assertEqual(len(model.native.blocks), 40)
        self.assertEqual(model.native.embedding.embedding_dim, 120)
        self.assertEqual(configuration(model)["native"]["ffn_dim"], 224)
        self.assertEqual(configuration(model)["native"]["window"], 128)
        self.assertEqual(configuration(model)["native"]["local_rope"], True)


class DeepMathAndState(unittest.TestCase):
    def setUp(self):
        import torch

        torch.set_num_threads(2)

    def test_byte_extension_preserves_four_layer_logits_and_parameter_count(self):
        import importlib
        import os
        import sys
        import types
        from pathlib import Path

        import torch
        from trainlab.fullcycle.backends import ModelConfig, create_model

        original_dir = os.environ.get("TAC104_REFERENCE_DIR")
        if not original_dir:
            self.skipTest("external original-source conformance run only; not bundled CI fixture")
        original = Path(original_dir)
        package = types.ModuleType("_fullcycle003_original")
        package.__path__ = [str(original)]
        sys.modules[package.__name__] = package
        module = importlib.import_module(package.__name__ + ".tac_model")
        reference = module.DeepCacheTAC104(
            module.Config104(
                d_model=120,
                n_layers=4,
                n_heads=4,
                key_dim=16,
                value_dim=16,
                write_rank=2,
                ffn_dim=224,
            )
        )
        candidate = create_model(
            ModelConfig(backend="tac104", vocab_size=256, width=120, layers=4, heads=4, context=128)
        ).native
        candidate.load_state_dict(reference.state_dict())
        self.assertEqual(sum(p.numel() for p in candidate.parameters()), 998024)
        x = torch.randint(0, 256, (1, 19))
        with torch.no_grad():
            torch.testing.assert_close(candidate(x)[0], reference(x)[0], rtol=0, atol=0)

    def test_cache_causality_owner_isolation_and_more_than_256_token_positions(self):
        import torch
        from trainlab.fullcycle.backends import ModelConfig, create_model

        model = create_model(
            ModelConfig(
                backend="tac104", vocab_size=3072, width=120, layers=2, heads=4, context=1024
            )
        ).eval()
        x = torch.randint(256, 3072, (1, 273))
        with torch.no_grad():
            full = model(x)
            prefix, state = model.step(x[:, :257])
            scores = []
            for i in range(257, 273):
                y, state = model.step(x[:, i : i + 1], state)
                scores.append(y)
            self.assertEqual(state.clock, 273)
            torch.testing.assert_close(torch.cat(scores, 1), full[:, 257:], atol=2e-5, rtol=2e-4)
            self.assertEqual(state.layers[0].recent_key.shape[2], 127)
            changed = x.clone()
            changed[:, 200:] = 1
            torch.testing.assert_close(model(changed)[:, :200], full[:, :200], atol=2e-5, rtol=2e-4)
            with self.assertRaises(ValueError):
                model.native(x[:, :1], state=state, owners=("another-session",))

    def test_activation_checkpointing_preserves_deep_gradients(self):
        import dataclasses

        import torch
        from trainlab.fullcycle.backends import ModelConfig, create_model

        config = ModelConfig(
            backend="tac104", vocab_size=300, width=120, layers=3, heads=4, context=128
        )
        first = create_model(config)
        second = create_model(dataclasses.replace(config, activation_checkpointing=True))
        second.load_state_dict(first.state_dict())
        x = torch.randint(0, 300, (1, 23))
        first(x).square().mean().backward()
        second(x).square().mean().backward()
        for (name, p), (_, q) in zip(first.named_parameters(), second.named_parameters()):
            self.assertIsNotNone(p.grad, name)
            self.assertTrue(torch.isfinite(p.grad).all(), name)
            torch.testing.assert_close(p.grad, q.grad, atol=1e-7, rtol=1e-5)
