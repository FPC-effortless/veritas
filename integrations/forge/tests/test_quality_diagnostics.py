import tempfile
import unittest
from pathlib import Path

from forge_data.core import ForgeError, canonical, hash_bytes
from forge_data.quality_diagnostics import (
    adjudicate,
    distributions,
    near_duplicates,
    transformation_audit,
)

THRESHOLDS = {"numeric": 0.2, "categorical": 0.2, "missingness": 0.1}
TIME = "2026-11-14T00:00:00Z"


def document():
    return {
        "schema": "forge.diagnostic-input.v1",
        "feature_fields": ["x", "category", "text"],
        "group_fields": [],
        "rows": [
            {
                "id": name,
                "split": split,
                "features": {"x": x, "category": cat, "text": text},
                "label": x,
            }
            for name, split, x, cat, text in [
                ("t0", "train", 0, "A", "red apple"),
                ("t1", "train", 1, "B", "blue moon"),
                ("v0", "validation", 0, "A", "green pear"),
                ("v1", "validation", 1, "B", "bright sun"),
            ]
        ],
    }


def review():
    return [
        {
            "id": "t0",
            "decision": "accept",
            "old_label": 0,
            "new_label": 1,
            "reviewer": "constructed-reviewer",
            "rationale": "Constructed correction control",
        }
    ]


def transforms():
    return [
        {
            "id": "direct",
            "outputs": ["x", "category", "text"],
            "fit_scope": "stateless",
            "fit_ids": [],
            "uses_target": False,
        }
    ]


def availability():
    return [
        {"id": row["id"], "field": f, "available_at": TIME, "prediction_at": TIME}
        for row in document()["rows"]
        for f in document()["feature_fields"]
    ]


