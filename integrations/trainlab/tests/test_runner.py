from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from trainlab.runner import (
    LabError,
    compare_runs,
    load_config,
    read_json,
    run_experiment,
    verify_run,
)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "data.txt").write_text("constructed training fixture")
        (self.root / "train.py").write_text(
            "import json,os; from pathlib import Path; "
            "p=Path(os.environ['TRAINLAB_OUTPUT_DIR']); "
            "(p/'metrics.json').write_text(json.dumps({'loss': 0.25})); "
            "(p/'model.json').write_text('{}')"
        )
        self.config = {
            "schema": "trainlab.experiment.v1",
            "name": "Test run",
            "description": "Constructed only",
            "command": [sys.executable, "train.py"],
            "seed": 7,
            "timeout_seconds": 5,
            "source_kind": "CONSTRUCTED",
            "split_identity": "fixture-v1",
            "inputs": ["data.txt", "train.py"],
            "artifacts": ["model.json"],
            "metrics": {"loss": "min"},
            "budget": {"updates": 10},
        }
        self.path = self.root / "experiment.json"
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.config))

    def run_one(self):
        return run_experiment(self.path, self.root / "runs")

    def test_run_records_reproducible_inputs_metrics_and_artifacts(self):
        run = self.run_one()
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(run["metrics"], {"loss": 0.25})
        self.assertEqual(run["qualification"], "NOT_QUALIFIED")
        self.assertIn("data.txt", run["inputs"])
        self.assertIn("model.json", run["artifacts"])
        self.assertTrue(verify_run(self.root / "runs" / run["id"])["valid"])
        self.assertNotEqual(run["id"], self.run_one()["id"])

    def test_tamper_is_detected(self):
        run = self.run_one()
        (self.root / "runs" / run["id"] / "output" / "model.json").write_text("tampered")
        self.assertFalse(verify_run(self.root / "runs" / run["id"])["valid"])

    def test_failure_timeout_and_missing_metrics(self):
        for command, timeout, status in [
            ([sys.executable, "-c", "raise SystemExit(3)"], 5, "failed"),
            ([sys.executable, "-c", "import time; time.sleep(5)"], 0.1, "timed_out"),
            ([sys.executable, "-c", "pass"], 5, "failed"),
        ]:
            with self.subTest(status=status):
                self.config.update(command=command, timeout_seconds=timeout)
                self.save()
                self.assertEqual(self.run_one()["status"], status)

    def test_strict_config_and_path_boundary(self):
        for key, value in [
            ("command", "echo hello"),
            ("seed", True),
            ("inputs", ["../outside"]),
            ("artifacts", ["../outside"]),
            ("metrics", {"loss": "fast"}),
            ("timeout_seconds", float("nan")),
            ("budget", {"updates": True}),
        ]:
            with self.subTest(key=key):
                original = self.config[key]
                self.config[key] = value
                self.save()
                with self.assertRaises(LabError):
                    load_config(self.path)
                self.config[key] = original
        self.path.write_text('{"schema":"a","schema":"b"}')
        with self.assertRaises(LabError):
            load_config(self.path)

    def test_compare_marks_mismatches_without_declaring_winners(self):
        first = self.run_one()
        second = self.run_one()
        comparison = compare_runs([first, second])
        self.assertTrue(comparison["matched_declared_conditions"])
        self.config["budget"]["updates"] = 20
        self.save()
        third = self.run_one()
        comparison = compare_runs([first, third])
        self.assertFalse(comparison["matched_declared_conditions"])
        self.assertIn("budget", comparison["mismatches"])
        self.assertEqual(comparison["qualification"], "NOT_QUALIFIED")

    def test_invalid_metrics_fail(self):
        (self.root / "train.py").write_text(
            "import os; from pathlib import Path; p=Path(os.environ['TRAINLAB_OUTPUT_DIR']); "
            "(p/'metrics.json').write_text('{\"loss\":NaN}')"
        )
        self.assertEqual(self.run_one()["status"], "failed")

    def test_replay_reproduces_metrics_and_checkpoint_bytes(self):
        first, second = self.run_one(), self.run_one()
        self.assertEqual(first["metrics"], second["metrics"])
        self.assertEqual(first["artifacts"], second["artifacts"])

    def test_changed_inputs_invalidate_success(self):
        (self.root / "train.py").write_text(
            (self.root / "train.py").read_text() + "; Path('data.txt').write_text('changed')"
        )
        self.assertEqual(self.run_one()["status"], "failed")

    def test_symlink_artifact_cannot_escape_output_directory(self):
        (self.root / "train.py").write_text(
            "import os; from pathlib import Path; p=Path(os.environ['TRAINLAB_OUTPUT_DIR']); "
            "(p/'metrics.json').write_text('{\"loss\":0.5}'); "
            "(p/'model.json').symlink_to(Path('data.txt').resolve())"
        )
        self.assertEqual(self.run_one()["status"], "failed")

    def test_saved_metrics_tampering_is_detected(self):
        run = self.run_one()
        path = self.root / "runs" / run["id"] / "run.json"
        run["metrics"]["loss"] = 0.0
        path.write_text(json.dumps(run))
        self.assertFalse(verify_run(path.parent)["valid"])

    def test_oversized_and_nonfinite_json_are_rejected(self):
        self.path.write_text("x" * 1025)
        with self.assertRaises(LabError):
            read_json(self.path, limit=1024)
        self.path.write_text('{"value":Infinity}')
        with self.assertRaises(LabError):
            read_json(self.path)

    def test_huge_metric_is_recorded_as_failure(self):
        (self.root / "train.py").write_text(
            "import os,json; from pathlib import Path; p=Path(os.environ['TRAINLAB_OUTPUT_DIR']); "
            "(p/'metrics.json').write_text(json.dumps({'loss':10**1000})); "
            "(p/'model.json').write_text('{}')"
        )
        self.assertEqual(self.run_one()["status"], "failed")


if __name__ == "__main__":
    unittest.main()
