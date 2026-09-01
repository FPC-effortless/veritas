from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class Gold10ManifestError(ValueError):
    """Raised when the frozen Gold-10 selection cannot be reconstructed safely."""


ROOT = Path(__file__).resolve().parents[3]
CORPUS_REL = Path("docs/investigation_data/corpora/csb_gold_10")
PILOTS_REL = Path("docs/investigation_data/pilots")
SOURCE_CATALOG_REL = Path("src/investigation_world/investigation_data/source_catalog.json")
FREEZE_REL = Path("data/gold10/case_selection_v1.json")


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


def _unique_by(items: list[dict[str, Any]], key: str, *, label: str) -> dict[str, dict[str, Any]]:
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


def _find_source(catalog: dict[str, Any], source_id: str) -> dict[str, Any]:
    sources = _require_list(catalog.get("sources"), label="source catalog sources")
    matches = [item for item in sources if item.get("source_id") == source_id]
    if len(matches) != 1:
        raise Gold10ManifestError(
            f"source_id {source_id!r} must resolve exactly once; found {len(matches)}"
        )
    return matches[0]


def _report_task_eligible(review_status: str) -> bool:
    # Fail closed. A future artifact-review lane must opt in with this exact state.
    return review_status == "approved_for_task_use"


def manifest_digest(manifest: dict[str, Any]) -> str:
    """Hash a Gold-10 manifest while excluding its self-referential digest field."""

    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    return _stable_hash(payload)


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

    if freeze.get("manifest_id") != "gold10-case-selection-v1":
        raise Gold10ManifestError("unexpected Gold-10 freeze manifest_id")
    if freeze.get("corpus_id") != index.get("corpus_id") != coverage.get("corpus_id"):
        raise Gold10ManifestError("Gold-10 corpus identities disagree")
    if freeze.get("source_id") != index.get("source_id") != reports.get("source_id"):
        raise Gold10ManifestError("Gold-10 source identities disagree")

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
    report_cases = _unique_by(
        _require_list(reports.get("artifacts"), label="report artifacts"),
        "case_id",
        label="report case",
    )

    expected_cases = set(index_cases)
    if len(expected_cases) != 10 or index.get("target_cases") != 10:
        raise Gold10ManifestError("canonical Gold-10 index must contain exactly 10 cases")
    for label, candidate in (
        ("freeze", set(freeze_cases)),
        ("coverage", set(coverage_cases)),
        ("reports", set(report_cases)),
    ):
        if candidate != expected_cases:
            raise Gold10ManifestError(f"{label} case set does not equal canonical Gold-10 index")

    split_counts = {"train": 0, "dev": 0, "eval": 0}
    for frozen in freeze_cases.values():
        split = frozen.get("split")
        if split not in split_counts:
            raise Gold10ManifestError(f"invalid Gold-10 split: {split!r}")
        split_counts[split] += 1
    if split_counts != {"train": 6, "dev": 2, "eval": 2}:
        raise Gold10ManifestError(f"Gold-10 split must remain 6/2/2; got {split_counts}")
    if not any(bool(item.get("calibration_required")) for item in freeze_cases.values()):
        raise Gold10ManifestError("Gold-10 must retain at least one calibration task")

    source_id = str(index["source_id"])
    source = _find_source(source_catalog, source_id)
    rights = source.get("rights")
    if not isinstance(rights, dict):
        raise Gold10ManifestError("canonical Gold-10 source has no rights policy")
    source_policy = {
        "source_id": source_id,
        "rights": rights,
        "contains_personal_data": bool(source.get("contains_personal_data")),
        "requires_redaction_review": bool(source.get("requires_redaction_review")),
        "truth": source.get("truth"),
    }

    case_rows: list[dict[str, Any]] = []
    for case_id in sorted(expected_cases):
        frozen = freeze_cases[case_id]
        canonical = index_cases[case_id]
        coverage_row = coverage_cases[case_id]
        report = report_cases[case_id]
        pilot_dir = coverage_row.get("pilot_dir")
        if not isinstance(pilot_dir, str) or not pilot_dir:
            raise Gold10ManifestError(f"case {case_id} has no pilot_dir")
        if report.get("pilot_dir") != pilot_dir:
            raise Gold10ManifestError(f"case {case_id} report/pilot directory mismatch")
        if report.get("verification_status") != "verified":
            raise Gold10ManifestError(f"case {case_id} report bytes are not verified")

        pilot_root = pilots_root / pilot_dir
        pilot_manifest, pilot_manifest_sha = _read_json(pilot_root / "manifest.json")
        review_record, review_record_sha = _read_json(pilot_root / "review_record.json")
        expected_source_case_id = f"CSB-{case_id}"
        source_case_ids = pilot_manifest.get("source_case_ids")
        if not isinstance(source_case_ids, list) or expected_source_case_id not in source_case_ids:
            raise Gold10ManifestError(f"case {case_id} pilot lost canonical source-case identity")
        if pilot_manifest.get("ground_truth_claims") not in ([], None):
            raise Gold10ManifestError(f"case {case_id} unexpectedly contains private ground truth")
        if review_record.get("source_id") != source_id:
            raise Gold10ManifestError(f"case {case_id} pilot review source mismatch")
        if review_record.get("case_id") != expected_source_case_id:
            raise Gold10ManifestError(f"case {case_id} pilot review case mismatch")
        if review_record.get("status") != "approved_for_link_only_pilot":
            raise Gold10ManifestError(f"case {case_id} pilot is not approved for link-only use")

        fragments = _require_list(pilot_manifest.get("fragments"), label=f"{case_id} fragments")
        modalities = sorted(
            {
                str(fragment["modality"])
                for fragment in fragments
                if isinstance(fragment.get("modality"), str)
            }
        )
        review_status = report.get("artifact_review_status")
        if not isinstance(review_status, str):
            raise Gold10ManifestError(f"case {case_id} report has no artifact review status")
        report_task_eligible = _report_task_eligible(review_status)
        if freeze.get("report_usage_policy") == "exclude_until_artifact_level_review":
            if review_status != "approved_for_task_use":
                report_task_eligible = False

        task_owner_root = str(freeze["task_owner_root"])
        verifier_owner_root = str(freeze["verifier_owner_root"])
        slug = canonical.get("slug")
        if not isinstance(slug, str) or not slug:
            raise Gold10ManifestError(f"case {case_id} has no canonical slug")

        case_rows.append(
            {
                "case_id": case_id,
                "slug": slug,
                "title": canonical.get("title"),
                "pilot_dir": pilot_dir,
                "pilot_manifest_sha256": pilot_manifest_sha,
                "pilot_review_sha256": review_record_sha,
                "pilot_review_id": review_record.get("review_id"),
                "report": {
                    "artifact_id": report.get("artifact_id"),
                    "canonical_source_url": report.get("canonical_source_url", report.get("source_url")),
                    "acquisition_url": report.get("acquisition_url", report.get("resolved_url")),
                    "byte_count": report.get("byte_count"),
                    "sha256": report.get("sha256"),
                    "receipt_sha256": report.get("receipt_sha256"),
                    "catalog_sha256": report.get("effective_catalog_sha256", report.get("catalog_sha256")),
                    "verification_status": report.get("verification_status"),
                    "artifact_review_status": review_status,
                    "eligible_for_task_evidence": report_task_eligible,
                },
                "rights": source_policy,
                "truth_regime": "institutional_findings",
                "controlled_private_truth_available": False,
                "calibration_required": bool(frozen.get("calibration_required")),
                "public_temporal_cut": {
                    "simulation_start": pilot_manifest.get("simulation_start"),
                    "simulation_as_of": pilot_manifest.get("simulation_as_of"),
                    "date_only_release_policy": index.get("date_only_availability_policy"),
                },
                "modalities": modalities,
                "capability_targets": canonical.get("capability_tags", []),
                "split": frozen["split"],
                "contamination_risk": "high_public_historical_nonsealed",
                "task_owner_path": f"{task_owner_root}/{slug}.py",
                "verifier_owner_path": f"{verifier_owner_root}/{slug}.py",
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "manifest_id": freeze["manifest_id"],
        "corpus_id": index["corpus_id"],
        "source_id": source_id,
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
        },
    }
    manifest["manifest_sha256"] = manifest_digest(manifest)
    return manifest


def write_gold10_manifest(output_path: Path, root: Path | None = None) -> dict[str, Any]:
    manifest = build_gold10_manifest(root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest
