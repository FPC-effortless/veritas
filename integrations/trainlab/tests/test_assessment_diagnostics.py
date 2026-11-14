import copy
import sys
import tempfile
import unittest
from pathlib import Path

from trainlab.assessment_diagnostics import (
    generalization_audit,
    measured_quality_session,
    paired_slices,
    training_order_audit,
)
from trainlab.experiment_diagnostics import quality_cost
from trainlab.runner import LabError


def descriptor(name="train", template="set", group="g1", size=4):
    return {
        "id": name,
        "group": group,
        "axes": {"template": template, "identity": "a"},
        "scales": {"active_records": size},
    }


def schedule(name, reverse=False):
    updates = [[{"example_sha256": c * 64, "supervision_sha256": "f" * 64}] for c in "ab"]
    return {
        "id": name,
        "initialization_sha256": "c" * 64,
        "optimizer_sha256": "d" * 64,
        "updates": updates[::-1] if reverse else updates,
    }


class AssessmentTests(unittest.TestCase):
    def test_known_templates_are_not_unseen(self):
        r = generalization_audit([descriptor()], [descriptor("eval", group="g2")])
        self.assertEqual(r["axes"]["template"]["unseen_ids"], [])
        self.assertEqual(r["independence"], "DECLARED_NOT_VERIFIED")

    def test_overlap_and_extrapolation(self):
        r = generalization_audit([descriptor()], [descriptor("eval", "link-copy", size=8)])
        self.assertEqual(r["overlapping_groups"], ["g1"])
        self.assertEqual(r["axes"]["template"]["unseen_ids"], ["eval"])
        self.assertEqual(r["scales"]["active_records"]["above_training_max_ids"], ["eval"])

    def test_missing_axis_and_boolean_scale_rejected(self):
        for change in ({"axes": {}}, {"scales": {"active_records": True}}):
            with self.assertRaises(LabError):
                generalization_audit([descriptor()], [{**descriptor("eval"), **change}])

    def test_schedule_matches_exposure_but_reports_order_change(self):
        r = training_order_audit([schedule("joint"), schedule("staged", True)])
        self.assertEqual(r["status"], "TESTED")
        self.assertFalse(r["identical_order"])
        self.assertEqual(r["total_updates"], {"joint": 2, "staged": 2})

    def test_schedule_differences_fail(self):
        for key in ("initialization_sha256", "optimizer_sha256"):
            b = schedule("b")
            b[key] = "e" * 64
            self.assertEqual(training_order_audit([schedule("a"), b])["status"], "FAILED")
        b = schedule("b")
        b["updates"][0][0]["supervision_sha256"] = "e" * 64
        self.assertEqual(training_order_audit([schedule("a"), b])["status"], "FAILED")
        b = schedule("b")
        b["updates"] = [sum(b["updates"], [])]
        self.assertEqual(training_order_audit([schedule("a"), b])["status"], "FAILED")

    def rows(self):
        return [
            {
                "id": str(i),
                "seed": seed,
                "group": str(i),
                "payload": payload,
                "template": "set",
                "candidate": c,
                "baseline": b,
            }
            for seed in (101, 202)
            for i, (payload, c, b) in enumerate(
                [("x", True, False), ("x", True, False), ("y", False, True)]
            )
        ]

    def test_payload_removal_exposes_reversal(self):
        r = paired_slices(self.rows(), required_ids=["0", "1", "2"], required_seeds=[101, 202])
        self.assertAlmostEqual(r["overall"]["query_delta"], 1 / 3)
        self.assertEqual(r["leave_one_payload_out"]["x"]["query_delta"], -1)
        self.assertTrue(r["leave_one_payload_out"]["x"]["sign_reversal"])
        self.assertEqual(len(r["by_seed"]), 2)

    def test_incomplete_or_duplicate_pairs_rejected(self):
        for rows in (self.rows()[:-1], self.rows() + self.rows()[:1]):
            with self.assertRaises(LabError):
                paired_slices(rows, required_ids=["0", "1", "2"], required_seeds=[101, 202])

    def test_metadata_cannot_change_across_seeds(self):
        rows = self.rows()
        rows[-1]["payload"] = "changed"
        with self.assertRaises(LabError):
            paired_slices(rows, required_ids=["0", "1", "2"], required_seeds=[101, 202])

    def test_boolean_outcomes_required(self):
        rows = self.rows()
        rows[0]["candidate"] = 1
        with self.assertRaises(LabError):
            paired_slices(rows, required_ids=["0", "1", "2"], required_seeds=[101, 202])

    def run_session(self, code, expected=None, file_bytes=4096):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        return measured_quality_session(
            [sys.executable, "-c", code, "{inputs}", "{predictions}"],
            root / "session",
            cwd=root,
            identities={k: "a" * 64 for k in ("model", "dataset", "code", "configuration")},
            inputs=[{"id": "a", "input": 1}],
            expected=expected or [{"id": "a", "answer": 1}],
            semantics={"query_mode": "fresh_replay", "operations": "set-v1"},
            limits={
                "wall_seconds": 3,
                "cpu_seconds": 2,
                "address_space_bytes": 256 * 1024**2,
                "file_bytes": file_bytes,
            },
        )

    @unittest.skipUnless(sys.platform == "linux", "CPU supervisor is Linux only")
    def test_actual_session_scores_output_and_binds_expected_panel(self):
        code = "import sys,json; json.dump([{'id':'a','answer':1}],open(sys.argv[2],'w'))"
        a = self.run_session(code)
        b = self.run_session(code, [{"id": "a", "answer": 2}])
        self.assertEqual(a["quality"], 1)
        self.assertEqual(b["quality"], 0)
        self.assertGreater(a["receipt"]["wall_seconds"], 0)
        r = quality_cost([dict(a["point"], id="a"), dict(b["point"], id="b")])
        self.assertIsNone(r["observations"]["pareto_ids"])

    @unittest.skipUnless(sys.platform == "linux", "CPU supervisor is Linux only")
    def test_failed_or_malformed_output_never_becomes_point(self):
        for code in (
            "raise SystemExit(3)",
            "pass",
            "import sys; open(sys.argv[2],'w').write('[]')",
            "import sys; open(sys.argv[2],'w').write('NaN')",
        ):
            r = self.run_session(code)
            self.assertIsNone(r["point"])
            self.assertIsNone(r["quality"])
            self.assertGreater(r["receipt"]["wall_seconds"], 0)

    @unittest.skipUnless(sys.platform == "linux", "CPU supervisor is Linux only")
    def test_json_type_mismatch_is_wrong(self):
        r = self.run_session(
            "import sys,json; json.dump([{'id':'a','answer':True}],open(sys.argv[2],'w'))"
        )
        self.assertEqual(r["quality"], 0)

    @unittest.skipUnless(sys.platform == "linux", "CPU supervisor is Linux only")
    def test_valid_prediction_over_one_megabyte_is_scored(self):
        r = self.run_session(
            "import sys,json; json.dump([{'id':'a','answer':'x'*(2**20+1)}],open(sys.argv[2],'w'))",
            [{"id": "a", "answer": "x" * (2**20 + 1)}],
            file_bytes=2**22,
        )
        self.assertEqual(r["quality"], 1)

    @unittest.skipUnless(sys.platform == "linux", "CPU supervisor is Linux only")
    def test_modified_input_or_symlink_output_cannot_qualify(self):
        for code in (
            "import sys,json; open(sys.argv[1],'w').write('[]'); "
            "json.dump([{'id':'a','answer':1}],open(sys.argv[2],'w'))",
            "import sys,os; os.symlink(sys.argv[1],sys.argv[2])",
            "import sys,json; json.dump([{'id':'other','answer':1}],open(sys.argv[2],'w'))",
        ):
            self.assertIsNone(self.run_session(code)["point"])

    def test_reports_do_not_mutate_input(self):
        train, evaluation = [descriptor()], [descriptor("eval")]
        saved = copy.deepcopy([train, evaluation])
        generalization_audit(train, evaluation)
        self.assertEqual([train, evaluation], saved)


if __name__ == "__main__":
    unittest.main()
