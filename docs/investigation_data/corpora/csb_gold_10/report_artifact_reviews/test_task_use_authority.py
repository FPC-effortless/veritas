from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from validate_task_use_authority import TaskUseAuthorityError, validate_authority

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[5]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class TaskUseAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.authority = _load(HERE / "task_use_authority_v1.json")
        self.reports = _load(
            ROOT / "docs/investigation_data/corpora/csb_gold_10/report_acquisition.json"
        )
        self.catalog = _load(
            ROOT / "src/investigation_world/investigation_data/source_catalog.json"
        )

    def assert_rejected(self, mutate) -> None:
        authority = copy.deepcopy(self.authority)
        reports = copy.deepcopy(self.reports)
        catalog = copy.deepcopy(self.catalog)
        mutate(authority, reports, catalog)
        with self.assertRaises(TaskUseAuthorityError):
            validate_authority(authority, reports, catalog)

    def test_current_authority_is_valid(self) -> None:
        validate_authority(self.authority, self.reports, self.catalog)

    def test_missing_artifact_id_fails_closed(self) -> None:
        self.assert_rejected(
            lambda authority, _reports, _catalog: authority["artifacts"][0].pop(
                "artifact_id"
            )
        )

    def test_report_hash_drift_fails_closed(self) -> None:
        self.assert_rejected(
            lambda authority, _reports, _catalog: authority["artifacts"][0].__setitem__(
                "report_sha256", "0" * 64
            )
        )

    def test_receipt_hash_drift_fails_closed(self) -> None:
        self.assert_rejected(
            lambda authority, _reports, _catalog: authority["artifacts"][0].__setitem__(
                "receipt_sha256", "0" * 64
            )
        )

    def test_catalog_authority_drift_fails_closed(self) -> None:
        self.assert_rejected(
            lambda authority, _reports, _catalog: authority["artifacts"][0].__setitem__(
                "catalog_sha256", "0" * 64
            )
        )

    def test_invalid_decision_fails_closed(self) -> None:
        self.assert_rejected(
            lambda authority, _reports, _catalog: authority["artifacts"][0].__setitem__(
                "decision", "approved"
            )
        )

    def test_missing_restriction_fails_closed(self) -> None:
        self.assert_rejected(
            lambda authority, _reports, _catalog: authority["artifacts"][0][
                "restrictions"
            ].pop()
        )

    def test_missing_non_authority_boundary_fails_closed(self) -> None:
        self.assert_rejected(
            lambda authority, _reports, _catalog: authority["not_authorized"].pop()
        )

    def test_source_policy_drift_fails_closed(self) -> None:
        def mutate(_authority, _reports, catalog) -> None:
            source = next(
                item for item in catalog["sources"] if item["source_id"] == "uscsb"
            )
            source["rights"]["ai_use"] = "review_required"

        self.assert_rejected(mutate)

    def test_personal_data_boundary_drift_fails_closed(self) -> None:
        def mutate(_authority, _reports, catalog) -> None:
            source = next(
                item for item in catalog["sources"] if item["source_id"] == "uscsb"
            )
            source["contains_personal_data"] = False

        self.assert_rejected(mutate)

    def test_redaction_boundary_drift_fails_closed(self) -> None:
        def mutate(_authority, _reports, catalog) -> None:
            source = next(
                item for item in catalog["sources"] if item["source_id"] == "uscsb"
            )
            source["requires_redaction_review"] = False

        self.assert_rejected(mutate)

    def test_report_registry_identity_drift_fails_closed(self) -> None:
        self.assert_rejected(
            lambda _authority, reports, _catalog: reports["artifacts"][0].__setitem__(
                "receipt_sha256", "1" * 64
            )
        )


if __name__ == "__main__":
    unittest.main()
