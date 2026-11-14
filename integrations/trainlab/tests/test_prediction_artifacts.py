import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trainlab.prediction_artifacts import (
    conformance_checks,
    make_request,
    read_predictions,
    write_predictions,
)
from trainlab.research_diagnostics import Adapter, Workbench
from trainlab.runner import LabError

IDENTITIES = {key: "a" * 64 for key in ("model", "dataset", "code", "configuration")}
STATE = {"mode": "stateless", "initial_state_sha256": "b" * 64,
         "persists": "weights only", "query_mutates": False, "reset": "not_applicable"}
ROWS = [{"id": "a", "input": 2}, {"id": "b", "input": 7}, {"id": "c", "input": 11}]
TASK = {"name": "double", "output_schema": "finite-json-v1"}


def predict(rows):
    return [{"id": r["id"], "output": 2 * r["input"]} for r in rows]


class PredictionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "predictions.json"
        self.request = make_request(IDENTITIES, ROWS, task=TASK, state=STATE)

    def test_reuse_is_pinned_and_consumers_are_independent(self):
        pin = write_predictions(self.path, self.request, predict(ROWS))
        self.assertEqual(pin, hashlib.sha256(self.path.read_bytes()).hexdigest())
        first = read_predictions(self.path, pin, self.request)
        first[0]["output"] = -999
        self.assertEqual(read_predictions(self.path, pin, self.request), predict(ROWS))
        with self.assertRaises(FileExistsError):
            write_predictions(self.path, self.request, predict(ROWS))

    def test_every_binding_rejects_stale_reuse(self):
        pin = write_predictions(self.path, self.request, predict(ROWS))
        cases = []
        for key in IDENTITIES:
            ids = dict(IDENTITIES, **{key: "c" * 64})
            cases.append(make_request(ids, ROWS, task=TASK, state=STATE))
        cases.append(make_request(IDENTITIES, ROWS[::-1], task=TASK, state=STATE))
        rows = copy.deepcopy(ROWS)
        rows[0]["input"] = 3
        cases.append(make_request(IDENTITIES, rows, task=TASK, state=STATE))
        cases.append(make_request(IDENTITIES, ROWS, task=dict(TASK, name="other"), state=STATE))
        cases.append(make_request(IDENTITIES, ROWS, task=TASK,
                                  state=dict(STATE, initial_state_sha256="c" * 64)))
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(LabError):
                read_predictions(self.path, pin, changed)

    def test_invalid_mappings_and_nonfinite_predictions_rejected(self):
        good = predict(ROWS)
        for bad in (good[::-1], good[:2], good + [good[0]],
                    [good[0], good[0], good[2]],
                    [{"id": "a", "output": float("nan")}] + good[1:],
                    [{"id": "a", "output": {1: "integer key"}}] + good[1:]):
            with self.subTest(bad=bad), self.assertRaises(LabError):
                write_predictions(self.path, self.request, bad)
            self.assertFalse(self.path.exists())

    def test_tampering_duplicate_keys_and_overflow_rejected_even_with_new_pin(self):
        pin = write_predictions(self.path, self.request, predict(ROWS))
        raw = self.path.read_bytes()
        self.path.write_bytes(raw + b" ")
        with self.assertRaises(LabError):
            read_predictions(self.path, pin, self.request)
        document = json.loads(raw)
        document["predictions"][0]["output"] = float("inf")
        bad = json.dumps(document).replace("Infinity", "1e999").encode()
        duplicate = raw.replace(b'"schema":', b'"schema": "duplicate", "schema":', 1)
        for data in (bad, duplicate):
            self.path.write_bytes(data)
            with self.assertRaises(LabError):
                read_predictions(self.path, hashlib.sha256(data).hexdigest(), self.request)

    def test_requests_are_bounded_and_detached(self):
        rows = copy.deepcopy(ROWS)
        request = make_request(IDENTITIES, rows, task=TASK, state=STATE)
        rows[0]["input"] = 99
        self.assertEqual(request, self.request)
        for rows in ([], ROWS + [ROWS[0]], [{"id": "a", "input": float("inf")}],
                     [{"id": "a", "input": {1: "not JSON"}}]):
            with self.assertRaises(LabError):
                make_request(IDENTITIES, rows, task=TASK, state=STATE)

    def test_tampered_row_mapping_rejected_with_recomputed_artifact_hash(self):
        write_predictions(self.path, self.request, predict(ROWS))
        document = json.loads(self.path.read_bytes())
        document["predictions"].reverse()
        data = json.dumps(document).encode()
        self.path.write_bytes(data)
        with self.assertRaises(LabError):
            read_predictions(self.path, hashlib.sha256(data).hexdigest(), self.request)

    def test_size_depth_and_invalid_contracts_fail_before_publication(self):
        with patch("trainlab.prediction_artifacts.MAX_BYTES", 8), self.assertRaises(LabError):
            write_predictions(self.path, self.request, predict(ROWS))
        nested = []
        nested.append(nested)
        with self.assertRaises(LabError):
            make_request(IDENTITIES, [{"id": "cycle", "input": nested}], task=TASK, state=STATE)
        for state in (dict(STATE, query_mutates=True), dict(STATE, initial_state_sha256="unknown")):
            with self.assertRaises(LabError):
                make_request(IDENTITIES, ROWS, task=TASK, state=state)
        with self.assertRaises(LabError):
            make_request(IDENTITIES, ROWS, task=dict(TASK, output_schema="unknown"), state=STATE)
        self.assertFalse(self.path.exists())

    def test_publication_failure_does_not_leave_partial_artifact(self):
        with patch("trainlab.prediction_artifacts.os.link", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                write_predictions(self.path, self.request, predict(ROWS))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_example_protocol_only_drift_invalidates_reuse(self):
        source = Path(__file__).resolve().parents[1] / "examples/diagnose_models.py"
        spec = importlib.util.spec_from_file_location("diagnose_example", source)
        example = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(example)
        recipe, protocol = self.root / "recipe.json", self.root / "protocol.json"
        recipe.write_text('{"inputs":["protocol.json"]}')
        protocol.write_text('{"runtime":"first"}')
        identities = dict(IDENTITIES,
                          configuration=example.configuration_identity(recipe, protocol))
        request = make_request(identities, ROWS, task=TASK, state=STATE)
        pin = write_predictions(self.path, request, predict(ROWS))
        protocol.write_text('{"runtime":"changed"}')
        identities["configuration"] = example.configuration_identity(recipe, protocol)
        changed = make_request(identities, ROWS, task=TASK, state=STATE)
        with self.assertRaises(LabError):
            read_predictions(self.path, pin, changed)

    def conformance(self, operation, *, mode="stateless", reset=None, limit=100):
        ops = {"predict_rows": operation}
        if reset is not None:
            ops["reset"] = reset
        semantics = {k: v for k, v in STATE.items() if k not in ("mode", "initial_state_sha256")}
        if mode == "sequential":
            semantics.update(persists="running total", query_mutates=True, reset="zero total")
        report = Workbench(Adapter("test", ops, semantics), IDENTITIES,
                           self.root / "report", max_calls=limit).run(
                               conformance_checks(ROWS, mode=mode))
        return {c["name"]: c["status"] for c in report["coverage"]}, report

    def test_stateless_clean_and_all_calls_are_metered(self):
        status, report = self.conformance(predict)
        self.assertEqual(set(status.values()), {"TESTED"})
        self.assertEqual(len(report["attempts"]), 7)

    def test_swapped_ids_are_failed_not_accepted(self):
        status, _ = self.conformance(lambda rows: predict(rows)[::-1])
        self.assertEqual(set(status.values()), {"FAILED"})

    def test_batch_dependent_control_fails(self):
        def bad(rows):
            return [{"id": r["id"], "output": len(rows)} for r in rows]
        status, _ = self.conformance(bad)
        self.assertEqual(status["adapter_batching"], "FAILED")

    def test_positional_outputs_with_correct_ids_fail_permutation(self):
        def positional(rows):
            return [{"id": r["id"], "output": i} for i, r in enumerate(rows)]
        status, _ = self.conformance(positional)
        self.assertEqual(status["adapter_permutation"], "FAILED")

    def test_consistently_wrong_answers_are_not_detected_without_a_label_oracle(self):
        status, _ = self.conformance(lambda rows: [{"id": r["id"], "output": -999} for r in rows])
        self.assertEqual(set(status.values()), {"TESTED"})

    def test_sequential_order_dependency_is_not_a_permutation_failure(self):
        total = [0]
        def step(rows):
            result = []
            for row in rows:
                total[0] += row["input"]
                result.append({"id": row["id"], "output": total[0]})
            return result
        status, _ = self.conformance(step, mode="sequential", reset=lambda: total.__setitem__(0, 0))
        self.assertEqual(status, {"adapter_replay": "TESTED", "adapter_batching": "TESTED"})

    def test_broken_reset_and_missing_reset_do_not_pass(self):
        counter = [0]
        def step(rows):
            counter[0] += 1
            return [{"id": r["id"], "output": counter[0]} for r in rows]
        status, _ = self.conformance(step, mode="sequential", reset=lambda: None)
        self.assertEqual(set(status.values()), {"FAILED"})
        self.root = self.root / "another"
        status, _ = self.conformance(step, mode="sequential")
        self.assertEqual(set(status.values()), {"UNSUPPORTED"})

    def test_budget_exhaustion_cannot_be_a_conformance_pass(self):
        status, report = self.conformance(predict, limit=1)
        self.assertEqual(status["adapter_replay"], "INCONCLUSIVE")
        self.assertEqual(report["session"]["budget_exhausted"], "CALLS")


if __name__ == "__main__":
    unittest.main()
