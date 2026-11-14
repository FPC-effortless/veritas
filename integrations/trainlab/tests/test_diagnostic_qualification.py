import copy
import tempfile
import unittest
from pathlib import Path

from trainlab.diagnostic_qualification import score
from trainlab.runner import LabError, digest, write_json

PIN = "a" * 64


class QualificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.plan = {
            "schema": "trainlab.diagnostic-fault-panel.v1",
            "repeats": [0, 1],
            "cases": [
                {
                    "id": "fixture",
                    "workload_sha256": PIN,
                    "targets": [
                        {"check": "data", "location": "bad", "fault": True},
                        {"check": "data", "location": "clean", "fault": False},
                    ],
                }
            ],
        }
        self.report = {
            "schema": "trainlab.diagnostic-fault-observations.v1",
            "runs": [
                {
                    "case": "fixture",
                    "repeat": repeat,
                    "workload_sha256": PIN,
                    "checks": [{"name": "data", "status": "CHECKED", "locations": ["bad"]}],
                    "timing": {
                        "baseline_ns": 100,
                        "diagnostic_ns": 120,
                        "baseline_work_sha256": PIN,
                        "diagnostic_work_sha256": PIN,
                        "hardware_sha256": PIN,
                        "boundary_sha256": PIN,
                    },
                }
                for repeat in (0, 1)
            ],
        }

    def evaluate(self, pin=None):
        plan = self.root / "plan.json"
        report = self.root / "observations.json"
        write_json(plan, self.plan)
        write_json(report, self.report)
        return score(
            plan, report, panel_sha256=digest(plan), observations_sha256=pin or digest(report)
        )

    def test_complete_matched_panel(self):
        result = self.evaluate()
        self.assertEqual(result["status"], "TESTED")
        self.assertEqual(result["counts"]["true_positive"], 2)
        self.assertEqual(result["counts"]["true_negative"], 2)
        self.assertEqual(result["overhead"]["fixture"]["median_difference_ns"], 20)
        self.assertEqual(result["rates"]["localization_precision"]["value"], 1)

    def test_wrong_location_is_both_miss_and_false_alarm(self):
        self.report["runs"][0]["checks"][0]["locations"] = ["clean"]
        result = self.evaluate()
        self.assertEqual(result["counts"]["false_positive"], 1)
        self.assertEqual(result["counts"]["false_negative"], 1)
        self.assertEqual(result["rates"]["false_alarm_rate"]["denominator"], 2)
        self.assertEqual(result["rates"]["detection_rate"]["value"], 1)
        self.assertEqual(result["rates"]["fault_location_recall"]["value"], 0.5)

    def test_absence_and_mismatched_work_are_explicit(self):
        self.report["runs"][0]["timing"]["baseline_work_sha256"] = "b" * 64
        self.report["runs"][1]["checks"] = []
        result = self.evaluate()
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["counts"]["unobserved"], 2)
        self.assertIsNone(result["overhead"]["fixture"]["median_difference_ns"])
        self.assertEqual(result["overhead"]["fixture"]["matched_repeats"], 1)

    def test_missing_repeat_and_unadjudicated_location(self):
        self.report["runs"].pop()
        self.report["runs"][0]["checks"][0]["locations"].append("unreviewed")
        result = self.evaluate()
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["counts"]["unobserved"], 2)
        self.assertEqual(result["counts"]["unadjudicated"], 1)
        self.assertEqual(result["counts"]["false_positive"], 0)

    def test_duplicate_and_unmatched_inputs_rejected(self):
        with self.assertRaises(LabError):
            self.evaluate("0" * 64)
        self.report["runs"].append(copy.deepcopy(self.report["runs"][0]))
        with self.assertRaises(LabError):
            self.evaluate()
        self.report["runs"].pop()
        self.report["runs"][0]["workload_sha256"] = "b" * 64
        with self.assertRaises(LabError):
            self.evaluate()
