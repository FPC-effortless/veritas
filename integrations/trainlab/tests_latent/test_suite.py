import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from trainlab.latent.artifacts import freeze, verify_bundle
from trainlab.latent.suite import _load_adapter, reanalyze, run_plan
from trainlab.runner import LabError, read_json


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        np.savez(
            self.root / "observations.npz",
            logits=np.array([[3.0, 0.0, -1.0], [0.0, 2.0, 0.0]]),
            targets=np.array([0, 1]),
            baseline=np.array([1.0, 2.0, 3.0, 4.0]),
            treatment=np.array([2.0, 3.0, 4.0, 5.0]),
        )

    def plan(self, jobs):
        doc = {
            "schema": "trainlab.latent-plan.v1",
            "title": "Constructed suite acceptance",
            "identities": {key: "a" * 64 for key in ("model", "dataset", "code", "configuration")},
            "artifacts": {"saved": {"path": "observations.npz", "kind": "npz", "sha256": "a" * 64}},
            "jobs": jobs,
            "budget": {"max_calls": 20, "max_seconds": 30},
        }
        freeze(doc, self.root, self.root / "plan.json")
        return self.root / "plan.json"

    def test_saved_metrics_and_paired_reanalysis_are_exact_without_native_loading(self):
        plan = self.plan(
            [
                {
                    "id": "metrics",
                    "operation": "scoring.classification_metrics",
                    "args": [
                        {"artifact": "saved", "key": "logits"},
                        {"artifact": "saved", "key": "targets"},
                    ],
                },
                {
                    "id": "paired",
                    "operation": "analysis.paired_estimate",
                    "args": [
                        {"artifact": "saved", "key": "treatment"},
                        {"artifact": "saved", "key": "baseline"},
                        ["a", "b", "c", "d"],
                    ],
                    "kwargs": {"draws": 32},
                },
            ]
        )
        result = run_plan(plan, self.root / "bundle", render_figures=False)
        self.assertEqual([row["status"] for row in result["coverage"]], ["TESTED", "TESTED"])
        verify_bundle(self.root / "bundle", result["bundle_sha256"])
        with patch("trainlab.latent.suite._load_adapter", side_effect=AssertionError("model load")):
            replay = reanalyze(
                self.root / "bundle",
                result["bundle_sha256"],
                self.root / "replayed",
                render_figures=False,
            )
        self.assertTrue(replay["byte_exact"])
        self.assertEqual(replay["model_forwards"], 0)
        estimate = read_json(self.root / "bundle/results/paired.json")["value"]["estimate"]
        self.assertEqual(estimate["mean"], 1)
        self.assertEqual(estimate["ci95"], [1.0, 1.0])

    def test_missing_native_capability_is_unsupported_and_failed_dependency_is_retained(self):
        plan = self.plan(
            [
                {"id": "native", "operation": "native.forward", "args": [[[1, 2]]]},
                {
                    "id": "dependent",
                    "operation": "scoring.classification_metrics",
                    "args": [{"result": "native", "path": ["logits"]}, [1]],
                },
            ]
        )
        result = run_plan(plan, self.root / "bundle", render_figures=False)
        self.assertEqual(
            [row["status"] for row in result["coverage"]], ["UNSUPPORTED", "INCONCLUSIVE"]
        )
        self.assertEqual(read_json(self.root / "bundle/ledger/report.json")["attempts"], [])

    def test_native_factory_requires_explicit_execution_and_is_not_used_on_reanalysis(self):
        script = """from trainlab.research_diagnostics import Adapter
import numpy as np
def build(plan, root):
    return Adapter("constructed", {"forward": lambda x: {"logits": np.asarray(x, dtype=float)}},
                   {"persists":"none", "query_mutates":False, "reset":"none"})
"""
        (self.root / "adapter.py").write_text(script)
        plan_path = self.plan(
            [{"id": "capture", "operation": "native.forward", "args": [[[1, 2]]]}]
        )
        plan = read_json(plan_path)
        plan_path.unlink()
        plan["adapter"] = {"path": "adapter.py", "sha256": "a" * 64, "factory": "build"}
        freeze(plan, self.root, plan_path)
        with self.assertRaisesRegex(LabError, "allow-native"):
            run_plan(plan_path, self.root / "not-created", render_figures=False)
        self.assertFalse((self.root / "not-created").exists())
        original_spec = importlib.util.spec_from_file_location

        def mutate_original_during_import(name, path):
            self.assertNotEqual(Path(path), self.root / "adapter.py")
            (self.root / "adapter.py").write_text("raise RuntimeError('unbound source')\n")
            try:
                return original_spec(name, path)
            finally:
                (self.root / "adapter.py").write_text(script)

        with patch(
            "trainlab.latent.suite.importlib.util.spec_from_file_location",
            side_effect=mutate_original_during_import,
        ):
            loaded = _load_adapter(read_json(plan_path), self.root, allow_native=True)
        self.assertEqual(loaded.name, "constructed")
        run = run_plan(plan_path, self.root / "bundle", allow_native=True, render_figures=False)
        with patch("trainlab.latent.suite._load_adapter", side_effect=AssertionError("model load")):
            replay = reanalyze(
                self.root / "bundle",
                run["bundle_sha256"],
                self.root / "replay",
                render_figures=False,
            )
        self.assertTrue(replay["byte_exact"])
        self.assertEqual(replay["comparisons"][0]["kind"], "REUSED_VERIFIED_CAPTURE")

    def test_unknown_operations_do_not_execute_or_create_output(self):
        plan = self.plan([{"id": "bad", "operation": "os.system", "args": ["false"]}])
        with self.assertRaisesRegex(LabError, "unknown"):
            run_plan(plan, self.root / "not-created")
        self.assertFalse((self.root / "not-created").exists())

    def test_literal_metadata_never_adds_native_capabilities_or_capture_provenance(self):
        plan = self.plan(
            [
                {
                    "id": "panel",
                    "operation": "data.language_panel",
                    "args": [
                        {
                            "literal": [
                                {
                                    "id": "a",
                                    "domain": "constructed",
                                    "text": "abcde",
                                    "capability": "ordinary_metadata",
                                }
                            ]
                        }
                    ],
                    "kwargs": {"context": 3},
                }
            ]
        )
        result = run_plan(plan, self.root / "bundle", render_figures=False)
        self.assertEqual(result["coverage"][0]["status"], "TESTED")
        self.assertEqual(
            read_json(self.root / "bundle/captures.json")["native_or_callback_jobs"], []
        )
        replay = reanalyze(
            self.root / "bundle",
            result["bundle_sha256"],
            self.root / "replay",
            render_figures=False,
        )
        self.assertEqual(replay["analysis_jobs_recomputed"], 1)

    def test_incomplete_figure_is_partial_and_worker_exits_unsuccessfully(self):
        from trainlab.latent.__main__ import main

        plan_path = self.plan(
            [
                {
                    "id": "geometry",
                    "operation": "geometry.latent_geometry",
                    "args": [{"artifact": "saved", "key": "logits"}],
                }
            ]
        )
        plan = read_json(plan_path)
        plan_path.unlink()
        plan["figures"] = [{"id": "missing", "kind": "curve", "data": {}}]
        freeze(plan, self.root, plan_path)
        output = self.root / "runner-output"
        output.mkdir()
        with patch.dict("os.environ", {"TRAINLAB_OUTPUT_DIR": str(output)}):
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(["worker", str(plan_path)])
        self.assertEqual(code, 1)
        receipt = read_json(output / "latent-receipt.json")
        self.assertEqual(receipt["state"], "PARTIAL")
        self.assertEqual(receipt["figure_errors"][0]["id"], "missing")

    def test_reused_diagnostic_failures_are_visible_in_suite_and_reports(self):
        rows = [
            {
                "id": "bad",
                "group": "control",
                "original": "wrong",
                "intervened": "wrong",
                "reference_original": "right",
                "reference_intervened": "right",
                "expect_change": True,
                "deficient_original": "wrong",
                "deficient_intervened": "wrong",
            }
        ]
        plan = self.plan(
            [{"id": "benchmark", "operation": "experiment.benchmark_diagnostics", "args": [rows]}]
        )
        result = run_plan(plan, self.root / "bundle", render_figures=False)
        self.assertEqual(result["coverage"][0]["status"], "FAILED")
        summary = read_json(self.root / "bundle/summary.json")
        self.assertEqual([row["status"] for row in summary["subchecks"]], ["FAILED"] * 4)
        self.assertIn("benchmark/oracle_parity", (self.root / "bundle/report.html").read_text())

    def test_native_views_to_token_rows_to_cka_replay_keeps_mapping_order(self):
        script = """import numpy as np
from trainlab.research_diagnostics import Adapter
from trainlab.latent.native import _input_digest
def build(plan, root):
    def forward(value):
        x = np.asarray(value)
        h = np.arange(x.size * 4, dtype=float).reshape(*x.shape, 4)
        return {"hidden": h, "logits": h, "input_sha256": _input_digest(x),
                "views": {"z_last": h * 2, "a_first": h + 1}, "context": {}}
    return Adapter("constructed", {"forward": forward},
                   {"persists": "none", "query_mutates": False, "reset": "per call"})
"""
        (self.root / "adapter.py").write_text(script)
        tokens = [[0, 1, 2], [2, 1, 0]]
        plan_path = self.plan(
            [
                {"id": "capture", "operation": "native.forward", "args": [tokens]},
                {
                    "id": "rows",
                    "operation": "data.prepare_token_rows",
                    "args": [{"result": "capture"}, tokens],
                    "kwargs": {"record_ids": ["a", "b"], "domains": ["d", "d"]},
                },
                {
                    "id": "cka",
                    "operation": "geometry.cka_matrix",
                    "args": [{"result": "rows", "path": ["views"]}],
                },
            ]
        )
        plan = read_json(plan_path)
        plan_path.unlink()
        plan["adapter"] = {"path": "adapter.py", "sha256": "a" * 64, "factory": "build"}
        freeze(plan, self.root, plan_path)
        run = run_plan(plan_path, self.root / "bundle", allow_native=True, render_figures=False)
        self.assertEqual([row["status"] for row in run["coverage"]], ["TESTED"] * 3)
        with patch("trainlab.latent.suite._load_adapter", side_effect=AssertionError("model load")):
            replay = reanalyze(
                self.root / "bundle",
                run["bundle_sha256"],
                self.root / "replay",
                render_figures=False,
            )
        self.assertTrue(replay["byte_exact"])
        self.assertEqual(
            read_json(self.root / "bundle/results/cka.json")["value"]["models"],
            ["a_first", "z_last"],
        )


if __name__ == "__main__":
    unittest.main()
