from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from trainlab.operations import backup_runs, recover_run, restore_runs, store_health
from trainlab.runner import LabError, run_experiment, verify_run


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        examples = Path(__file__).resolve().parents[1] / "examples"
        shutil.copytree(examples, self.root / "recipes")
        config = self.root / "recipes/linear.json"
        recipe = json.loads(config.read_text())
        recipe["command"][0] = sys.executable
        config.write_text(json.dumps(recipe))
        self.run = run_experiment(config, self.root / "runs")
        self.assertEqual(self.run["status"], "succeeded")

    def test_backup_restore_verifies_all_bytes_and_refuses_overwrite(self):
        archive = self.root / "backup.zip"
        receipt = backup_runs(self.root / "runs", archive)
        restored = self.root / "restored"
        result = restore_runs(archive, restored, expected_sha256=receipt["sha256"])
        self.assertEqual(result["runs"], 1)
        self.assertTrue(verify_run(restored / self.run["id"])["valid"])
        self.assertEqual(
            (restored / self.run["id"] / "run.json").read_bytes(),
            (self.root / "runs" / self.run["id"] / "run.json").read_bytes(),
        )
        with self.assertRaises(LabError):
            restore_runs(archive, restored, expected_sha256=receipt["sha256"])
        with self.assertRaises(LabError):
            backup_runs(self.root / "runs", archive)

    def test_backup_rejects_corrupt_or_unfinished_records(self):
        directory = self.root / "runs" / self.run["id"]
        artifact = next(iter(self.run["artifacts"]))
        (directory / "output" / artifact).write_text("tampered")
        with self.assertRaises(LabError):
            backup_runs(self.root / "runs", self.root / "backup.zip")
        self.assertFalse((self.root / "backup.zip").exists())
        (directory / "run.json").write_text("{}")
        with self.assertRaises(LabError):
            backup_runs(self.root / "runs", self.root / "backup.zip")

    def test_restore_checks_pin_and_zip_paths_before_publication(self):
        archive = self.root / "backup.zip"
        backup_runs(self.root / "runs", archive)
        with self.assertRaises(LabError):
            restore_runs(archive, self.root / "wrong-pin", expected_sha256="0" * 64)
        self.assertFalse((self.root / "wrong-pin").exists())
        with zipfile.ZipFile(archive, "a") as z:
            z.writestr("../escape", "bad")
        from trainlab.runner import digest

        with self.assertRaises(LabError):
            restore_runs(archive, self.root / "unsafe", expected_sha256=digest(archive))
        self.assertFalse((self.root / "unsafe").exists())
        self.assertFalse((self.root / "escape").exists())

    def test_health_is_aggregate_and_fails_closed_on_malformed_records(self):
        health = store_health(self.root / "runs")
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["runs"], 1)
        self.assertNotIn(self.run["name"], json.dumps(health))
        broken = self.root / "runs/broken"
        broken.mkdir()
        (broken / "run.json").write_text("{}")
        self.assertEqual(store_health(self.root / "runs")["status"], "degraded")

    def test_crash_recovery_requires_offline_confirmation_and_never_claims_success(self):
        directory = self.root / "runs" / self.run["id"]
        self.run.update(status="running", finished_at=None)
        (directory / "run.json").write_text(json.dumps(self.run))
        with self.assertRaises(LabError):
            recover_run(directory)
        recovered = recover_run(directory, confirm_no_running_jobs=True)
        self.assertEqual(recovered["status"], "interrupted")
        self.assertEqual(recovered["metrics"], {})
        self.assertEqual(recovered["qualification"], "NOT_QUALIFIED")
        self.assertTrue(verify_run(directory)["valid"])
        with self.assertRaises(LabError):
            recover_run(directory, confirm_no_running_jobs=True)

    def test_backup_and_restore_byte_limits_fail_without_publication(self):
        with self.assertRaises(LabError):
            backup_runs(self.root / "runs", self.root / "small.zip", max_bytes=1)
        self.assertFalse((self.root / "small.zip").exists())
        receipt = backup_runs(self.root / "runs", self.root / "backup.zip")
        with self.assertRaises(LabError):
            restore_runs(
                self.root / "backup.zip",
                self.root / "restored",
                expected_sha256=receipt["sha256"],
                max_bytes=1,
            )
        self.assertFalse((self.root / "restored").exists())

    def test_replacing_archive_path_cannot_substitute_unpinned_records(self):
        archive = self.root / "backup.zip"
        receipt = backup_runs(self.root / "runs", archive)
        empty = self.root / "empty"
        empty.mkdir()
        alternative = self.root / "alternative.zip"
        backup_runs(empty, alternative)
        real_zip = zipfile.ZipFile

        def replace_then_open(file, *args, **kwargs):
            archive.rename(self.root / "original.zip")
            shutil.copyfile(alternative, archive)
            return real_zip(file, *args, **kwargs)

        with patch("trainlab.operations.zipfile.ZipFile", side_effect=replace_then_open):
            result = restore_runs(
                archive, self.root / "restored", expected_sha256=receipt["sha256"]
            )
        self.assertEqual(result["runs"], 1)
        self.assertTrue(verify_run(self.root / "restored" / self.run["id"])["valid"])

    def test_in_place_archive_change_is_detected_before_publication(self):
        archive = self.root / "backup.zip"
        receipt = backup_runs(self.root / "runs", archive)
        empty = self.root / "empty"
        empty.mkdir()
        alternative = self.root / "alternative.zip"
        backup_runs(empty, alternative)
        real_zip = zipfile.ZipFile

        def change_then_open(file, *args, **kwargs):
            archive.write_bytes(alternative.read_bytes())
            return real_zip(file, *args, **kwargs)

        with patch("trainlab.operations.zipfile.ZipFile", side_effect=change_then_open):
            with self.assertRaises(LabError):
                restore_runs(archive, self.root / "restored", expected_sha256=receipt["sha256"])
        self.assertFalse((self.root / "restored").exists())
