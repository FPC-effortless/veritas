import sys
import tempfile
import unittest
from pathlib import Path

from trainlab.competence_panels import freeze_panel
from trainlab.prediction_artifacts import make_request
from trainlab.reliability_cost import compare_at_reliability, read_panel_session, run_panel_session
from trainlab.runner import LabError, read_json


def plan(model="a", labels=(1, 2), mode="fresh_replay"):
    inputs = [{"id": str(i), "input": i} for i in range(2)]
    request = make_request(
        {
            k: (model if k == "model" else "a") * 64
            for k in ("model", "dataset", "code", "configuration")
        },
        inputs,
        task={"name": "two-member-map", "output_schema": "finite-json-v1"},
        state={
            "mode": "stateless" if mode == "fresh_replay" else "sequential",
            "initial_state_sha256": "a" * 64,
            "persists": "declared map",
            "reset": "each map",
            "query_mutates": False,
        },
    )
    cases = [
        {
            "id": str(i),
            "seed": 0,
            "map_id": "m",
            "group": "g",
            "template": "primitive",
            "payload": "v",
            "query_id": str(i),
            "expected": labels[i],
        }
        for i in range(2)
    ]
    return inputs, freeze_panel(
        request,
        cases,
        required_seeds=[0],
        required_templates=["primitive"],
        query_mode=mode,
        thresholds={"query_accuracy": 1, "map_accuracy": 1},
    )


