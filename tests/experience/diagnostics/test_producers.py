import json

import pytest

from investigation_world.experience import FailureMechanism, MachineExperience
from investigation_world.experience.diagnostics import (
    buyer_safe_diagnostics,
    diagnose_experience,
    failure_family_candidates,
)
from investigation_world.gold10 import reference_submission, traceable_experience
from investigation_world.trajectory import FailureCategory, VisibilityClass


def gold(case="2005-04-I-TX", *, missing_evidence=False):
    submission = reference_submission(case)
    if missing_evidence:
        submission = submission.model_copy(update={"evidence_ids": ()})
    return traceable_experience(case, submission)


def test_real_gold10_deficits_are_observations_not_model_blame_or_causal_history():
    experience = gold(missing_evidence=True)
    before = experience.model_dump_json()
    report = diagnose_experience(experience)
    assert report.origin.primary_category is FailureCategory.UNKNOWN
    assert report.diagnostics.failure_mechanisms == (FailureMechanism.UNKNOWN,)
    evidence = next(x for x in report.observations if x.code == "gold10.evidence_coverage")
    assert evidence.value == 0
    assert evidence.status == "OBSERVED"
    assert evidence.mechanism_status == "HYPOTHESIZED"
    assert evidence.evidence_references
    assert report.metrics["belief_revision_consistency"] is None
    assert report.metrics["evidence_cost_per_distinct_reference"] is None
    assert report.diagnostics.first_divergence_reference is None
    assert report.diagnostics.successful_recovery_references == ()
    assert report.capability_gaps == ()
    assert experience.model_dump_json() == before
    assert diagnose_experience(experience) == report


def test_gold10_reference_is_not_failure_from_reward_ceiling_or_order():
    experience = gold()
    assert experience.trajectory.original_evaluation.reward == 0.75
    assert not diagnose_experience(experience).observations
    assert failure_family_candidates([experience]) == ()
    submission = reference_submission("2005-04-I-TX")
    alternative = traceable_experience(
        "2005-04-I-TX",
        submission.model_copy(update={"evidence_ids": tuple(reversed(submission.evidence_ids))}),
    )
    assert not diagnose_experience(alternative).observations


def test_failure_families_require_repeated_distinct_sources_and_retain_evidence():
    a, b = gold(missing_evidence=True), gold("2012-03-I-CA", missing_evidence=True)
    assert failure_family_candidates([a, a]) == ()
    families = failure_family_candidates([a, b])
    assert families
    assert families == failure_family_candidates([b, a])
    for candidate in families:
        assert candidate.status == "HYPOTHESIZED"
        assert candidate.family.member_experience_ids == tuple(
            sorted((a.experience_id, b.experience_id))
        )
        assert candidate.family.candidate_origin is FailureCategory.UNKNOWN
        assert candidate.family.recoverability is None
        assert candidate.evidence_references
        assert candidate.family.affected_capability == "unknown"


def test_buyer_projection_withholds_private_source_and_private_derived_identity():
    original = gold(missing_evidence=True)
    payload = original.model_dump(mode="python")
    payload["private_metadata"] = {"hidden_label": "SECRET-SENTINEL"}
    private = MachineExperience.model_validate(payload)
    safe = buyer_safe_diagnostics(private)
    assert safe == {"status": "UNKNOWN", "reason": "source_not_fully_buyer_safe"}
    assert private.experience_id not in json.dumps(safe)
    assert "SECRET-SENTINEL" not in json.dumps(safe)
    payload["private_metadata"] = {}
    payload["visibility"] = VisibilityClass.SEALED
    assert buyer_safe_diagnostics(MachineExperience.model_validate(payload)) == safe
    assert buyer_safe_diagnostics(original)["observations"]


def test_missing_and_stale_identity_inputs_fail_closed():
    experience = gold()
    stale = experience.model_copy(update={"experience_id": "EXP-fake"})
    with pytest.raises(ValueError):
        diagnose_experience(stale)
    payload = experience.model_dump(mode="python")
    payload["trajectory"]["original_evaluation"]["component_scores"]["evidence_coverage"] = float(
        "nan"
    )
    payload["trajectory"]["trajectory_id"] = ""
    payload["experience_id"] = ""
    with pytest.raises(ValueError, match="finite|JSON compliant"):
        diagnose_experience(MachineExperience.model_validate(payload))


