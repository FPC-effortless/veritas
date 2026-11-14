import hashlib
import tempfile
import unittest
from pathlib import Path

from trainlab.intervention_comparison import compare
from trainlab.prediction_artifacts import make_request, write_predictions
from trainlab.runner import LabError, write_json

TASK = {"name": "binary", "output_schema": "finite-json-v1"}
STATE = {
    "mode": "stateless",
    "initial_state_sha256": "a" * 64,
    "persists": "none",
    "query_mutates": False,
    "reset": "each input",
}


class InterventionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.rows = [
            {"id": row, "input": v} for row, v in (("focal", 1), ("peer", 2), ("unknown", 3))
        ]
        self.labels = {
            "focal": {"label": 1, "labeled": True, "role": "focal"},
            "peer": {"label": 0, "labeled": True, "role": "collateral"},
            "unknown": {"label": None, "labeled": False, "role": "collateral"},
        }
        self.panel = self.json_pin("panel.json", {"labels": self.labels})

    def json_pin(self, name, value):
        path = self.root / name
        write_json(path, value)
        return {"path": path, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def artifact(self, name, outputs, *, weights="b" * 64, config="c" * 64, rows=None):
        request = make_request(
            {"model": weights, "configuration": config, "dataset": "d" * 64, "code": "e" * 64},
            self.rows if rows is None else rows,
            task=TASK,
            state=STATE,
        )
        predictions = [
            {"id": row["id"], "output": value}
            for row, value in zip(request["rows"], outputs, strict=True)
        ]
        path = self.root / name
        return {
            "path": path,
            "sha256": write_predictions(path, request, predictions),
            "request": request,
        }

    def prescription(self, mode, baseline, treatment, *, training=None):
        recipe = self.json_pin("recipe.json", {"operation": "configured test intervention"})
        return self.json_pin(
            "design.json",
            {
                "schema": "trainlab.intervention-comparison.v1",
                "mode": mode,
                "recipe_sha256": recipe["sha256"],
                "panel_sha256": self.panel["sha256"],
                "prediction_sha256": {
                    "baseline": baseline["sha256"],
                    "treatment": treatment["sha256"],
                },
                "training_run_sha256": training,
            },
        ), recipe

    def test_frozen_intervention_counts_rescue_damage_and_partial(self):
        def frozen_predict(feature):
            return int(2 * feature >= 10)

        raw = [row["input"] for row in self.rows]
        before = [frozen_predict(feature) for feature in raw]
        after = [frozen_predict(feature + 4) for feature in raw]
        baseline = self.artifact("before.json", before)
        treatment = self.artifact("after.json", after, config="f" * 64)
        design, recipe = self.prescription("frozen", baseline, treatment)
        report = compare(design, recipe, self.panel, baseline, treatment)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["counts"]["changed"], 3)
        self.assertEqual(report["roles"]["focal"]["rescued"], 1)
        self.assertEqual(report["roles"]["collateral"]["harmed"], 1)
        self.assertEqual(report["counts"]["unknown_labels"], 1)
        recipe["path"].write_text("{}")
        with self.assertRaisesRegex(LabError, "recipe.*pin"):
            compare(design, recipe, self.panel, baseline, treatment)

    def test_frozen_weights_and_input_scope_are_validated(self):
        baseline = self.artifact("before.json", [0, 0, 0])
        changed = self.artifact("after.json", [1, 1, 1], weights="c" * 64)
        design, recipe = self.prescription("frozen", baseline, changed)
        with self.assertRaisesRegex(LabError, "frozen.*model"):
            compare(design, recipe, self.panel, baseline, changed)
        shifted_rows = [dict(row) for row in self.rows]
        shifted_rows[0]["input"] = 99
        mismatched = self.artifact("shift.json", [1, 1, 1], config="f" * 64, rows=shifted_rows)
        design, recipe = self.prescription("frozen", baseline, mismatched)
        with self.assertRaisesRegex(LabError, "evaluation"):
            compare(design, recipe, self.panel, baseline, mismatched)

    def test_observed_null_is_a_scored_reference_value(self):
        self.labels["unknown"]["labeled"] = True
        self.panel = self.json_pin("panel.json", {"labels": self.labels})
        baseline = self.artifact("before.json", [1, 0, 7])
        treatment = self.artifact("after.json", [1, 0, None])
        design, recipe = self.prescription("frozen", baseline, treatment)
        report = compare(design, recipe, self.panel, baseline, treatment)
        self.assertEqual(report["status"], "TESTED")
        self.assertEqual(report["witnesses"]["rescued"], ["unknown"])

    def test_deterministic_refit_with_training_artifact_identities(self):
        samples = [0, 1, 2, 3]

        def fit(targets):
            weights = [sum(x * y for x, y in zip(samples, targets, strict=True)), sum(targets)]
            digest = hashlib.sha256(repr(weights).encode()).hexdigest()
            predictions = [int(weights[0] * row["input"] >= 10) for row in self.rows]
            return predictions, digest

        before, base_weights = fit([0, 0, 0, 0])
        after, new_weights = fit([0, 0, 1, 1])
        baseline = self.artifact("before.json", before, weights=base_weights)
        treatment = self.artifact("after.json", after, weights=new_weights)
        design, recipe = self.prescription(
            "retrained", baseline, treatment, training={"baseline": "5" * 64, "treatment": "6" * 64}
        )
        report = compare(design, recipe, self.panel, baseline, treatment)
        self.assertEqual(report["mode"], "retrained")
        self.assertEqual(report["counts"]["changed"], 2)
        self.assertEqual(report["counts"]["harmed"], 1)
