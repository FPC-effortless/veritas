from __future__ import annotations

import json

import pytest

from investigation_world.foundry.models import stable_hash
from investigation_world.operational.models import (
    ActionKind,
    EpisodeSubmission,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
    WorldDomain,
)
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.trajectory import (
    ArtifactIdentity,
    EvaluationRecord,
    ModelIdentity,
    StateDigest,
    TaskIdentity,
    TrajectoryEvent,
    TrajectoryV2,
    UsageTotals,
    VerifierIdentity,
    VisibilityClass,
    WorldIdentity,
    canonical_hash,
)
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    AuthorizedVerifierRegistry,
    OperationalReplayEvidence,
    ReverificationStatus,
    attach_operational_replay_evidence,
    current_operational_verifier_binding,
    evaluator_input_from_evidence,
    reverify_trajectory,
)


def _episode() -> OperationalEpisode:
    action = PublicActionSpec(
        name="close_case",
        kind=ActionKind.WRITE,
        system="case_system",
        description="Close the operational case.",
        parameter_names=["status"],
        cost=2,
    )
    return OperationalEpisode(
        episode_id="episode-reverify-1",
        world_id="world-reverify",
        task=TaskContract(
            task_id="task-reverify-1",
            world_id="world-reverify",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Close the case with evidence.",
            role="operator",
            permitted_systems=["case_system"],
            available_actions=[action],
        ),
        records=[
            OperationalRecord(
                record_id="REC-1",
                system="case_system",
                record_type="case",
                object_id="case",
                fields={"status": "open"},
                searchable_text="case open",
            )
        ],
        oracle=HiddenOracle(
            task_id="task-reverify-1",
            initial_state={"case.status": "open"},
            target_state=[
                StateAssertion(
                    object_id="case",
                    field_name="status",
                    expected_value="closed",
                )
            ],
            required_actions=["close_case"],
            required_evidence_ids=["REC-1"],
            action_effects=[
                HiddenActionEffect(
                    action_name="close_case",
                    required_parameters={"status": "closed"},
                    set_state={"case.status": "closed"},
                    observable_result={"accepted": True},
                )
            ],
            max_cost=10,
            max_tool_calls=5,
            metadata={"private_marker": "PRIVATE-ORACLE-SECRET"},
        ),
    )


def _reverifiable_trajectory(
    *,
    include_required_evidence: bool = True,
) -> tuple[TrajectoryV2, OperationalReplayEvidence]:
    episode = _episode()
    contract = compile_operational_episode(episode)
    runtime = OperationalRuntime(episode)
    initial_state = runtime.state_snapshot()
    runtime.act("close_case", status="closed")
    submission = EpisodeSubmission(
        conclusion="closed",
        claimed_state={"case.status": "closed"},
        evidence_ids=["REC-1"] if include_required_evidence else [],
        confidence=0.9,
    )
    runtime.submit(submission)
    final_state = runtime.state_snapshot()

    trajectory_events = (
        TrajectoryEvent(
            step=0,
            event_type="act",
            payload={
                "method": "act",
                "args": ["close_case"],
                "kwargs": {"status": "closed"},
                "result": {
                    "action": "close_case",
                    "system": "case_system",
                    "submitted": True,
                    "accepted": True,
                },
                "success": True,
            },
            cost=2.0,
        ),
        TrajectoryEvent(
            step=1,
            event_type="submit",
            payload={
                "method": "submit",
                "args": [submission.model_dump(mode="json")],
                "kwargs": {},
                "success": True,
            },
            cost=0.0,
        ),
    )
    evidence = OperationalReplayEvidence(
        portable_contract=contract,
        trajectory_events_digest=canonical_hash(trajectory_events),
        initial_state=initial_state,
        initial_state_digest=stable_hash(initial_state),
        final_state=final_state,
        final_state_digest=stable_hash(final_state),
        action_events=tuple(runtime.events),
        submission=submission,
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
    )
    old_verifier = VerifierIdentity(verifier_id="legacy-operational", version="legacy-v1")
    trajectory = TrajectoryV2(
        world=WorldIdentity(
            environment_id="operational",
            environment_version="test",
            world_id=episode.world_id,
            world_version="1",
            portable_operational_contract=ArtifactIdentity(
                artifact_id=contract.contract_id,
                contract="veritas.portable-operational-contract",
                version=contract.schema_version,
            ),
        ),
        task=TaskIdentity(task_id=episode.task.task_id, taskset_version="tests", split="iid_test"),
        model=ModelIdentity(provider="offline-test", model_id="model", snapshot="snapshot"),
        verifier=old_verifier,
        initial_state=StateDigest(digest=evidence.initial_state_digest),
        events=trajectory_events,
        evidence_references=(evidence.reference(),),
        usage=UsageTotals(environment_cost=float(runtime.budget.spent)),
        original_evaluation=EvaluationRecord(
            verifier=old_verifier,
            component_scores={"outcome": 0.25},
            reward=0.25,
        ),
        final_state=StateDigest(digest=evidence.final_state_digest),
    )
    evidence = evidence.for_trajectory(trajectory)
    trajectory = attach_operational_replay_evidence(trajectory, evidence)
    return trajectory, evidence


def _registry() -> tuple[AuthorizedVerifierRegistry, VerifierIdentity]:
    binding = current_operational_verifier_binding()
    return AuthorizedVerifierRegistry((binding,)), binding.identity


def test_reverification_appends_without_mutating_original_evaluation() -> None:
    trajectory, _ = _reverifiable_trajectory()
    registry, verifier = _registry()

    result = reverify_trajectory(trajectory, verifier=verifier, registry=registry)

    assert result.status is ReverificationStatus.REVERIFIED
    assert result.record is not None
    assert result.trajectory_with_reverification is not None
    assert trajectory.reverifications == ()
    assert trajectory.original_evaluation.reward == 0.25
    assert trajectory.original_evaluation.component_scores == {"outcome": 0.25}
    assert (
        result.trajectory_with_reverification.original_evaluation
        == trajectory.original_evaluation
    )
    assert result.trajectory_with_reverification.trajectory_id == trajectory.trajectory_id
    assert result.record.verifier == verifier
    assert result.record.reward == 1.0
    assert result.record.component_scores["evidence"] == 1.0

    original_verifier_provenance = next(
        item
        for item in result.record.provenance
        if item.source_kind == "trajectory.original_verifier"
    )
    assert original_verifier_provenance.source_id == "legacy-operational"
    assert original_verifier_provenance.source_version == "legacy-v1"


def test_same_reverification_is_idempotently_not_appended_twice() -> None:
    trajectory, _ = _reverifiable_trajectory()
    registry, verifier = _registry()
    first = reverify_trajectory(trajectory, verifier=verifier, registry=registry)
    assert first.trajectory_with_reverification is not None

    second = reverify_trajectory(
        first.trajectory_with_reverification,
        verifier=verifier,
        registry=registry,
    )

    assert second.status is ReverificationStatus.ALREADY_RECORDED
    assert second.trajectory_with_reverification is not None
    assert len(second.trajectory_with_reverification.reverifications) == 1


def test_missing_private_replay_evidence_is_not_reverifiable_and_has_no_score() -> None:
    trajectory, _ = _reverifiable_trajectory()
    registry, verifier = _registry()
    stripped = TrajectoryV2.model_validate(
        {
            **trajectory.model_dump(mode="python"),
            "private_metadata": {},
        }
    )

    result = reverify_trajectory(stripped, verifier=verifier, registry=registry)

    assert result.status is ReverificationStatus.NOT_REVERIFIABLE
    assert result.reason_code == "PRIVATE_REPLAY_EVIDENCE_MISSING"
    assert result.record is None
    assert result.trajectory_with_reverification is None
    assert stripped.original_evaluation.reward == 0.25


def test_buyer_safe_projection_does_not_contain_private_replay_truth() -> None:
    trajectory, _ = _reverifiable_trajectory()
    safe_text = json.dumps(trajectory.buyer_safe_payload(), sort_keys=True)

    assert REPLAY_EVIDENCE_PRIVATE_KEY not in safe_text
    assert "PRIVATE-ORACLE-SECRET" not in safe_text

    registry, verifier = _registry()
    no_private_truth = TrajectoryV2.model_validate(
        {
            **trajectory.model_dump(mode="python"),
            "private_metadata": {},
        }
    )
    result = reverify_trajectory(no_private_truth, verifier=verifier, registry=registry)
    assert result.status is ReverificationStatus.NOT_REVERIFIABLE
    assert result.record is None


def test_wrong_verifier_version_is_not_treated_as_equivalent() -> None:
    trajectory, _ = _reverifiable_trajectory()
    registry, verifier = _registry()
    wrong = VerifierIdentity(
        verifier_id=verifier.verifier_id,
        version=f"{verifier.version}-different",
    )

    result = reverify_trajectory(trajectory, verifier=wrong, registry=registry)

    assert result.status is ReverificationStatus.UNAUTHORIZED
    assert result.reason_code == "EXACT_VERIFIER_BINDING_NOT_AUTHORIZED"
    assert result.record is None


def test_event_sequence_tampering_is_detected_even_after_new_id_is_computed() -> None:
    trajectory, evidence = _reverifiable_trajectory()
    registry, verifier = _registry()
    payload = trajectory.model_dump(mode="python")
    payload["trajectory_id"] = ""
    payload["events"] = tuple(reversed(trajectory.events))
    tampered = TrajectoryV2.model_validate(payload)

    rebound = evidence.for_trajectory(tampered)
    tampered_payload = tampered.model_dump(mode="python")
    private_metadata = dict(tampered.private_metadata)
    private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY] = rebound.model_dump(mode="json")
    tampered_payload["private_metadata"] = private_metadata
    tampered = TrajectoryV2.model_validate(tampered_payload)

    result = reverify_trajectory(tampered, verifier=verifier, registry=registry)

    assert result.status is ReverificationStatus.UNKNOWN
    assert result.reason_code == "TRAJECTORY_EVENT_SEQUENCE_DIGEST_MISMATCH"
    assert result.record is None


def test_private_evidence_requirement_is_enforced_by_offline_verifier() -> None:
    trajectory, _ = _reverifiable_trajectory(include_required_evidence=False)
    registry, verifier = _registry()

    result = reverify_trajectory(trajectory, verifier=verifier, registry=registry)

    assert result.status is ReverificationStatus.REVERIFIED
    assert result.record is not None
    assert result.record.component_scores["evidence"] == 0.0
    assert result.record.reward < 1.0


def test_evaluator_input_reconstruction_is_deterministic() -> None:
    _, evidence = _reverifiable_trajectory()

    first = evaluator_input_from_evidence(evidence)
    second = evaluator_input_from_evidence(evidence)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.oracle.required_evidence_ids == ["REC-1"]
    assert first.state == {"case.status": "closed"}
    assert first.tool_calls == 1
    assert first.cost_spent == 2


def test_registry_rejects_arbitrary_callable_bindings() -> None:
    class ProviderCallingBinding:
        def verify(self, _input):
            raise AssertionError("must never be injectable")

    with pytest.raises(TypeError, match="statically authorized offline verifier bindings"):
        AuthorizedVerifierRegistry((ProviderCallingBinding(),))  # type: ignore[arg-type]
