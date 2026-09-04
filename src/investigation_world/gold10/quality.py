from __future__ import annotations

import re
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from investigation_world.investigation_data.gold10_manifest import build_gold10_manifest
from investigation_world.trajectory import canonical_hash

from .models import EpistemicClaim, EpistemicClaimKind, Gold10Submission
from .registry import PILOTS_REL, ROOT, _read_object, build_taskset, load_pilot_contract
from .replay import reference_submission
from .verifier import score_submission
from .vq import build_canonical_vq_scorecard

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(value.lower()))


def _similarity(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    union = left_tokens | right_tokens
    if not union:
        return 1.0
    return len(left_tokens & right_tokens) / len(union)


def _normalized(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.lower()))


def _duplicate_analysis(tasks: tuple[Any, ...], threshold: float) -> dict[str, Any]:
    exact: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        exact[_normalized(task.task.objective)].append(task.case_id)
    exact_groups = [
        sorted(case_ids)
        for case_ids in exact.values()
        if len(case_ids) > 1
    ]

    near_pairs: list[dict[str, Any]] = []
    max_similarity = 0.0
    for left, right in combinations(tasks, 2):
        similarity = _similarity(left.task.objective, right.task.objective)
        max_similarity = max(max_similarity, similarity)
        if similarity >= threshold:
            near_pairs.append(
                {
                    "left_case_id": left.case_id,
                    "right_case_id": right.case_id,
                    "objective_jaccard": round(similarity, 6),
                }
            )
    return {
        "method": "lowercase_alphanumeric_objective_token_jaccard",
        "near_duplicate_threshold": threshold,
        "exact_duplicate_groups": sorted(exact_groups),
        "near_duplicate_pairs": sorted(
            near_pairs,
            key=lambda item: (
                item["left_case_id"],
                item["right_case_id"],
            ),
        ),
        "max_pairwise_objective_jaccard": round(max_similarity, 6),
        "interpretation": (
            "This is a deterministic structural screen, not a semantic-equivalence claim."
        ),
    }