def test_real_runtime_adapter_and_authorized_verifier_supply_private_reasons():
    from investigation_world.foundry.models import stable_hash
    from investigation_world.operational.catalog import build_enterprise_operations_world
    from investigation_world.operational.models import EpisodeSubmission
    from investigation_world.operational.runtime import OperationalRuntime
    from investigation_world.portable_contract import compile_operational_episode
    from investigation_world.trajectory import (
        ArtifactIdentity,
        OperationalRuntimeAdapterContext,
        TrajectoryV2,
        canonical_hash,
        trajectory_v2_from_operational_runtime,
    )
    from investigation_world.trajectory.reverify import (
        AuthorizedVerifierRegistry,
        OperationalReplayEvidence,
        attach_operational_replay_evidence,
        current_operational_verifier_binding,
    )

    episode = build_enterprise_operations_world(seed=42)
    runtime = OperationalRuntime(episode)
    initial = runtime.state_snapshot()
    submission = EpisodeSubmission(
        conclusion="No actions attempted", evidence_ids=[], confidence=0.1
    )
    breakdown = runtime.submit(submission)
    final = runtime.state_snapshot()
    contract = compile_operational_episode(episode)
    trajectory = trajectory_v2_from_operational_runtime(
        runtime,
        context=OperationalRuntimeAdapterContext(
            submission=submission,
            breakdown=breakdown,
            initial_state_digest=stable_hash(initial),
            final_state_digest=stable_hash(final),
            portable_operational_contract=ArtifactIdentity(
                artifact_id=contract.contract_id,
                contract="veritas.portable-operational-contract",
                version="1.0.0",
            ),
        ),
    )
    evidence = OperationalReplayEvidence(
        portable_contract=contract,
        trajectory_events_digest=canonical_hash(trajectory.events),
        initial_state=initial,
        initial_state_digest=stable_hash(initial),
        final_state=final,
        final_state_digest=stable_hash(final),
        action_events=tuple(runtime.events),
        submission=submission,
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
    )
    payload = trajectory.model_dump(mode="python")
    payload.update(trajectory_id="", evidence_references=(evidence.reference(),))
    trajectory = TrajectoryV2.model_validate(payload)
    trajectory = attach_operational_replay_evidence(trajectory, evidence.for_trajectory(trajectory))
    experience = MachineExperience(trajectory=trajectory)
    registry = AuthorizedVerifierRegistry((current_operational_verifier_binding(),))
    report = diagnose_experience(experience, registry=registry)
    codes = {o.code for o in report.observations}
    assert "verifier.missing_required_actions" in codes
    assert "verifier.missing_evidence_ids" in codes
    assert report.origin.primary_category is FailureCategory.UNKNOWN
    assert all(o.visibility is VisibilityClass.EVALUATOR_PRIVATE for o in report.observations)
    classified = experience.model_dump(mode="python")
    classified["visibility"] = VisibilityClass.SEALED
    sealed_report = diagnose_experience(
        MachineExperience.model_validate(classified), registry=registry
    )
    assert all(
        ref.visibility is VisibilityClass.SEALED
        for obs in sealed_report.observations
        for ref in obs.evidence_references
    )

    assert all(o.evidence_references[0].private_metadata["reasons"] for o in report.observations)
    assert buyer_safe_diagnostics(experience)["status"] == "UNKNOWN"
    unauthorized = diagnose_experience(experience, registry=AuthorizedVerifierRegistry(()))
    assert not unauthorized.observations
    assert unauthorized.unavailable["reverification"] == "EXACT_VERIFIER_BINDING_NOT_AUTHORIZED"


def test_history_consistency_requires_complete_matching_snapshots_and_evidence():
    from investigation_world.experience import BeliefRevision, EpistemicSnapshot, HypothesisState

    experience = gold()
    reference = experience.trajectory.evidence_references[0].reference_id
    snapshots = (
        EpistemicSnapshot(
            snapshot_id="before",
            step=1,
            hypotheses=(
                HypothesisState(
                    hypothesis_id="h", statement="Synthetic explicit belief", confidence=0.2
                ),
            ),
        ),
        EpistemicSnapshot(
            snapshot_id="after",
            step=2,
            hypotheses=(
                HypothesisState(
                    hypothesis_id="h", statement="Synthetic explicit belief", confidence=0.7
                ),
            ),
        ),
    )
    revision = BeliefRevision(
        revision_id="r",
        step=2,
        hypothesis_id="h",
        prior_confidence=0.2,
        revised_confidence=0.7,
        evidence_reference_ids=(reference,),
    )
    payload = experience.model_dump(mode="python")
    payload.update(epistemic_snapshots=snapshots, belief_revisions=(revision,))
    coherent = MachineExperience.model_validate(payload)
    assert diagnose_experience(coherent).metrics["belief_revision_consistency"] == 1
    assert diagnose_experience(coherent).metrics["belief_revision_temporal_support"] == 1
    payload["belief_revisions"] = (revision.model_copy(update={"prior_confidence": 0.9}),)
    assert (
        diagnose_experience(MachineExperience.model_validate(payload)).metrics[
            "belief_revision_consistency"
        ]
        == 0
    )
    payload["epistemic_snapshots"] = (snapshots[1],)
    assert (
        diagnose_experience(MachineExperience.model_validate(payload)).metrics[
            "belief_revision_consistency"
        ]
        is None
    )


