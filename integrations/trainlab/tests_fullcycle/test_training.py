"""Constructed integrity controls, causal decoding and exact optimizer replay."""

from __future__ import annotations

import dataclasses
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from forge_data.language import ForgeError, LanguageRelease, build_release, canonical, digest
from trainlab.fullcycle._work_counter import GlobalFlopCounter
from trainlab.fullcycle.backends import ModelConfig, create_model
from trainlab.fullcycle.tokenization import Tokens, fit_tokenizer, pack_training
from trainlab.fullcycle.training import (
    checkpoint_load,
    dpo_loss,
    task_reward,
    train_stage,
    validate_stage,
)


def fixture(root):
    source = root / "source.jsonl"
    data = []
    for i in range(100):
        data.extend(
            [
                {
                    "kind": "text",
                    "source_id": "fixture",
                    "group": str(i),
                    "text": f"Public document {i}. A small language model learns a useful pattern. "
                    * 12,
                },
                {
                    "kind": "conversation",
                    "source_id": "fixture",
                    "group": str(i),
                    "messages": [
                        {"role": "user", "content": f"Number {i}: say hello."},
                        {"role": "assistant", "content": "hello"},
                    ],
                },
                {
                    "kind": "preference",
                    "source_id": "fixture",
                    "group": str(i),
                    "prompt": f"Say hello. Case {i}.",
                    "chosen": "hello",
                    "rejected": "goodbye",
                },
                {
                    "kind": "task",
                    "source_id": "fixture",
                    "group": str(i),
                    "prompt": f"Compare {i}, 50. Reply 0 if first is larger, else 1.",
                    "left": i,
                    "right": 50,
                    "verifier": "integer-comparison-v1",
                },
            ]
        )
    source.write_bytes(b"".join(canonical(r) + b"\n" for r in data))
    spec = {
        "schema": "forge.language-source.v1",
        "source_sha256": digest(source),
        "split_salt": "test-fixture",
        "sources": {
            "fixture": {
                "rights_reviewed": True,
                "license": "Apache-2.0",
                "provenance": "constructed tests",
                "source_kind": "CONSTRUCTED",
            }
        },
    }
    pin = build_release(source, spec, root / "release", shard_bytes=4096)
    release = LanguageRelease(root / "release", pin)
    fit_tokenizer(release, root / "tokenizer.json", kind="byte")
    tokens = Tokens(root / "tokenizer.json")
    pack_training(release, tokens, root / "tokens")
    return release, tokens, source, spec


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.release, self.tokens, self.source, self.spec = fixture(self.root)
        torch.set_num_threads(1)

    def test_reproducible_release_and_global_group_isolation(self):
        pin = build_release(self.source, self.spec, self.root / "repeat", shard_bytes=4096)
        self.assertEqual(pin, self.release.manifest_sha256)
        groups = {
            split: {
                r["group"]
                for kind in ("text", "conversation", "preference", "task")
                for r in self.release.iter_rows(split, kind)
            }
            for split in ("train", "validation", "test")
        }
        self.assertTrue(all(groups.values()))
        self.assertFalse(groups["train"] & groups["test"])
        self.assertFalse(groups["train"] & groups["validation"])
        self.assertFalse(groups["validation"] & groups["test"])

    def test_rights_and_tamper_rejected(self):
        self.spec["sources"]["fixture"]["rights_reviewed"] = False
        with self.assertRaises(ForgeError):
            build_release(self.source, self.spec, self.root / "bad")
        name = next(iter(self.release.manifest["files"]))
        (self.root / "release" / name).write_text("tampered")
        with self.assertRaises(ForgeError):
            self.release.verify()

    def test_bpe_fitting_never_requests_heldout(self):
        observed = []
        original = self.release.iter_rows

        def guarded(split, kind):
            observed.append(split)
            self.assertEqual(split, "train")
            return original(split, kind)

        self.release.iter_rows = guarded
        fit_tokenizer(self.release, self.root / "bpe.json", kind="bpe", vocab_size=300)
        self.assertEqual(set(observed), {"train"})

    def test_assistant_only_masks_and_reserved_tokens(self):
        messages = [
            {"role": "user", "content": "secret prompt"},
            {"role": "assistant", "content": "answer"},
            {"role": "tool", "content": "tool data"},
            {"role": "assistant", "content": "final"},
        ]
        ids, mask = self.tokens.conversation(messages)
        expected = sum(
            len(self.tokens.encode(m["content"])) + 1 for m in messages if m["role"] == "assistant"
        )
        self.assertEqual(sum(mask), expected)
        self.assertFalse(mask[0])
        for i, token in enumerate(ids):
            if token in self.tokens.special.values() and token != self.tokens.end:
                self.assertFalse(mask[i])
        with self.assertRaises(ValueError):
            self.tokens.encode("literal <|assistant|>")

    def test_cached_decode_causality_and_reset_both_models(self):
        for backend in ("transformer", "tac098"):
            torch.manual_seed(3)
            config = ModelConfig(
                backend=backend,
                vocab_size=256,
                width=32,
                layers=1,
                heads=4 if backend == "transformer" else 1,
                context=128,
            )
            model = create_model(config).eval()
            x = torch.randint(8, 128, (2, 12))
            with torch.no_grad():
                full = model(x)
                prefix, state = model.step(x[:, :7])
                suffix = []
                for i in range(7, 12):
                    scores, state = model.step(x[:, i : i + 1], state)
                    suffix.append(scores)
                torch.testing.assert_close(torch.cat(suffix, 1), full[:, 7:], atol=2e-6, rtol=2e-5)
                changed = x.clone()
                changed[:, 7:] = 90
                torch.testing.assert_close(model(changed)[:, :7], full[:, :7])
                torch.testing.assert_close(model(x), full)

    def test_dpo_reference_math_and_public_reward(self):
        value = dpo_loss(
            torch.tensor([2.0]), torch.tensor([1.0]), torch.tensor([0.0]), torch.tensor([0.0]), 0.5
        )
        self.assertAlmostEqual(
            value.item(), torch.nn.functional.softplus(torch.tensor(-0.5)).item()
        )
        row = {"verifier": "integer-comparison-v1", "left": 3, "right": 2, "reward": 999}
        self.assertEqual(task_reward(row, "0"), 1)
        self.assertEqual(task_reward(row, "1"), 0)
        self.assertEqual(task_reward(row, "0\nextra"), 0)

    def test_empty_updates_and_bad_group_rejected(self):
        for key, value in [
            ("gradient_accumulation", 0),
            ("gradient_accumulation", True),
            ("group_size", 1),
            ("steps", 0),
            ("beta", 0),
            ("replay_weight", -1),
            ("replay_weight", float("nan")),
        ]:
            stage = {"name": "sft", "steps": 2, "batch_size": 1, "learning_rate": 0.001, key: value}
            with self.assertRaises(ValueError):
                validate_stage(stage)

    def test_empty_stage_receipt_rejected(self):
        from trainlab.fullcycle.pipeline import verify_receipt

        with self.assertRaises(ValueError):
            verify_receipt(
                self.root, {"status": "complete", "input_identity": "x", "files": {}}, "x"
            )

    def test_resume_rejects_changed_pipeline_identity(self):
        config = dataclasses.asdict(
            ModelConfig(vocab_size=256, width=32, layers=1, heads=4, context=128)
        )
        stage = {"name": "sft", "steps": 2, "batch_size": 1, "learning_rate": 0.001}
        out = self.root / "identity-check"
        kwargs = dict(
            model_config=config,
            stage=stage,
            release=self.release,
            tokens=self.tokens,
            packed=self.root / "tokens",
            output=out,
        )
        train_stage(**kwargs, stop_after=1, input_identity="pipeline-A")
        with self.assertRaises(ValueError):
            train_stage(**kwargs, resume=out / "resume.pt", input_identity="pipeline-B")

    def test_checkpoint_pointer_survives_crash_before_index_publication(self):
        from trainlab.runner import write_json as original_write

        config = dataclasses.asdict(
            ModelConfig(vocab_size=256, width=32, layers=1, heads=4, context=128)
        )
        stage = {"name": "sft", "steps": 4, "batch_size": 2, "learning_rate": 0.001}
        kwargs = dict(
            model_config=config,
            stage=stage,
            release=self.release,
            tokens=self.tokens,
            packed=self.root / "tokens",
            checkpoint_every=2,
        )
        control, crashed = self.root / "crash-control", self.root / "crashed"
        train_stage(**kwargs, output=control)
        commits = [0]

        def crash(path, value):
            if Path(path).name == "checkpoint-index.json":
                commits[0] += 1
                if commits[0] == 2:
                    raise RuntimeError("simulated interruption after blob, before pointer")
            return original_write(path, value)

        with patch("trainlab.fullcycle.training.write_json", side_effect=crash):
            with self.assertRaises(RuntimeError):
                train_stage(**kwargs, output=crashed)
        train_stage(**kwargs, output=crashed, resume=crashed / "resume.pt")
        a, b = [checkpoint_load(p / "checkpoint.pt") for p in (control, crashed)]
        self.assertEqual(a["losses"], b["losses"])
        for key in a["model"]:
            torch.testing.assert_close(a["model"][key], b["model"][key], atol=0, rtol=0)

    def test_checkpointed_tac_global_counter_preserves_math_without_retained_hooks(self):
        from torch.utils.flop_counter import FlopCounterMode
        from trainlab.runner import write_json as original_write

        config = dataclasses.asdict(
            ModelConfig(
                backend="tac104",
                vocab_size=256,
                width=120,
                layers=4,
                heads=4,
                context=64,
                activation_checkpointing=True,
            )
        )
        stage = {
            "name": "pretrain",
            "steps": 3,
            "batch_size": 1,
            "sequence_length": 32,
            "gradient_accumulation": 2,
            "learning_rate": 0.001,
        }
        results, retained = [], []
        original_step = torch.optim.AdamW.step
        for name in ("attributed", "global"):
            counter = (
                FlopCounterMode(display=False) if name == "attributed" else GlobalFlopCounter()
            )
            hooks, commits = [], []

            def observed_step(optimizer, *args, **kwargs):
                hooks.append(len(counter.mod_tracker._hooks))
                return original_step(optimizer, *args, **kwargs)

            def observed_write(path, value):
                if Path(path).name == "checkpoint-index.json":
                    commits.append(value["step"])
                return original_write(path, value)

            output = self.root / name
            with (
                patch("trainlab.fullcycle.training.GlobalFlopCounter", return_value=counter),
                patch.object(torch.optim.AdamW, "step", observed_step),
                patch("trainlab.fullcycle.training.write_json", side_effect=observed_write),
            ):
                metrics = train_stage(
                    model_config=config,
                    stage=stage,
                    release=self.release,
                    tokens=self.tokens,
                    packed=self.root / "tokens",
                    output=output,
                    checkpoint_every=128,
                )
            self.assertEqual(commits, [1, 3])
            results.append((metrics, checkpoint_load(output / "checkpoint.pt")))
            retained.append(hooks)
        self.assertGreater(retained[0][-1], retained[0][0])
        self.assertEqual(retained[1], [0, 0, 0])
        first, second = results
        self.assertEqual(first[1]["losses"], second[1]["losses"])
        self.assertGreater(second[0]["counted_training_operator_flops"], 0)
        self.assertEqual(
            first[0]["counted_training_operator_flops"],
            second[0]["counted_training_operator_flops"],
        )
        for key in first[1]["model"]:
            torch.testing.assert_close(
                first[1]["model"][key], second[1]["model"][key], atol=0, rtol=0
            )

    def test_exact_interrupted_optimizer_rng_replay_all_objectives(self):
        config = dataclasses.asdict(
            ModelConfig(vocab_size=256, width=32, layers=1, heads=4, context=128)
        )
        for name in ("pretrain", "midtrain", "sft", "dpo", "rl"):
            stage = {"name": name, "steps": 4, "batch_size": 2, "learning_rate": 0.001}
            if name != "pretrain":
                stage["replay_weight"] = 0.5
            continuous = self.root / (name + "-continuous")
            paused = self.root / (name + "-paused")
            kwargs = dict(
                model_config=config,
                stage=stage,
                release=self.release,
                tokens=self.tokens,
                packed=self.root / "tokens",
                seed=17,
                checkpoint_every=2,
            )
            train_stage(**kwargs, output=continuous)
            result = train_stage(**kwargs, output=paused, stop_after=2)
            self.assertEqual(result["status"], "paused")
            train_stage(**kwargs, output=paused, resume=paused / "resume.pt")
            first, second = (checkpoint_load(p / "checkpoint.pt") for p in (continuous, paused))
            self.assertEqual(first["losses"], second["losses"])
            self.assertEqual(first["trained_tokens"], second["trained_tokens"])
            self.assertEqual(
                first["runtimes"][0]["counted_flops"], second["runtimes"][0]["counted_flops"]
            )
            for key in first["model"]:
                torch.testing.assert_close(
                    first["model"][key], second["model"][key], rtol=0, atol=0
                )
            if name == "rl":
                self.assertEqual(first["rollouts"], 64)
                self.assertGreater(sum(first["rewards"]), 0)


if __name__ == "__main__":
    unittest.main()
