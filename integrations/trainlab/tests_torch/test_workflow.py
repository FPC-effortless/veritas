"""Real single-process/DDP/export/checkpoint acceptance on constructed data."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import torch
from forge_data.core import release
from trainlab.runner import digest, list_runs, read_json, run_experiment, verify_run, write_json


class PyTorchWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="trainlab-pytorch-tests-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name) / "workflow"
        integrations = Path(__file__).resolve().parents[2]
        cls.env = dict(os.environ)
        cls.env["PYTHONPATH"] = (
            os.pathsep.join(
                str(integrations / package / "src") for package in ("trainlab", "forge")
            )
            + os.pathsep
            + cls.env.get("PYTHONPATH", "")
        )
        completed = subprocess.run(
            [
                sys.executable,
                str(integrations / "forge/examples/torch_workflow.py"),
                "--output",
                str(cls.root),
            ],
            env=cls.env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode:
            raise AssertionError(completed.stderr)
        cls.summary = json.loads(completed.stdout)
        cls.runs = {run["name"].split()[-1]: run for run in list_runs(cls.root / "runs")}

    def execute(self, label, config):
        path = self.root / "recipes" / label / "trial.json"
        write_json(path, config)
        with patch.dict(os.environ, self.env):
            run = run_experiment(path, self.root / "runs")
        self.assertTrue(verify_run(self.root / "runs" / run["id"])["valid"])
        return run

    def test_lifecycle_records_real_ranks_module_timings_and_export(self):
        self.assertEqual(len(self.runs), 8)
        self.assertTrue(all(run["status"] == "succeeded" for run in self.runs.values()))
        self.assertEqual(self.summary["qualification"], "NOT_QUALIFIED")
        self.assertEqual(self.summary["cuda"], "NOT_RUN")
        for run in self.runs.values():
            self.assertTrue(verify_run(self.root / "runs" / run["id"])["valid"])
        distributed = self.root / "runs" / self.runs["distributed"]["id"] / "output"
        ranks = [read_json(distributed / f"rank-{rank}.json") for rank in range(2)]
        self.assertEqual([rank["rank"] for rank in ranks], [0, 1])
        self.assertTrue(
            all(rank["backend"] == "gloo" and rank["world_size"] == 2 for rank in ranks)
        )
        self.assertEqual(ranks[0]["state_sha256"], ranks[1]["state_sha256"])
        profile = self.root / "runs" / self.runs["profile"]["id"] / "output"
        modules = read_json(profile / "runtime.json")["module_profile"]["modules"]
        self.assertEqual(set(modules), {"encoder", "activation", "head"})
        self.assertTrue(all(row["calls"] == 10 for row in modules.values()))
        self.assertIn("aten::linear", (profile / "operators.json").read_text())
        self.assertLessEqual(self.runs["deployment-check"]["metrics"]["export_max_error"], 1e-6)

    def test_nan_debug_and_changed_export_fail(self):
        config = read_json(self.root / "recipes/debug/recipe.json")
        config["command"] += ["--inject-nonfinite"]
        failed = self.execute("debug", config)
        self.assertEqual(failed["status"], "failed")
        stderr = (self.root / "runs" / failed["id"] / "stderr.log").read_text()
        self.assertIn("nonfinite tensor in activation encoder", stderr)
        model_path = self.root / "recipes/deployment-check/model.pt2"
        exported = torch.export.load(model_path)
        with torch.no_grad():
            exported.state_dict["head.bias"].add_(1)
        torch.export.save(exported, model_path)
        failed = self.execute(
            "deployment-check", read_json(self.root / "recipes/deployment-check/recipe.json")
        )
        self.assertEqual(failed["status"], "failed")
        self.assertIn("export_max_error", failed["error"])
        self.assertGreater(failed["metrics"]["export_max_error"], 0.1)

    def test_rank_failure_propagates_to_run(self):
        config = read_json(self.root / "recipes/distributed/recipe.json")
        config["command"] += ["--fail-rank", "0"]
        failed = self.execute("distributed", config)
        self.assertEqual(failed["status"], "failed")
        self.assertNotEqual(failed["exit_code"], 0)
        self.assertLess(failed["elapsed_seconds"], config["timeout_seconds"])
        self.assertIn(
            "injected constructed rank failure",
            (self.root / "runs" / failed["id"] / "stderr.log").read_text(),
        )

    def test_resume_replays_optimizer_rng_and_remaining_updates(self):
        initial = self.runs["supervised"]
        root = self.root / "recipes/supervised"
        checkpoint = self.root / "runs" / initial["id"] / "output/checkpoint.pt"
        (root / "checkpoint.pt").write_bytes(checkpoint.read_bytes())
        config = read_json(root / "recipe.json")
        config["inputs"].append("checkpoint.pt")
        config["command"] += ["--checkpoint", "checkpoint.pt", "--resume", "--updates", "5"]
        config["budget"].update(updates=5, exposures=5 * 8)
        resumed = self.execute("supervised", config)
        self.assertEqual(resumed["status"], "succeeded")
        config = read_json(root / "recipe.json")
        config["command"] += ["--updates", "85"]
        config["budget"].update(updates=85, exposures=85 * 8)
        full = self.execute("supervised", config)
        self.assertEqual(full["status"], "succeeded")
        snapshots = [
            torch.load(self.root / "runs" / run["id"] / "output/checkpoint.pt", weights_only=True)
            for run in (resumed, full)
        ]
        self.assertTrue(all(saved["step"] == 85 for saved in snapshots))
        for name in snapshots[0]["model"]:
            self.assertTrue(torch.equal(snapshots[0]["model"][name], snapshots[1]["model"][name]))
        self.assertTrue(torch.equal(snapshots[0]["torch_rng"], snapshots[1]["torch_rng"]))
        self.assertEqual(resumed["metrics"], full["metrics"])

    def test_small_partition_reports_actual_sample_exposure(self):
        small = self.root / "recipes/small"
        small.mkdir()
        for name in ("torch_model.py", "requirements-pytorch-cpu.txt"):
            shutil.copyfile(self.root / "recipes/supervised" / name, small / name)
        source = self.root / "small-source.jsonl"
        source.write_bytes(b"".join((self.root / "source.jsonl").read_bytes().splitlines(True)[:6]))
        release(source, self.root / "source-spec.json", small / "dataset")
        pin = digest(small / "dataset/manifest.json")
        config = read_json(self.root / "recipes/supervised/recipe.json")
        config["command"][config["command"].index("--pin") + 1] = pin
        config["command"] += ["--updates", "1"]
        config.update(split_identity=pin, checks={})
        config["budget"].update(updates=1, exposures=4)
        run = self.execute("small", config)
        self.assertEqual(run["status"], "succeeded")
        report = read_json(self.root / "runs" / run["id"] / "output/runtime.json")
        self.assertEqual(report["training_examples"], 4)
        self.assertEqual(report["batch_size"], 4)
        self.assertEqual(report["exposures"], 4)