def test_reference_difference_is_state_grounded_descriptive_and_not_failure():
    from investigation_world.experience.diagnostics import reference_action_divergence
    from investigation_world.trajectory import RuntimeIdentity, StateDigest, TrajectoryEvent

    def synthetic(action):
        payload = gold().model_dump(mode="python")
        payload["trajectory"]["initial_state"] = StateDigest(digest="public-state-0")
        payload["trajectory"]["runtime"] = RuntimeIdentity(
            runtime_id="synthetic-protocol", version="1"
        )
        payload["trajectory"]["events"] = tuple(
            TrajectoryEvent(
                step=step,
                event_type="act",
                payload={"method": "act", "args": [name], "kwargs": {}},
                state_before=StateDigest(digest=f"public-state-{step}"),
                state_after=StateDigest(digest=f"public-state-{step + 1}"),
            )
            for step, name in enumerate(("inspect", action, "finish"))
        )
        payload["trajectory"]["trajectory_id"] = ""
        payload["experience_id"] = ""
        return MachineExperience.model_validate(payload)

    a, b = synthetic("valid-a"), synthetic("valid-b")
    difference = reference_action_divergence(a, b)
    assert difference is not None
    assert difference.public_metadata["step"] == 1
    assert difference.public_metadata["causal_status"] == "UNKNOWN"
    assert difference.public_metadata["failure_claim"] is False
    report = diagnose_experience(a, reference=b)
    assert not report.observations
    assert report.diagnostics.failure_mechanisms == (FailureMechanism.UNKNOWN,)
    assert report.diagnostics.first_divergence_reference == difference
    sealed_payload = b.model_dump(mode="python")
    sealed_payload["visibility"] = VisibilityClass.SEALED
    sealed_reference = MachineExperience.model_validate(sealed_payload)
    sealed_comparison = diagnose_experience(a, reference=sealed_reference)
    assert sealed_comparison.visibility is VisibilityClass.SEALED
    assert sealed_comparison.diagnostics.visibility is VisibilityClass.SEALED
    assert (
        sealed_comparison.diagnostics.first_divergence_reference.visibility
        is VisibilityClass.SEALED
    )

    longer = b.model_dump(mode="python")
    longer["trajectory"]["events"] = (
        *longer["trajectory"]["events"],
        TrajectoryEvent(
            step=3,
            event_type="act",
            payload={"method": "act", "args": ["extra"], "kwargs": {}},
            state_before=StateDigest(digest="public-state-3"),
            state_after=StateDigest(digest="public-state-4"),
        ),
    )
    longer["trajectory"]["trajectory_id"] = ""
    longer["experience_id"] = ""
    assert reference_action_divergence(a, MachineExperience.model_validate(longer)) is not None
    assert reference_action_divergence(a, a) is None
    assert reference_action_divergence(gold(), gold(missing_evidence=True)) is None
    payload = b.model_dump(mode="python")
    payload["trajectory"]["events"][1]["state_before"]["digest"] = "different-state"
    payload["trajectory"]["trajectory_id"] = ""
    payload["experience_id"] = ""
    assert reference_action_divergence(a, MachineExperience.model_validate(payload)) is None