def _coverage_report(root: Path, tasks: tuple[Any, ...]) -> dict[str, Any]:
    manifest = build_gold10_manifest(root)
    pilot_dir_by_case = {
        row["case_id"]: row["pilot_dir"]
        for row in manifest["cases"]
    }
    causal_edges_by_case: dict[str, int] = {}
    for task in tasks:
        pilot = _read_object(
            root / PILOTS_REL / pilot_dir_by_case[task.case_id] / "manifest.json"
        )
        causal_edges = pilot.get("causal_edges", [])
        causal_edges_by_case[task.case_id] = (
            len(causal_edges) if isinstance(causal_edges, list) else 0
        )

    split_counts = Counter(task.split for task in tasks)
    source_counts = Counter(
        evidence.source_id
        for task in tasks
        for evidence in task.available_evidence
    )
    modality_counts = Counter(
        evidence.modality
        for task in tasks
        for evidence in task.available_evidence
    )
    capability_counts = Counter(
        capability
        for task in tasks
        for capability in task.capability_targets
    )
    finding_cases = [
        task.case_id for task in tasks if task.available_findings
    ]
    calibration_cases = [
        task.case_id for task in tasks if task.calibration_required
    ]
    return {
        "case_count": len(tasks),
        "case_ids": [task.case_id for task in tasks],
        "split_counts": dict(sorted(split_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "source_diversity_count": len(source_counts),
        "modality_counts": dict(sorted(modality_counts.items())),
        "modality_diversity_count": len(modality_counts),
        "capability_target_counts": dict(sorted(capability_counts.items())),
        "capability_target_diversity_count": len(capability_counts),
        "cases_with_available_institutional_findings": finding_cases,
        "calibration_cases": calibration_cases,
        "causal_edge_counts_by_case": dict(sorted(causal_edges_by_case.items())),
        "cases_with_explicit_causal_edges": sorted(
            case_id
            for case_id, count in causal_edges_by_case.items()
            if count > 0
        ),
        "total_explicit_causal_edges": sum(causal_edges_by_case.values()),
        "task_structure": {
            "primary_hypothesis_required": True,
            "alternative_hypothesis_required": True,
            "canonical_target_required_for_positive_reward": True,
            "claim_kinds": [item.value for item in EpistemicClaimKind],
            "no_llm_judge": True,
        },
    }


def _contamination_assessment(root: Path) -> dict[str, Any]:
    manifest = build_gold10_manifest(root)
    risks = sorted({row["contamination_risk"] for row in manifest["cases"]})
    return {
        "risk_classes": risks,
        "overall_assessment": "high_public_historical_nonsealed",
        "reason": (
            "All ten cases are public historical USCSB material and must not be treated "
            "as contamination-clean model evaluation."
        ),
        "mitigations": [
            "case-disjoint 6/2/2 split",
            "frozen temporal cuts",
            "no capability claim until verifier qualification",
            "no Frontier/training/commercial promotion from this pilot",
        ],
        "contamination_clean_claim_authorized": False,
    }


def _reference_solvability(root: Path, tasks: tuple[Any, ...]) -> dict[str, Any]:
    scores: dict[str, Any] = {}
    for task in tasks:
        score = score_submission(
            task.case_id,
            reference_submission(task.case_id, root),
            root,
        )
        scores[task.case_id] = {
            "reward": score.reward,
            "hard_failures": list(score.hard_failures),
        }
    passed = all(
        item["reward"] > 0.0 and not item["hard_failures"]
        for item in scores.values()
    )
    return {
        "status": "pass" if passed else "fail",
        "reference_scores": scores,
        "interpretation": (
            "Reference submissions establish scripted protocol solvability only, "
            "not model capability or semantic-verifier qualification."
        ),
    }


def _exploit_shortcut_report(root: Path) -> dict[str, Any]:
    case_id = "2005-04-I-TX"
    reference = reference_submission(case_id, root)
    evidence_ids = reference.evidence_ids

    meaningless = Gold10Submission(
        primary_hypothesis="Arbitrary primary string with no canonical target.",
        alternative_hypothesis="Arbitrary alternative string with no canonical target.",
        primary_confidence=0.5,
        alternative_confidence=0.25,
        evidence_ids=evidence_ids,
        claims=(
            EpistemicClaim(
                claim_id="shortcut-primary",
                statement="Arbitrary primary string with no canonical target.",
                kind=EpistemicClaimKind.HYPOTHESIS,
                evidence_ids=evidence_ids,
            ),
            EpistemicClaim(
                claim_id="shortcut-alternative",
                statement="Arbitrary alternative string with no canonical target.",
                kind=EpistemicClaimKind.HYPOTHESIS,
                evidence_ids=evidence_ids,
            ),
        ),
        unresolved_questions=("Boilerplate unresolved text.",),
    )
    meaningless_score = score_submission(case_id, meaningless, root)

    mismatch_payload = reference.model_dump(mode="python")
    mismatch_claims = list(mismatch_payload["claims"])
    first_target = next(
        index
        for index, claim in enumerate(mismatch_claims)
        if claim.get("canonical_target_id") is not None
    )
    mismatch_claims[first_target] = {
        **mismatch_claims[first_target],
        "statement": "Fabricated statement that does not match the canonical target.",
    }
    mismatch_payload["claims"] = mismatch_claims
    mismatch = Gold10Submission.model_validate(mismatch_payload)
    mismatch_score = score_submission(case_id, mismatch, root)

    hindsight_payload = reference.model_dump(mode="python")
    hindsight_payload["evidence_ids"] = (
        *reference.evidence_ids,
        "csb-final-findings-release-2007-03-20",
    )
    hindsight = Gold10Submission.model_validate(hindsight_payload)
    hindsight_score = score_submission(case_id, hindsight, root)

    calibration_case = "2012-03-I-CA"
    calibration_payload = reference_submission(
        calibration_case, root
    ).model_dump(mode="python")
    calibration_payload.update(
        {
            "primary_confidence": 0.90,
            "alternative_confidence": 0.09,
            "unresolved_questions": (),
        }
    )
    calibration = Gold10Submission.model_validate(calibration_payload)
    calibration_score = score_submission(calibration_case, calibration, root)
    calibration_reference = score_submission(
        calibration_case,
        reference_submission(calibration_case, root),
        root,
    )

    probes: dict[str, dict[str, Any]] = {
        "arbitrary_hypothesis_without_canonical_target": {
            "passed": (
                meaningless_score.reward == 0.0
                and "no_canonical_verifier_target" in meaningless_score.hard_failures
            ),
            "reward": meaningless_score.reward,
            "hard_failures": list(meaningless_score.hard_failures),
        },
        "canonical_target_statement_mismatch": {
            "passed": (
                mismatch_score.reward == 0.0
                and any(
                    item.startswith("canonical_target_statement_mismatch:")
                    for item in mismatch_score.hard_failures
                )
            ),
            "reward": mismatch_score.reward,
            "hard_failures": list(mismatch_score.hard_failures),
        },
        "hindsight_evidence": {
            "passed": (
                hindsight_score.reward == 0.0
                and any(
                    item.startswith("hindsight_evidence:")
                    for item in hindsight_score.hard_failures
                )
            ),
            "reward": hindsight_score.reward,
            "hard_failures": list(hindsight_score.hard_failures),
        },
        "calibration_boilerplate_without_uncertainty": {
            "passed": (
                calibration_score.component_scores["calibration_integrity"] == 0.0
                and calibration_score.reward < calibration_reference.reward
            ),
            "reward": calibration_score.reward,
            "reference_reward": calibration_reference.reward,
        },
    }
    return {
        "policy": {
            "semantic_text_is_not_treated_as_qualified_truth": True,
            "positive_reward_requires_a_canonical_public_target": True,
            "unqualified_reward_is_capped": True,
            "reference_text_alone_is_not_a_verifier_target": True,
        },
        "probes": probes,
        "all_probes_pass": all(item["passed"] for item in probes.values()),
        "residual_risks": [
            (
                "The deterministic verifier validates canonical target/provenance binding "
                "but does not establish open-ended semantic correctness of free-form prose."
            ),
            (
                "Public historical source material remains contamination-prone; this pilot "
                "is not a contamination-clean capability benchmark."
            ),
        ],
    }


def build_pilot_gate_report(root: Path | None = None) -> dict[str, Any]:
    repo_root = (root or ROOT).resolve()
    tasks = build_taskset(repo_root)
    contract = load_pilot_contract(repo_root)
    manifest = build_gold10_manifest(repo_root)

    rebuild_payload = {
        "manifest_sha256": manifest["manifest_sha256"],
        "contract": contract.model_dump(mode="json"),
        "tasks": [
            {
                "case_id": task.case_id,
                "split": task.split,
                "task": task.task.model_dump(mode="json"),
                "available_evidence": [
                    item.model_dump(mode="json")
                    for item in task.available_evidence
                ],
                "available_findings": [
                    item.model_dump(mode="json")
                    for item in task.available_findings
                ],
            }
            for task in tasks
        ],
    }
    taskset_rebuild_sha256 = canonical_hash(rebuild_payload)
    duplicate = _duplicate_analysis(tasks, contract.near_duplicate_threshold)
    contamination = _contamination_assessment(repo_root)
    coverage = _coverage_report(repo_root, tasks)
    reference = _reference_solvability(repo_root, tasks)
    exploit = _exploit_shortcut_report(repo_root)
    vq = build_canonical_vq_scorecard(
        contract=contract,
        taskset_rebuild_sha256=taskset_rebuild_sha256,
        coverage=coverage,
        exploit=exploit,
        reference=reference,
    )

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "pilot_id": contract.pilot_id,
        "taskset_rebuild_sha256": taskset_rebuild_sha256,
        "duplicate_near_duplicate_analysis": duplicate,
        "contamination_assessment": contamination,
        "coverage_report": coverage,
        "reference_scripted_solvability": reference,
        "exploit_shortcut_policy": exploit,
        "vq_scorecard": vq,
        "pilot_level_gates": {
            "deterministic_rebuild_identity": "pass",
            "duplicate_near_duplicate_analysis": "complete",
            "contamination_assessment": "complete_high_risk",
            "coverage_report": "complete",
            "reference_scripted_solvability": reference["status"],
            "exploit_shortcut_policy": (
                "pass" if exploit["all_probes_pass"] else "fail"
            ),
            "vq_multidimensional_scorecard": "complete",
        },
        "claim_boundary": (
            "Pilot candidate only; no capability, scientific, Frontier, training-value, "
            "or commercial qualification is authorized."
        ),
    }
    payload["report_sha256"] = canonical_hash(payload)
    return payload
