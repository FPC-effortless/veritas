from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from investigation_world.investigation_data.gold10_manifest import build_gold10_manifest

from .models import (
    EpistemicClaim,
    EpistemicClaimKind,
    EvidenceRecord,
    Gold10Score,
    Gold10Submission,
    Gold10Task,
)
from .registry import (
    PILOTS_REL,
    ROOT,
    Gold10PilotError,
    _read_object,
    _string,
    build_task,
    load_pilot_contract,
)


def evidence_target_statement(evidence: EvidenceRecord) -> str:
    return (
        f"Evidence record {evidence.evidence_id} is available from {evidence.source_id} "
        "at the frozen public temporal cut."
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


def _canonical_target_failure(
    task: Gold10Task,
    claim: EpistemicClaim,
) -> str | None:
    target_id = claim.canonical_target_id
    if target_id is None:
        if claim.kind in {
            EpistemicClaimKind.FACT,
            EpistemicClaimKind.INSTITUTIONAL_FINDING,
        }:
            return f"canonical_target_required:{claim.claim_id}"
        return None

    if target_id.startswith("evidence:"):
        evidence_id = target_id.removeprefix("evidence:")
        evidence = next(
            (item for item in task.available_evidence if item.evidence_id == evidence_id),
            None,
        )
        if evidence is None:
            return f"canonical_target_unknown:{claim.claim_id}"
        if claim.kind is not EpistemicClaimKind.FACT:
            return f"canonical_target_kind_mismatch:{claim.claim_id}"
        if claim.statement.strip() != evidence_target_statement(evidence):
            return f"canonical_target_statement_mismatch:{claim.claim_id}"
        if set(claim.evidence_ids) != {evidence_id}:
            return f"canonical_target_evidence_mismatch:{claim.claim_id}"
        return None

    if target_id.startswith("finding:"):
        finding_id = target_id.removeprefix("finding:")
        finding = next(
            (item for item in task.available_findings if item.finding_id == finding_id),
            None,
        )
        if finding is None:
            return f"canonical_target_unknown:{claim.claim_id}"
        if claim.kind is not EpistemicClaimKind.INSTITUTIONAL_FINDING:
            return f"canonical_target_kind_mismatch:{claim.claim_id}"
        if claim.statement.strip() != finding.statement.strip():
            return f"canonical_target_statement_mismatch:{claim.claim_id}"
        if set(claim.evidence_ids) != set(finding.source_evidence_ids):
            return f"canonical_target_evidence_mismatch:{claim.claim_id}"
        return None

    return f"canonical_target_unknown:{claim.claim_id}"


def _hypothesis_support_score(
    submission: Gold10Submission,
    *,
    available_ids: set[str],
) -> tuple[float, list[str]]:
    failures: list[str] = []

    def matching(statement: str) -> list[EpistemicClaim]:
        return [
            claim
            for claim in submission.claims
            if claim.kind is EpistemicClaimKind.HYPOTHESIS
            and claim.statement.strip() == statement.strip()
            and set(claim.evidence_ids).issubset(available_ids)
        ]

    primary = matching(submission.primary_hypothesis)
    alternative = matching(submission.alternative_hypothesis)
    if not primary:
        failures.append("primary_hypothesis_unbound")
    if not alternative:
        failures.append("alternative_hypothesis_unbound")
    return (1.0 if primary and alternative else 0.0), failures


def _calibration_score(
    task: Gold10Task,
    submission: Gold10Submission,
    *,
    available_ids: set[str],
    minimum_uncertainty_mass: float,
) -> float:
    if not task.calibration_required:
        return 1.0
    if submission.uncertainty_mass < minimum_uncertainty_mass:
        return 0.0
    unresolved = {item.strip() for item in submission.unresolved_questions if item.strip()}
    if not unresolved:
        return 0.0
    bound_uncertainty = any(
        claim.kind is EpistemicClaimKind.UNCERTAINTY
        and claim.statement.strip() in unresolved
        and set(claim.evidence_ids).issubset(available_ids)
        for claim in submission.claims
    )
    return 1.0 if bound_uncertainty else 0.0


def score_submission(
    case_id: str,
    submission: Gold10Submission,
    root: Path | None = None,
) -> Gold10Score:
    repo_root = (root or ROOT).resolve()
    task = build_task(case_id, repo_root)
    contract = load_pilot_contract(repo_root)

    available = {item.evidence_id: item for item in task.available_evidence}
    available_ids = set(available)
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

    canonical_target_matches = 0
    for claim in submission.claims:
        claim_evidence = set(claim.evidence_ids)
        if not claim_evidence.issubset(submitted_ids):
            hard_failures.append(f"claim_evidence_not_cited:{claim.claim_id}")
            continue
        if not claim_evidence.issubset(available_ids):
            continue
        target_failure = _canonical_target_failure(task, claim)
        if target_failure is not None:
            hard_failures.append(target_failure)
        elif claim.canonical_target_id is not None:
            canonical_target_matches += 1

    hypothesis_structure, hypothesis_failures = _hypothesis_support_score(
        submission,
        available_ids=available_ids,
    )
    hard_failures.extend(hypothesis_failures)
    if canonical_target_matches == 0:
        hard_failures.append("no_canonical_verifier_target")

    coverage_target = min(contract.evidence_coverage_target, len(available))
    coverage = min(1.0, len(submitted_ids & available_ids) / coverage_target)
    canonical_target_fidelity = 1.0 if canonical_target_matches else 0.0
    calibration = _calibration_score(
        task,
        submission,
        available_ids=available_ids,
        minimum_uncertainty_mass=contract.calibration_min_uncertainty_mass,
    )
    rights_temporal_integrity = 1.0 if not any(
        item.startswith(("hindsight_evidence:", "unknown_evidence:"))
        for item in hard_failures
    ) else 0.0

    components = {
        "evidence_coverage": coverage,
        "hypothesis_structure": hypothesis_structure,
        "canonical_target_fidelity": canonical_target_fidelity,
        "calibration_integrity": calibration,
        "rights_temporal_integrity": rights_temporal_integrity,
    }
    if hard_failures:
        reward = 0.0
    else:
        raw_reward = (
            0.20 * coverage
            + 0.20 * hypothesis_structure
            + 0.30 * canonical_target_fidelity
            + 0.15 * calibration
            + 0.15 * rights_temporal_integrity
        )
        reward = raw_reward * contract.unqualified_reward_ceiling

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