class QualityTests(unittest.TestCase):
    def test_huge_threshold_rejected_as_invalid_input(self):
        with self.assertRaises(ForgeError):
            near_duplicates(self.path, sha256=self.pin, field="text", threshold=10**1000)

    def test_malformed_time_with_unknown_companion_rejected(self):
        rows = availability()
        rows[0].update(available_at="not-a-time", prediction_at=None)
        with self.assertRaises(ForgeError):
            self.audit(availability=rows)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "view.json"
        self.pin = self.write(document())

    def write(self, doc):
        data = canonical(doc)
        self.path.write_bytes(data)
        return hash_bytes(data)

    def drift(self, **kwargs):
        return distributions(
            self.path,
            self.path,
            reference_sha256=self.pin,
            current_sha256=self.pin,
            fields={"x": "numeric", "category": "categorical"},
            thresholds=THRESHOLDS,
            **kwargs,
        )

    def audit(self, **kwargs):
        return transformation_audit(
            self.path,
            sha256=self.pin,
            transforms=kwargs.get("transforms", transforms()),
            availability=kwargs.get("availability", availability()),
        )

    def test_identical_distribution_and_missingness(self):
        report = self.drift()
        self.assertEqual(report["status"], "TESTED")
        self.assertEqual([x["distance"] for x in report["observations"]["checks"]], [0, 0])

    def test_complete_numeric_and_categorical_shift(self):
        doc = document()
        for row in doc["rows"][2:]:
            row["features"].update(x=10, category="novel")
        self.pin = self.write(doc)
        report = self.drift()
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual([x["distance"] for x in report["observations"]["checks"]], [1, 1])
        self.assertEqual(report["observations"]["checks"][1]["categories"]["novel_current"], 1)

    def test_missingness_changes_separate_from_known_values(self):
        doc = document()
        doc["rows"][2]["features"]["x"] = None
        self.pin = self.write(doc)
        result = self.drift()["observations"]["checks"][0]
        self.assertEqual(result["missing"], [0, 1])
        self.assertEqual(result["missingness_delta"], 0.5)

    def test_all_missing_and_partial_coverage_never_clean(self):
        doc = document()
        for row in doc["rows"]:
            row["features"]["x"] = None
        self.pin = self.write(doc)
        report = self.drift()
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["observations"]["checks"][0]["status"], "UNSUPPORTED")
        self.pin = self.write(document())
        self.assertEqual(self.drift(max_rows=1)["status"], "INCONCLUSIVE")

    def test_numeric_bool_and_complex_category_are_invalid(self):
        doc = document()
        doc["rows"][0]["features"].update(x=True, category={"bad": 1})
        self.pin = self.write(doc)
        self.assertEqual(self.drift()["status"], "FAILED")

    def test_categorical_equality_is_typed(self):
        doc = document()
        for row in doc["rows"]:
            row["features"]["category"] = False if row["split"] == "train" else 0
        self.pin = self.write(doc)
        self.assertEqual(self.drift()["observations"]["checks"][1]["distance"], 1)

    def test_hash_mismatch_and_test_after_prefix_rejected(self):
        with self.assertRaises(ForgeError):
            distributions(
                self.path,
                self.path,
                reference_sha256="a" * 64,
                current_sha256=self.pin,
                fields={"x": "numeric"},
                thresholds=THRESHOLDS,
            )
        doc = document()
        doc["rows"][-1]["split"] = "test"
        self.pin = self.write(doc)
        with self.assertRaises(ForgeError):
            self.drift(max_rows=1)

    def test_adjudication_preserves_source_and_binds_new_version(self):
        original = self.path.read_bytes()
        result = adjudicate(self.path, sha256=self.pin, reviews=review())
        changed = result["observations"]["document"]
        self.assertEqual(changed["rows"][0]["label"], 1)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(result["observations"]["document_sha256"], hash_bytes(canonical(changed)))
        self.assertEqual(result["observations"]["repair_effect"], "NOT_MEASURED")

    def test_stale_typed_label_duplicate_and_unknown_reviewer_rejected(self):
        for changes in ({"old_label": False}, {"reviewer": ""}, {"id": "absent"}):
            rows = review()
            rows[0].update(changes)
            with self.assertRaises(ForgeError):
                adjudicate(self.path, sha256=self.pin, reviews=rows)
        with self.assertRaises(ForgeError):
            adjudicate(self.path, sha256=self.pin, reviews=review() * 2)

    def test_rejected_and_unresolved_labels_are_not_applied(self):
        for decision in ("reject", "unresolved"):
            rows = review()
            rows[0]["decision"] = decision
            result = adjudicate(self.path, sha256=self.pin, reviews=rows)
            self.assertEqual(result["observations"]["document"], document())
            self.assertEqual(result["observations"]["applied_ids"], [])
            if decision == "unresolved":
                self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_transform_stateless_clean_and_fitted_validation(self):
        self.assertEqual(self.audit()["status"], "TESTED")
        bad = transforms()
        bad[0].update(fit_scope="fitted", fit_ids=["t0", "v0"], uses_target=True)
        report = self.audit(transforms=bad)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(
            {x["kind"] for x in report["observations"]["findings"]},
            {"TARGET_DERIVED", "EVALUATION_FIT"},
        )

    def test_unknown_fit_and_missing_availability_remain_unresolved(self):
        unknown = transforms()
        unknown[0].update(fit_scope="unknown", fit_ids=None)
        self.assertEqual(self.audit(transforms=unknown)["status"], "INCONCLUSIVE")
        self.assertEqual(self.audit(availability=[])["status"], "INCONCLUSIVE")
        unknown[0].update(fit_scope="fitted", fit_ids=["outside"])
        self.assertEqual(self.audit(transforms=unknown)["status"], "INCONCLUSIVE")

    def test_future_availability_and_timezone_equivalence(self):
        rows = availability()
        rows[0]["available_at"] = "2026-11-14T01:00:00+01:00"
        self.assertEqual(self.audit(availability=rows)["status"], "TESTED")
        rows[0]["available_at"] = "2026-11-14T01:00:01+01:00"
        report = self.audit(availability=rows)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["observations"]["findings"][0]["kind"], "FUTURE_FEATURE")

    def test_unknown_time_duplicate_and_unknown_field(self):
        rows = availability()
        rows[0]["prediction_at"] = None
        self.assertEqual(self.audit(availability=rows)["status"], "INCONCLUSIVE")
        with self.assertRaises(ForgeError):
            self.audit(availability=rows + rows[:1])
        rows[0]["field"] = "undeclared"
        with self.assertRaises(ForgeError):
            self.audit(availability=rows)

    def test_uncovered_transform_field_and_false_stateless_fit(self):
        rows = transforms()
        rows[0]["outputs"] = ["x"]
        self.assertEqual(self.audit(transforms=rows)["status"], "INCONCLUSIVE")
        rows[0]["fit_ids"] = ["t0"]
        with self.assertRaises(ForgeError):
            self.audit(transforms=rows)

    def test_near_duplicate_witness_is_not_leakage_verdict(self):
        doc = document()
        doc["rows"][2]["features"]["text"] = "Red apple extra"
        self.pin = self.write(doc)
        report = near_duplicates(self.path, sha256=self.pin, field="text", threshold=0.6)
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual(report["observations"]["match_count"], 1)
        self.assertAlmostEqual(report["observations"]["findings"][0]["similarity"], 2 / 3)

    def test_no_overlap_full_partial_and_zero_budget(self):
        self.assertEqual(
            near_duplicates(self.path, sha256=self.pin, field="text")["status"], "TESTED"
        )
        self.assertEqual(
            near_duplicates(self.path, sha256=self.pin, field="text", max_pairs=1)["status"],
            "INCONCLUSIVE",
        )
        self.assertEqual(
            near_duplicates(self.path, sha256=self.pin, field="text", max_pairs=0)["status"],
            "NOT_RUN",
        )

    def test_empty_long_and_nontext_values_unsupported(self):
        for value in ("", "a b c", 1):
            doc = document()
            for row in doc["rows"]:
                row["features"]["text"] = value
            self.pin = self.write(doc)
            report = near_duplicates(self.path, sha256=self.pin, field="text", max_tokens=2)
            self.assertEqual(report["status"], "UNSUPPORTED")
            self.assertEqual(report["observations"]["unsupported_count"], 4)

    def test_nonfinite_and_deep_json_rejected(self):
        for raw in (b'{"x":NaN}', b'{"x":1e999}'):
            self.path.write_bytes(raw)
            self.pin = hash_bytes(raw)
            with self.assertRaises(ForgeError):
                self.drift()
        doc = document()
        nested = 1
        for _ in range(40):
            nested = [nested]
        doc["rows"][0]["label"] = nested
        self.pin = self.write(doc)
        with self.assertRaises(ForgeError):
            adjudicate(self.path, sha256=self.pin, reviews=review())


if __name__ == "__main__":
    unittest.main()
