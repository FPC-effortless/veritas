"""Constructed adversarial controls for Hub acquisition and split/verifier boundaries."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge_data.hub import (
    HeldoutScreen,
    acquire,
    heldout_prompts,
    parquet_rows,
    question_group,
    read_plan,
)
from forge_data.language import ForgeError, build_release, canonical, digest
from forge_data.verifiers import extract_gsm8k_answer, verify_math
from trainlab.fullcycle.tokenization import fit_tokenizer

PLAN = Path(__file__).resolve().parents[1] / "examples/fullcycle003/data-plan.json"


class DataContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_operational_timeouts_reject_invalid_values_without_changing_budgets(self):
        from trainlab.fullcycle.pipeline import validate_config
        from trainlab.runner import LabError

        path = PLAN.with_name("tac-10m-full.json")
        config = json.loads(path.read_bytes())
        config["device"] = "cpu"
        validate_config(config)
        self.assertEqual(config["distributed_timeout_seconds"], 18000)
        self.assertEqual(config["evaluation_timeout_seconds"], 1800)
        self.assertEqual(config["stages"][0]["steps"], 12208)
        for key in ("distributed_timeout_seconds", "evaluation_timeout_seconds"):
            for value in (0, -1, True, 3.5, "18000", None):
                with self.subTest(key=key, value=value):
                    changed = copy.deepcopy(config)
                    changed[key] = value
                    with self.assertRaisesRegex(LabError, key):
                        validate_config(changed)

    def test_floating_revision_and_test_mislabel_rejected(self):
        plan = json.loads(PLAN.read_bytes())
        plan["datasets"][0]["revision"] = "main"
        path = self.root / "bad.json"
        path.write_bytes(canonical(plan))
        with self.assertRaises(ForgeError):
            read_plan(path)
        plan = json.loads(PLAN.read_bytes())
        source = next(s for s in plan["datasets"] if s["name"] == "gsm8k")
        next(f for f in source["files"] if f["upstream_split"] == "test")["upstream_split"] = (
            "train"
        )
        path.write_bytes(canonical(plan))
        with self.assertRaises(ForgeError):
            read_plan(path)

    def test_anonymous_download_verified_and_cached_corruption_rejected(self):
        plan = json.loads(PLAN.read_bytes())
        source = copy.deepcopy(plan["datasets"][0])
        blob = self.root / "fixture.parquet"
        blob.write_bytes(b"CONSTRUCTED pinned bytes")
        source.update(
            name="fixture",
            repo_id="constructed/fixture",
            revision="1" * 40,
            provenance="constructed://test",
        )
        source["files"] = [
            {
                "path": "train-00000.parquet",
                "size": blob.stat().st_size,
                "sha256": digest(blob),
                "upstream_split": "train",
            }
        ]
        plan["datasets"] = [source]
        path = self.root / "plan.json"
        path.write_bytes(canonical(plan))
        with (
            patch.dict("os.environ", {"HF_TOKEN": ""}),
            patch("huggingface_hub.hf_hub_download", return_value=str(blob)) as download,
        ):
            first = acquire(path, self.root / "cache")
            second = acquire(path, self.root / "cache")
            self.assertEqual(download.call_count, 1)
            self.assertIs(download.call_args.kwargs["token"], False)
            self.assertEqual(first, second)
            target = self.root / "cache" / first["files"][0]["file"]
            target.write_bytes(b"bad")
            with self.assertRaises(ForgeError):
                acquire(path, self.root / "cache")

    def test_public_test_reassignment_fails_even_if_caller_policy_allows(self):
        source = self.root / "rows.jsonl"
        row = {
            "kind": "text",
            "source_id": "fixture",
            "group": "public-test",
            "text": "public fixture",
            "split": "train",
            "upstream_split": "test",
        }
        source.write_bytes(canonical(row) + b"\n")
        spec = {
            "schema": "forge.language-source.v1",
            "source_sha256": digest(source),
            "split_salt": "x",
            "sources": {
                "fixture": {
                    "rights_reviewed": True,
                    "license": "Apache-2.0",
                    "provenance": "constructed://test",
                    "source_kind": "CONSTRUCTED",
                    "upstream_splits": {"test": ["train"]},
                }
            },
        }
        with self.assertRaises(ForgeError):
            build_release(source, spec, self.root / "release")
        row.pop("split")
        source.write_bytes(canonical(row) + b"\n")
        spec["source_sha256"] = digest(source)
        with self.assertRaises(ForgeError):
            build_release(source, spec, self.root / "one-sided")

    def test_all_official_test_groups_reserved_before_quotas_or_shape_filtering(self):
        smol = {"kind": "conversation"}
        preference = {"kind": "preference"}
        prompt = "Official held out prompt which exceeds any stored quota"
        stream = [
            (smol, "test", {"messages": [{"role": "user", "content": prompt}]}),
            (preference, "test", {"prompt": "A held out preference without a valid chosen reply"}),
        ]
        with patch("forge_data.hub.source_rows", return_value=iter(stream)):
            questions, reserved = heldout_prompts({"split_salt": "x"}, self.root)
        self.assertEqual(len(questions), 2)
        self.assertIn(question_group(prompt), reserved)
        screen = HeldoutScreen(questions)
        self.assertTrue(screen.contains("Text embedding this " + prompt))

    def test_parquet_projection_keeps_requested_component_without_changing_heldout_read(self):
        import pyarrow as pa
        import pyarrow.parquet as pq

        path = self.root / "conversations.parquet"
        pq.write_table(
            pa.Table.from_pylist(
                [
                    {
                        "source": "selected",
                        "messages": [{"role": "user", "content": "First"}],
                        "unused": 1,
                    },
                    {
                        "source": "other",
                        "messages": [{"role": "user", "content": "Second"}],
                        "unused": 2,
                    },
                ]
            ),
            path,
        )
        selected = list(parquet_rows(path, columns=("source", "messages"), component="selected"))
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["messages"][0]["content"], "First")
        self.assertNotIn("unused", selected[0])
        self.assertEqual(len(list(parquet_rows(path, columns=("source", "messages")))), 2)

    def test_normalized_public_question_overlap_screen(self):
        question = "A farmer has twelve sheep and buys eight more sheep. How many sheep now?"
        screen = HeldoutScreen([question])
        self.assertTrue(screen.contains("PREFIX " + question.upper() + " SUFFIX"))
        self.assertFalse(screen.contains("A different unrelated public document on biology."))

    def test_verifier_requires_final_number_and_resists_prefix_or_code(self):
        row = {"verifier": "gsm8k-exact-v1", "expected_answer": "1234.5"}
        self.assertEqual(verify_math(row, "Work\n#### $1,234.500"), 1)
        for text in (
            "1234.5",
            "#### 1234.5e2",
            "#### 1234.5.7",
            "#### 1234.5\nActually 9",
            '#### __import__("os")',
        ):
            self.assertEqual(verify_math(row, text), 0, text)
        large = "123456789012345678901234567890123456789"
        self.assertEqual(extract_gsm8k_answer("#### " + large), large)

    def test_artifact_tokenizer_is_hash_checked_without_reading_heldout(self):
        artifact, output = self.root / "fitted.json", self.root / "copied.json"
        artifact.write_text('{"kind":"byte-v1"}')

        class ForbiddenReader:
            def iter_rows(self, *args):
                raise AssertionError("fitted artifact must not consume any dataset split")

        expected = digest(artifact)
        actual = fit_tokenizer(
            ForbiddenReader(),
            output,
            kind="artifact",
            artifact_path=artifact,
            artifact_sha256=expected,
        )
        self.assertEqual(actual, expected)
        artifact.write_text('{"kind":"changed"}')
        with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
            fit_tokenizer(
                ForbiddenReader(),
                output,
                kind="artifact",
                artifact_path=artifact,
                artifact_sha256=expected,
            )

    def test_cuda_evaluator_handoff_releases_parent_cache_before_spawn(self):
        from types import SimpleNamespace

        from trainlab.fullcycle.pipeline import _evaluation

        checkpoint, tokenizer = self.root / "checkpoint.pt", self.root / "tokenizer.json"
        checkpoint.write_bytes(b"CONSTRUCTED checkpoint bytes")
        tokenizer.write_text("{}")
        order = []

        def execute(argv, **kwargs):
            order.append("spawn")
            self.assertEqual(argv[-1], "cuda")
            Path(argv[argv.index("--output") + 1]).write_text('{"fixture":true}')
            return SimpleNamespace(returncode=0)

        with (
            patch("trainlab.fullcycle.pipeline.source_identity", return_value={"fixture": "x"}),
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.empty_cache", side_effect=lambda: order.append("release")),
            patch("trainlab.fullcycle.pipeline.subprocess.run", side_effect=execute),
        ):
            _evaluation(
                checkpoint,
                tokenizer,
                {
                    "device": "cuda",
                    "dataset": {"directory": str(self.root), "manifest_sha256": "x"},
                },
                self.root / "evaluation.json",
            )
        self.assertEqual(order, ["release", "spawn"])
