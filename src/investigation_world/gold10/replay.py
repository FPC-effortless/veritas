from __future__ import annotations

from pathlib import Path

from investigation_world.experience import (
    EpistemicSnapshot,
    ExperienceInitialConditions,
    ExperienceMaturity,
    ExperienceReference,
    HypothesisState,
    MachineExperience,
)
from investigation_world.trajectory import (
    EvaluationRecord,
    ProvenanceRecord,
    StateDigest,
    TaskIdentity,
    TerminationRecord,
    TrajectoryEvent,
    TrajectoryReference,
    TrajectoryV2,
    VerifierIdentity,
    VisibilityClass,
    WorldIdentity,
    canonical_hash,
)

from .models import (
    EpistemicClaim,
    EpistemicClaimKind,
    Gold10Submission,
)
from .registry import ROOT, build_task, build_taskset, load_pilot_contract
from .verifier import evidence_target_statement, score_submission


def reference_submission(case_id: str, root: Path | None = None) -> Gold10Submission:
    repo_root = (root or ROOT).resolve()
    task = build_task(case_id, repo_root)
    contract = load_pilot_contract(repo_root)

    primary_hypothesis = (
        "The evidence available at the frozen cut supports a provisional causal account "
        "that should remain explicitly evidence-bounded."
    )
    alternative_hypothesis = (
        "A materially different causal account remains plausible because the frozen "
        "record is incomplete and institutional findings are not private truth."
    )
    unresolved_question = (
        "What material evidence remains unavailable at the frozen temporal cut?"
    )

    selected_ids: list[str] = []
    canonical_claim: EpistemicClaim
    if task.available_findings:
        finding = task.available_findings[0]
        selected_ids.extend(finding.source_evidence_ids)
        canonical_claim = EpistemicClaim(
            claim_id=f"{case_id}-canonical-finding",
            statement=finding.statement,
            kind=EpistemicClaimKind.INSTITUTIONAL_FINDING,
            evidence_ids=finding.source_evidence_ids,
            canonical_target_id=f"finding:{finding.finding_id}",
        )
    else:
        evidence = task.available_evidence[0]
        selected_ids.append(evidence.evidence_id)
        canonical_claim = EpistemicClaim(
            claim_id=f"{case_id}-canonical-evidence",
            statement=evidence_target_statement(evidence),
            kind=EpistemicClaimKind.FACT,
            evidence_ids=(evidence.evidence_id,),
            canonical_target_id=f"evidence:{evidence.evidence_id}",
        )

    for evidence in task.available_evidence:
        if len(selected_ids) >= contract.evidence_coverage_target:
            break
        if evidence.evidence_id not in selected_ids:
            selected_ids.append(evidence.evidence_id)
    cited_ids = tuple(selected_ids)
    claims: list[EpistemicClaim] = [
        canonical_claim,
        EpistemicClaim(
            claim_id=f"{case_id}-primary-hypothesis",
            statement=primary_hypothesis,
            kind=EpistemicClaimKind.HYPOTHESIS,
            evidence_ids=cited_ids,
        ),
        EpistemicClaim(
            claim_id=f"{case_id}-alternative-hypothesis",
            statement=alternative_hypothesis,
            kind=EpistemicClaimKind.HYPOTHESIS,
            evidence_ids=cited_ids,
        ),
    ]
    if task.calibration_required:
        claims.append(
            EpistemicClaim(
                claim_id=f"{case_id}-uncertainty",
                statement=unresolved_question,
                kind=EpistemicClaimKind.UNCERTAINTY,
                evidence_ids=cited_ids,
            )
        )

    return Gold10Submission(
        primary_hypothesis=primary_hypothesis,
        alternative_hypothesis=alternative_hypothesis,
        primary_confidence=0.55,
        alternative_confidence=0.25,
        evidence_ids=cited_ids,
        claims=tuple(claims),
        unresolved_questions=(unresolved_question,),
    )


