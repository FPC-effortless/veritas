import copy
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trainlab.adequacy_capture import capture_training, verify_capture
from trainlab.execution_adequacy import assess_execution
from trainlab.prediction_artifacts import _bytes
from trainlab.research_adequacy import recipe_identity
from trainlab.runner import LabError, digest, write_json


@unittest.skipUnless(importlib.util.find_spec("torch"), "optional PyTorch unavailable")
class AdequacyCaptureTests(unittest.TestCase):
    def setUp(self):
        import torch

        self.torch = torch
        threads = torch.get_num_threads()
        torch.set_num_threads(1)
        self.addCleanup(torch.set_num_threads, threads)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "producer.py").write_text("# constructed trusted producer\n")
        rows = [
            {
                "record_id": str(i),
                "episode_id": str(i),
                "subject_id": str(i),
                "features": {"x": [float(i % 2), float(1 - i % 2)]},
                "target": {"value": i % 2, "status": "known"},
            }
            for i in range(8)
        ]
        write_json(
            self.root / "train.json",
            {
                "schema": "trainlab.forge-train-export.v1",
                "split": "train",
                "forge_manifest_sha256": "a" * 64,
                "feature_field": "x",
                "classes": 2,
                "examples": rows,
            },
        )
        self.config = {
            "inputs": ["producer.py", "train.json", "adequacy.json"],
            "artifacts": ["observations.json", "capture.json"],
            "command": ["python", "producer.py"],
            "budget": {"updates": 4},
            "seed": 7,
        }
        criteria = {
            dimension: [
                {
                    "field": field,
                    "operator": "eq",
                    "threshold": target,
                    "rationale": "constructed acceptance",
                }
            ]
            for dimension, field, target in [
                ("model_size", "parameters", 6),
                ("training_duration", "optimizer_updates", 4),
                ("datasets", "training_rows", 8),
                ("training_regime", "batch_size", 4),
            ]
        }
        self.contract = {
            "recipe_sha256": recipe_identity(self.config),
            "inputs": {n: digest(self.root / n) for n in ("producer.py", "train.json")},
            "execution": {"artifact": "observations.json", "dimensions": criteria},
        }
        write_json(self.root / "adequacy.json", self.contract)
        self.config["research_adequacy"] = {
            "file": "adequacy.json",
            "sha256": digest(self.root / "adequacy.json"),
        }
        torch.manual_seed(22)
        self.model = torch.nn.Linear(2, 2)

    def run_capture(self, **kwargs):
        return capture_training(
            self.config,
            self.root,
            data_file="train.json",
            producer_file="producer.py",
            model=kwargs.pop("model", self.model),
            steps=kwargs.pop("steps", 4),
            batch_size=4,
            learning_rate=0.1,
            seed=7,
            **kwargs,
        )

    def verify(self, receipt, report):
        return verify_capture(report, receipt, self.config, receipt["inputs"])

    def test_real_cpu_steps_exposures_and_replay(self):
        initial = copy.deepcopy(self.model)
        receipt, report = self.run_capture()
        self.assertEqual(receipt["observations"]["parameters"], 6)
        self.assertEqual(receipt["observations"]["optimizer_updates"], 4)
        self.assertEqual(receipt["observations"]["answer_exposures"], 16)
        self.assertNotEqual(
            report["model"]["initial_state_sha256"], report["model"]["final_state_sha256"]
        )
        checked = self.verify(receipt, report)
        self.assertEqual(checked["admissible"], 1)
        replay_receipt, replay_report = self.run_capture(model=initial)
        self.assertEqual(
            checked["replay_sha256"], self.verify(replay_receipt, replay_report)["replay_sha256"]
        )
        self.assertEqual(
            assess_execution(self.contract, self.config, receipt["inputs"], receipt)["status"],
            "MET",
        )

    def test_final_accuracy_rescored_from_frozen_source(self):
        receipt, report = self.run_capture()
        checked = self.verify(receipt, report)
        targets = [i % 2 for i in range(8)]
        expected = sum(a == b for a, b in zip(report["evaluation"]["predictions"], targets)) / 8
        self.assertEqual(checked["metrics"], {"accuracy": expected})
        altered = copy.deepcopy(report)
        altered["evaluation"]["accuracy"] = 0.99
        with self.assertRaises(LabError):
            self.verify(receipt, altered)
        altered = copy.deepcopy(report)
        altered["data_source"] = "{}"
        with self.assertRaises(LabError):
            self.verify(receipt, altered)

    def test_forged_dataset_counts_are_recomputed(self):
        receipt, report = self.run_capture()
        for metadata, observation in [
            ("groups", "training_groups"),
            ("feature_width", "feature_width"),
        ]:
            changed_receipt, changed_report = copy.deepcopy(receipt), copy.deepcopy(report)
            changed_report["dataset"][metadata] += 1
            changed_receipt["observations"][observation] += 1
            changed_report["receipt"] = changed_receipt
            changed_report["receipt_sha256"] = hashlib.sha256(_bytes(changed_receipt)).hexdigest()
            with self.subTest(field=metadata), self.assertRaises(LabError):
                self.verify(changed_receipt, changed_report)

    def test_sampler_seed_must_match_frozen_recipe(self):
        with self.assertRaises(LabError):
            capture_training(
                self.config,
                self.root,
                data_file="train.json",
                producer_file="producer.py",
                model=self.model,
                steps=4,
                batch_size=4,
                learning_rate=0.1,
                seed=8,
            )

    def test_runtime_identity_is_part_of_replay(self):
        receipt, report = self.run_capture()
        original = self.verify(receipt, report)["replay_sha256"]
        for field in (
            "python",
            "platform",
            "torch",
            "torch_build",
            "observer_sha256",
            "capture_sha256",
        ):
            changed = copy.deepcopy(report)
            changed["runtime"][field] = "0" * 64 if field.endswith("sha256") else "changed runtime"
            with self.subTest(field=field):
                self.assertNotEqual(original, self.verify(receipt, changed)["replay_sha256"])
        for mutation in (
            lambda r: r["runtime"].pop("torch_build"),
            lambda r: r["runtime"].update(extra="unrecognized"),
            lambda r: r["runtime"].update(observer_sha256="not-a-sha"),
        ):
            changed = copy.deepcopy(report)
            mutation(changed)
            with self.assertRaises(LabError):
                self.verify(receipt, changed)

    def test_under_run_measured_not_planned(self):
        receipt, report = self.run_capture(steps=2)
        self.assertEqual(receipt["observations"]["optimizer_updates"], 2)
        self.assertEqual(receipt["observations"]["answer_exposures"], 8)
        self.assertEqual(
            assess_execution(self.contract, self.config, receipt["inputs"], receipt)["status"],
            "INADEQUATE",
        )

    def test_nonfinite_parameter_failure_retained(self):
        with self.torch.no_grad():
            self.model.weight.fill_(float("nan"))
        receipt, report = self.run_capture()
        self.assertEqual(receipt["observations"]["optimizer_updates"], 0)
        self.assertEqual(receipt["observations"]["capture_complete"], 0)
        self.assertEqual(self.verify(receipt, report)["admissible"], 0)

    def test_source_mutation_closes_capture(self):
        from trainlab import training_observer

        original = training_observer.train_step

        def mutate(*args, **kwargs):
            (self.root / "producer.py").write_text("# changed source\n")
            return original(*args, **kwargs)

        with patch.object(training_observer, "train_step", side_effect=mutate):
            receipt, report = self.run_capture()
        self.assertEqual(receipt["observations"]["input_integrity"], 0)
        self.assertEqual(self.verify(receipt, report)["admissible"], 0)

    def test_counter_or_sampling_tampering_rejected(self):
        receipt, report = self.run_capture()
        bad_receipt, bad_report = copy.deepcopy(receipt), copy.deepcopy(report)
        bad_receipt["observations"]["optimizer_updates"] = 512
        bad_report["receipt"] = bad_receipt
        bad_report["receipt_sha256"] = hashlib.sha256(_bytes(bad_receipt)).hexdigest()
        with self.assertRaises(LabError):
            self.verify(bad_receipt, bad_report)
        bad_report = copy.deepcopy(report)
        bad_report["batch_indices_sha256"][0] = "0" * 64
        with self.assertRaises(LabError):
            self.verify(receipt, bad_report)

    def test_test_split_and_custom_model_unsupported(self):
        data = __import__("json").loads((self.root / "train.json").read_text())
        data["split"] = "test"
        write_json(self.root / "train.json", data)
        with self.assertRaises(LabError):
            self.run_capture()


if __name__ == "__main__":
    unittest.main()
