from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from investigation_world.investigation_data.gold10_manifest import build_gold10_manifest

from .models import EpistemicClaimKind, Gold10Score, Gold10Submission
from .registry import (
    PILOTS_REL,
    ROOT,
    Gold10PilotError,
    _read_object,
    _string,
    build_task,
    load_pilot_contract,
)


def _case_row(case_id: str, root: Path) -> dict[str, Any]:
    manifest = build_gold10_manifest(root)
    for row in manifest.get("cases", []):
        if isinstance(row, dict) and row.get("case_id") == case_id:
            return row
    raise Gold10PilotError(f"unknown frozen Gold-10 case: {case_id}")


def _all_fragment_ids(case_id: str, root: Path) -> set[str]:
    row = _case_row(case_id, root)
    pilot_dir = _string(row.get("pilot_dir"), label=f"{case_id} pilot_dir")
    pilot = _read_object(root / PILOTS_REL / pilot_dir / "manifest.json")
    fragments = pilot.get("fragments")
    if not isinstance(fragments, list):
        raise Gold10PilotError(f"case {case_id} fragments must be a list")
    output: set[str] = set()
    for raw in fragments:
        if not isinstance(raw, dict):
            raise Gold10PilotError(f"case {case_id} contains a malformed fragment")
        evidence_id = _string(raw.get("fragment_id"), label=f"{case_id} fragment_id")
        if evidence_id in output:
            raise Gold10PilotError(f"case {case_id} has duplicate fragment id {evidence_id}")
        output.add(evidence_id)
    return output


def score_submission(
    case_id: str,
    submission: Gold10Submission,
    root: Path | None = None,
) -> Gold10Score:
    repo_root = (root or ROOT).resolve()
    task = build_task(case_id, repo_root)
    contract = load_pilot_contract(repo_root)

    available = {item.evidence_id: item for item in task.available_evidence}
    all_fragments = _all_fragment_ids(case_id, repo_root)
    submitted_ids = set(submission.evidence_ids)

    hard_failures: list[str] = []
    hindsight = sorted(
        evidence_id
        for evidence_id in submitted_ids
        if evidence_id in all_fragments and evidence_id not in available
    )
    unknown = sorted(submitted_ids - all_fragments)
    if hindsight:
        hard_failures.append(f"hindsight_evidence:{','.join(hindsight)}")
    if unknown:
        hard_failures.append(f"unknown_evidence:{','.join(unknown)}")

    claim_ids = [claim.claim_id for claim in submission.claims]
    if len(claim_ids) != len(set(claim_ids)):
        hard_failures.append("duplicate_claim_id")

    for claim in submission.claims:
        claim_evidence = set(claim.evidence_ids)
        if not claim_evidence.issubset(submitted_ids):
            hard_failures.append(f"claim_evidence_not_cited:{claim.claim_id}")
            continue
        if not claim_evidence.issubset(available):
            continue
        if claim.kind is EpistemicClaimKind.INSTITUTIONAL_FINDING:
            roles = {available[evidence_id].epistemic_role for evidence_id in claim_evidence}
            if "official_finding" not in roles:
                hard_failures.append(
                    f"institutional_finding_without_official_evidence:{claim.claim_id}"
                )

    coverage_target = min(contract.evidence_coverage_target, len(available))
    coverage = min(1.0, len(submitted_ids & set(available)) / coverage_target)
    hypothesis_structure = 1.0
    epistemic_integrity = 1.0 if submission.claims else 0.5

    calibration = 1.0
    if task.calibration_required:
        if (
            submission.uncertainty_mass < contract.calibration_min_uncertainty_mass
            or not submission.unresolved_questions
        ):
            calibration = 0.0

    rights_temporal_integrity = 1.0 if not hard_failures else 0.0
    components = {
        "evidence_coverage": coverage,
        "hypothesis_structure": hypothesis_structure,
        "epistemic_integrity": epistemic_integrity,
        "calibration_integrity": calibration,
        "rights_temporal_integrity": rights_temporal_integrity,
    }
    if hard_failures:
        reward = 0.0
    else:
        reward = (
            0.25 * coverage
            + 0.20 * hypothesis_structure
            + 0.25 * epistemic_integrity
            + 0.15 * calibration
            + 0.15 * rights_temporal_integrity
        )
    return Gold10Score(
        reward=round(reward, 6),
        component_scores={key: round(value, 6) for key, value in components.items()},
        hard_failures=tuple(sorted(set(hard_failures))),
    )


def score_submission_json(
    case_id: str,
    payload: str,
    root: Path | None = None,
) -> Gold10Score:
    raw = json.loads(payload)
    return score_submission(case_id, Gold10Submission.model_validate(raw), root)