@unittest.skipUnless(sys.platform == "linux", "Linux CPU resource backend")
class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.n = 0

    def run_case(self, model="a", values=(1, 2), failure=False, **changes):
        self.n += 1
        inputs, panel = plan(
            model=model,
            labels=changes.pop("labels", (1, 2)),
            mode=changes.pop("mode", "fresh_replay"),
        )
        code = (
            "raise SystemExit(7)"
            if failure
            else "import sys,json; json.dump("
            + repr([{"id": str(i), "answer": v} for i, v in enumerate(values)])
            + ",open(sys.argv[2],'w'))"
        )
        result = run_panel_session(
            [sys.executable, "-c", code, "{inputs}", "{predictions}"],
            self.root / str(self.n),
            cwd=self.root,
            panel=panel["panel"],
            panel_sha256=panel["panel_sha256"],
            inputs=inputs,
            operations="set-v1",
            limits={
                "wall_seconds": 3,
                "cpu_seconds": 2,
                "address_space_bytes": 256 * 1024**2,
                "file_bytes": 4096,
            },
            **changes,
        )
        return {
            "root": str(self.root / str(self.n)),
            "manifest_sha256": result["manifest_sha256"],
        }, result

    def test_replay_recomputes_both_metrics_from_same_output(self):
        ref, result = self.run_case(values=(1, 9))
        replay = read_panel_session(**ref)
        self.assertEqual(result, replay)
        self.assertEqual(replay["metrics"]["query_accuracy"], 0.5)
        self.assertEqual(replay["metrics"]["map_accuracy"], 0)
        self.assertTrue(replay["complete"])
        self.assertEqual(replay["competence_status"], "FAILED")
        self.assertNotEqual(
            replay["points"]["query_accuracy"]["workload_sha256"],
            replay["points"]["map_accuracy"]["workload_sha256"],
        )

    def test_failed_cost_retained_without_quality_point(self):
        _, r = self.run_case(failure=True)
        self.assertFalse(r["complete"])
        self.assertGreater(r["wall_seconds"], 0)
        self.assertIsNone(r["points"]["map_accuracy"])

    def test_cheaper_wrong_answers_do_not_meet_reliability(self):
        a, _ = self.run_case(model="a")
        b, _ = self.run_case(model="b", values=(1, 9))
        report = compare_at_reliability(
            [{"arm": "good", "repeat": 0, **a}, {"arm": "bad", "repeat": 0, **b}],
            required_arms=["good", "bad"],
            required_repeats=[0],
            metric="map_accuracy",
            quality_floor=1,
        )
        self.assertEqual(report["status"], "TESTED")
        self.assertEqual(report["eligible_arms"], ["good"])
        self.assertEqual(report["lowest_median_cost_arms"], ["good"])

    def test_one_failed_repeat_blocks_ranking_but_retains_cost(self):
        a, _ = self.run_case(model="a")
        b, _ = self.run_case(model="b", failure=True)
        report = compare_at_reliability(
            [{"arm": "a", "repeat": 0, **a}, {"arm": "b", "repeat": 0, **b}],
            required_arms=["a", "b"],
            required_repeats=[0],
            metric="query_accuracy",
            quality_floor=1,
        )
        self.assertEqual(report["status"], "INCONCLUSIVE")
        self.assertIsNone(report["lowest_median_cost_arms"])
        self.assertGreater(report["arms"]["b"]["observed_seconds_total"], 0)

    def test_missing_duplicate_or_reused_runs_rejected(self):
        a, _ = self.run_case()
        row = {"arm": "a", "repeat": 0, **a}
        for rows in ([row], [row, row], [row, {**row, "arm": "b"}]):
            with self.assertRaises(LabError):
                compare_at_reliability(
                    rows,
                    required_arms=["a", "b"],
                    required_repeats=[0],
                    metric="map_accuracy",
                    quality_floor=1,
                )

    def test_different_panel_or_query_mode_blocks_context_match(self):
        a, _ = self.run_case()
        for changes in ({"labels": (1, 3)}, {"mode": "continuous"}):
            b, _ = self.run_case(model="b", **changes)
            r = compare_at_reliability(
                [{"arm": "a", "repeat": 0, **a}, {"arm": "b", "repeat": 0, **b}],
                required_arms=["a", "b"],
                required_repeats=[0],
                metric="map_accuracy",
                quality_floor=1,
            )
            self.assertEqual(r["status"], "FAILED")
            self.assertIsNone(r["lowest_median_cost_arms"])

    def test_all_pinned_files_detect_tampering(self):
        ref, _ = self.run_case()
        root = Path(ref["root"])
        manifest = read_json(root / "manifest.json")
        for name, pin in manifest["files"].items():
            if pin is None:
                continue
            path = root / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaises(LabError):
                read_panel_session(**ref)
            path.write_bytes(original)
        (root / "manifest.json").write_text("{}")
        with self.assertRaises(LabError):
            read_panel_session(**ref)

    def test_input_hash_mismatch_rejected_before_launch(self):
        inputs, p = plan()
        inputs[0]["input"] = 99
        target = self.root / "invalid"
        with self.assertRaises(LabError):
            run_panel_session(
                [sys.executable, "-c", "pass", "{inputs}", "{predictions}"],
                target,
                cwd=self.root,
                panel=p["panel"],
                panel_sha256=p["panel_sha256"],
                inputs=inputs,
                operations="set-v1",
                limits={},
            )
        self.assertFalse(target.exists())

    def test_arm_identity_changes_across_repeats_rejected(self):
        refs = []
        for arm, repeat, model in (("a", 0, "a"), ("a", 1, "c"), ("b", 0, "b"), ("b", 1, "b")):
            ref, _ = self.run_case(model=model)
            refs.append({"arm": arm, "repeat": repeat, **ref})
        with self.assertRaises(LabError):
            compare_at_reliability(
                refs,
                required_arms=["a", "b"],
                required_repeats=[0, 1],
                metric="map_accuracy",
                quality_floor=1,
            )

    def test_manifest_cannot_select_arbitrary_file_paths(self):
        from trainlab.runner import digest, write_json

        ref, _ = self.run_case()
        path = Path(ref["root"]) / "manifest.json"
        m = read_json(path)
        m["files"]["../outside"] = "a" * 64
        write_json(path, m)
        with self.assertRaises(LabError):
            read_panel_session(ref["root"], digest(path))

    def test_rehashed_manifest_does_not_bypass_cross_bindings(self):
        from trainlab.runner import digest, write_json

        ref, _ = self.run_case()
        root = Path(ref["root"])
        path = root / "session/run/predictions.json"
        write_json(path, [{"id": "0", "answer": 9}, {"id": "1", "answer": 9}])
        manifest = read_json(root / "manifest.json")
        manifest["files"]["session/run/predictions.json"] = digest(path)
        write_json(root / "manifest.json", manifest)
        with self.assertRaises(LabError):
            read_panel_session(root, digest(root / "manifest.json"))

    def test_no_eligible_arm_is_not_a_reliability_pass(self):
        records = []
        for arm in ("a", "b"):
            ref, _ = self.run_case(model=arm, values=(9, 9))
            records.append({"arm": arm, "repeat": 0, **ref})
        report = compare_at_reliability(
            records,
            required_arms=["a", "b"],
            required_repeats=[0],
            metric="map_accuracy",
            quality_floor=1,
        )
        self.assertEqual(report["status"], "TESTED")
        self.assertEqual(report["eligible_arms"], [])
        self.assertEqual(report["lowest_median_cost_arms"], [])

    def test_symlink_output_rejected_even_with_matching_bytes(self):
        ref, _ = self.run_case()
        root = Path(ref["root"])
        output = root / "session/run/predictions.json"
        backup = root / "backup.json"
        output.rename(backup)
        output.symlink_to(backup)
        with self.assertRaises(LabError):
            read_panel_session(**ref)

    def test_copied_receipt_cannot_become_another_repeat(self):
        import shutil

        from trainlab.runner import digest

        ref, _ = self.run_case()
        copied = self.root / "copied"
        shutil.copytree(ref["root"], copied)
        manifest = copied / "manifest.json"
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        records = [
            {"arm": "a", "repeat": 0, **ref},
            {"arm": "b", "repeat": 0, "root": str(copied), "manifest_sha256": digest(manifest)},
        ]
        with self.assertRaises(LabError):
            compare_at_reliability(
                records,
                required_arms=["a", "b"],
                required_repeats=[0],
                metric="map_accuracy",
                quality_floor=1,
            )


if __name__ == "__main__":
    unittest.main()
