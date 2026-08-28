from __future__ import annotations

import pytest
from pydantic import ValidationError

from investigation_world.experience import (
    BeliefRevision,
    CapabilityGap,
    EpistemicSnapshot,
    ExperienceDiagnostics,
    ExperienceMaturity,
    ExperienceReadiness,
    ExperienceReference,
    ExperienceSequence,
    ExperienceSpan,
    FailureFamily,
    FailureMechanism,
    HypothesisState,
    MachineExperience,
    ReadinessAssessment,
    ReadinessStatus,
    machine_experience_from_trajectory,
)
from investigation_world.trajectory import (
    EvaluationRecord,
    StateDigest,
    TrajectoryEvent,
    TrajectoryReference,
    TrajectoryV2,
    VerifierIdentity,
    VisibilityClass,
    WorldIdentity,
    TaskIdentity,
)


def _trajectory() -> TrajectoryV2:
    verifier = VerifierIdentity(verifier_id="verifier:test", version="1")
    return TrajectoryV2(
        world=WorldIdentity(
            environment_id="environment:test",
            environment_version="1",
            world_id="world:test",
            world_version="1",
        ),
        task=TaskIdentity(task_id="task:test", taskset_version="1", split="test"),
        verifier=verifier,
        initial_state=StateDigest(digest="initial-state"),
        events=(
            TrajectoryEvent(
                step=0,
                event_type="observation",
                payload={"public": "visible"},
                private_payload={"sealed_secret": "never-public"},
                observation_references=(
                    TrajectoryReference(
                        reference_id="sealed-observation",
                        reference_type="observation",
                        visibility=VisibilityClass.SEALED,
                        private_metadata={"secret": "never-public"},
                    ),
                ),
            ),
            TrajectoryEvent(
                step=1,
                event_type="action",
                payload={"action": "inspect"},
            ),
        ),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={"outcome": 1.0},
            reward=1.0,
        ),
    )


def _pass_assessment(reference_id: str) -> ReadinessAssessment:
    return ReadinessAssessment(
        status=ReadinessStatus.PASS,
        evidence_references=(
            ExperienceReference(
                reference_id=reference_id,
                reference_type="qualification_evidence",
            ),
        ),
    )


def test_traceable_experience_wraps_trajectory_without_new_execution_semantics() -> None:
    trajectory = _trajectory()
    experience = machine_experience_from_trajectory(trajectory)

    assert experience.trajectory is trajectory
    assert experience.maturity is ExperienceMaturity.E0_TRACEABLE
    assert experience.experience_id.startswith("EXP-")


def test_pass_readiness_requires_visible_evidence() -> None:
    with pytest.raises(ValidationError, match="PASS readiness requires"):
        ReadinessAssessment(status=ReadinessStatus.PASS)

    with pytest.raises(ValidationError, match="more private than the assessment"):
        ReadinessAssessment(
            status=ReadinessStatus.PASS,
            evidence_references=(
                ExperienceReference(
                    reference_id="private-evidence",
                    reference_type="qualification_evidence",
                    visibility=VisibilityClass.INTERNAL,
                ),
            ),
            visibility=VisibilityClass.PUBLIC,
        )


def test_experience_maturity_fails_closed_on_unknown_readiness() -> None:
    with pytest.raises(ValidationError, match="requires PASS readiness"):
        MachineExperience(
            trajectory=_trajectory(),
            maturity=ExperienceMaturity.E1_REVERIFIABLE,
        )

    experience = MachineExperience(
        trajectory=_trajectory(),
        maturity=ExperienceMaturity.E2_DIAGNOSTIC,
        readiness=ExperienceReadiness(
            reverification_ready=_pass_assessment("reverification-evidence"),
            failure_analysis_ready=_pass_assessment("diagnostic-evidence"),
        ),
    )
    assert experience.maturity is ExperienceMaturity.E2_DIAGNOSTIC


def test_experience_identity_is_stable_across_diagnostic_annotations() -> None:
    trajectory = _trajectory()
    first = MachineExperience(trajectory=trajectory)
    second = MachineExperience(
        trajectory=trajectory,
        diagnostics=ExperienceDiagnostics(
            failure_mechanisms=(FailureMechanism.TEMPORAL_REASONING,)
        ),
    )

    assert first.experience_id == second.experience_id


def test_public_projection_never_widens_trajectory_visibility() -> None:
    experience = MachineExperience(
        trajectory=_trajectory(),
        derivation_references=(
            ExperienceReference(
                reference_id="sealed-derivation",
                reference_type="counterfactual",
                visibility=VisibilityClass.SEALED,
                private_metadata={"secret": "never-public"},
            ),
        ),
    )

    payload = experience.public_payload()
    serialized = repr(payload)

    assert "never-public" not in serialized
    assert "sealed-observation" not in serialized
    assert "sealed-derivation" not in serialized
    assert "private_payload" not in serialized
    assert payload["trajectory"]["events"][0]["payload"] == {"public": "visible"}


def test_structured_epistemic_state_and_span_hierarchy_are_bounded_by_trace() -> None:
    experience = MachineExperience(
        trajectory=_trajectory(),
        epistemic_snapshots=(
            EpistemicSnapshot(
                snapshot_id="epistemic:0",
                step=0,
                hypotheses=(
                    HypothesisState(
                        hypothesis_id="hypothesis:a",
                        statement="Mechanism A best explains the current evidence.",
                        confidence=0.4,
                        evidence_for=("evidence:1",),
                        unresolved_questions=("question:1",),
                    ),
                ),
            ),
        ),
        belief_revisions=(
            BeliefRevision(
                revision_id="revision:1",
                step=1,
                hypothesis_id="hypothesis:a",
                prior_confidence=0.4,
                revised_confidence=0.7,
                evidence_reference_ids=("evidence:2",),
            ),
        ),
        spans=(
            ExperienceSpan(
                span_id="span:root",
                span_type="investigation",
                start_step=0,
                end_step=1,
            ),
            ExperienceSpan(
                span_id="span:inspect",
                span_type="evidence_review",
                start_step=0,
                end_step=0,
                parent_span_id="span:root",
            ),
        ),
    )

    assert experience.epistemic_snapshots[0].hypotheses[0].confidence == 0.4

    with pytest.raises(ValidationError, match="contained by its parent"):
        MachineExperience(
            trajectory=_trajectory(),
            spans=(
                ExperienceSpan(
                    span_id="span:parent",
                    span_type="parent",
                    start_step=1,
                    end_step=1,
                ),
                ExperienceSpan(
                    span_id="span:child",
                    span_type="child",
                    start_step=0,
                    end_step=1,
                    parent_span_id="span:parent",
                ),
            ),
        )


def test_sequence_failure_family_and_capability_gap_are_content_derived() -> None:
    trajectory = _trajectory()
    experience = MachineExperience(trajectory=trajectory)
    sequence = ExperienceSequence(
        experience_ids=(experience.experience_id,),
        transfer_test_experience_ids=("EXP-transfer",),
    )
    family = FailureFamily(
        member_experience_ids=(experience.experience_id,),
        affected_capability="temporal_reasoning",
        severity=0.8,
        mechanisms=(FailureMechanism.TEMPORAL_REASONING,),
    )
    gap = CapabilityGap(
        capability="temporal_reasoning",
        supporting_failure_family_ids=(family.family_id,),
        frequency=1,
        severity=0.8,
        environment_ids=("environment:test",),
    )

    assert sequence.sequence_id.startswith("EXPSEQ-")
    assert family.family_id.startswith("FAILFAM-")
    assert gap.gap_id.startswith("CAPGAP-")
