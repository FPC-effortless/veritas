import copy
import tempfile
import unittest
from pathlib import Path

from trainlab.competence_panels import freeze_panel, score_artifact, score_panel
from trainlab.prediction_artifacts import make_request, write_predictions
from trainlab.runner import LabError


def fixture(seeds=(11, 22), mode="fresh_replay", threshold=1):
    inputs, cases = [], []
    for seed in seeds:
        for template in ("primitive", "composition"):
            for map_id in ("m1", "m2"):
                for query in ("a", "b"):
                    rid = f"{seed}:{template}:{map_id}:{query}"
                    inputs.append({"id": rid, "input": [template, map_id, query]})
                    cases.append(
                        {
                            "id": rid,
                            "seed": seed,
                            "map_id": template + map_id,
                            "group": map_id,
                            "template": template,
                            "payload": "v",
                            "query_id": query,
                            "expected": 1,
                        }
                    )
    state = {
        "mode": "stateless" if mode == "fresh_replay" else "sequential",
        "initial_state_sha256": "a" * 64,
        "persists": "rows within map",
        "query_mutates": False,
        "reset": "explicit protocol reset",
    }
    request = make_request(
        {k: "a" * 64 for k in ("model", "dataset", "code", "configuration")},
        inputs,
        task={"name": "panel", "output_schema": "finite-json-v1"},
        state=state,
    )
    envelope = freeze_panel(
        request,
        cases,
        required_seeds=list(seeds),
        required_templates=["primitive", "composition"],
        query_mode=mode,
        thresholds={"query_accuracy": threshold, "map_accuracy": threshold},
    )
    observations = [{"id": c["id"], "status": "observed", "value": 1} for c in cases]
    return envelope, observations


