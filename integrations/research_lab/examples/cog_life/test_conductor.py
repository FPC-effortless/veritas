"""Constructed unit fixtures; no research inputs or scientific results."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import tempfile
import unittest
from unittest.mock import patch

import conductor as c
from trainlab.runner import digest


def prepared(tmp_path):
    bundle = tmp_path / "inputs"
    bundle.mkdir()
    roles = {"worker.py": "code", "spec.json": "world_spec", "protocol.md": "protocol"}
    for file in roles:
        (bundle / file).write_text("inert fixture\n")
    recipe = {
        "schema": "trainlab.experiment.v1", "execution_purpose": "engineering_diagnostic",
        "name": "cog081-world-check", "description": "Constructed unit fixture.",
        "command": [sys.executable, "worker.py", "world-check"], "source_kind": "CONSTRUCTED",
        "seed": 1, "timeout_seconds": 5, "split_identity": "INERT ENGINEERING DESIGN",
        "metrics": {"checks": "max"}, "budget": {"cpu": 1}, "inputs": list(roles),
        "artifacts": ["world-check.json"],
    }
    (bundle / "recipe.json").write_text(json.dumps(recipe))
    token = {
        "schema": c.TOKEN_SCHEMA, "decision": "GO", "study": "cog081",
        "phase": "world-check", "author": "author-fixture", "reviewer": "independent-fixture",
        "recipe_sha256": digest(bundle / "recipe.json"),
        "inputs": {n: digest(bundle / n) for n in roles}, "input_roles": roles,
        "runtime": c.runtime(), "parent_receipt_sha256": {},
        "execution_root": str(tmp_path / "runs"), "conductor_sha256": digest(Path(c.__file__)),
    }
    review = tmp_path / "approved.json"
    review.write_text(json.dumps(token))
    return bundle, review, tmp_path / "runs", token


class TestAdmission(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.bundle, self.review, self.output, self.token = prepared(Path(self.scratch.name))

    def preflight(self):
        return c.admission(self.bundle, self.review, self.output, "cog081", "world-check")

    def test_exact_reviewed_world_preflight_no_launch(self):
        self.assertEqual(self.preflight()[0]["budget"], {"cpu": 1})
        self.assertFalse(self.output.exists())

    def test_modified_scope_rejected(self):
        self.token["input_roles"]["spec.json"] = "truth"
        self.review.write_text(json.dumps(self.token))
        with self.assertRaisesRegex(ValueError, "roles"):
            self.preflight()

    def test_self_review_rejected(self):
        self.token["reviewer"] = " " + self.token["author"].upper()
        self.review.write_text(json.dumps(self.token))
        with self.assertRaisesRegex(ValueError, "independent"):
            self.preflight()

    def test_input_change_rejected(self):
        (self.bundle / "spec.json").write_text("changed")
        with self.assertRaisesRegex(ValueError, "input manifest"):
            self.preflight()

    def test_environment_does_not_forward_secret(self):
        with patch.dict(os.environ, COG_LIFE_INERT_SECRET="fixture", PYTHONPATH="/nonexistent/truth"):
            with c.worker_environment():
                self.assertNotIn("COG_LIFE_INERT_SECRET", os.environ)
                self.assertNotIn("PYTHONPATH", os.environ)
                self.assertEqual(os.environ["CUDA_VISIBLE_DEVICES"], "")
            self.assertEqual(os.environ["COG_LIFE_INERT_SECRET"], "fixture")

    def test_wrong_study_rejected(self):
        with self.assertRaisesRegex(ValueError, "study name"):
            c.admission(self.bundle, self.review, self.output, "cog091", "world-check")

    def test_wrong_run_root_rejected(self):
        with self.assertRaisesRegex(ValueError, "execution root"):
            c.admission(self.bundle, self.review, self.output / "other", "cog081", "world-check")

    def test_post_admission_stager_failure_retained(self):
        with patch.object(c.shutil, "copyfile", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                c.launch(self.bundle, self.review, self.output, "cog081", "world-check")
        record = json.loads((self.output / "cog081/world-check/stage-receipt.json").read_text())
        self.assertEqual((record["status"], record["error_type"]), ("FAILED", "OSError"))