def test_public_gold10_temporal_and_belief_components_are_distinct_observed_symptoms():
    from investigation_world.gold10 import Gold10Submission

    case = "2005-04-I-TX"
    submission = reference_submission(case)
    payload = submission.model_dump(mode="python")
    payload["evidence_ids"] = (*submission.evidence_ids, "csb-final-findings-release-2007-03-20")
    temporal = diagnose_experience(
        traceable_experience(case, Gold10Submission.model_validate(payload))
    )
    row = next(x for x in temporal.observations if x.code == "gold10.rights_temporal_integrity")
    assert row.value == 0
    assert row.mechanism_status == "HYPOTHESIZED"
    case = "2012-03-I-CA"
    payload = reference_submission(case).model_dump(mode="python")
    payload.update(primary_confidence=0.99, alternative_confidence=0.01)
    belief = diagnose_experience(
        traceable_experience(case, Gold10Submission.model_validate(payload))
    )
    assert any(x.code == "gold10.calibration_integrity" for x in belief.observations)
    assert belief.metrics["belief_revision_consistency"] is None


def test_global_references_do_not_dilute_event_evidence_cost():
    from investigation_world.trajectory import TrajectoryReference

    payload = gold().model_dump(mode="python")
    for event in payload["trajectory"]["events"]:
        event["cost"] = 10
    payload["trajectory"]["trajectory_id"] = ""
    payload["experience_id"] = ""
    original = MachineExperience.model_validate(payload)
    first = diagnose_experience(original).metrics["evidence_cost_per_distinct_reference"]
    payload["trajectory"]["evidence_references"] = (
        *payload["trajectory"]["evidence_references"],
        *(
            TrajectoryReference(reference_id=f"unacquired-{n}", reference_type="synthetic")
            for n in range(99)
        ),
    )
    second = diagnose_experience(MachineExperience.model_validate(payload)).metrics[
        "evidence_cost_per_distinct_reference"
    ]
    assert first == second


def test_future_only_evidence_and_ambiguous_prior_never_pass_protocol_quality():
    from investigation_world.experience import BeliefRevision, EpistemicSnapshot, HypothesisState

    payload = gold().model_dump(mode="python")
    future = payload["trajectory"]["events"][2]["evidence_references"][0]["reference_id"]
    payload["trajectory"]["events"][1]["evidence_references"] = ()
    payload["trajectory"]["trajectory_id"] = ""
    payload["experience_id"] = ""
    before = EpistemicSnapshot(
        snapshot_id="prior",
        step=0,
        hypotheses=(
            HypothesisState(
                hypothesis_id="h",
                statement="Declared synthetic belief",
                confidence=0.2,
                contradictions=("declared-conflict",),
            ),
        ),
    )
    after = EpistemicSnapshot(
        snapshot_id="after",
        step=1,
        hypotheses=(
            HypothesisState(
                hypothesis_id="h", statement="Declared synthetic belief", confidence=0.7
            ),
        ),
    )
    payload.update(
        epistemic_snapshots=(before, after),
        belief_revisions=(
            BeliefRevision(
                revision_id="r",
                step=1,
                hypothesis_id="h",
                prior_confidence=0.2,
                revised_confidence=0.7,
                evidence_reference_ids=(future,),
            ),
        ),
    )
    metrics = diagnose_experience(MachineExperience.model_validate(payload)).metrics
    assert metrics["belief_revision_consistency"] == 1
    assert metrics["belief_revision_temporal_support"] == 0
    assert metrics["reported_contradiction_count_reduction"] == 1
    payload["epistemic_snapshots"] = (
        before,
        before.model_copy(update={"snapshot_id": "ambiguous"}),
        after,
    )
    metrics = diagnose_experience(MachineExperience.model_validate(payload)).metrics
    assert metrics["belief_revision_snapshot_coverage"] == 0
    assert metrics["belief_revision_consistency"] is None
    assert metrics["belief_revision_temporal_support"] is None


def test_derived_classification_never_widens_sealed_synthetic_source():
    # Synthetic visibility sentinel only; no actual sealed benchmark input is loaded.
    original = gold(missing_evidence=True)
    payload = original.model_dump(mode="python")
    payload["visibility"] = VisibilityClass.SEALED
    sealed = MachineExperience.model_validate(payload)
    report = diagnose_experience(sealed)
    assert report.visibility is VisibilityClass.SEALED
    assert report.diagnostics.visibility is VisibilityClass.SEALED
    assert all(o.visibility is VisibilityClass.SEALED for o in report.observations)
    assert all(
        r.visibility is VisibilityClass.SEALED
        for o in report.observations
        for r in o.evidence_references
    )
    other = gold("2012-03-I-CA", missing_evidence=True)
    for candidate in failure_family_candidates([sealed, other]):
        assert candidate.visibility is VisibilityClass.SEALED
        assert candidate.family.visibility is VisibilityClass.SEALED