def traceable_experience(
    case_id: str,
    submission: Gold10Submission,
    root: Path | None = None,
) -> MachineExperience:
    repo_root = (root or ROOT).resolve()
    task = build_task(case_id, repo_root)
    contract = load_pilot_contract(repo_root)
    score = score_submission(case_id, submission, repo_root)
    verifier = VerifierIdentity(
        verifier_id=contract.verifier_id,
        version=contract.verifier_version,
    )

    references = tuple(
        TrajectoryReference(
            reference_id=item.evidence_id,
            reference_type="gold10_public_evidence",
            uri=item.locator,
            visibility=VisibilityClass.PUBLIC,
            public_metadata={
                "content_ref": item.content_ref,
                "modality": item.modality,
                "epistemic_role": item.epistemic_role,
                "available_from": item.available_from,
            },
        )
        for item in task.available_evidence
        if item.evidence_id in set(submission.evidence_ids)
    )
    task_digest = canonical_hash(task.task.model_dump(mode="json"))
    submission_digest = canonical_hash(submission.model_dump(mode="json"))
    events = (
        TrajectoryEvent(
            step=0,
            event_type="gold10.task.reset",
            payload={
                "task_id": task.task.task_id,
                "objective": task.task.objective,
                "public_temporal_cut": task.public_temporal_cut,
            },
            visibility=VisibilityClass.PUBLIC,
        ),
        TrajectoryEvent(
            step=1,
            event_type="gold10.evidence.inspect",
            payload={"evidence_ids": list(submission.evidence_ids)},
            evidence_references=references,
            visibility=VisibilityClass.PUBLIC,
        ),
        TrajectoryEvent(
            step=2,
            event_type="gold10.findings.submit",
            payload=submission.model_dump(mode="json"),
            evidence_references=references,
            visibility=VisibilityClass.PUBLIC,
        ),
    )
    trajectory = TrajectoryV2(
        world=WorldIdentity(
            environment_id=contract.world_id,
            environment_version=contract.world_version,
            world_id=task.task.world_id,
            world_version=task.manifest_sha256,
        ),
        task=TaskIdentity(
            task_id=task.task.task_id,
            taskset_version=contract.taskset_version,
            split=task.split,
        ),
        verifier=verifier,
        initial_state=StateDigest(digest=task_digest),
        events=events,
        evidence_references=references,
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores=score.component_scores,
            reward=score.reward,
        ),
        termination=TerminationRecord(
            reason="submission_scored",
            terminated=True,
            truncated=False,
        ),
        final_state=StateDigest(digest=submission_digest),
        capability_tags=task.capability_targets,
        provenance=(
            ProvenanceRecord(
                source_kind="gold10_case_manifest",
                source_id=case_id,
                source_version=contract.taskset_version,
                source_digest=task.manifest_sha256,
                visibility=VisibilityClass.PUBLIC,
            ),
        ),
        visibility=VisibilityClass.PUBLIC,
        public_metadata={
            "case_id": case_id,
            "split": task.split,
            "calibration_required": task.calibration_required,
            "reward_ceiling": contract.unqualified_reward_ceiling,
            "verifier_qualification": "unqualified_pilot_candidate",
        },
    )
    return MachineExperience(
        trajectory=trajectory,
        maturity=ExperienceMaturity.E0_TRACEABLE,
        initial_conditions=ExperienceInitialConditions(
            public_state_reference=ExperienceReference(
                reference_id=task.task.task_id,
                reference_type="gold10_task",
                digest=task_digest,
                uri=f"gold10://task/{case_id}",
                visibility=VisibilityClass.PUBLIC,
            ),
            role="independent industrial accident investigator",
            objectives=(task.task.objective,),
            constraints={
                "no_hindsight": True,
                "institutional_findings_are_not_private_truth": True,
            },
        ),
        epistemic_snapshots=(
            EpistemicSnapshot(
                snapshot_id=f"{case_id}-submission",
                step=2,
                hypotheses=(
                    HypothesisState(
                        hypothesis_id=f"{case_id}-primary",
                        statement=submission.primary_hypothesis,
                        confidence=submission.primary_confidence,
                        evidence_for=submission.evidence_ids,
                        unresolved_questions=submission.unresolved_questions,
                    ),
                    HypothesisState(
                        hypothesis_id=f"{case_id}-alternative",
                        statement=submission.alternative_hypothesis,
                        confidence=submission.alternative_confidence,
                        evidence_for=submission.evidence_ids,
                        unresolved_questions=submission.unresolved_questions,
                    ),
                ),
                unresolved_questions=submission.unresolved_questions,
                visibility=VisibilityClass.PUBLIC,
            ),
        ),
        derivation_references=(
            ExperienceReference(
                reference_id=f"gold10-manifest:{task.manifest_sha256}",
                reference_type="gold10_case_selection_manifest",
                digest=task.manifest_sha256,
                visibility=VisibilityClass.PUBLIC,
            ),
        ),
        visibility=VisibilityClass.PUBLIC,
        public_metadata={
            "pilot_id": contract.pilot_id,
            "case_id": case_id,
            "split": task.split,
            "evidence_boundary": "pilot_candidate_only",
            "verifier_qualification": "unqualified",
        },
    )


def build_reference_experiences(
    root: Path | None = None,
) -> tuple[MachineExperience, ...]:
    repo_root = (root or ROOT).resolve()
    tasks = build_taskset(repo_root)
    return tuple(
        traceable_experience(
            task.case_id,
            reference_submission(task.case_id, repo_root),
            repo_root,
        )
        for task in tasks
    )
