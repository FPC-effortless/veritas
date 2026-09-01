from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
AUTHORITY_PATH = HERE / "task_use_authority_v1.json"
REPORT_REGISTRY_PATH = ROOT / "docs/investigation_data/corpora/csb_gold_10/report_acquisition.json"
SOURCE_CATALOG_PATH = ROOT / "src/investigation_world/investigation_data/source_catalog.json"
APPROVED = "approved_for_internal_task_evidence_with_conditions"
REQUIRED_RESTRICTIONS = {
    "internal_extraction_and_normalization_only",
    "no_raw_pdf_git_commit",
    "no_raw_pdf_public_or_exported_redistribution",
    "exclude_or_separately_review_embedded_third_party_media",
    "retain_csb_attribution_and_source_locator_provenance",
    "institutional_findings_are_not_private_ground_truth",
    "respect_frozen_temporal_cut",
    "apply_personal_data_and_redaction_review_before_agent_visibility",
    "minimize_verbatim_reproduction",
    "no_commercial_frontier_scientific_or_training_value_claim",
}
REQUIRED_NON_AUTHORITIES = {
    "raw_pdf_redistribution",
    "public_package_redistribution",
    "model_training_rights",
    "commercial_release",
    "scientific_qualification",
    "frontier_qualification",
}
ALLOWED_DECISIONS = {APPROVED, "link_only", "excluded"}


class TaskUseAuthorityError(ValueError):
    """Raised when report task-use authority is missing, stale, or unsafe."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TaskUseAuthorityError(f"expected object JSON at {path}")
    return value


def _objects(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TaskUseAuthorityError(f"{label} must be a list of objects")
    return value


def _index(items: list[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not value:
            raise TaskUseAuthorityError(f"{label} is missing {key}")
        if value in result:
            raise TaskUseAuthorityError(f"duplicate {label} {key}: {value}")
        result[value] = item
    return result


def validate_authority(
    authority: dict[str, Any],
    report_registry: dict[str, Any],
    source_catalog: dict[str, Any],
) -> None:
    if authority.get("source_id") != "uscsb":
        raise TaskUseAuthorityError("authority must remain bound to source_id uscsb")
    if authority.get("review_scope") != "internal_task_and_verifier_evidence_only":
        raise TaskUseAuthorityError("authority scope must remain internal-only")
    non_authorities = authority.get("not_authorized")
    if not isinstance(non_authorities, list) or set(non_authorities) != REQUIRED_NON_AUTHORITIES:
        raise TaskUseAuthorityError("authority must preserve the complete non-authority boundary")

    reports = _index(
        _objects(report_registry.get("artifacts"), "report artifacts"),
        "artifact_id",
        "report",
    )
    records = _index(
        _objects(authority.get("artifacts"), "authority artifacts"),
        "artifact_id",
        "authority record",
    )
    if len(reports) != 10 or len(records) != 10 or set(records) != set(reports):
        raise TaskUseAuthorityError(
            "authority must cover exactly the ten current Gold report artifacts"
        )

    sources = _index(
        _objects(source_catalog.get("sources"), "source catalog sources"),
        "source_id",
        "source",
    )
    source = sources.get("uscsb")
    if source is None:
        raise TaskUseAuthorityError("canonical uscsb source policy is missing")
    rights = source.get("rights")
    if not isinstance(rights, dict):
        raise TaskUseAuthorityError("canonical uscsb rights policy is malformed")
    expected_policy = {
        "acquisition": rights.get("acquisition"),
        "redistribution": rights.get("redistribution"),
        "ai_use": rights.get("ai_use"),
        "attribution_required": rights.get("attribution_required"),
    }
    authority_policy = authority.get("source_policy")
    if not isinstance(authority_policy, dict):
        raise TaskUseAuthorityError("authority source_policy is missing")
    for key, expected in expected_policy.items():
        if authority_policy.get(key) != expected:
            raise TaskUseAuthorityError(f"authority source policy drift for {key}")

    if expected_policy != {
        "acquisition": "approved",
        "redistribution": "review_required",
        "ai_use": "allowed_with_conditions",
        "attribution_required": True,
    }:
        raise TaskUseAuthorityError(
            "canonical uscsb policy no longer supports this review decision"
        )
    if source.get("contains_personal_data") is not True:
        raise TaskUseAuthorityError(
            "canonical uscsb personal-data boundary changed; re-review is required"
        )
    if source.get("requires_redaction_review") is not True:
        raise TaskUseAuthorityError(
            "canonical uscsb redaction boundary changed; re-review is required"
        )

    for artifact_id, record in records.items():
        report = reports[artifact_id]
        acquisition_url = report.get("acquisition_url") or report.get("resolved_url")
        exact_fields = {
            "case_id": report.get("case_id"),
            "artifact_id": report.get("artifact_id"),
            "report_sha256": report.get("sha256"),
            "receipt_sha256": report.get("receipt_sha256"),
            "catalog_sha256": report.get("catalog_sha256"),
            "canonical_url": report.get("source_url"),
            "acquisition_url": acquisition_url,
        }
        for key, expected in exact_fields.items():
            if not isinstance(expected, str) or not expected:
                raise TaskUseAuthorityError(
                    f"canonical report {artifact_id} is missing {key}"
                )
            if record.get(key) != expected:
                raise TaskUseAuthorityError(
                    f"stale authority for {artifact_id}: {key} mismatch"
                )

        decision = record.get("decision")
        if decision not in ALLOWED_DECISIONS:
            raise TaskUseAuthorityError(f"invalid decision for {artifact_id}")
        if report.get("verification_status") != "verified":
            raise TaskUseAuthorityError(
                f"report {artifact_id} is no longer byte-verified"
            )
        if not isinstance(record.get("review_basis"), str) or not record[
            "review_basis"
        ].strip():
            raise TaskUseAuthorityError(
                f"record {artifact_id} is missing review rationale"
            )
        if decision == APPROVED:
            restrictions = record.get("restrictions")
            if (
                not isinstance(restrictions, list)
                or set(restrictions) != REQUIRED_RESTRICTIONS
            ):
                raise TaskUseAuthorityError(
                    f"approved record {artifact_id} is missing required restrictions"
                )


def is_eligible_for_internal_task_evidence(
    *, artifact_id: str, report_sha256: str, receipt_sha256: str
) -> bool:
    authority = _load(AUTHORITY_PATH)
    reports = _load(REPORT_REGISTRY_PATH)
    source_catalog = _load(SOURCE_CATALOG_PATH)
    validate_authority(authority, reports, source_catalog)
    records = _index(
        _objects(authority["artifacts"], "authority artifacts"),
        "artifact_id",
        "authority record",
    )
    record = records.get(artifact_id)
    return bool(
        record
        and record.get("decision") == APPROVED
        and record.get("report_sha256") == report_sha256
        and record.get("receipt_sha256") == receipt_sha256
    )


if __name__ == "__main__":
    validate_authority(
        _load(AUTHORITY_PATH),
        _load(REPORT_REGISTRY_PATH),
        _load(SOURCE_CATALOG_PATH),
    )
    print("Gold-10 report task-use authority: valid")
