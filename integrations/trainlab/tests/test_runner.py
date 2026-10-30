from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Event
from unittest.mock import patch

from trainlab.runner import (
    LabError,
    compare_runs,
    list_runs,
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

    def test_noisy_experiment_has_bounded_logs_and_fails(self):
        self.config["command"] = [
            sys.executable,
            "-c",
            "import os; os.write(1,b'x'*100000); os.write(2,b'y'*100000)",
        ]
        self.save()
        run = run_experiment(self.path, self.root / "runs", log_limit=4096)
        self.assertEqual(run["status"], "failed")
        self.assertIn("log limit", run["error"])
        for name in ("stdout.log", "stderr.log"):
            self.assertLessEqual((self.root / "runs" / run["id"] / name).stat().st_size, 4096)
        self.assertTrue(verify_run(self.root / "runs" / run["id"])["valid"])

    def test_operator_cancellation_finalizes_interrupted_record(self):
        self.config["command"] = [sys.executable, "-c", "import time; time.sleep(20)"]
        self.save()
        cancelled = Event()
        cancelled.set()
        run = run_experiment(self.path, self.root / "runs", cancel=cancelled)
        self.assertEqual(run["status"], "interrupted")
        self.assertIsNotNone(run["finished_at"])
        self.assertTrue(verify_run(self.root / "runs" / run["id"])["valid"])

    def test_invalid_runtime_limits_rejected_before_launch(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(LabError):
                run_experiment(self.path, self.root / "runs", log_limit=value)

    def test_metadata_is_private_and_fsynced(self):
        from trainlab.runner import write_json

        with patch("trainlab.runner.os.fsync", wraps=__import__("os").fsync) as sync:
            write_json(self.root / "private.json", {"value": 1})
        self.assertTrue(sync.called)
        if sys.platform != "win32":
            self.assertEqual((self.root / "private.json").stat().st_mode & 0o777, 0o600)

    def test_active_store_limits_block_admission_and_oversized_state(self):
        self.run_one()
        with patch("trainlab.runner.MAX_ACTIVE_RUNS", 1), self.assertRaises(LabError):
            self.run_one()
        with patch("trainlab.runner.MAX_ACTIVE_RECORD_BYTES", 1), self.assertRaises(LabError):
            list_runs(self.root / "runs")

    def test_failed_metadata_write_preserves_previous_record(self):
        from trainlab.runner import write_json

        path = self.root / "private.json"
        write_json(path, {"value": "old"})
        with patch("trainlab.runner.os.fsync", side_effect=OSError("simulated I/O failure")):
            with self.assertRaises(OSError):
                write_json(path, {"value": "new"})
        self.assertEqual(json.loads(path.read_text()), {"value": "old"})
        self.assertEqual(list(self.root.glob(".metadata-*")), [])

    @unittest.skipUnless(os.name == "posix", "POSIX process-group acceptance")
    def test_detached_log_writer_cannot_mutate_finalized_logs(self):
        (self.root / "train.py").write_text(
            "import os,sys,subprocess,json; from pathlib import Path; "
            "p=Path(os.environ['TRAINLAB_OUTPUT_DIR']); "
            "(p/'metrics.json').write_text('{\"loss\":0.25}'); "
            "(p/'model.json').write_text('{}'); "
            "child=subprocess.Popen([sys.executable,'-c',"
            "\"import time; print('detached',flush=True); time.sleep(10)\"],"
            "start_new_session=True); "
            "Path('child.pid').write_text(str(child.pid))"
        )
        child = None
        try:
            run = self.run_one()
            child = int((self.root / "child.pid").read_text())
            self.assertEqual(run["status"], "failed")
            self.assertIn("detached workers", run["error"])
            self.assertTrue(verify_run(self.root / "runs" / run["id"])["valid"])
        finally:
            if child is not None:
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    unittest.main()
