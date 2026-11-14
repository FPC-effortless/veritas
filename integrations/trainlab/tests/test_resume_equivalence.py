import copy
import tempfile
import unittest
from pathlib import Path

from trainlab.resume_equivalence import compare
from trainlab.runner import LabError, digest, write_json


class ResumeEquivalenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.plan = {
            "schema": "trainlab.resume-plan.v1",
            "steps": [10, 11],
            "context_sha256": "a" * 64,
            "checkpoint_sha256": "b" * 64,
            "components": {
                "weights": {"kind": "numeric", "atol": 1e-4, "rtol": 0, "length": 2},
                "sampler": {"kind": "exact"},
            },
        }
        self.samples = [
            {"step": i, "components": {"weights": [1.0, 2.0], "sampler": [0, 1]}} for i in (10, 11)
        ]
        self.resumed = copy.deepcopy(self.samples)

    def evaluate(self, *, trace_fields=None, resumed_sha256=None):
        path = self.root / "plan.json"
        write_json(path, self.plan)
        plan_pin = digest(path)
        traces = {}
        for name, samples in [("reference", self.samples), ("resumed", self.resumed)]:
            trace = {
                "schema": "trainlab.resume-trace.v1",
                "role": name,
                "context_sha256": self.plan["context_sha256"],
                "checkpoint_sha256": self.plan["checkpoint_sha256"],
                "plan_sha256": plan_pin,
                "samples": samples,
            }
            if name == "resumed":
                trace.update(trace_fields or {})
            traces[name] = self.root / (name + ".json")
            write_json(traces[name], trace)
        return compare(
            path,
            traces["reference"],
            traces["resumed"],
            plan_sha256=plan_pin,
            reference_sha256=digest(traces["reference"]),
            resumed_sha256=resumed_sha256 or digest(traces["resumed"]),
        )

    def test_numerical_tolerance_and_typed_equality(self):
        self.resumed[0]["components"]["weights"][0] += 0.00005
        self.assertEqual(self.evaluate()["status"], "TESTED")
        self.resumed[1]["components"]["sampler"][0] = False
        result = self.evaluate()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["first_observed_difference"], 11)
        self.assertEqual(result["first_observed_components"], ["sampler"])

    def test_unknown_coverage_and_known_divergence(self):
        self.resumed[0]["components"].pop("sampler")
        self.assertEqual(self.evaluate()["status"], "INCONCLUSIVE")
        self.resumed[1]["components"]["weights"][1] = 3
        result = self.evaluate()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["components"]["sampler"]["missing_steps"], [10])
        self.assertFalse(result["coverage_complete"])

    def test_mismatched_provenance_and_duplicate_steps_rejected(self):
        for field in ("checkpoint_sha256", "context_sha256", "plan_sha256"):
            with self.subTest(field=field), self.assertRaises(LabError):
                self.evaluate(trace_fields={field: "d" * 64})
        with self.assertRaises(LabError):
            self.evaluate(resumed_sha256="e" * 64)
        self.resumed[1]["step"] = 10
        with self.assertRaises(LabError):
            self.evaluate()

    def test_false_numeric_observation_rejected(self):
        self.resumed[0]["components"]["weights"][0] = True
        with self.assertRaises(LabError):
            self.evaluate()
