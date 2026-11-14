import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from forge_data.core import ForgeError, canonical, hash_bytes
from forge_data.diagnostics import diagnose


def row(identity, value, split="train", label=0, group=None):
    return {"id": identity, "split": split, "features": {"x": value}, "label": label,
            "groups": {"entity": group or identity}}


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "view.json"
        self.document = {"schema": "forge.diagnostic-input.v1", "feature_fields": ["x"],
                         "group_fields": ["entity"],
                         "rows": [row("a", 1), row("b", 2, "validation", 1)]}

    def run_audit(self, **limits):
        data = canonical(self.document)
        self.path.write_bytes(data)
        return diagnose(self.path, sha256=hash_bytes(data), **limits)

    def statuses(self, result):
        return {c["name"]: c["status"] for c in result["coverage"]}

    def test_clean_complete_scan_has_bounded_scope_and_unrun_checks(self):
        report = self.run_audit()
        self.assertEqual(report["state"], "COMPLETE")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["scientific_qualification"], "NOT_QUALIFIED")
        status = self.statuses(report)
        for name in ("completeness", "duplicates", "split_content", "group:entity", "labels"):
            self.assertEqual(status[name], "TESTED")
        self.assertEqual(status["near_duplicates"], "NOT_RUN")

    def test_cross_split_content_and_groups_localize_exact_witnesses(self):
        self.document["rows"][1] = row("b", 1, "validation", 1, "a")
        report = self.run_audit()
        status = self.statuses(report)
        self.assertEqual(status["split_content"], "FAILED")
        self.assertEqual(status["group:entity"], "FAILED")
        self.assertEqual(status["labels"], "INCONCLUSIVE")
        self.assertEqual(status["duplicates"], "INCONCLUSIVE")
        self.assertEqual({f["kind"] for f in report["findings"]},
                         {"EXACT_DUPLICATE", "SPLIT_CONTENT_OVERLAP",
                          "GROUP_OVERLAP", "LABEL_CONFLICT"})
        for finding in report["findings"]:
            self.assertEqual({r["id"] for r in finding["rows"]}, {"a", "b"})
            self.assertIn("interpretation", finding)

    def test_missing_and_null_are_distinct_and_not_duplicate_signatures(self):
        self.document["rows"][0]["features"] = {}
        self.document["rows"][1]["features"]["x"] = None
        report = self.run_audit()
        self.assertEqual(self.statuses(report)["completeness"], "FAILED")
        self.assertEqual({f["kind"] for f in report["findings"]},
                         {"MISSING_FEATURE", "NULL_FEATURE"})
        self.assertEqual(self.statuses(report)["split_content"], "INCONCLUSIVE")

    def test_equal_labels_on_repeated_observation_do_not_become_label_errors(self):
        self.document["rows"].append(row("c", 1, label=0))
        report = self.run_audit()
        self.assertEqual(self.statuses(report)["labels"], "TESTED")
        self.assertFalse(any(f["kind"] == "LABEL_CONFLICT" for f in report["findings"]))

    def test_partial_label_and_group_access_never_yields_clean_whole_view(self):
        self.document["rows"][1].pop("label")
        self.document["rows"][1]["groups"] = {}
        report = self.run_audit()
        self.assertEqual(self.statuses(report)["labels"], "INCONCLUSIVE")
        self.assertEqual(self.statuses(report)["group:entity"], "INCONCLUSIVE")
        for item in self.document["rows"]:
            item.pop("label", None)
            item["groups"] = {}
        status = self.statuses(self.run_audit())
        self.assertEqual(status["labels"], "UNSUPPORTED")
        self.assertEqual(status["group:entity"], "UNSUPPORTED")

    def test_prefix_budget_preserves_failures_but_no_absence_claim(self):
        self.document["rows"] += [row("c", 3), row("d", 3, "validation")]
        report = self.run_audit(max_rows=2)
        self.assertEqual(report["state"], "PARTIAL")
        self.assertNotIn("TESTED", self.statuses(report).values())
        self.assertEqual(report["scope"]["scanned_rows"], 2)
        self.document["rows"][0]["features"]["x"] = None
        report = self.run_audit(max_rows=2)
        self.assertEqual(self.statuses(report)["completeness"], "FAILED")
        self.assertEqual(len(report["findings"]), 1)

    def test_zero_budget_explicitly_runs_no_diagnostics(self):
        report = self.run_audit(max_rows=0)
        self.assertEqual(set(self.statuses(report).values()), {"NOT_RUN"})
        self.assertEqual(report["findings"], [])

    def test_finding_limit_does_not_suppress_positive_counts(self):
        self.document["rows"][1] = row("b", 1, "validation", 1, "a")
        full, capped = self.run_audit(), self.run_audit(max_findings=1)
        self.assertEqual(full["coverage"], capped["coverage"])
        self.assertEqual(len(capped["findings"]), 1)
        self.assertEqual(capped["findings_omitted"], 3)

    def test_witness_counts_are_groups_not_quadratic_pairs(self):
        self.document["rows"] = [row(str(i), 1, "train" if i % 2 else "validation", i % 3)
                                 for i in range(100)]
        report = self.run_audit()
        metrics = {c["name"]: c["metrics"] for c in report["coverage"]}
        self.assertEqual(metrics["duplicates"]["groups"], 1)
        self.assertEqual(metrics["duplicates"]["additional_rows"], 99)
        self.assertEqual(metrics["split_content"]["groups"], 1)
        self.assertEqual(metrics["labels"]["conflicting_groups"], 1)

    def test_input_and_order_are_pinned_and_repeatable(self):
        first = self.run_audit()
        self.assertEqual(first, self.run_audit())
        self.document["rows"].reverse()
        second = self.run_audit()
        self.assertNotEqual(first["input_sha256"], second["input_sha256"])
        with self.assertRaises(ForgeError):
            diagnose(self.path, sha256=first["input_sha256"])

    def test_example_forge_view_gate_rejects_python_equal_but_typed_json_drift(self):
        path = Path(__file__).resolve().parents[2] / "trainlab/examples/diagnose_dataset.py"
        spec = importlib.util.spec_from_file_location("dataset_example", path)
        example = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(example)
        self.assertTrue(example.views_match(self.document, copy.deepcopy(self.document)))
        for value in (1.0, True):
            changed = copy.deepcopy(self.document)
            changed["rows"][0]["features"]["x"] = value
            self.assertEqual(changed, self.document)  # The original bug's false acceptance.
            self.assertFalse(example.views_match(self.document, changed))

    def test_no_raw_feature_or_label_values_in_report(self):
        self.document["rows"] = [row("a", "private-feature", label="private-label-a"),
                                 row("b", "private-feature", "validation", "private-label-b")]
        text = json.dumps(self.run_audit())
        self.assertNotIn("private-feature", text)
        self.assertNotIn("private-label", text)

    def test_unsupported_test_row_rejected_even_outside_prefix(self):
        self.document["rows"][1]["split"] = "test"
        with self.assertRaises(ForgeError):
            self.run_audit(max_rows=1)

    def test_malformed_identity_features_and_configuration_fail_closed(self):
        original = copy.deepcopy(self.document)
        for change in (
            lambda d: d["rows"][1].update(id="a"),
            lambda d: d["rows"][0].update(features=[]),
            lambda d: d.update(feature_fields=["x", "x"]),
            lambda d: d["rows"][0].update(unknown="field"),
            lambda d: d["rows"][0]["groups"].update(entity=[]),
            lambda d: d.update(rows=[]),
        ):
            self.document = copy.deepcopy(original)
            change(self.document)
            with self.assertRaises(ForgeError):
                self.run_audit()

    def test_duplicate_json_keys_nonfinite_and_oversized_bytes_rejected(self):
        data = canonical(self.document)
        for bad in (data.replace(b'"schema":', b'"schema":"duplicate","schema":', 1),
                    data.replace(b'"x":1', b'"x":1e999'), b" " * (16 * 1024 * 1024 + 1)):
            self.path.write_bytes(bad)
            with self.assertRaises(ForgeError):
                diagnose(self.path, sha256=hash_bytes(bad))

    def test_single_split_cannot_establish_disjoint_splits(self):
        self.document["rows"][1]["split"] = "train"
        status = self.statuses(self.run_audit())
        self.assertEqual(status["split_content"], "INCONCLUSIVE")
        self.assertEqual(status["group:entity"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
