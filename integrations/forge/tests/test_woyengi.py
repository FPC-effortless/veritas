"""Constructed no-fit Woyengi->Forge projection tests; NOT real source rights evidence."""
import copy
import unittest

from forge_data.core import ForgeError, point_in_time
from forge_data.woyengi import convert_export_candidate


def constructed_export():
    def row(cid, leader, known, sha):
        return {
            "claimId": cid, "validFrom": "2026-02-01T00:00:00Z",
            "knownFrom": known, "sourceAvailableAt": known, "featureHash": sha,
            "features": {"observed_owner": leader},
        }
    return {
        "kind": "PREDICTIVE_READ_EXPORT", "schemaVersion": 1,
        "status": "ADVISORY_ONLY", "subject": "entity:fixture-workflow",
        "predicate": "workflow:owner", "validAt": "2026-02-05T00:00:00Z",
        "recordedAt": "2026-02-15T00:00:00Z",
        "predictionCutoff": "2026-02-15T00:00:00Z",
        "selectedClaimId": "claim:fixture-second",
        "conflictingClaimIds": ["claim:fixture-first"],
        "observations": [
            row("claim:fixture-first", "entity:one", "2026-02-01T12:00:00Z", "a" * 64),
            row("claim:fixture-second", "entity:two", "2026-02-10T12:00:00Z", "b" * 64),
        ],
        "qualification": "STRUCTURAL_EXPORT_ONLY",
        "publisherAuthenticity": "NOT_ATTESTED_BY_THIS_EXPORTER",
        "independentRewardVerification": "NOT_PERFORMED",
        "actionAuthority": "NOT_GRANTED",
    }


class WoyengiForgeContractTest(unittest.TestCase):
    def setUp(self):
        self.source = constructed_export()

    def reject(self):
        with self.assertRaises(ForgeError):
            convert_export_candidate(self.source)

    def test_registered_export_is_candidate_not_training_release(self):
        result = convert_export_candidate(self.source)
        self.assertEqual(result["conversion"], "STRUCTURAL_ONLY")
        self.assertFalse(result["source_legal_permission_verified"])
        self.assertFalse(result["woyengi_host_authenticated"])
        self.assertFalse(result["independent_outcome_verified"])
        self.assertEqual(len(result["rows"]), 2)
        self.assertTrue(all(x["outcome"]["status"] == "unknown" for x in result["rows"]))
        self.assertTrue(all(x["outcome"]["verified"] is False for x in result["rows"]))
        self.assertTrue(all(x["action"] is None for x in result["rows"]))
        self.assertEqual({x["subject_id"] for x in result["rows"]}, {"entity:fixture-workflow"})

    def test_earlier_history_cannot_see_later_conflict_selection(self):
        rows = convert_export_candidate(self.source)["rows"]
        for row in rows:
            self.assertIsNone(point_in_time(row, "2026-02-14T23:59:59Z"))
            view = point_in_time(row, "2026-02-15T00:00:00Z")
            self.assertIsNotNone(view)
            self.assertNotIn("verified", view["observation"])
            self.assertIsNone(view["outcome"])

    def test_claim_validity_is_not_sensor_observation(self):
        x = convert_export_candidate(self.source)["rows"][0]
        self.assertEqual(x["observed_at"], "2026-02-01T00:00:00.000000Z")
        self.assertEqual(x["available_at"], "2026-02-15T00:00:00.000000Z")
        self.assertEqual(x["observation"]["kind"], "woyengi_bitemporal_claim_projection")
        self.assertEqual(x["observation"]["selected_at_projection"], False)
        self.assertEqual(x["observation"]["conflicted_at_projection"], True)

    def test_unknown_outcomes_never_fabricated(self):
        x = convert_export_candidate(self.source)["rows"]
        self.assertEqual([r["outcome"]["available_at"] for r in x], [None, None])
        self.assertEqual([r["outcome"].get("value") for r in x], [None, None])

    def test_future_known_claim_rejected(self):
        self.source["observations"][1]["knownFrom"] = "2026-02-16T00:00:00Z"
        self.reject()

    def test_future_available_claim_rejected(self):
        self.source["observations"][1]["sourceAvailableAt"] = "2026-02-16T00:00:00Z"
        self.reject()

    def test_conflicting_claim_omitted_rejected(self):
        self.source["conflictingClaimIds"] = ["claim:nonexistent"]
        self.reject()

    def test_selected_claim_missing_rejected(self):
        self.source["selectedClaimId"] = "claim:nonexistent"
        self.reject()

    def test_duplicate_claim_rejected(self):
        self.source["observations"].append(copy.deepcopy(self.source["observations"][0]))
        self.reject()

    def test_false_authority_rejected(self):
        self.source["actionAuthority"] = "AUTHORIZED"
        self.reject()

    def test_false_verification_rejected(self):
        self.source["independentRewardVerification"] = "VERIFIED"
        self.reject()

    def test_oracle_features_rejected(self):
        self.source["observations"][0]["features"]["oracle_reward"] = 3
        self.reject()

    def test_invalid_numeric_input_rejected(self):
        self.source["observations"][0]["features"]["signal"] = float("nan")
        self.reject()

    def test_projection_time_after_cutoff_rejected(self):
        self.source["recordedAt"] = "2026-02-16T00:00:00Z"
        self.reject()

    def test_future_target_cannot_enter_model(self):
        self.source["observations"][0]["features"] = {"future_outcome": True}
        self.reject()

    def test_different_registered_claim_no_extra_predictions(self):
        b = constructed_export()
        result = convert_export_candidate(b)
        self.assertEqual(len(result["rows"]), 2)
        self.assertNotIn("predictions", result)
        self.assertNotIn("reward", result)


if __name__ == "__main__":
    unittest.main()
