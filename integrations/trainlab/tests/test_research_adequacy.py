import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trainlab.research_adequacy import DIMENSIONS, assess, recipe_identity, verify_report
from trainlab.runner import LabError, digest, load_config, run_experiment, verify_run, write_json


class AdequacyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            "schema": "trainlab.experiment.v1",
            "name": "bounded control",
            "description": "constructed acceptance only",
            "command": ["true"],
            "seed": 1,
            "timeout_seconds": 5,
            "source_kind": "CONSTRUCTED",
            "split_identity": "forge-pin",
            "inputs": ["summary.json", "adequacy.json"],
            "artifacts": ["result.json"],
            "metrics": {"loss": "min"},
            "budget": {"updates": 512},
        }
        write_json(self.root / "summary.json", {"probe_accuracy": 1.0, "updates": 512})
        self.contract = {
            "schema": "trainlab.research-adequacy.v1",
            "claim": "bounded fixed-budget result",
            "claim_kind": "fixed_budget_comparison",
            "scope": "constructed acceptance fixture",
            "excluded_claims": "No convergence, capacity, transfer or scientific qualification",
            "recipe_sha256": recipe_identity(self.config),
            "inputs": {"summary.json": digest(self.root / "summary.json")},
            "review": {
                "author": "author",
                "reviewer": "reviewer",
                "basis": "fixture only",
                "criteria_frozen_before_evaluation": True,
            },
            "dimensions": {
                name: {
                    "configuration": "fixture configuration",
                    "justification": "fixture-only test",
                    "limitations": "not scientific evidence",
                    "criteria": [
                        {
                            "id": "primitive",
                            "rationale": "required control works",
                            "evidence": "summary.json",
                            "field": "probe_accuracy",
                            "operator": "ge",
                            "threshold": 0.95,
                        }
                    ],
                }
                for name in DIMENSIONS
            },
        }
        self.save()

    def assert_rejected(self, directory):
        try:
            report = verify_run(directory)
        except LabError:
            return
        self.assertFalse(report["valid"])

    def save(self):
        write_json(self.root / "adequacy.json", self.contract)
        self.config["research_adequacy"] = {
            "file": "adequacy.json",
            "sha256": digest(self.root / "adequacy.json"),
        }
        write_json(self.root / "experiment.json", self.config)
        self.hashes = {n: digest(self.root / n) for n in self.config["inputs"]}

    def assess(self):
        return assess(self.config, self.root, self.hashes)

    def test_met_is_not_qualified_and_replays(self):
        report = self.assess()
        self.assertEqual(report["status"], "DECLARED_CRITERIA_MET")
        self.assertEqual(report["qualification"], "NOT_QUALIFIED")
        self.assertTrue(verify_report(report, self.config, self.hashes))

    def test_unknown_blocks_before_subprocess_and_retains_refusal(self):
        self.contract["dimensions"]["training_duration"]["criteria"][0]["field"] = "missing"
        self.save()
        with patch("trainlab.runner.subprocess.Popen") as launch:
            with self.assertRaisesRegex(LabError, "UNKNOWN"):
                run_experiment(self.root / "experiment.json", self.root / "runs")
            launch.assert_not_called()
        self.assertEqual(len(list((self.root / "runs" / "adequacy-refusals").glob("*.json"))), 1)

    def test_failed_criterion_blocks(self):
        self.contract["dimensions"]["datasets"]["criteria"][0]["threshold"] = 1.1
        self.save()
        self.assertEqual(self.assess()["status"], "INADEQUATE")

    def test_each_dimension_required(self):
        for name in DIMENSIONS:
            original = self.contract["dimensions"].pop(name)
            self.save()
            with self.assertRaises(LabError):
                self.assess()
            self.contract["dimensions"][name] = original

    def test_recipe_change_invalidates_gate(self):
        self.config["budget"]["updates"] = 1
        with self.assertRaisesRegex(LabError, "recipe changed"):
            self.assess()

    def test_source_change_invalidates_gate(self):
        write_json(self.root / "summary.json", {"probe_accuracy": 0})
        with self.assertRaisesRegex(LabError, "evidence changed"):
            self.assess()

    def test_boolean_and_nonfinite_not_observations(self):
        for value in (True, float("nan")):
            (self.root / "summary.json").write_text(json.dumps({"probe_accuracy": value}))
            self.contract["inputs"]["summary.json"] = digest(self.root / "summary.json")
            self.save()
            with self.assertRaises(LabError):
                self.assess()

    def test_retrospective_or_self_review_rejected(self):
        self.contract["review"]["criteria_frozen_before_evaluation"] = False
        self.save()
        with self.assertRaises(LabError):
            self.assess()

    def test_forged_saved_observation_or_status_rejected(self):
        report = self.assess()
        for key in ("evidence", "source_texts", "status"):
            bad = copy.deepcopy(report)
            bad[key] = {} if key != "status" else "PASS"
            with self.assertRaises(LabError):
                verify_report(bad, self.config, self.hashes)

    def add_execution(self, updates=512):
        import sys

        script = """import hashlib,json,os
from pathlib import Path
c=json.loads(Path('experiment.json').read_text())
recipe={k:v for k,v in c.items() if k!='research_adequacy'}
h=lambda b:hashlib.sha256(b).hexdigest()
pin=h(json.dumps(recipe,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
inputs={n:h(Path(n).read_bytes()) for n in c['inputs']}
p=Path(os.environ['TRAINLAB_OUTPUT_DIR'])
(p/'metrics.json').write_text(json.dumps({'loss':1}))
(p/'result.json').write_text('{}')
(p/'executed.json').write_text(json.dumps({
'schema':'trainlab.execution-adequacy-observations.v1','recipe_sha256':pin,
'inputs':inputs,'producer':{'file':'producer.py','sha256':inputs['producer.py']},
'observations':{'parameters':32,'updates':UPDATES,'records':400,'regime':1}}))
""".replace("UPDATES", str(updates))
        (self.root / "producer.py").write_text(script)
        self.config["command"] = [sys.executable, "producer.py"]
        self.config["inputs"].append("producer.py")
        self.config["artifacts"].append("executed.json")
        self.contract["inputs"]["producer.py"] = digest(self.root / "producer.py")
        self.contract["recipe_sha256"] = recipe_identity(self.config)
        fields = dict(
            zip(DIMENSIONS, (("parameters", 32), ("updates", 512), ("records", 400), ("regime", 1)))
        )
        self.contract["execution"] = {
            "artifact": "executed.json",
            "dimensions": {
                dimension: [
                    {
                        "field": field,
                        "operator": "eq",
                        "threshold": value,
                        "rationale": "constructed actual observation check",
                    }
                ]
                for dimension, (field, value) in fields.items()
            },
        }
        self.save()

    def test_guarded_execution_and_saved_verification(self):
        self.add_execution()
        record = run_experiment(self.root / "experiment.json", self.root / "runs")
        self.assertEqual(record["status"], "succeeded")
        directory = self.root / "runs" / record["id"]
        # Verification does not rely on original mutable input directory.
        (self.root / "summary.json").unlink()
        self.assertTrue(verify_run(directory)["valid"])
        report = json.loads((directory / "research_adequacy.json").read_text())
        report["status"] = "PASS"
        write_json(directory / "research_adequacy.json", report)
        record["files"]["research_adequacy.json"] = digest(directory / "research_adequacy.json")
        write_json(directory / "run.json", record)
        self.assert_rejected(directory)

    def test_legacy_load_remains_unassessed(self):
        del self.config["research_adequacy"]
        write_json(self.root / "experiment.json", self.config)
        self.assertNotIn("research_adequacy", load_config(self.root / "experiment.json"))

    def test_crlf_sources_replay_exact_bytes(self):
        for name in ("summary.json",):
            p = self.root / name
            p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        self.contract["inputs"]["summary.json"] = digest(self.root / "summary.json")
        self.save()
        p = self.root / "adequacy.json"
        p.write_bytes(p.read_bytes().replace(b"\n", b"\r\n"))
        self.config["research_adequacy"]["sha256"] = digest(p)
        self.hashes["adequacy.json"] = digest(p)
        self.assertTrue(verify_report(self.assess(), self.config, self.hashes))

    def test_oversized_retained_report_blocks_before_execution(self):
        write_json(self.root / "summary.json", {("x" * 1000) + str(i): 1 for i in range(550)})
        self.contract["inputs"]["summary.json"] = digest(self.root / "summary.json")
        for dimension in self.contract["dimensions"].values():
            dimension["criteria"][0]["field"] = "x" * 1000 + "0"
        self.save()
        with self.assertRaisesRegex(LabError, "report exceeds"):
            self.assess()

    def test_missing_default_research_contract_blocks(self):
        del self.config["research_adequacy"]
        write_json(self.root / "experiment.json", self.config)
        with patch("trainlab.runner.subprocess.Popen") as launch:
            with self.assertRaisesRegex(LabError, "missing contract"):
                run_experiment(self.root / "experiment.json", self.root / "runs")
            launch.assert_not_called()

    def test_completed_command_underrun_is_not_adequate(self):
        self.add_execution(updates=1)
        record = run_experiment(self.root / "experiment.json", self.root / "runs")
        self.assertEqual(record["exit_code"], 0)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["research_adequacy"], "INADEQUATE")
        self.assertEqual(record["claim_eligibility"], "NOT_ESTABLISHED")
        directory = self.root / "runs" / record["id"]
        self.assertTrue(verify_run(directory)["valid"])
        record["research_adequacy"] = "EXECUTED_CRITERIA_MET"
        write_json(directory / "run.json", record)
        self.assert_rejected(directory)

    def test_native_failed_report_cannot_hide_in_favorable_counts(self):
        from test_benchmark_adequacy import benchmark_fixture

        for mode, alias, max_calls in (
            ("direct", False, 384),
            ("alias", True, 384),
            ("partial", False, 2),
        ):
            frozen, native, workbench = benchmark_fixture(
                self.root / mode, alias=alias, max_calls=max_calls
            )
            for filename, doc in (
                ("panel.json", frozen),
                ("native.json", native),
                ("workbench.json", workbench),
            ):
                write_json(self.root / filename, doc)
                if filename not in self.config["inputs"]:
                    self.config["inputs"].append(filename)
                self.contract["inputs"][filename] = digest(self.root / filename)
            self.contract["benchmark_projections"] = {
                "native.json": {"panel": "panel.json", "workbench": "workbench.json"}
            }
            self.contract["recipe_sha256"] = recipe_identity(self.config)
            # Existing favorable scalar criteria unchanged: mandatory native gate still applies.
            self.save()
            report = self.assess()
            self.assertEqual(
                report["status"],
                {"direct": "DECLARED_CRITERIA_MET", "alias": "INADEQUATE", "partial": "UNKNOWN"}[
                    mode
                ],
            )
            if mode == "direct":
                self.assertTrue(verify_report(report, self.config, self.hashes))

    def test_engineering_receipt_cannot_forge_research_eligibility(self):
        self.add_execution()
        del self.config["research_adequacy"]
        self.config["execution_purpose"] = "engineering_diagnostic"
        # A harmless command, not the research producer that expects a gate.
        import sys

        self.config["command"] = [
            sys.executable,
            "-c",
            "import os,json;from pathlib import Path;p=Path(os.environ['TRAINLAB_OUTPUT_DIR']);"
            "[(p/n).write_text('{}') for n in ['result.json','executed.json']];"
            "(p/'metrics.json').write_text(json.dumps({'loss':1}))",
        ]
        write_json(self.root / "experiment.json", self.config)
        record = run_experiment(self.root / "experiment.json", self.root / "runs")
        directory = self.root / "runs" / record["id"]
        self.assertTrue(verify_run(directory)["valid"])
        for field, value in (
            ("claim_eligibility", "DECLARED_CONDITIONS_ONLY"),
            ("execution_purpose", "research"),
            ("research_adequacy", "EXECUTED_CRITERIA_MET"),
        ):
            forged = copy.deepcopy(record)
            forged[field] = value
            write_json(directory / "run.json", forged)
            self.assert_rejected(directory)

    def test_gated_engineering_cannot_forge_executed_phase(self):
        self.add_execution()
        self.config["execution_purpose"] = "engineering_diagnostic"
        self.contract["recipe_sha256"] = recipe_identity(self.config)
        self.save()
        record = run_experiment(self.root / "experiment.json", self.root / "runs")
        directory = self.root / "runs" / record["id"]
        self.assertTrue(verify_run(directory)["valid"])
        self.assertEqual(record["research_adequacy"], "PLAN_ADMITTED")
        record["research_adequacy"] = "EXECUTED_CRITERIA_MET"
        write_json(directory / "run.json", record)
        self.assert_rejected(directory)

    def test_interrupt_after_reconciliation_cannot_leave_eligible_claim(self):
        self.add_execution()
        with patch("trainlab.runner.failed_checks", side_effect=KeyboardInterrupt):
            record = run_experiment(self.root / "experiment.json", self.root / "runs")
        self.assertEqual(record["status"], "interrupted")
        self.assertEqual(record["claim_eligibility"], "NOT_ESTABLISHED")
        self.assertTrue(verify_run(self.root / "runs" / record["id"])["valid"])
