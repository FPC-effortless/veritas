import copy
import hashlib
import unittest

from trainlab.execution_adequacy import assess_execution, validate_execution
from trainlab.prediction_artifacts import _bytes
from trainlab.research_adequacy import recipe_identity
from trainlab.runner import LabError


def execution_fixture():
    config = {
        "inputs": ["producer.py", "data.json", "adequacy.json"],
        "artifacts": ["observations.json"],
        "budget": {"updates": 512},
        "command": ["python", "producer.py"],
        "seed": 1,
    }
    inputs = {"producer.py": "a" * 64, "data.json": "b" * 64}

    def condition(field, value, op="eq"):
        return {
            "field": field,
            "operator": op,
            "threshold": value,
            "rationale": "Constructed contract condition, not scientific qualification",
        }

    contract = {
        "recipe_sha256": recipe_identity(config),
        "inputs": dict(inputs),
        "execution": {
            "artifact": "observations.json",
            "dimensions": {
                "model_size": [condition("parameters", 18359)],
                "training_duration": [
                    condition("optimizer_updates", 512),
                    condition("answer_exposures", 16384),
                    condition("elapsed_training_seconds", 1, "ge"),
                ],
                "datasets": [condition("training_groups", 100), condition("split_overlap", 0)],
                "training_regime": [
                    condition("learning_rate", 0.002),
                    condition("supervised_heads", 6),
                ],
            },
        },
    }
    pin = hashlib.sha256(_bytes(contract)).hexdigest()
    inputs["adequacy.json"] = pin
    config["research_adequacy"] = {"file": "adequacy.json", "sha256": pin}
    receipt = {
        "schema": "trainlab.execution-adequacy-observations.v1",
        "recipe_sha256": recipe_identity(config),
        "inputs": dict(inputs),
        "producer": {"file": "producer.py", "sha256": inputs["producer.py"]},
        "observations": {
            "parameters": 18359,
            "optimizer_updates": 512,
            "answer_exposures": 16384,
            "elapsed_training_seconds": 60,
            "training_groups": 100,
            "split_overlap": 0,
            "learning_rate": 0.002,
            "supervised_heads": 6,
        },
    }
    return contract, config, inputs, receipt


class ExecutionAdequacyTests(unittest.TestCase):
    def setUp(self):
        self.fixture = execution_fixture()

    def test_met_remains_declared_and_not_qualified(self):
        report = assess_execution(*self.fixture)
        self.assertEqual(report["status"], "MET")
        self.assertEqual(report["qualification"], "NOT_QUALIFIED")
        self.assertIn("NOT_INDEPENDENTLY_ATTESTED", report["evidence_scope"])
        self.assertEqual(len(report["checks"]), 8)

    def test_under_run_not_hidden_by_declared_budget(self):
        for field, value in [
            ("optimizer_updates", 32),
            ("answer_exposures", 1024),
            ("elapsed_training_seconds", 0.1),
            ("parameters", 100),
            ("training_groups", 20),
            ("learning_rate", 0.1),
        ]:
            altered = copy.deepcopy(self.fixture)
            altered[3]["observations"][field] = value
            with self.subTest(field=field):
                self.assertEqual(assess_execution(*altered)["status"], "INADEQUATE")

    def test_missing_observations_unknown_even_when_budget_matches(self):
        for field in self.fixture[3]["observations"]:
            altered = copy.deepcopy(self.fixture)
            del altered[3]["observations"][field]
            self.assertEqual(assess_execution(*altered)["status"], "UNKNOWN")
        self.fixture[3]["observations"] = {}
        self.assertEqual(assess_execution(*self.fixture)["status"], "UNKNOWN")

    def test_failure_dominates_unknown_without_hiding_missing_check(self):
        self.fixture[3]["observations"].pop("parameters")
        self.fixture[3]["observations"]["optimizer_updates"] = 0
        report = assess_execution(*self.fixture)
        self.assertEqual(report["status"], "INADEQUATE")
        self.assertIn("UNKNOWN", {r["status"] for r in report["checks"]})

    def test_exact_receipt_source_recipe_and_input_bindings(self):
        mutations = [
            lambda f: f[3].update(recipe_sha256="0" * 64),
            lambda f: f[3]["inputs"].update({"data.json": "0" * 64}),
            lambda f: f[3]["producer"].update(sha256="0" * 64),
            lambda f: f[3]["producer"].update(file="unlisted.py"),
            lambda f: f[1]["budget"].update(updates=32),
            lambda f: f[2].pop("data.json"),
            lambda f: f[1]["research_adequacy"].update(sha256="0" * 64),
        ]
        for i, mutation in enumerate(mutations):
            altered = copy.deepcopy(self.fixture)
            mutation(altered)
            with self.subTest(i=i), self.assertRaises(LabError):
                assess_execution(*altered)

    def test_all_dimensions_and_retained_artifact_required(self):
        for dimension in self.fixture[0]["execution"]["dimensions"]:
            altered = copy.deepcopy(self.fixture)
            del altered[0]["execution"]["dimensions"][dimension]
            with self.assertRaises(LabError):
                validate_execution(*altered[:2])
        self.fixture[0]["execution"]["artifact"] = "missing.json"
        with self.assertRaises(LabError):
            validate_execution(*self.fixture[:2])

    def test_nonfinite_boolean_null_and_nested_observations_rejected(self):
        for bad in [True, float("nan"), float("inf"), None, {}, "512"]:
            altered = copy.deepcopy(self.fixture)
            altered[3]["observations"]["optimizer_updates"] = bad
            with self.subTest(value=bad), self.assertRaises(LabError):
                assess_execution(*altered)

    def test_criteria_cannot_be_empty_nonfinite_or_duplicate(self):
        c, config, _, _ = self.fixture
        original = c["execution"]["dimensions"]["model_size"]
        for bad in [
            [],
            original * 2,
            [{**original[0], "threshold": True}],
            [{**original[0], "threshold": float("inf")}],
        ]:
            altered = copy.deepcopy(c)
            altered["execution"]["dimensions"]["model_size"] = bad
            with self.assertRaises(LabError):
                validate_execution(altered, config)

    def test_oversized_derived_report_cannot_become_eligible(self):
        contract, config, inputs, receipt = self.fixture
        receipt["observations"] = {"x" * 1900 + str(i): 1 for i in range(500)}
        keys = list(receipt["observations"])
        for dimension in contract["execution"]["dimensions"]:
            contract["execution"]["dimensions"][dimension] = [
                {"field": key, "operator": "eq", "threshold": 1, "rationale": "size control"}
                for key in keys[:32]
            ]
        pin = hashlib.sha256(_bytes(contract)).hexdigest()
        inputs["adequacy.json"] = pin
        receipt["inputs"] = dict(inputs)
        config["research_adequacy"]["sha256"] = pin
        with self.assertRaisesRegex(LabError, "report exceeds 1 MiB"):
            assess_execution(contract, config, inputs, receipt)


if __name__ == "__main__":
    unittest.main()
