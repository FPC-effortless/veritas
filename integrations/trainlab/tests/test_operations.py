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
from trainlab.runner import LabError, digest, list_runs, run_experiment, verify_run, write_json


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

    def refuse(self, status="UNKNOWN", *, missing_contract=True):
        from trainlab.research_adequacy import DIMENSIONS, recipe_identity

        path = self.root / "recipes/linear.json"
        config = json.loads(path.read_text())
        config["execution_purpose"] = "research"
        if not missing_contract:
            write_json(path.parent / "summary.json", {"observed": 1})
            config["inputs"] += ["summary.json", "adequacy.json"]
            contract = {
                "schema": "trainlab.research-adequacy.v1",
                "claim": "Constructed refusal test",
                "claim_kind": "bounded_diagnostic",
                "scope": "Operations regression fixture",
                "excluded_claims": "No model quality or scientific qualification",
                "recipe_sha256": recipe_identity(config),
                "inputs": {
                    name: digest(path.parent / name)
                    for name in config["inputs"]
                    if name != "adequacy.json"
                },
                "review": {
                    "author": "fixture-author",
                    "reviewer": "fixture-reviewer",
                    "basis": "Constructed storage check",
                    "criteria_frozen_before_evaluation": True,
                },
                "dimensions": {
                    name: {
                        "configuration": "Fixture",
                        "justification": "Exercise refusal storage",
                        "limitations": "Not scientific evidence",
                        "criteria": [
                            {
                                "id": "control",
                                "rationale": "Constructed failure",
                                "evidence": "summary.json",
                                "field": "missing" if status == "UNKNOWN" else "observed",
                                "operator": "ge",
                                "threshold": 2,
                            }
                        ],
                    }
                    for name in DIMENSIONS
                },
            }
            write_json(path.parent / "adequacy.json", contract)
            config["research_adequacy"] = {
                "file": "adequacy.json",
                "sha256": digest(path.parent / "adequacy.json"),
            }
        write_json(path, config)
        before = set((self.root / "runs/adequacy-refusals").glob("*.json"))
        with self.assertRaisesRegex(LabError, status):
            run_experiment(path, self.root / "runs")
        return (set((self.root / "runs/adequacy-refusals").glob("*.json")) - before).pop()

    def test_refused_research_does_not_break_health_and_survives_backup(self):
        refusal = self.refuse()
        with patch("trainlab.operations.MAX_ACTIVE_RUNS", 1):
            health = store_health(self.root / "runs")
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["runs"], 1)
        self.assertEqual(health["refusals"], 1)
        self.assertEqual(health["invalid"], 0)
        self.assertNotIn("Constructed", json.dumps(health))
        archive = self.root / "with-refusal.zip"
        receipt = backup_runs(self.root / "runs", archive)
        self.assertEqual(receipt["refusals"], 1)
        restored = self.root / "restored"
        result = restore_runs(archive, restored, expected_sha256=receipt["sha256"])
        self.assertEqual(result["runs"], 1)
        self.assertEqual(result["refusals"], 1)
        self.assertEqual(result["qualification"], "NOT_QUALIFIED")
        self.assertEqual(
            (restored / "adequacy-refusals" / refusal.name).read_bytes(), refusal.read_bytes()
        )
        self.assertTrue(verify_run(restored / self.run["id"])["valid"])

    def test_assessed_unknown_and_inadequate_refusals_are_preserved(self):
        original = (self.root / "recipes/linear.json").read_bytes()
        refusals = []
        for status in ("UNKNOWN", "INADEQUATE"):
            (self.root / "recipes/linear.json").write_bytes(original)
            refusals.append(self.refuse(status, missing_contract=False))
        self.assertEqual(store_health(self.root / "runs")["refusals"], 2)
        receipt = backup_runs(self.root / "runs", self.root / "refusals.zip")
        restored = self.root / "restored"
        restore_runs(self.root / "refusals.zip", restored, expected_sha256=receipt["sha256"])
        for refusal in refusals:
            self.assertEqual(
                (restored / "adequacy-refusals" / refusal.name).read_bytes(), refusal.read_bytes()
            )

    def test_bad_refusal_records_remain_visible_and_block_backup(self):
        refusal = self.refuse()
        valid = json.loads(refusal.read_text())
        for document in (
            {},
            {**valid, "status": "DECLARED_CRITERIA_MET"},
            {**valid, "qualification": "QUALIFIED"},
        ):
            with self.subTest(document=document):
                write_json(refusal, document)
                health = store_health(self.root / "runs")
                self.assertEqual(health["status"], "degraded")
                self.assertGreater(health["invalid"], 0)
                with self.assertRaises(LabError):
                    backup_runs(self.root / "runs", self.root / "bad.zip")
                self.assertFalse((self.root / "bad.zip").exists())

    def test_refusal_namespace_is_bounded_and_rejects_links_and_unknown_files(self):
        refusal = self.refuse()
        for name, value in (("MAX_REFUSALS", 0), ("MAX_REFUSAL_BYTES", 1)):
            with self.subTest(limit=name), patch("trainlab.operations." + name, value):
                self.assertEqual(store_health(self.root / "runs")["status"], "degraded")
                with self.assertRaises(LabError):
                    backup_runs(self.root / "runs", self.root / "bad.zip")
        invalid = refusal.with_name("unexpected.json")
        refusal.rename(invalid)
        self.assertEqual(store_health(self.root / "runs")["status"], "degraded")
        with self.assertRaises(LabError):
            backup_runs(self.root / "runs", self.root / "bad.zip")
        invalid.rename(refusal)
        if __import__("os").name == "posix":
            namespace = refusal.parent
            outside = self.root / "outside-refusals"
            namespace.rename(outside)
            namespace.symlink_to(outside, target_is_directory=True)
            self.assertEqual(store_health(self.root / "runs")["status"], "degraded")
            with self.assertRaises(LabError):
                backup_runs(self.root / "runs", self.root / "bad.zip")

    def test_restore_accepts_legacy_manifest_and_rejects_wrong_refusal_count(self):
        old = self.root / "original.zip"
        backup_runs(self.root / "runs", old)
        legacy = self.root / "legacy.zip"
        with zipfile.ZipFile(old) as source, zipfile.ZipFile(legacy, "w") as output:
            for name in source.namelist():
                data = source.read(name)
                if name == "backup-manifest.json":
                    manifest = json.loads(data)
                    manifest.pop("refusals", None)
                    data = json.dumps(manifest).encode()
                output.writestr(name, data)
        self.assertEqual(
            restore_runs(legacy, self.root / "legacy-restored", expected_sha256=digest(legacy))[
                "runs"
            ],
            1,
        )
        self.refuse()
        archive = self.root / "refusal.zip"
        backup_runs(self.root / "runs", archive)
        changed = self.root / "changed.zip"
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(changed, "w") as output:
            for name in source.namelist():
                data = source.read(name)
                if name == "backup-manifest.json":
                    manifest = json.loads(data)
                    manifest["refusals"] = 0
                    data = json.dumps(manifest).encode()
                output.writestr(name, data)
        with self.assertRaises(LabError):
            restore_runs(changed, self.root / "bad-restore", expected_sha256=digest(changed))
        self.assertFalse((self.root / "bad-restore").exists())

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

    def test_health_uses_the_dashboard_metadata_capacity_boundary(self):
        root = self.root / "runs"
        size = len(json.dumps(self.run, allow_nan=False).encode())
        for limit, expected in ((size, "ok"), (size - 1, "degraded")):
            with (
                self.subTest(limit=limit),
                patch("trainlab.operations.MAX_ACTIVE_RECORD_BYTES", limit),
                patch("trainlab.runner.MAX_ACTIVE_RECORD_BYTES", limit),
            ):
                if expected == "degraded":
                    with self.assertRaisesRegex(LabError, "metadata exceeds"):
                        list_runs(root)
                else:
                    self.assertEqual(len(list_runs(root)), 1)
                self.assertEqual(store_health(root)["status"], expected)

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
