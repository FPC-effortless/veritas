"""Real sibling-package lifecycle on constructed data; no scientific claims."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from trainlab.runner import list_runs, read_json, verify_run, write_json
from trainlab.server import Workspace


class ModelWorkflowTests(unittest.TestCase):
    @unittest.skipUnless(
        (Path(__file__).resolve().parents[2] / "forge/examples/model_workflow.py").is_file(),
        "requires sibling Forge checkout",
    )
    def test_pinned_forge_training_diagnostics_tests_and_export(self):
        integrations = Path(__file__).resolve().parents[2]
        sources = [integrations / package / "src" for package in ("forge", "trainlab")]
        env = dict(os.environ)
        env["PYTHONPATH"] = (
            os.pathsep.join(map(str, sources)) + os.pathsep + env.get("PYTHONPATH", "")
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "workflow"
            result = subprocess.run(
                [
                    sys.executable,
                    str(integrations / "forge/examples/model_workflow.py"),
                    "--output",
                    str(root),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads(result.stdout)
            self.assertEqual(summary["qualification"], "NOT_QUALIFIED")
            self.assertEqual(summary["deployment"], "LOCAL_CHECK_ONLY")
            runs = list_runs(root / "runs")
            self.assertEqual(len(runs), 7)
            self.assertTrue(all(run["status"] == "succeeded" for run in runs))
            self.assertTrue(all(verify_run(root / "runs" / run["id"])["valid"] for run in runs))
            profile = next(run for run in runs if run["workload"]["kind"] == "profile")
            report = read_json(root / "runs" / profile["id"] / "output/profile.json")
            self.assertEqual(set(report["modules"]), {"encoder", "affine", "output"})
            self.assertTrue(all(row["calls"] > 0 for row in report["modules"].values()))
            fine = next(run for run in runs if run["workload"]["training_method"] == "fine_tuning")
            initial = next(
                run for run in runs if run["workload"]["training_method"] == "supervised"
            )
            self.assertEqual(
                fine["inputs"]["checkpoint.json"], initial["artifacts"]["checkpoint.json"]
            )
            self.assertEqual(fine["split_identity"], summary["manifest_sha256"])
            workspace = Workspace(root / "runs", root / "recipes/test")
            self.addCleanup(workspace.close)
            recipe = workspace.recipes()[0]
            self.assertEqual(recipe["workload"]["kind"], "test")
            self.assertEqual(recipe["checks"], {"validation_mse": {"max": 0.1}})
            # Change a valid export to different finite weights: the command
            # completes, but numerical parity must make the acceptance fail.
            model_path = root / "recipes/deployment-check/model.json"
            model = read_json(model_path)
            model["slope"] += 1
            write_json(model_path, model)
            rejected = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "trainlab",
                    "run",
                    str(root / "recipes/deployment-check/recipe.json"),
                    "--runs",
                    str(root / "runs"),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(rejected.returncode, 1, rejected.stderr)
            failed = json.loads(rejected.stdout)
            self.assertEqual(failed["status"], "failed")
            self.assertIn("export_max_error", failed["error"])
            self.assertGreater(failed["metrics"]["export_max_error"], 0)
            self.assertTrue(verify_run(root / "runs" / failed["id"])["valid"])
