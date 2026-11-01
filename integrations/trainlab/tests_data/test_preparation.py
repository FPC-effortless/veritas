"""Full constructed acquisition controls: quotas, deterministic BPE, and leakage."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge_data.hub import _prepare, object_hash, question_group, split_for
from forge_data.language import ForgeError, LanguageRelease, canonical

PLAN = Path(__file__).resolve().parents[1] / "examples/fullcycle003/data-plan.json"


def constructed_inputs():
    plan = json.loads(PLAN.read_bytes())
    plan.update(
        vocab_size=264,
        tokenizer_training_bytes=4096,
        pretrain_tokens=512,
        evaluation_text_tokens=64,
    )
    plan["quotas"] = {
        kind: dict(train=1, validation=1, test=1) for kind in ("conversation", "preference")
    }
    sources = {s["kind"]: s for s in plan["datasets"]}
    rows = []
    for i in range(400):
        rows.append(
            (
                sources["text"],
                "train",
                {
                    "url": f"https://constructed.test/{i}",
                    "text": f"Public constructed document {i} about science and language. " * 8,
                },
            )
        )
    for split in ("train", "validation", "test"):
        for kind in ("conversation", "preference", "task"):
            for i in range(1000):
                prompt = (
                    f"Constructed {kind} {split} problem {i} asks for "
                    "a descriptive explanation of an example."
                )
                upstream = "test" if split == "test" else "train"
                if split_for(question_group(prompt), plan["split_salt"], upstream) == split:
                    break
            if kind == "conversation":
                raw = {
                    "source": "smol-magpie-ultra-short",
                    "messages": [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": "Example answer."},
                    ],
                }
            elif kind == "preference":
                raw = {
                    "prompt": prompt,
                    "chosen": [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": "Good answer."},
                    ],
                    "rejected": [
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": "Bad answer."},
                    ],
                    "score_chosen": 2.0,
                    "score_rejected": 1.0,
                }
            else:
                raw = {"question": prompt, "answer": "Reasoning.\n#### 4"}
            rows.append((sources[kind], upstream, raw))
    # This official TEST row is beyond quota. Its exact prompt also appears in TRAIN.
    prompt = next(
        f"Excluded official test prompt number {i}."
        for i in range(1000)
        if split_for(
            question_group(f"Excluded official test prompt number {i}."), plan["split_salt"]
        )
        == "train"
    )
    raw = {
        "source": "smol-magpie-ultra-short",
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": "Answer."},
        ],
    }
    rows.extend([(sources["conversation"], "test", raw), (sources["conversation"], "train", raw)])
    return plan, rows, prompt


class PreparationContracts(unittest.TestCase):
    def test_preparation_is_repeatable_and_reserves_even_unretained_test_prompts(self):
        plan, rows, excluded = constructed_inputs()

        def stream(plan, root, kind=None, upstream_split=None, *, skip_text=False):
            return (
                copy.deepcopy(row)
                for row in rows
                if (not kind or row[0]["kind"] == kind)
                and (not upstream_split or row[1] == upstream_split)
                and (not skip_text or row[0]["kind"] != "text")
            )

        with (
            tempfile.TemporaryDirectory() as d,
            patch("forge_data.hub.source_rows", side_effect=stream),
        ):
            results = []
            for name in ("first", "second"):
                root = Path(d) / name
                root.mkdir()
                (root / "acquisition.json").write_bytes(
                    canonical({"plan_sha256": object_hash(plan)})
                )
                result = _prepare(plan, root, {})
                results.append(result)
                release = LanguageRelease(root / "release", result["manifest_sha256"])
                self.assertNotIn(
                    question_group(excluded),
                    {r["group"] for r in release.iter_rows("train", "conversation")},
                )
                for split in ("train", "validation", "test"):
                    self.assertGreaterEqual(result["training_text_tokens_before_pack"][split], 64)
            self.assertEqual(results[0], results[1])

    def test_missing_heldout_text_budget_fails_instead_of_freezing(self):
        plan, rows, _ = constructed_inputs()

        def stream(plan, root, kind=None, upstream_split=None, *, skip_text=False):
            return (
                copy.deepcopy(row)
                for row in rows
                if (not kind or row[0]["kind"] == kind)
                and (not upstream_split or row[1] == upstream_split)
                and (not skip_text or row[0]["kind"] != "text")
                and (
                    row[0]["kind"] != "text"
                    or split_for(
                        "document:" + hashlib.sha256(row[2]["url"].encode()).hexdigest(),
                        plan["split_salt"],
                        text=True,
                    )
                    == "train"
                )
            )

        with (
            tempfile.TemporaryDirectory() as d,
            patch("forge_data.hub.source_rows", side_effect=stream),
        ):
            root = Path(d)
            (root / "acquisition.json").write_text("{}")
            with self.assertRaisesRegex(ForgeError, "validation token budget"):
                _prepare(plan, root, {})
            self.assertFalse((root / "prepared.json").exists())
