import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from trainlab.dataset_repair import (
    classification_request,
    compare_drift_performance,
    compare_label_repair,
)
from trainlab.prediction_artifacts import write_predictions
from trainlab.runner import LabError, digest, write_json

CONFIG = {"code_sha256": "a" * 64, "configuration_sha256": "b" * 64}


@unittest.skipUnless(importlib.util.find_spec("forge_data"), "optional Forge dependency")
class DatasetRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.view = {
            "schema": "forge.diagnostic-input.v1",
            "feature_fields": ["x", "slice"],
            "group_fields": [],
            "rows": [
                {
                    "id": identity,
                    "split": split,
                    "features": {"x": x, "slice": "group"},
                    "label": label,
                }
                for identity, split, x, label in (
                    ("t", "train", 0, "a"),
                    ("v1", "validation", 1, "a"),
                    ("v2", "validation", 2, "b"),
                )
            ],
        }
        self.reviews = [
            {
                "id": "t",
                "decision": "accept",
                "old_label": "a",
                "new_label": "b",
                "reviewer": "control",
                "rationale": "restore known injected label",
            }
        ]
        self.corrected = copy.deepcopy(self.view)
        self.corrected["rows"][0]["label"] = "b"

    def evidence(self, name, doc, outputs, model):
        path = self.root / f"{name}.json"
        write_json(path, doc)
        pin = digest(path)
        request = classification_request(doc, dataset_sha256=pin, model_sha256=model, **CONFIG)
        prediction = self.root / f"{name}-predictions.json"
        prediction.unlink(missing_ok=True)
        artifact_pin = write_predictions(
            prediction,
            request,
            [
                {"id": row["id"], "output": value}
                for row, value in zip(request["rows"], outputs, strict=True)
            ],
        )
        return path, pin, {"path": prediction, "sha256": artifact_pin, "model_sha256": model}

    def repair(self, before=("b", "b"), after=("a", "a")):
        parent, parent_pin, baseline = self.evidence("parent", self.view, before, "c" * 64)
        corrected, corrected_pin, repaired = self.evidence(
            "corrected", self.corrected, after, "d" * 64
        )
        return compare_label_repair(
            parent,
            corrected,
            parent_sha256=parent_pin,
            corrected_sha256=corrected_pin,
            reviews=self.reviews,
            baseline=baseline,
            repaired=repaired,
            slice_field="slice",
            **CONFIG,
        )

    def test_paired_repair_reports_rescued_and_damaged_rows(self):
        result = self.repair()
        self.assertEqual(result["status"], "TESTED")
        self.assertEqual(result["overall"]["rescued_ids"], ["v1"])
        self.assertEqual(result["overall"]["damaged_ids"], ["v2"])
        self.assertEqual(result["overall"]["net_accuracy_change"], 0)
        self.assertEqual(result["slices"][0]["before_accuracy"], 0.5)

    def test_missing_prediction_not_counted_as_wrong(self):
        report = self.repair(after=("a", None))
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["overall"]["scored"], 1)
        self.assertEqual(report["overall"]["unknown"], 1)

    def test_unreviewed_feature_or_label_edit_rejected(self):
        self.corrected["rows"][1]["features"]["x"] = 8
        with self.assertRaisesRegex(LabError, "reviewed revision"):
            self.repair()
        self.corrected["rows"][1]["features"]["x"] = 1
        self.corrected["rows"][1]["label"] = "c"
        self.reviews.append({**self.reviews[0], "id": "v1", "new_label": "c"})
        with self.assertRaisesRegex(LabError, "training labels"):
            self.repair()

    def test_feature_reuse_rejected(self):
        self.view["rows"][0]["features"]["x"] = 1
        self.corrected["rows"][0]["features"]["x"] = 1
        with self.assertRaisesRegex(LabError, "exact selected features"):
            self.repair()

    def test_extra_features_do_not_become_inputs_and_unassigned_slice_is_visible(self):
        self.view["rows"][1]["features"].update(slice=None, unlisted="not an input")
        self.corrected["rows"][1]["features"].update(slice=None, unlisted="not an input")
        original = classification_request(
            self.view, dataset_sha256="c" * 64, model_sha256="d" * 64, **CONFIG
        )
        self.view["rows"][1]["features"].pop("unlisted")
        self.assertEqual(
            original,
            classification_request(
                self.view, dataset_sha256="c" * 64, model_sha256="d" * 64, **CONFIG
            ),
        )
        self.view["rows"][1]["features"]["unlisted"] = "not an input"
        self.assertIsNone(self.repair()["slices"][0]["value"])

    def test_missing_to_null_is_not_a_label_repair(self):
        self.view["rows"][0].pop("label")
        self.corrected["rows"][0]["label"] = None
        self.reviews[0].update(old_label=None, new_label=None)
        with self.assertRaisesRegex(LabError, "does not change"):
            self.repair()

    def test_drift_report_uses_fixed_model_and_known_slice_labels(self):
        current = copy.deepcopy(self.view)
        for row in current["rows"][1:]:
            row["id"] += "-current"
            row["features"]["x"] += 10
        args = {
            "fields": {"x": "numeric"},
            "thresholds": {"numeric": 0.2, "categorical": 0.2, "missingness": 0.1},
        }
        reference, ref_pin, ref_pred = self.evidence("ref", self.view, ("a", "b"), "c" * 64)
        shifted, shift_pin, shift_pred = self.evidence("cur", current, ("b", "a"), "c" * 64)
        result = compare_drift_performance(
            reference,
            shifted,
            reference_sha256=ref_pin,
            current_sha256=shift_pin,
            reference_predictions=ref_pred,
            current_predictions=shift_pred,
            slice_field="slice",
            **CONFIG,
            **args,
        )
        self.assertEqual(result["status"], "TESTED")
        self.assertEqual(result["distribution"]["status"], "FAILED")
        self.assertEqual(result["accuracy_by_slice"][0]["accuracy_difference"], -1)
        shifted, shift_pin, shift_pred = self.evidence("cur", current, ("b", "a"), "d" * 64)
        with self.assertRaisesRegex(LabError, "one fixed model"):
            compare_drift_performance(
                reference,
                shifted,
                reference_sha256=ref_pin,
                current_sha256=shift_pin,
                reference_predictions=ref_pred,
                current_predictions=shift_pred,
                **CONFIG,
                **args,
            )
