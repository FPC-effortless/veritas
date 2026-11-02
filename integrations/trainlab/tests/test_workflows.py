from __future__ import annotations

import copy
import unittest

import test_runner
from trainlab.runner import (
    LabError,
    compare_runs,
    load_config,
    validate_record,
    verify_run,
    write_json,
)


class WorkflowTests(unittest.TestCase):
    save = test_runner.RunnerTests.save
    run_one = test_runner.RunnerTests.run_one

    def setUp(self):
        test_runner.RunnerTests.setUp(self)
        self.config.update(
            schema="trainlab.experiment.v2",
            workload={
                "kind": "train",
                "training_method": "supervised",
                "execution": "single_process",
            },
            checks={"loss": {"max": 0.3}},
        )
        self.save()

    def test_v2_records_workload_and_enforces_thresholds(self):
        run = self.run_one()
        self.assertEqual(run["status"], "succeeded")
        self.assertEqual(run["schema"], "trainlab.run.v2")
        self.assertEqual(run["workload"], self.config["workload"])
        self.config["checks"]["loss"]["max"] = 0.2
        self.save()
        failed = self.run_one()
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["metrics"], {"loss": 0.25})
        self.assertIn("model.json", failed["artifacts"])
        self.assertIn("loss", failed["error"])
        self.assertTrue(verify_run(self.root / "runs" / failed["id"])["valid"])

    def test_workload_and_checks_reject_invalid_declarations(self):
        original = copy.deepcopy(self.config)
        for key, value in [
            ("workload", {"kind": "profile"}),
            ("workload", {**original["workload"], "kind": []}),
            ("workload", {**original["workload"], "kind": "profile"}),
            ("workload", {**original["workload"], "execution": "magic"}),
            ("checks", {"unknown": {"max": 1}}),
            ("checks", {"loss": {}}),
            ("checks", {"loss": {"max": True}}),
            ("checks", {"loss": {"min": 1, "max": 0}}),
            ("checks", {"loss": {"max": float("inf")}}),
        ]:
            with self.subTest(key=key, value=value):
                self.config = {**original, key: value}
                self.save()
                with self.assertRaises(LabError):
                    load_config(self.path)
        self.config = original
        self.config["schema"] = "trainlab.experiment.v1"
        self.save()
        with self.assertRaises(LabError):
            load_config(self.path)

    def test_all_workload_kinds_and_training_methods(self):
        for kind in ("train", "debug", "profile", "test", "export", "deployment_check"):
            self.config["workload"].update(
                kind=kind, training_method="supervised" if kind == "train" else None
            )
            self.save()
            self.assertEqual(self.run_one()["status"], "succeeded")
        self.config["workload"]["kind"] = "train"
        for method in (
            "supervised",
            "self_supervised",
            "fine_tuning",
            "distillation",
            "reinforcement",
            "continual",
            "custom",
        ):
            self.config["workload"].update(training_method=method, execution="distributed")
            self.save()
            self.assertEqual(load_config(self.path)["workload"]["training_method"], method)

    def test_record_metadata_remains_bound_to_saved_recipe(self):
        for status in ("succeeded", "failed"):
            self.config["checks"]["loss"]["max"] = 0.3 if status == "succeeded" else 0.2
            self.save()
            run = self.run_one()
            directory = self.root / "runs" / run["id"]
            run["workload"]["training_method"] = "fine_tuning"
            write_json(directory / "run.json", run)
            self.assertFalse(verify_run(directory)["valid"])
        run["checks"] = {"unknown": {"max": 1}}
        with self.assertRaises(LabError):
            validate_record(run)

    def test_comparison_flags_workload_and_threshold_differences(self):
        first = self.run_one()
        self.config["workload"]["training_method"] = "fine_tuning"
        self.config["checks"]["loss"]["max"] = 0.4
        self.save()
        compared = compare_runs([first, self.run_one()])
        self.assertIn("workload", compared["mismatches"])
        self.assertIn("checks", compared["mismatches"])

    def test_failed_acceptance_outputs_are_still_verified(self):
        self.config["checks"]["loss"]["max"] = 0.2
        self.save()
        run = self.run_one()
        directory = self.root / "runs" / run["id"]
        for key, value in (("metrics", {"loss": 0.0}), ("metrics", {}), ("artifacts", {})):
            with self.subTest(key=key, value=value):
                changed = {**run, key: value}
                write_json(directory / "run.json", changed)
                self.assertFalse(verify_run(directory)["valid"])

    def test_failed_acceptance_cannot_erase_all_result_identities(self):
        from trainlab.operations import backup_runs

        self.config["checks"]["loss"]["max"] = 0.2
        self.save()
        run = self.run_one()
        directory = self.root / "runs" / run["id"]
        run.update(metrics={}, artifacts={})
        write_json(directory / "run.json", run)
        self.assertFalse(verify_run(directory)["valid"])
        (directory / "output/model.json").unlink()
        self.assertFalse(verify_run(directory)["valid"])
        with self.assertRaisesRegex(LabError, "integrity"):
            backup_runs(self.root / "runs", self.root / "erased.zip")

    def test_failure_before_result_collection_still_verifies(self):
        # A command may write valid metrics but fail before all artifacts exist.
        # Such an explicitly failed execution is a valid diagnostic record.
        (self.root / "train.py").write_text(
            "import json,os; from pathlib import Path; "
            "p=Path(os.environ['TRAINLAB_OUTPUT_DIR']); "
            "(p/'metrics.json').write_text(json.dumps({'loss':0.25}))"
        )
        self.config["checks"]["loss"]["max"] = 0.2
        self.save()
        run = self.run_one()
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["metrics"], {})
        self.assertEqual(run["artifacts"], {})
        self.assertTrue(verify_run(self.root / "runs" / run["id"])["valid"])
