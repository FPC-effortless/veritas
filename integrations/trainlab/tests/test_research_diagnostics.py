import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
from trainlab.runner import LabError, read_json, run_experiment, verify_run, write_json

IDENTITIES = {key: "a" * 64 for key in ("model", "dataset", "code", "configuration")}
STATE = {"persists": "none", "query_mutates": False, "reset": "not_applicable"}


def observed(context):
    value = context.invoke("predict", phase="answer")
    return {"status": "TESTED" if value == 2 else "FAILED",
            "summary": "Constructed scalar agreement.", "metrics": {"correct": int(value == 2)}}


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "report"

    def bench(self, ops=None, **kwargs):
        return Workbench(Adapter("control", ops or {"predict": lambda: 2}, STATE),
                         IDENTITIES, self.root, **kwargs)

    def test_missing_capability_and_unselected_check_are_visible(self):
        checks = [Diagnostic("answer", "1", ("predict",), observed, "one invented scalar"),
                  Diagnostic("gradient", "1", ("gradients",), observed, "unavailable"),
                  Diagnostic("later", "1", ("predict",), observed, "not requested")]
        result = self.bench().run(checks, selected=["answer", "gradient"])
        self.assertEqual([r["status"] for r in result["coverage"]],
                         ["TESTED", "UNSUPPORTED", "NOT_RUN"])
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["scientific_qualification"], "NOT_QUALIFIED")

    def test_partial_started_event_is_durable_before_adapter_call(self):
        def predict():
            saved = read_json(self.root / "report.json")
            self.assertEqual(saved["state"], "PARTIAL")
            self.assertEqual(saved["attempts"][0]["status"], "STARTED")
            raise KeyboardInterrupt()
        bench = self.bench({"predict": predict})
        with self.assertRaises(KeyboardInterrupt):
            bench.run([Diagnostic("answer", "1", ("predict",), observed, "control")])
        saved = read_json(self.root / "report.json")
        self.assertEqual(saved["state"], "PARTIAL")
        self.assertEqual(saved["attempts"][0]["status"], "INTERRUPTED")

    def test_direct_session_time_includes_work_outside_spans(self):
        clock = [0]
        def predict():
            clock[0] += 2_000_000_000
            return 2
        def check(context):
            clock[0] += 5_000_000_000  # Diagnostic overhead outside the operation span.
            return observed(context)
        with patch("trainlab.research_diagnostics.perf_counter_ns", lambda: clock[0]):
            result = self.bench({"predict": predict}).run([
                Diagnostic("answer", "1", ("predict",), check, "scalar")])
        self.assertEqual(result["session"]["elapsed_seconds"], 7)
        self.assertEqual(result["attempts"][0]["elapsed_seconds"], 2)
        self.assertEqual(result["session"]["cost_coverage"], "MEASURED")

    def test_failures_and_explicit_retries_are_counted_without_private_payloads(self):
        calls = []
        def predict():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("private input detail")
            return 2
        def check(context):
            with self.assertRaises(RuntimeError):
                context.invoke("predict", phase="answer")
            self.assertEqual(context.invoke("predict", phase="answer", retry_of=0), 2)
            return {"status": "TESTED", "summary": "Recovered control", "metrics": {}}
        result = self.bench({"predict": predict}).run([
            Diagnostic("answer", "1", ("predict",), check, "scalar")])
        self.assertEqual([a["status"] for a in result["attempts"]], ["FAILED", "SUCCEEDED"])
        self.assertEqual(result["attempts"][1]["retry_of"], 0)
        self.assertNotIn("private input detail", (self.root / "report.json").read_text())

    def test_call_budget_keeps_partial_observations_and_stops_later_checks(self):
        def twice(context):
            observed(context)
            return observed(context)
        result = self.bench(max_calls=1).run([
            Diagnostic("twice", "1", ("predict",), twice, "scalar"),
            Diagnostic("later", "1", ("predict",), observed, "scalar")])
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual([c["status"] for c in result["coverage"]], ["INCONCLUSIVE", "NOT_RUN"])
        self.assertEqual(result["session"]["budget_exhausted"], "CALLS")

    def test_wall_limit_records_overrun_and_stops_next_operation(self):
        clock = [0]
        def predict():
            clock[0] += 5_000_000_000
            return 2
        with patch("trainlab.research_diagnostics.perf_counter_ns", lambda: clock[0]):
            result = self.bench({"predict": predict}, max_seconds=2).run([
                Diagnostic("first", "1", ("predict",), observed, "scalar"),
                Diagnostic("later", "1", ("predict",), observed, "scalar")])
        self.assertEqual(result["session"]["elapsed_seconds"], 5)
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual([c["status"] for c in result["coverage"]], ["INCONCLUSIVE", "NOT_RUN"])

    def test_journal_or_presync_overrun_cancels_intent_before_operation(self):
        for where in ("journal", "synchronize"):
            with self.subTest(where=where):
                clock, invoked = [0], []
                def predict():
                    invoked.append(True)
                    return 2
                def sync():
                    if where == "synchronize":
                        clock[0] = 5_000_000_000
                bench = Workbench(Adapter("control", {"predict": predict, "synchronize": sync},
                                          STATE), IDENTITIES, self.root / where, max_seconds=1)
                save = bench._save
                def journal():
                    save()
                    if where == "journal" and bench.report["attempts"]:
                        clock[0] = 5_000_000_000
                bench._save = journal
                with patch("trainlab.research_diagnostics.perf_counter_ns", lambda: clock[0]):
                    result = bench.run([
                        Diagnostic("first", "1", ("predict",), observed, "scalar")])
                self.assertEqual(invoked, [])
                self.assertEqual(result["attempts"][0]["status"], "BUDGET_CANCELLED")
                self.assertEqual(result["coverage"][0]["status"], "INCONCLUSIVE")

    def test_check_without_operations_cannot_overrun_and_remain_tested(self):
        clock, later = [0], []
        def overrun(context):
            clock[0] = 5_000_000_000
            return {"status": "TESTED", "summary": "Late observation", "metrics": {}}
        def forbidden(context):
            later.append(True)
            return overrun(context)
        with patch("trainlab.research_diagnostics.perf_counter_ns", lambda: clock[0]):
            result = self.bench(max_seconds=1).run([
                Diagnostic("first", "1", (), overrun, "scalar"),
                Diagnostic("later", "1", (), forbidden, "scalar")])
        self.assertEqual(later, [])
        self.assertEqual([c["status"] for c in result["coverage"]], ["INCONCLUSIVE", "NOT_RUN"])
        self.assertEqual(result["session"]["cost_coverage"], "INCOMPLETE")

    def test_sync_failure_cannot_look_like_success_or_mask_original_failure(self):
        def fail():
            raise ValueError("synchronizer failed")
        bench = Workbench(Adapter("async", {"predict": lambda: 2, "synchronize": fail},
                                  STATE, True), IDENTITIES, self.root)
        result = bench.run([Diagnostic("first", "1", ("predict",), observed, "scalar")])
        self.assertTrue(result["attempts"][0]["sync_error"])
        self.assertEqual(result["attempts"][0]["status"], "FAILED")
        self.assertEqual(result["session"]["cost_coverage"], "INCOMPLETE")
        calls = []
        def sync():
            calls.append(1)
            if len(calls) == 2:
                fail()
        def predict():
            raise RuntimeError("original")
        second = Workbench(Adapter("async", {"predict": predict, "synchronize": sync},
                                   STATE, True), IDENTITIES, self.root.with_name("other"))
        result = second.run([Diagnostic("first", "1", ("predict",), observed, "scalar")])
        self.assertEqual(result["attempts"][0]["error_type"], "RuntimeError")
        self.assertTrue(result["attempts"][0]["sync_error"])

    def test_unsynchronized_async_and_missing_phases_never_claim_complete_cost(self):
        result = Workbench(Adapter("async", {"predict": lambda: 2}, STATE, True),
                           IDENTITIES, self.root, required_phases=("load", "answer")).run([
                               Diagnostic("first", "1", ("predict",), observed, "scalar")])
        self.assertEqual(result["session"]["cost_coverage"], "INCOMPLETE")
        self.assertEqual(result["session"]["missing_successful_phases"], ["load"])
        self.assertEqual(result["session"]["device_completion"], "UNVERIFIED_ASYNC")

    def test_duplicate_unknown_and_malformed_contracts_fail_before_output_creation(self):
        check = Diagnostic("first", "1", ("predict",), observed, "scalar")
        for checks, selection in (([check, check], None), ([check], ["unknown"])):
            with self.subTest(selection=selection), self.assertRaises(LabError):
                self.bench().run(checks, selected=selection)
            self.assertFalse(self.root.exists())
        for kwargs in ({"max_calls": True}, {"max_seconds": float("nan")},
                       {"required_phases": ("invented",)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(LabError):
                self.bench(**kwargs)
        with self.assertRaises(LabError):
            Workbench(Adapter("bad", {"predict": 1}, STATE), IDENTITIES, self.root)
        with self.assertRaises(LabError):
            Workbench(Adapter("bad", {}, STATE), {"dataset": "unbound"}, self.root)

    def test_invalid_observation_is_inconclusive_and_report_is_detached(self):
        def invalid(context):
            return {"status": "TESTED", "summary": "invalid", "metrics": {"x": float("nan")}}
        bench = self.bench()
        result = bench.run([Diagnostic("first", "1", (), invalid, "scalar")])
        self.assertEqual(result["coverage"][0]["status"], "INCONCLUSIVE")
        result["coverage"][0]["status"] = "TESTED"
        self.assertEqual(read_json(self.root / "report.json")["coverage"][0]["status"],
                         "INCONCLUSIVE")
        with self.assertRaises(LabError):
            bench.run([Diagnostic("first", "1", (), invalid, "scalar")])

    def test_wrong_retry_and_nested_operations_do_not_add_unmetered_attempts(self):
        def check(context):
            with self.assertRaises(LabError):
                context.invoke("predict", phase="answer", retry_of=0)
            return observed(context)
        bench = self.bench()
        result = bench.run([Diagnostic("first", "1", ("predict",), check, "scalar")])
        self.assertEqual(len(result["attempts"]), 1)
        nested = self.bench()
        nested.root = self.root.with_name("nested")
        nested.adapter.operations["predict"] = lambda: nested.invoke("predict", phase="answer")
        result = nested.run([Diagnostic("first", "1", ("predict",), observed, "scalar")])
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["attempts"][0]["status"], "FAILED")

    def test_trainlab_timeout_preserves_unfinished_call(self):
        source = self.root.with_name("source")
        source.mkdir()
        (source / "driver.py").write_text('''import os, time
from pathlib import Path
from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
adapter = Adapter("slow", {"predict": lambda: time.sleep(60)},
                  {"persists": "none", "query_mutates": False, "reset": "none"})
identities = {k: "a" * 64 for k in ("model", "dataset", "code", "configuration")}
def check(ctx):
    ctx.invoke("predict", phase="answer")
    return {"status": "TESTED", "summary": "finished", "metrics": {}}
Workbench(adapter, identities, Path(os.environ["TRAINLAB_OUTPUT_DIR"]) / "diagnostics").run(
    [Diagnostic("slow", "1", ("predict",), check, "timeout control")])
''')
        write_json(source / "recipe.json", {
            "schema": "trainlab.experiment.v1", "name": "timeout-control",
            "description": "No model; intentionally stalled callback", "seed": 1,
            "command": [sys.executable, "driver.py"], "timeout_seconds": 2,
            "source_kind": "CONSTRUCTED", "split_identity": "invented",
            "inputs": ["driver.py"], "artifacts": ["diagnostics/report.json"],
            "metrics": {"never": "max"}, "budget": {"model_fits": 0},
        })
        receipt = run_experiment(source / "recipe.json", self.root.with_name("runs"))
        self.assertEqual(receipt["status"], "timed_out")
        directory = self.root.with_name("runs") / receipt["id"]
        self.assertTrue(verify_run(directory)["valid"])
        report = read_json(directory / "output/diagnostics/report.json")
        self.assertEqual(report["state"], "PARTIAL")
        self.assertEqual(report["attempts"][0]["status"], "STARTED")
        self.assertIsNone(report["attempts"][0]["end_seconds"])


if __name__ == "__main__":
    unittest.main()
