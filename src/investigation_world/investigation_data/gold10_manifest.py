from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class Gold10ManifestError(ValueError):
    """Raised when the frozen Gold-10 selection cannot be reconstructed safely."""


ROOT = Path(__file__).resolve().parents[3]
CORPUS_REL = Path("docs/investigation_data/corpora/csb_gold_10")
PILOTS_REL = Path("docs/investigation_data/pilots")
SOURCE_CATALOG_REL = Path("src/investigation_world/investigation_data/source_catalog.json")
FREEZE_REL = Path("data/gold10/case_selection_v1.json")
TASK_USE_AUTHORITY_REL = (
    CORPUS_REL / "report_artifact_reviews" / "task_use_authority_v1.json"
)
EXPECTED_SOURCE_ID = "uscsb"
EXPECTED_TASK_OWNER_ROOT = "src/investigation_world/gold10/tasks"
EXPECTED_VERIFIER_OWNER_ROOT = "src/investigation_world/gold10/verifiers"
EXPECTED_TRUTH_POLICY = "institutional_findings_are_evidence_not_private_truth"
EXPECTED_CONTAMINATION_POLICY = "public_historical_nonsealed"
EXPECTED_DATE_ONLY_RELEASE_POLICY = "next_day_12z"
EXPECTED_TRUTH_REGIME = "institutional_findings"
EXPECTED_CONTAMINATION_RISK = "high_public_historical_nonsealed"
EXPECTED_PILOT_REVIEW_STATUS = "approved_for_link_only_pilot"
EXPECTED_REPORT_USAGE_POLICY = "require_exact_content_bound_task_use_authority"
EXPECTED_TASK_USE_AUTHORITY_ID = "gold10-report-task-use-v1"
EXPECTED_TASK_USE_SCOPE = "internal_task_and_verifier_evidence_only"
EXPECTED_TASK_USE_DECISION = "approved_for_internal_task_evidence_with_conditions"
EXPECTED_TASK_USE_NOT_AUTHORIZED = frozenset(
    {
        "raw_pdf_redistribution",
        "public_package_redistribution",
        "model_training_rights",
        "commercial_release",
        "scientific_qualification",
        "frontier_qualification",
    }
)
EXPECTED_TASK_USE_RESTRICTIONS = frozenset(
    {
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
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise Gold10ManifestError(f"expected object JSON at {path}")
    return value, _sha256_bytes(raw)


def _unique_by(
    items: list[dict[str, Any]],
    key: str,
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        value = item.get(key)
        if not isinstance(value, str) or not value:
            raise Gold10ManifestError(f"{label} entry is missing string {key}")
        if value in result:
            raise Gold10ManifestError(f"duplicate {label} {key}: {value}")
        result[value] = item
    return result


def _require_list(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise Gold10ManifestError(f"{label} must be a list of objects")
    return value


def _require_object(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Gold10ManifestError(f"{label} must be an object")
    return value


def _find_source(catalog: dict[str, Any], source_id: str) -> dict[str, Any]:
    sources = _require_list(catalog.get("sources"), label="source catalog sources")
    matches = [item for item in sources if item.get("source_id") == source_id]
    if len(matches) != 1:
        raise Gold10ManifestError(
            f"source_id {source_id!r} must resolve exactly once; found {len(matches)}"
        )
    return matches[0]


def _parse_timestamp(value: Any, *, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise Gold10ManifestError(f"{label} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Gold10ManifestError(f"{label} is not a valid ISO timestamp") from exc
    if parsed.utcoffset() is None:
        raise Gold10ManifestError(f"{label} must include a timezone offset")
    return parsed


def _require_nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Gold10ManifestError(f"{label} must be a non-empty string")
    return value


def _require_trimmed_string(value: Any, *, label: str) -> str:
    text = _require_nonempty_string(value, label=label)
    if text != text.strip():
        raise Gold10ManifestError(f"{label} must not contain surrounding whitespace")
    return text


def _require_exact_string(value: Any, *, label: str, expected: str) -> str:
    actual = _require_trimmed_string(value, label=label)
    if actual != expected:
        raise Gold10ManifestError(
            f"{label} must remain frozen at {expected!r}; got {actual!r}"
        )
    return actual


def _require_exact_string_set(
    value: Any,
    *,
    label: str,
    expected: frozenset[str],
) -> list[str]:
    if not isinstance(value, list):
        raise Gold10ManifestError(f"{label} must be a list of strings")
    items = [
        _require_trimmed_string(item, label=f"{label}[{index}]")
        for index, item in enumerate(value)
    ]
    if len(items) != len(set(items)):
        raise Gold10ManifestError(f"{label} must not contain duplicates")
    if set(items) != expected:
        raise Gold10ManifestError(f"{label} does not preserve the exact authority boundary")
    return items


def _require_sha256(value: Any, *, label: str) -> str:
    digest = _require_trimmed_string(value, label=label)
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise Gold10ManifestError(
            f"{label} must be a lowercase 64-hex SHA-256 digest"
        )
    return digest


def _require_positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise Gold10ManifestError(f"{label} must be a positive integer")
    return value


def _require_bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise Gold10ManifestError(f"{label} must be a JSON boolean")
    return value


def _require_safe_component(value: Any, *, label: str) -> str:
    component = _require_trimmed_string(value, label=label)
    if component in {".", ".."} or "/" in component or "\\" in component or ".." in component:
        raise Gold10ManifestError(f"{label} must be a safe repository path component")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if any(character not in allowed for character in component):
        raise Gold10ManifestError(f"{label} must be a safe repository path component")
    return component


def _require_owner_root(value: Any, *, label: str, expected: str) -> str:
    root = _require_trimmed_string(value, label=label)
    if "\\" in root or root.startswith("/") or root.endswith("/"):
        raise Gold10ManifestError(
            f"{label} must be a normalized repository-relative path"
        )
    parts = root.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise Gold10ManifestError(
            f"{label} must be a normalized repository-relative path"
        )
    if root != expected:
        raise Gold10ManifestError(
            f"{label} must remain frozen at {expected!r}; got {root!r}"
        )
    return root


def _require_safe_slug(value: Any, *, label: str) -> str:
    return _require_safe_component(value, label=label)


def _require_capability_targets(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise Gold10ManifestError(f"{label} must be a non-empty list of strings")
    targets: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        target = _require_trimmed_string(item, label=f"{label}[{index}]")
        if target in seen:
            raise Gold10ManifestError(
                f"{label} must not contain duplicate capability targets"
            )
        seen.add(target)
        targets.append(target)
    return targets


def _require_case_ids(
    value: Any,
    *,
    label: str,
    expected: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise Gold10ManifestError(f"{label} must be a non-empty list of case IDs")
    case_ids: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        case_id = _require_trimmed_string(item, label=f"{label}[{index}]")
        if case_id in seen:
            raise Gold10ManifestError(f"{label} must not contain duplicate case IDs")
        seen.add(case_id)
        case_ids.append(case_id)
    if expected not in seen:
        raise Gold10ManifestError(f"{label} must retain canonical case ID {expected!r}")
    return case_ids


def _reviewed_case_aliases(
    review_record: dict[str, Any],
    *,
    case_id: str,
    expected: str,
) -> set[str]:
    aliases_raw = review_record.get("source_case_aliases")
    if aliases_raw is None:
        return {expected}
    aliases = _require_case_ids(
        aliases_raw,
        label=f"case {case_id} pilot review source_case_aliases",
        expected=expected,
    )
    return set(aliases)


def _require_exact_reviewed_case_ids(
    value: Any,
    *,
    label: str,
    expected: str,
    reviewed_aliases: set[str],
) -> list[str]:
    case_ids = _require_case_ids(value, label=label, expected=expected)
    if set(case_ids) != reviewed_aliases:
        raise Gold10ManifestError(
            f"{label} must equal exact reviewed aliases {sorted(reviewed_aliases)!r}"
        )
    return case_ids


def _report_task_eligible(review_status: str) -> bool:
    """Never derive task-use authority from a mutable status string alone."""

    del review_status
    return False


def manifest_digest(manifest: dict[str, Any]) -> str:
    """Hash a Gold-10 manifest while excluding its self-referential digest field."""

    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    return _stable_hash(payload)


def _validated_source_policy(
    source: dict[str, Any],
    report_policy: dict[str, Any],
    *,
    source_id: str,
) -> dict[str, Any]:
    rights = _require_object(source.get("rights"), label="canonical Gold-10 source rights")
    validated_rights = dict(rights)
    for field in ("acquisition", "redistribution", "ai_use"):
        source_value = _require_trimmed_string(
            rights.get(field), label=f"canonical source rights {field}"
        )
        report_value = _require_trimmed_string(
            report_policy.get(field), label=f"Gold-10 report policy {field}"
        )
        if report_value != source_value:
            raise Gold10ManifestError(
                f"Gold-10 report policy {field!r} disagrees with canonical source rights"
            )
        validated_rights[field] = source_value

    attribution_required = _require_bool(
        rights.get("attribution_required"),
        label="canonical source rights attribution_required",
    )
    if not attribution_required:
        raise Gold10ManifestError(
            "canonical source rights attribution_required changed; task-use re-review is required"
        )
    validated_rights["attribution_required"] = True
    if report_policy.get("raw_bytes_committed_to_git") is not False:
        raise Gold10ManifestError("Gold-10 report bytes must not be committed to Git")

    contains_personal_data = _require_bool(
        source.get("contains_personal_data"),
        label="canonical source contains_personal_data",
    )
    if not contains_personal_data:
        raise Gold10ManifestError(
            "canonical source contains_personal_data changed; task-use re-review is required"
        )
    requires_redaction_review = _require_bool(
        source.get("requires_redaction_review"),
        label="canonical source requires_redaction_review",
    )
    if not requires_redaction_review:
        raise Gold10ManifestError(
            "canonical source requires_redaction_review changed; task-use re-review is required"
        )
    truth = _require_object(source.get("truth"), label="canonical Gold-10 source truth")
    validated_truth = dict(truth)
    validated_truth["strength"] = _require_trimmed_string(
        truth.get("strength"), label="canonical source truth strength"
    )
    validated_truth["basis"] = _require_trimmed_string(
        truth.get("basis"), label="canonical source truth basis"
    )
    if _require_bool(
        truth.get("official_findings_are_ground_truth"),
        label="canonical source truth official_findings_are_ground_truth",
    ):
        raise Gold10ManifestError(
            "canonical source truth cannot promote institutional findings to ground truth"
        )
    validated_truth["official_findings_are_ground_truth"] = False
    validated_truth["verifier_use"] = _require_exact_string(
        truth.get("verifier_use"),
        label="canonical source truth verifier_use",
        expected="evidence_reference",
    )

    return {
        "source_id": source_id,
        "rights": validated_rights,
        "contains_personal_data": contains_personal_data,
        "requires_redaction_review": requires_redaction_review,
        "truth": validated_truth,
    }


def _validated_task_use_authority(
    authority: dict[str, Any],
    *,
    expected_cases: set[str],
    expected_artifact_ids: set[str],
    source_id: str,
) -> dict[str, dict[str, Any]]:
    _require_exact_string(
        authority.get("authority_id"),
        label="Gold-10 task-use authority_id",
        expected=EXPECTED_TASK_USE_AUTHORITY_ID,
    )
    if source_id != EXPECTED_SOURCE_ID:
        raise Gold10ManifestError(
            "Gold-10 task-use authority must remain bound to source_id uscsb"
        )
    _require_exact_string(
        authority.get("source_id"),
        label="Gold-10 task-use authority source_id",
        expected=EXPECTED_SOURCE_ID,
    )
    _require_exact_string(
        authority.get("review_scope"),
        label="Gold-10 task-use authority review_scope",
        expected=EXPECTED_TASK_USE_SCOPE,
    )
    _require_exact_string_set(
        authority.get("not_authorized"),
        label="Gold-10 task-use authority not_authorized",
        expected=EXPECTED_TASK_USE_NOT_AUTHORIZED,
    )
    source_policy = _require_object(
        authority.get("source_policy"), label="Gold-10 task-use authority source_policy"
    )
    _require_exact_string(
        source_policy.get("acquisition"),
        label="task-use authority source_policy acquisition",
        expected="approved",
    )
    _require_exact_string(
        source_policy.get("redistribution"),
        label="task-use authority source_policy redistribution",
        expected="review_required",
    )
    _require_exact_string(
        source_policy.get("ai_use"),
        label="task-use authority source_policy ai_use",
        expected="allowed_with_conditions",
    )
    if source_policy.get("attribution_required") is not True:
        raise Gold10ManifestError(
            "task-use authority source_policy attribution_required must remain true"
        )
    _require_nonempty_string(
        source_policy.get("personal_data_redaction_rule"),
        label="task-use authority personal_data_redaction_rule",
    )
    _require_nonempty_string(
        authority.get("staleness_rule"), label="Gold-10 task-use authority staleness_rule"
    )

    authority_artifacts = _require_list(
        authority.get("artifacts"), label="task-use authority artifacts"
    )
    records = _unique_by(
        authority_artifacts,
        "case_id",
        label="task-use authority case",
    )
    if len(records) != 10 or set(records) != expected_cases:
        raise Gold10ManifestError(
            "task-use authority must cover exactly the canonical ten Gold-10 cases"
        )
    records_by_artifact = _unique_by(
        authority_artifacts,
        "artifact_id",
        label="task-use authority artifact",
    )
    if len(records_by_artifact) != 10 or set(records_by_artifact) != expected_artifact_ids:
        raise Gold10ManifestError(
            "task-use authority artifact_id set mismatches canonical Gold reports"
        )
    return records


def _validate_task_use_source_policy(
    authority: dict[str, Any],
    canonical_source_policy: dict[str, Any],
) -> None:
    authority_policy = _require_object(
        authority.get("source_policy"), label="Gold-10 task-use authority source_policy"
    )
    canonical_rights = _require_object(
        canonical_source_policy.get("rights"),
        label="validated canonical Gold-10 source rights",
    )
    for field in ("acquisition", "redistribution", "ai_use", "attribution_required"):
        if authority_policy.get(field) != canonical_rights.get(field):
            raise Gold10ManifestError(
                f"task-use authority source_policy {field!r} disagrees with current "
                "canonical source policy; task-use re-review is required"
            )


def _validated_task_use_record(
    record: dict[str, Any],
    *,
    case_id: str,
    artifact_id: str,
    report_sha256: str,
    receipt_sha256: str,
    catalog_sha256: str,
    canonical_url: str,
    acquisition_url: str,
) -> dict[str, Any]:
    expected_fields = {
        "case_id": case_id,
        "artifact_id": artifact_id,
        "report_sha256": report_sha256,
        "receipt_sha256": receipt_sha256,
        "catalog_sha256": catalog_sha256,
        "canonical_url": canonical_url,
        "acquisition_url": acquisition_url,
    }
    for field, expected in expected_fields.items():
        actual = _require_trimmed_string(
            record.get(field), label=f"case {case_id} task-use authority {field}"
        )
        if actual != expected:
            raise Gold10ManifestError(
                f"case {case_id} authority {field} mismatches canonical report identity"
            )

    decision = _require_exact_string(
        record.get("decision"),
        label=f"case {case_id} task-use authority decision",
        expected=EXPECTED_TASK_USE_DECISION,
    )
    restrictions = _require_exact_string_set(
        record.get("restrictions"),
        label=f"case {case_id} task-use authority restrictions",
        expected=EXPECTED_TASK_USE_RESTRICTIONS,
    )
    review_basis = _require_nonempty_string(
        record.get("review_basis"),
        label=f"case {case_id} task-use authority review_basis",
    )
    return {
        "authority_id": EXPECTED_TASK_USE_AUTHORITY_ID,
        "review_scope": EXPECTED_TASK_USE_SCOPE,
        "decision": decision,
        "restrictions": restrictions,
        "review_basis": review_basis,
    }


def _validated_fragment(
    fragment: dict[str, Any],
    *,
    case_id: str,
    expected_source_case_id: str,
    source_id: str,
    review_id: str,
    reviewed_aliases: set[str],
) -> tuple[str, bool, bool, Any]:
    fragment_id = _require_trimmed_string(
        fragment.get("fragment_id"), label=f"case {case_id} fragment_id"
    )
    if fragment.get("source_id") != source_id:
        raise Gold10ManifestError(
            f"case {case_id} fragment {fragment_id} source mismatch"
        )
    _require_exact_reviewed_case_ids(
        fragment.get("case_ids"),
        label=f"case {case_id} fragment {fragment_id} case_ids",
        expected=expected_source_case_id,
        reviewed_aliases=reviewed_aliases,
    )
    modality = _require_trimmed_string(
        fragment.get("modality"),
        label=f"case {case_id} fragment {fragment_id} modality",
    )
    sensitivity = _require_trimmed_string(
        fragment.get("sensitivity"),
        label=f"case {case_id} fragment {fragment_id} sensitivity",
    )
    if sensitivity != "public":
        return modality, False, False, None

    if fragment.get("rights_review_id") != review_id:
        raise Gold10ManifestError(
            f"case {case_id} fragment {fragment_id} is not bound to the exact pilot review"
        )
    _require_trimmed_string(
        fragment.get("locator"),
        label=f"case {case_id} fragment {fragment_id} locator",
    )
    _require_trimmed_string(
        fragment.get("content_ref"),
        label=f"case {case_id} fragment {fragment_id} content_ref",
    )
    timeless_raw = fragment.get("timeless", False)
    timeless = _require_bool(
        timeless_raw,
        label=f"case {case_id} fragment {fragment_id} timeless",
    )
    return modality, True, timeless, fragment.get("available_from")


def build_gold10_manifest(root: Path | None = None) -> dict[str, Any]:
    """Reconstruct the frozen Gold-10 case manifest from canonical repository inputs."""

    repo_root = (root or ROOT).resolve()
    corpus_root = repo_root / CORPUS_REL
    pilots_root = repo_root / PILOTS_REL

    freeze, freeze_sha = _read_json(repo_root / FREEZE_REL)
    index, index_sha = _read_json(corpus_root / "index.json")
    coverage, coverage_sha = _read_json(corpus_root / "pilot_coverage.json")
    reports, reports_sha = _read_json(corpus_root / "report_acquisition.json")
    source_catalog, source_catalog_sha = _read_json(repo_root / SOURCE_CATALOG_REL)
    task_use_authority, task_use_authority_sha = _read_json(
        repo_root / TASK_USE_AUTHORITY_REL
    )

    if freeze.get("manifest_id") != "gold10-case-selection-v1":
        raise Gold10ManifestError("unexpected Gold-10 freeze manifest_id")

    corpus_ids = {
        freeze.get("corpus_id"),
        index.get("corpus_id"),
        coverage.get("corpus_id"),
        reports.get("corpus_id"),
    }
    if None in corpus_ids or len(corpus_ids) != 1:
        raise Gold10ManifestError("Gold-10 corpus identities disagree")

    source_ids = {
        freeze.get("source_id"),
        index.get("source_id"),
        reports.get("source_id"),
        task_use_authority.get("source_id"),
    }
    if None in source_ids or len(source_ids) != 1:
        raise Gold10ManifestError(
            "Gold-10 source identities disagree with task-use authority"
        )

    freeze_cases = _unique_by(
        _require_list(freeze.get("cases"), label="freeze cases"),
        "case_id",
        label="freeze case",
    )
    index_cases = _unique_by(
        _require_list(index.get("cases"), label="index cases"),
        "case_id",
        label="index case",
    )
    coverage_cases = _unique_by(
        _require_list(coverage.get("pilots"), label="pilot coverage"),
        "case_id",
        label="coverage case",
    )
    report_artifacts = _require_list(reports.get("artifacts"), label="report artifacts")
    report_cases = _unique_by(
        report_artifacts,
        "case_id",
        label="report case",
    )
    reports_by_artifact = _unique_by(
        report_artifacts,
        "artifact_id",
        label="report artifact",
    )

    expected_cases = set(index_cases)
    if len(expected_cases) != 10 or index.get("target_cases") != 10:
        raise Gold10ManifestError("canonical Gold-10 index must contain exactly 10 cases")
    if coverage.get("coverage_target") != 10:
        raise Gold10ManifestError("Gold-10 pilot coverage target must remain 10")
    for label, candidate in (
        ("freeze", set(freeze_cases)),
        ("coverage", set(coverage_cases)),
        ("reports", set(report_cases)),
    ):
        if candidate != expected_cases:
            raise Gold10ManifestError(
                f"{label} case set does not equal canonical Gold-10 index"
            )

    source_id = _require_trimmed_string(
        index.get("source_id"), label="Gold-10 source_id"
    )
    authority_cases = _validated_task_use_authority(
        task_use_authority,
        expected_cases=expected_cases,
        expected_artifact_ids=set(reports_by_artifact),
        source_id=source_id,
    )

    split_counts = {"train": 0, "dev": 0, "eval": 0}
    calibration_by_case: dict[str, bool] = {}
    for case_id, frozen in freeze_cases.items():
        split = frozen.get("split")
        if split not in split_counts:
            raise Gold10ManifestError(f"invalid Gold-10 split: {split!r}")
        split_counts[split] += 1
        calibration_by_case[case_id] = _require_bool(
            frozen.get("calibration_required"),
            label=f"case {case_id} calibration_required",
        )
    if split_counts != {"train": 6, "dev": 2, "eval": 2}:
        raise Gold10ManifestError(f"Gold-10 split must remain 6/2/2; got {split_counts}")
    if not any(calibration_by_case.values()):
        raise Gold10ManifestError("Gold-10 must retain at least one calibration task")

    truth_policy = _require_exact_string(
        freeze.get("truth_policy"),
        label="Gold-10 truth_policy",
        expected=EXPECTED_TRUTH_POLICY,
    )
    contamination_policy = _require_exact_string(
        freeze.get("contamination_policy"),
        label="Gold-10 contamination_policy",
        expected=EXPECTED_CONTAMINATION_POLICY,
    )
    _require_exact_string(
        freeze.get("report_usage_policy"),
        label="Gold-10 report_usage_policy",
        expected=EXPECTED_REPORT_USAGE_POLICY,
    )
    date_only_release_policy = _require_exact_string(
        index.get("date_only_availability_policy"),
        label="Gold-10 date_only_availability_policy",
        expected=EXPECTED_DATE_ONLY_RELEASE_POLICY,
    )

    source = _find_source(source_catalog, source_id)
    report_policy = _require_object(
        reports.get("policy"), label="Gold-10 report registry policy"
    )
    source_policy = _validated_source_policy(
        source,
        report_policy,
        source_id=source_id,
    )
    _validate_task_use_source_policy(task_use_authority, source_policy)

    task_owner_root = _require_owner_root(
        freeze.get("task_owner_root"),
        label="Gold-10 task_owner_root",
        expected=EXPECTED_TASK_OWNER_ROOT,
    )
    verifier_owner_root = _require_owner_root(
        freeze.get("verifier_owner_root"),
        label="Gold-10 verifier_owner_root",
        expected=EXPECTED_VERIFIER_OWNER_ROOT,
    )

    case_rows: list[dict[str, Any]] = []
    for case_id in sorted(expected_cases):
        frozen = freeze_cases[case_id]
        canonical = index_cases[case_id]
        coverage_row = coverage_cases[case_id]
        report = report_cases[case_id]

        pilot_dir = _require_safe_component(
            coverage_row.get("pilot_dir"),
            label=f"case {case_id} pilot_dir",
        )
        if report.get("pilot_dir") != pilot_dir:
            raise Gold10ManifestError(
                f"case {case_id} report/pilot directory mismatch"
            )
        if report.get("verification_status") != "verified":
            raise Gold10ManifestError(f"case {case_id} report bytes are not verified")

        artifact_id = _require_trimmed_string(
            report.get("artifact_id"),
            label=f"case {case_id} report artifact_id",
        )
        canonical_source_url = _require_trimmed_string(
            report.get("canonical_source_url", report.get("source_url")),
            label=f"case {case_id} report canonical source URL",
        )
        acquisition_url = _require_trimmed_string(
            report.get("acquisition_url", report.get("resolved_url")),
            label=f"case {case_id} report acquisition URL",
        )
        byte_count = _require_positive_int(
            report.get("byte_count"), label=f"case {case_id} report byte_count"
        )
        report_sha256 = _require_sha256(
            report.get("sha256"), label=f"case {case_id} report sha256"
        )
        receipt_sha256 = _require_sha256(
            report.get("receipt_sha256"),
            label=f"case {case_id} report receipt_sha256",
        )
        catalog_sha256 = _require_sha256(
            report.get("effective_catalog_sha256", report.get("catalog_sha256")),
            label=f"case {case_id} report catalog_sha256",
        )
        validated_task_use = _validated_task_use_record(
            authority_cases[case_id],
            case_id=case_id,
            artifact_id=artifact_id,
            report_sha256=report_sha256,
            receipt_sha256=receipt_sha256,
            catalog_sha256=catalog_sha256,
            canonical_url=canonical_source_url,
            acquisition_url=acquisition_url,
        )

        pilot_root = pilots_root / pilot_dir
        pilot_manifest, pilot_manifest_sha = _read_json(pilot_root / "manifest.json")
        review_record, review_record_sha = _read_json(
            pilot_root / "review_record.json"
        )
        expected_source_case_id = f"CSB-{case_id}"

        review_id = _require_trimmed_string(
            review_record.get("review_id"),
            label=f"case {case_id} pilot review_id",
        )
        if review_record.get("source_id") != source_id:
            raise Gold10ManifestError(f"case {case_id} pilot review source mismatch")
        if review_record.get("case_id") != expected_source_case_id:
            raise Gold10ManifestError(f"case {case_id} pilot review case mismatch")
        _require_exact_string(
            review_record.get("status"),
            label=f"case {case_id} pilot review status",
            expected=EXPECTED_PILOT_REVIEW_STATUS,
        )
        reviewed_aliases = _reviewed_case_aliases(
            review_record,
            case_id=case_id,
            expected=expected_source_case_id,
        )
        _require_exact_reviewed_case_ids(
            pilot_manifest.get("source_case_ids"),
            label=f"case {case_id} pilot source_case_ids",
            expected=expected_source_case_id,
            reviewed_aliases=reviewed_aliases,
        )
        if pilot_manifest.get("ground_truth_claims") != []:
            raise Gold10ManifestError(
                f"case {case_id} must explicitly contain zero private ground-truth claims"
            )

        fragments = _require_list(
            pilot_manifest.get("fragments"), label=f"{case_id} fragments"
        )
        if not fragments:
            raise Gold10ManifestError(f"case {case_id} must retain reviewed fragments")

        simulation_start_raw = pilot_manifest.get("simulation_start")
        simulation_as_of_raw = pilot_manifest.get("simulation_as_of")
        simulation_start = _parse_timestamp(
            simulation_start_raw, label=f"{case_id} simulation_start"
        )
        simulation_as_of = _parse_timestamp(
            simulation_as_of_raw, label=f"{case_id} simulation_as_of"
        )
        if simulation_start > simulation_as_of:
            raise Gold10ManifestError(
                f"case {case_id} simulation_start must not be later than simulation_as_of"
            )

        declared_modalities: set[str] = set()
        available_modalities: set[str] = set()
        fragment_ids: set[str] = set()
        for fragment in fragments:
            fragment_id = _require_trimmed_string(
                fragment.get("fragment_id"),
                label=f"case {case_id} fragment_id",
            )
            if fragment_id in fragment_ids:
                raise Gold10ManifestError(
                    f"case {case_id} has duplicate fragment_id {fragment_id!r}"
                )
            fragment_ids.add(fragment_id)
            modality, is_public, timeless, available_from_raw = _validated_fragment(
                fragment,
                case_id=case_id,
                expected_source_case_id=expected_source_case_id,
                source_id=source_id,
                review_id=review_id,
                reviewed_aliases=reviewed_aliases,
            )
            declared_modalities.add(modality)
            if not is_public:
                continue
            if timeless:
                available_modalities.add(modality)
                continue
            available_from = _parse_timestamp(
                available_from_raw,
                label=f"case {case_id} fragment {fragment_id} available_from",
            )
            if available_from <= simulation_as_of:
                available_modalities.add(modality)

        review_status = _require_trimmed_string(
            report.get("artifact_review_status"),
            label=f"case {case_id} report artifact review status",
        )
        report_task_eligible = True

        slug = _require_safe_slug(
            canonical.get("slug"), label=f"case {case_id} canonical slug"
        )
        capability_targets = _require_capability_targets(
            canonical.get("capability_tags"),
            label=f"case {case_id} capability targets",
        )

        case_rows.append(
            {
                "case_id": case_id,
                "slug": slug,
                "title": canonical.get("title"),
                "pilot_dir": pilot_dir,
                "pilot_manifest_sha256": pilot_manifest_sha,
                "pilot_review_sha256": review_record_sha,
                "pilot_review_id": review_id,
                "report": {
                    "artifact_id": artifact_id,
                    "canonical_source_url": canonical_source_url,
                    "acquisition_url": acquisition_url,
                    "byte_count": byte_count,
                    "sha256": report_sha256,
                    "receipt_sha256": receipt_sha256,
                    "catalog_sha256": catalog_sha256,
                    "verification_status": "verified",
                    "artifact_review_status": review_status,
                    "eligible_for_task_evidence": report_task_eligible,
                    "task_use_authority": validated_task_use,
                    "authority_note": (
                        "Eligibility derives only from the exact content-bound Gold-10 "
                        "task-use authority; artifact_review_status remains non-authoritative."
                    ),
                },
                "rights": source_policy,
                "truth_regime": EXPECTED_TRUTH_REGIME,
                "controlled_private_truth_available": False,
                "calibration_required": calibration_by_case[case_id],
                "public_temporal_cut": {
                    "simulation_start": simulation_start_raw,
                    "simulation_as_of": simulation_as_of_raw,
                    "date_only_release_policy": date_only_release_policy,
                },
                "declared_modalities": sorted(declared_modalities),
                "available_modalities_at_cut": sorted(available_modalities),
                "capability_targets": capability_targets,
                "split": frozen["split"],
                "contamination_risk": EXPECTED_CONTAMINATION_RISK,
                "task_owner_path": f"{task_owner_root}/{slug}.py",
                "verifier_owner_path": f"{verifier_owner_root}/{slug}.py",
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "manifest_id": freeze["manifest_id"],
        "corpus_id": index["corpus_id"],
        "source_id": source_id,
        "truth_policy": truth_policy,
        "contamination_policy": contamination_policy,
        "cases": case_rows,
        "split_counts": split_counts,
        "controlled_private_truth_available": False,
        "selection_inputs": {
            "freeze_sha256": freeze_sha,
            "canonical_index_sha256": index_sha,
            "pilot_coverage_sha256": coverage_sha,
            "report_acquisition_sha256": reports_sha,
            "source_catalog_sha256": source_catalog_sha,
            "source_policy_sha256": _stable_hash(source_policy),
            "task_use_authority_sha256": task_use_authority_sha,
        },
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    return manifest


def write_gold10_manifest(
    output_path: Path,
    root: Path | None = None,
) -> dict[str, Any]:
    manifest = build_gold10_manifest(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
