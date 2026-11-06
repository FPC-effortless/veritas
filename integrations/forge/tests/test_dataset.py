"""Constructed behavioral checks for the pinned trainer boundary."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forge_data.core import ForgeError, canonical, hash_bytes, release
from forge_data.dataset import Dataset
from test_core import BASE, operations


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "release"
        self.spec = self.root / "spec.json"
        self.spec.write_bytes(canonical(BASE))
        self.input = self.root / "input.jsonl"
        rows = [operations(f"machine-{i}") for i in range(12)]
        for i, row in enumerate(rows):
            row["observation"]["temperature"] = i
            row["observation"]["unselected_private_field"] = "omit"
            row["outcome"].update(value=2 * i + 1, verified=True)
        self.input.write_bytes(b"".join(canonical(row) for row in rows))
        release(self.input, self.spec, self.output)
        self.pin = hash_bytes((self.output / "manifest.json").read_bytes())

    def read(self):
        return Dataset(self.output, manifest_sha256=self.pin)

    def alter(self, transform):
        manifest_path = self.output / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        path = self.output / "train.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        transform(manifest, rows)
        path.write_bytes(b"".join(canonical(row) for row in rows))
        manifest["file_sha256"]["train.jsonl"] = hash_bytes(path.read_bytes())
        manifest_path.write_bytes(canonical(manifest))
        self.pin = hash_bytes(manifest_path.read_bytes())

    def test_pin_and_snapshot(self):
        dataset = self.read()
        self.assertEqual(dataset.summary()["records"], 12)
        with self.assertRaises(ForgeError):
            Dataset(self.output, manifest_sha256="0" * 64)
        (self.output / "train.jsonl").write_text("tampered")
        with self.assertRaises(ForgeError):
            self.read()
        self.assertEqual(
            len(
                dataset.examples(
                    "train", cutoff="2026-01-01T10:00:01Z", feature_fields=["temperature"]
                )
            ),
            10,
        )

    def test_explicit_split_and_feature_selection_and_defensive_copies(self):
        dataset = self.read()
        with self.assertRaises(ForgeError):
            dataset.examples("test", cutoff="2026-01-01T10:00:01Z", feature_fields=["temperature"])
        for fields in ([], ["missing"], ["temperature", "temperature"], "temperature"):
            with self.subTest(fields=fields), self.assertRaises(ForgeError):
                dataset.examples("train", cutoff="2026-01-01T10:00:01Z", feature_fields=fields)
        values = dataset.examples(
            "train", cutoff="2026-01-01T10:00:01Z", feature_fields=["temperature"]
        )
        self.assertEqual(set(values[0]["features"]), {"temperature"})
        self.assertNotIn("action", values[0])
        self.assertIsNone(values[0]["target"])
        original = copy.deepcopy(values)
        values[0]["features"]["temperature"] = "changed"
        self.assertEqual(
            dataset.examples(
                "train", cutoff="2026-01-01T10:00:01Z", feature_fields=["temperature"]
            ),
            original,
        )
        self.assertEqual(
            len(
                dataset.examples(
                    "test",
                    cutoff="2026-01-01T10:00:01Z",
                    feature_fields=["temperature"],
                    allow_test=True,
                )
            ),
            1,
        )

    def test_asof_and_separate_supervised_target_clock(self):
        dataset = self.read()
        self.assertEqual(
            dataset.examples(
                "train", cutoff="2026-01-01T10:00:00Z", feature_fields=["temperature"]
            ),
            [],
        )
        examples = dataset.examples(
            "train",
            cutoff="2026-01-01T10:00:01Z",
            feature_fields=["temperature"],
            target_cutoff="2026-01-01T10:04:00Z",
        )
        for example in examples:
            self.assertEqual(example["target"]["value"], 2 * example["features"]["temperature"] + 1)
            self.assertTrue(example["target"]["verified"])
            self.assertEqual(set(example["features"]), {"temperature"})
        with self.assertRaises(ForgeError):
            dataset.examples(
                "train",
                cutoff="2026-01-01T10:00:01Z",
                feature_fields=["temperature"],
                target_cutoff="2026-01-01T09:00:00Z",
            )

    def test_rehashed_invalid_rows_fail(self):
        self.alter(lambda manifest, rows: rows[0].update(available_at="2025-01-01T00:00:00Z"))
        with self.assertRaises(ForgeError):
            self.read()

    def test_rehashed_identity_and_group_counts_fail(self):
        self.alter(lambda manifest, rows: manifest["groups"].update(train=999))
        with self.assertRaises(ForgeError):
            self.read()

    def test_rehashed_subject_assignment_fail(self):
        def change(manifest, rows):
            rows[0]["subject_id"] = json.loads((self.output / "test.jsonl").read_text())[
                "subject_id"
            ]

        self.alter(change)
        with self.assertRaises(ForgeError):
            self.read()

    def test_duplicate_keys_symlinks_and_bad_manifest_fail(self):
        original = (self.output / "manifest.json").read_bytes()
        (self.output / "manifest.json").write_bytes(
            original.replace(b'"adapter":', b'"adapter":"bad","adapter":', 1)
        )
        self.pin = hash_bytes((self.output / "manifest.json").read_bytes())
        with self.assertRaises(ForgeError):
            self.read()
        (self.output / "manifest.json").write_bytes(original)
        self.pin = hash_bytes(original)
        train = self.output / "train.jsonl"
        train.rename(self.root / "outside.jsonl")
        train.symlink_to(self.root / "outside.jsonl")
        with self.assertRaises(ForgeError):
            self.read()

    def test_unknown_outcomes_not_imputed(self):
        self.alter(
            lambda manifest, rows: rows[0].update(
                outcome={"status": "unknown", "verified": False, "available_at": None}
            )
        )
        examples = self.read().examples(
            "train",
            cutoff="2026-01-01T10:00:01Z",
            feature_fields=["temperature"],
            target_cutoff="2026-01-01T11:00:00Z",
        )
        self.assertEqual(sum(row["target"] is None for row in examples), 1)

    def test_cli_redacted_summary_and_guarded_export(self):
        cmd = [
            sys.executable,
            "-m",
            "forge_data.dataset",
            "inspect",
            "--release",
            str(self.output),
            "--manifest-sha256",
            self.pin,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["records"], 12)
        self.assertNotIn("machine-", result.stdout)
        result = subprocess.run(
            cmd[:3]
            + ["export"]
            + cmd[4:]
            + ["--split", "test", "--cutoff", "2026-01-01T10:00:01Z", "--feature", "temperature"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)

    def test_out_of_range_absolute_cutoffs_are_clean_errors(self):
        dataset = self.read()
        for cutoff in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:00:00-02:00"):
            with self.subTest(cutoff=cutoff), self.assertRaises(ForgeError):
                dataset.examples("train", cutoff=cutoff, feature_fields=["temperature"])
            with self.subTest(target_cutoff=cutoff), self.assertRaises(ForgeError):
                dataset.examples(
                    "train",
                    cutoff="2026-01-01T10:00:01Z",
                    target_cutoff=cutoff,
                    feature_fields=["temperature"],
                )
        cmd = [
            sys.executable,
            "-m",
            "forge_data.dataset",
            "export",
            "--release",
            str(self.output),
            "--manifest-sha256",
            self.pin,
            "--split",
            "train",
            "--feature",
            "temperature",
            "--cutoff",
            "0001-01-01T00:00:00+01:00",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_robot_relative_clocks_and_missing_labels(self):
        spec = dict(BASE, adapter="robot-jsonl")
        self.spec.write_bytes(canonical(spec))
        self.input.write_bytes(
            canonical(
                {
                    "episode_id": "robot-ep",
                    "subject_id": "robot-1",
                    "record_id": "frame-0",
                    "time_seconds": 0,
                    "available_seconds": 1,
                    "frame_index": 0,
                    "observation": {"joint": [0.1, 0.2]},
                    "action": None,
                    "outcome": None,
                }
            )
        )
        release(self.input, self.spec, self.root / "robot")
        pin = hash_bytes((self.root / "robot/manifest.json").read_bytes())
        dataset = Dataset(self.root / "robot", manifest_sha256=pin)
        self.assertEqual(dataset.examples("train", cutoff=0, feature_fields=["joint"]), [])
        row = dataset.examples("train", cutoff=1, feature_fields=["joint"])[0]
        self.assertEqual(row["features"], {"joint": [0.1, 0.2]})
        self.assertIsNone(row["target"])
        with self.assertRaises(ForgeError):
            dataset.examples("train", cutoff=10**1000, feature_fields=["joint"])

    def test_constructed_trainlab_workflow_and_immutable_output(self):
        try:
            from trainlab.runner import list_runs, verify_run
        except ImportError:
            self.skipTest(
                "install TrainLab or include its src in PYTHONPATH for the cross-package gate"
            )
        script = Path(__file__).parents[1] / "examples/dataset_quickstart.py"
        module_spec = importlib.util.spec_from_file_location("dataset_quickstart", script)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        result = module.prepare(self.root / "workbench", run=True)
        self.assertEqual(result["dataset"]["records"], 30)
        self.assertTrue(result["matched_declared_conditions"])
        self.assertEqual(result["qualification"], "NOT_QUALIFIED")
        runs = list_runs(self.root / "workbench/runs")
        self.assertEqual(len(runs), 2)
        self.assertTrue(all(run["status"] == "succeeded" for run in runs))
        self.assertTrue(
            all(verify_run(self.root / "workbench/runs" / run["id"])["valid"] for run in runs)
        )
        self.assertEqual(
            {run["split_identity"] for run in runs}, {result["dataset"]["manifest_sha256"]}
        )
        with self.assertRaises(ForgeError):
            module.prepare(self.root / "workbench")


if __name__ == "__main__":
    unittest.main()
