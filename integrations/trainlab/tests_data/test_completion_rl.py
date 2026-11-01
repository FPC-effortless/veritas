"""Actual policy sampling must lead the verified completion objective's gradient."""

from __future__ import annotations

import copy
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch
from torch import nn
from trainlab.fullcycle.backends import ModelConfig
from trainlab.fullcycle.rl import completion_grpo
from trainlab.fullcycle.tokenization import Tokens, pack_training
from trainlab.fullcycle.training import checkpoint_load, train_stage


class ScriptedChoicePolicy(nn.Module):
    def __init__(self, prefix):
        super().__init__()
        self.bias = nn.Parameter(torch.tensor(0.0))
        self.prefix = prefix
        self.config = SimpleNamespace(context=128)

    def forward(self, x):
        positions = torch.arange(x.shape[1]) + 1
        return self.scores(positions).expand(x.shape[0], -1, -1)

    def scores(self, positions):
        output = torch.full((len(positions), 256), -80.0) + self.bias * 0
        sequence = [35, 35, 35, 35, 32, 55, 7]
        for i, position in enumerate(positions.tolist()):
            index = position - self.prefix
            token = sequence[index] if 0 <= index < len(sequence) else 65
            if index == 5:
                output[i, 55] = self.bias
                output[i, 56] = 0
            else:
                output[i, token] = 0
        return output

    def step(self, x, state=None):
        clock = (state or 0) + x.shape[1]
        return self.scores(torch.tensor([clock]))[None], clock


class CompletionRLContracts(unittest.TestCase):
    def test_native_completion_replay_preserves_optimizer_schedule_and_rollouts(self):
        torch.set_num_threads(1)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "tokens.json"
            path.write_text('{"kind":"byte-v1"}')
            tokens = Tokens(path)

            class ConstructedRelease:
                def iter_rows(self, split, kind):
                    if kind == "text":
                        yield {"text": "Constructed replay control document. " * 20}
                    elif kind == "task":
                        yield {
                            "group": "constructed-replay",
                            "prompt": "Two plus two? Finish with #### and a number.",
                            "expected_answer": "4",
                            "verifier": "gsm8k-exact-v1",
                        }

            release = ConstructedRelease()
            pack_training(release, tokens, root / "packed")
            stage = {
                "name": "rl",
                "steps": 3,
                "batch_size": 1,
                "learning_rate": 0.001,
                "betas": [0.9, 0.95],
                "lr_schedule": "cosine",
                "warmup_steps": 1,
                "replay_weight": 0.1,
                "rl_mode": "completion",
                "group_size": 2,
                "max_new_tokens": 4,
            }
            options = dict(
                model_config=dataclasses.asdict(
                    ModelConfig(
                        backend="tac104",
                        vocab_size=256,
                        width=120,
                        layers=2,
                        heads=4,
                        context=128,
                    )
                ),
                stage=stage,
                release=release,
                tokens=tokens,
                packed=root / "packed",
                seed=71,
                checkpoint_every=1,
            )
            control, paused = root / "control", root / "paused"
            train_stage(**options, output=control)
            train_stage(**options, output=paused, stop_after=1)
            train_stage(**options, output=paused, resume=paused / "resume.pt")
            first, second = [checkpoint_load(p / "checkpoint.pt") for p in (control, paused)]
            self.assertEqual(first["optimizer"]["param_groups"][0]["betas"], (0.9, 0.95))
            self.assertEqual(first["losses"], second["losses"])
            for key in first["model"]:
                torch.testing.assert_close(
                    first["model"][key], second["model"][key], atol=0, rtol=0
                )
            torch.testing.assert_close(
                first["runtimes"][0]["data_rng"], second["runtimes"][0]["data_rng"]
            )
            for p in (control / "rollouts").glob("*.json"):
                self.assertEqual(
                    json.loads(p.read_bytes()),
                    json.loads((paused / "rollouts" / p.name).read_bytes()),
                )

    def test_verified_samples_push_policy_toward_correct_final_answer(self):
        torch.set_num_threads(1)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tokens.json"
            p.write_text('{"kind":"byte-v1"}')
            tokens = Tokens(p)
            prompt = "Solve."
            ids, _ = tokens.conversation([{"role": "user", "content": prompt}], prompt=True)
            policy = ScriptedChoicePolicy(len(ids))
            reference = copy.deepcopy(policy)
            stage = {"group_size": 16, "max_new_tokens": 8, "temperature": 1.0, "kl_beta": 0.02}
            row = {
                "group": "fixture",
                "prompt": prompt,
                "verifier": "gsm8k-exact-v1",
                "expected_answer": "7",
            }
            loss, used, targets, n, records, rewards = completion_grpo(
                policy, policy, reference, [row], tokens, torch.Generator().manual_seed(7), stage
            )
            self.assertEqual(n, 16)
            self.assertEqual(set(rewards), {0.0, 1.0})
            self.assertGreater(used, targets)
            self.assertTrue(torch.isfinite(loss))
            loss.backward()
            self.assertLess(policy.bias.grad.item(), 0)
            self.assertTrue(
                all(t["completion"] in ("#### 7", "#### 8") for t in records[0]["trajectories"])
            )
