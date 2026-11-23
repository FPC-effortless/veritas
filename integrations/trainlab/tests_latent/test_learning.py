import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from trainlab.latent.learning import (
    audit_first_update,
    audit_matched_recipes,
    audit_seed_panel,
    audit_training_events,
    run_training_recipe,
    runner_config,
    training_recipe,
)
from trainlab.runner import LabError, load_config


class LatentLearningTests(unittest.TestCase):
    def recipe(self, **changes):
        return training_recipe(
            **(
                dict(
                    name="task",
                    parent_checkpoint_sha256="a" * 64,
                    seed=11,
                    updates=2,
                    task_schedule_sha256="b" * 64,
                )
                | changes
            )
        )

    def test_joint_recipe_matches_task_exposure_but_records_extra_language(self):
        task = self.recipe()
        joint = self.recipe(
            language_weight=1.0, language_targets_per_update=128, language_schedule_sha256="c" * 64
        )
        result = audit_matched_recipes(task, joint)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["right_budget"]["language_targets"], 256)
        self.assertEqual(audit_matched_recipes(task, self.recipe(seed=23))["status"], "FAIL")
        broken = copy.deepcopy(task)
        broken["updates"] = 3
        with self.assertRaises(LabError):
            audit_matched_recipes(task, broken)

    def test_language_only_control_matches_language_not_removed_task(self):
        joint = self.recipe(
            language_weight=1.0, language_targets_per_update=128, language_schedule_sha256="c" * 64
        )
        language = self.recipe(
            task_weight=0.0,
            task_targets_per_update=0,
            task_schedule_sha256=None,
            language_weight=1.0,
            language_targets_per_update=128,
            language_schedule_sha256="c" * 64,
        )
        result = audit_matched_recipes(
            joint,
            language,
            match_task_schedule=False,
            match_language_schedule=True,
            equal_budgets=("language_targets", "optimizer_updates"),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(audit_matched_recipes(joint, language)["status"], "UNKNOWN")

    def test_events_reject_skipped_updates_and_unverified_provenance(self):
        recipe = self.recipe()
        events = [
            {
                "update": i,
                "losses": {"task": 1.0},
                "combined_objective": 1.0,
                "preclip_gradient_norm": 2.0,
                "clipped": True,
                "gradients_finite": True,
                "weights_finite": True,
                "task_batch_sha256": "d" * 64,
            }
            for i in (1, 2)
        ]
        evidence = dict(
            expected_batch_hashes={"task": ["d" * 64] * 2},
            observed_seed=11,
            optimizer_fresh=True,
            reset_policy="per_sequence",
            source_hashes_before={"parent": "a" * 64},
            source_hashes_after={"parent": "a" * 64},
        )
        self.assertEqual(audit_training_events(recipe, events, **evidence)["status"], "PASS")
        self.assertEqual(audit_training_events(recipe, events)["status"], "UNKNOWN")
        changed = copy.deepcopy(events)
        changed[1]["task_batch_sha256"] = "e" * 64
        self.assertEqual(audit_training_events(recipe, changed, **evidence)["status"], "FAIL")
        changed[1]["update"] = 3
        with self.assertRaises(LabError):
            audit_training_events(recipe, changed, **evidence)

    def test_exact_first_update_includes_rng_optimizer_and_gradients(self):
        reference = {
            key: np.asarray([1.0, 2.0])
            for key in ("logits", "loss", "gradients", "norm", "state", "optimizer", "rng")
        }
        observed = copy.deepcopy(reference)
        self.assertEqual(audit_first_update(reference, observed)["status"], "PASS")
        observed["rng"][0] = 9
        self.assertEqual(audit_first_update(reference, observed)["status"], "FAIL")
        reference["norm"][0] = observed["norm"][0] = float("inf")
        self.assertFalse(audit_first_update(reference, observed)["checks"]["norm"])
        self.assertEqual(audit_seed_panel([11, 11, 23], [11, 23, 37])["status"], "FAIL")

    def test_empty_first_update_placeholders_cannot_pass(self):
        names = ("logits", "loss", "gradients", "norm", "state", "optimizer", "rng")
        for empty in (None, {}, [], np.array([]), {"unavailable": None}, "missing"):
            with self.subTest(empty=repr(empty)):
                reference = {name: copy.deepcopy(empty) for name in names}
                result = audit_first_update(reference, copy.deepcopy(reference))
                self.assertEqual(result["status"], "UNKNOWN")
                self.assertEqual(result["missing_evidence"], list(names))
        captured = {name: np.zeros(2) for name in names}
        captured["loss"], captured["norm"] = 0.0, 0.0
        captured["optimizer"] = {"state": {}, "param_groups": [{"params": [0, 1], "lr": 0.01}]}
        captured["rng"] = (3, np.arange(4, dtype=np.uint32), None)
        self.assertEqual(audit_first_update(captured, copy.deepcopy(captured))["status"], "PASS")
        for nonfinite in (float("inf"), np.float32("inf"), complex(float("inf"), 0)):
            captured["loss"] = nonfinite
            self.assertEqual(
                audit_first_update(captured, copy.deepcopy(captured))["status"], "FAIL"
            )

    def test_runner_translation_preserves_existing_research_gate(self):
        recipe = self.recipe()
        config = runner_config(
            recipe,
            recipe_input="learning.json",
            command=["python", "train.py"],
            inputs=["learning.json", "train.py", "adequacy.json"],
            artifacts=["checkpoint.json"],
            metrics={"loss": "min"},
            split_identity="fixed-family-split",
            source_kind="CONSTRUCTED",
            timeout_seconds=60,
            research_adequacy={"file": "adequacy.json", "sha256": "f" * 64},
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "learning.json").write_text(json.dumps(recipe))
            (root / "recipe.json").write_text(json.dumps(config))
            self.assertEqual(load_config(root / "recipe.json")["execution_purpose"], "research")
            with patch(
                "trainlab.latent.learning.run_experiment", return_value={"called": True}
            ) as runner:
                self.assertTrue(
                    run_training_recipe(
                        root / "recipe.json", root / "runs", recipe_input="learning.json"
                    )["called"]
                )
                runner.assert_called_once()
            config["execution_purpose"] = "engineering_diagnostic"
            (root / "recipe.json").write_text(json.dumps(config))
            with self.assertRaises(LabError):
                run_training_recipe(
                    root / "recipe.json", root / "runs", recipe_input="learning.json"
                )


if __name__ == "__main__":
    unittest.main()