class PanelTests(unittest.TestCase):
    def score(self, envelope, rows):
        return score_panel(envelope["panel"], rows, panel_sha256=envelope["panel_sha256"])

    def test_clean_panel_has_query_and_map_scores(self):
        p, rows = fixture()
        result = self.score(p, rows)
        r = result["report"]
        self.assertEqual(r["status"], "TESTED")
        self.assertEqual(r["overall"]["query_accuracy"], 1)
        self.assertEqual(r["overall"]["map_accuracy"], 1)
        self.assertEqual(len(r["cells"]), 4)
        self.assertEqual(result["competence_reference"]["status"], "supported")
        self.assertEqual(result["competence_reference"]["evidence_sha256"], result["report_sha256"])

    def test_one_bad_member_breaks_whole_map(self):
        p, rows = fixture(seeds=(11,))
        rows[0]["value"] = 2
        r = self.score(p, rows)["report"]
        self.assertEqual(r["overall"]["query_accuracy"], 7 / 8)
        self.assertEqual(r["overall"]["map_accuracy"], 3 / 4)
        self.assertEqual(r["status"], "FAILED")

    def test_pooled_accuracy_cannot_hide_seed_template_failure(self):
        p, rows = fixture(threshold=0.8)
        rows[0]["value"] = 2
        r = self.score(p, rows)["report"]
        self.assertGreater(r["overall"]["query_accuracy"], 0.8)
        self.assertGreater(r["overall"]["map_accuracy"], 0.8)
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual([c["seed"] for c in r["cells"] if c["status"] == "FAILED"], [11])

    def test_missing_queries_are_inconclusive_not_clean(self):
        p, rows = fixture()
        r = self.score(p, rows[1:])["report"]
        self.assertEqual(r["status"], "INCONCLUSIVE")
        self.assertIsNone(r["overall"]["query_accuracy"])
        self.assertEqual(r["missing_ids"], [rows[0]["id"]])

    def test_known_failure_survives_missing_observations(self):
        p, rows = fixture()
        rows[0]["value"] = 2
        r = self.score(p, rows[:-1])["report"]
        self.assertEqual(r["status"], "FAILED")
        self.assertEqual(r["overall"]["query_upper_bound"], 15 / 16)

    def test_all_missing_and_failed_remain_unknown(self):
        p, rows = fixture()
        for obs in ([], [{**r, "status": "failed", "value": None} for r in rows]):
            result = self.score(p, obs)
            self.assertEqual(result["report"]["status"], "INCONCLUSIVE")
            self.assertEqual(result["competence_reference"]["status"], "unknown")

    def test_null_is_valid_answer_boolean_is_not_integer(self):
        p, rows = fixture()
        rows[0]["value"] = True
        self.assertEqual(self.score(p, rows)["report"]["status"], "FAILED")
        p["panel"]["cases"][0]["expected"] = None
        from trainlab.competence_panels import _sha

        p["panel_sha256"] = _sha(p["panel"])
        rows[0]["value"] = None
        self.assertEqual(self.score(p, rows)["report"]["status"], "TESTED")

    def test_panel_hash_binds_thresholds_labels_and_mode(self):
        for modify in (
            lambda p: p["thresholds"].update(query_accuracy=0.5),
            lambda p: p["cases"][0].update(expected=2),
            lambda p: p.update(query_mode="continuous"),
        ):
            p, rows = fixture()
            modify(p["panel"])
            with self.assertRaises(LabError):
                self.score(p, rows)

    def test_extra_duplicate_or_malformed_observations_rejected(self):
        p, rows = fixture()
        for obs in (
            rows + rows[:1],
            rows + [{"id": "x", "status": "observed", "value": 1}],
            [{**rows[0], "status": "missing", "value": 2}],
            [{**rows[0], "value": float("nan")}],
            [{**rows[0], "status": "success"}],
        ):
            with self.assertRaises(LabError):
                self.score(p, obs)

    def test_required_seed_template_and_map_members_cannot_disappear(self):
        p, _ = fixture()
        panel = p["panel"]
        for cases in (panel["cases"][:8], panel["cases"][:-1], panel["cases"] + panel["cases"][:1]):
            with self.assertRaises(LabError):
                freeze_panel(
                    panel["request"],
                    cases,
                    required_seeds=[11, 22],
                    required_templates=["primitive", "composition"],
                    query_mode="fresh_replay",
                    thresholds=panel["thresholds"],
                )

    def test_mixed_map_metadata_and_duplicate_query_rejected(self):
        p, _ = fixture()
        panel = p["panel"]
        for field, value in (("template", "composition"), ("query_id", "a"), ("group", "other")):
            cases = copy.deepcopy(panel["cases"])
            cases[1][field] = value
            with self.assertRaises(LabError):
                freeze_panel(
                    panel["request"],
                    cases,
                    required_seeds=[11, 22],
                    required_templates=["primitive", "composition"],
                    query_mode="fresh_replay",
                    thresholds=panel["thresholds"],
                )

    def test_artifact_reuse_binds_exact_request_and_bytes(self):
        p, rows = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.json"
            pin = write_predictions(
                path, p["panel"]["request"], [{"id": r["id"], "output": r["value"]} for r in rows]
            )
            a = score_artifact(path, pin, p["panel"], panel_sha256=p["panel_sha256"])
            b = score_artifact(path, pin, p["panel"], panel_sha256=p["panel_sha256"])
            self.assertEqual(a, b)
            self.assertEqual(a["report"]["source"]["kind"], "VERIFIED_ARTIFACT_BINDING")
            path.write_text(path.read_text() + " ")
            with self.assertRaises(LabError):
                score_artifact(path, pin, p["panel"], panel_sha256=p["panel_sha256"])

    def test_continuous_label_requires_sequential_request(self):
        p, rows = fixture(mode="continuous")
        self.assertEqual(self.score(p, rows)["report"]["query_mode"], "continuous")
        p["panel"]["request"]["state"]["mode"] = "stateless"
        from trainlab.competence_panels import _sha

        p["panel_sha256"] = _sha(p["panel"])
        with self.assertRaises(LabError):
            self.score(p, rows)

    def test_changed_model_data_configuration_or_order_rejects_cached_outputs(self):
        from trainlab.competence_panels import _sha

        p, rows = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "predictions.json"
            pin = write_predictions(
                path, p["panel"]["request"], [{"id": r["id"], "output": r["value"]} for r in rows]
            )
            for field in ("model", "dataset", "configuration", "code"):
                altered = copy.deepcopy(p["panel"])
                altered["request"]["identities"][field] = "b" * 64
                with self.assertRaises(LabError):
                    score_artifact(path, pin, altered, panel_sha256=_sha(altered))
            altered = copy.deepcopy(p["panel"])
            altered["cases"].reverse()
            altered["request"]["rows"].reverse()
            with self.assertRaises(LabError):
                score_artifact(path, pin, altered, panel_sha256=_sha(altered))

    def test_nonpositive_boolean_or_nonfinite_threshold_rejected(self):
        p, _ = fixture()
        for value in (0, True, float("nan"), float("inf"), 1.1):
            with self.assertRaises(LabError):
                freeze_panel(
                    p["panel"]["request"],
                    p["panel"]["cases"],
                    required_seeds=[11, 22],
                    required_templates=["primitive", "composition"],
                    query_mode="fresh_replay",
                    thresholds={"query_accuracy": value, "map_accuracy": 1},
                )

    def test_map_bound_uses_same_arithmetic_as_exact_accuracy(self):
        from trainlab.competence_panels import _sha

        p, rows = fixture(seeds=(11,))
        # One correct and two failed maps: no subtraction-rounding pass at a threshold
        # infinitesimally above 1/3.
        panel = p["panel"]
        extra = copy.deepcopy(panel["cases"][:2])
        extra_inputs = copy.deepcopy(panel["request"]["rows"][:2])
        for c, i in zip(extra, extra_inputs):
            c["id"] += ":third"
            i["id"] = c["id"]
            c["map_id"] += "third"
        panel["cases"] += extra
        panel["request"]["rows"] += extra_inputs
        panel["thresholds"] = {"query_accuracy": 0.1, "map_accuracy": 0.33333333333333337}
        rows[0]["value"] = 2
        rows += [{"id": c["id"], "status": "observed", "value": 2} for c in extra]
        p["panel_sha256"] = _sha(panel)
        r = self.score(p, rows)["report"]
        cell = next(c for c in r["cells"] if c["template"] == "primitive")
        self.assertEqual(cell["map_accuracy"], 1 / 3)
        self.assertEqual(cell["map_upper_bound"], 1 / 3)
        self.assertEqual(cell["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
