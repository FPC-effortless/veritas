import tempfile
import unittest
from pathlib import Path

from trainlab.diagnostic_imports import import_history, import_trace
from trainlab.runner import LabError, digest, write_json


class DiagnosticImportsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def history(self, metrics, token=None, max_events=100):
        path = self.root / "history.json"
        data = {"metrics": metrics}
        if token is not None:
            data["next_page_token"] = token
        write_json(path, data)
        return import_history(
            path, sha256=digest(path), run_id="run-1", metric_key="loss", max_events=max_events
        )

    def metric(self, step=1, **changes):
        return {
            "key": "loss",
            "value": 0.5,
            "timestamp": "1740000000000",
            "step": str(step),
            **changes,
        }

    def trace(self, events, max_events=100):
        path = self.root / "trace.json"
        write_json(path, {"schemaVersion": 1, "displayTimeUnit": "ms", "traceEvents": events})
        return import_trace(path, sha256=digest(path), capture_id="example", max_events=max_events)

    def span(self, **changes):
        return {
            "ph": "X",
            "cat": "cpu_op",
            "name": "aten::mm",
            "ts": 100.0,
            "dur": 20.5,
            "pid": 1,
            "tid": 1,
            **changes,
        }

    def test_preserves_repeated_metric_steps_and_partial_page(self):
        report = self.history([self.metric(), self.metric(value=0.4)], token="opaque-secret-marker")
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertEqual([row["step"] for row in report["rows"]], [1, 1])
        self.assertEqual([row["source_index"] for row in report["rows"]], [0, 1])
        self.assertNotIn("opaque-secret-marker", str(report))

    def test_preserves_scopes_and_rejects_cross_run_or_key(self):
        result = self.history(
            [
                self.metric(dataset_name="a", dataset_digest="ab"),
                self.metric(dataset_name="a", dataset_digest="cd"),
            ]
        )
        self.assertEqual(len(result["scopes"]), 2)
        for bad in (
            self.metric(run_id="run-2"),
            {**self.metric(), "key": "wrong"},
            self.metric(timestamp="nan"),
            self.metric(step=True),
        ):
            with self.subTest(row=bad), self.assertRaises(LabError):
                self.history([bad])

    def test_only_complete_cpu_durations_are_aggregated(self):
        result = self.trace(
            [
                self.span(),
                self.span(dur=40.5, ts=101),
                self.span(cat="kernel"),
                {"ph": "M", "name": "thread_name"},
            ]
        )
        self.assertEqual(result["observations"]["inclusive_cpu_duration_us"], 61)
        self.assertEqual(
            result["observations"]["unsupported_by_phase_category"],
            [
                {"phase": "M", "category": None, "events": 1},
                {"phase": "X", "category": "kernel", "events": 1},
            ],
        )
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(len(result["rows"]), 2)

    def test_invalid_duration_and_truncated_scan(self):
        with self.assertRaises(LabError):
            self.trace([self.span(dur=-1)])
        result = self.trace([self.span(), self.span()], max_events=1)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["observations"]["omitted_events"], 1)

    def test_changed_bytes_and_invalid_integer_strings(self):
        path = self.root / "history.json"
        path.write_text('{"metrics":[]}')
        pin = digest(path)
        path.write_text('{"metrics":[{}]}')
        with self.assertRaises(LabError):
            import_history(path, sha256=pin, run_id="run-1", metric_key="loss")
        with self.assertRaises(LabError):
            self.history([self.metric(step="1.0")])
