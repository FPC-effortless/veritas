from __future__ import annotations

import pytest

from investigation_world.experience import MachineExperience
from investigation_world.experience.annotation import (
    SemanticAnnotationBundle,
    SemanticAnnotationError,
    SemanticDerivationStatus,
    SemanticInvocationKind,
    apply_semantic_annotations,
    compile_semantic_annotations,
)
from investigation_world.operational.models import (
    ActionKind,
    AssertionComparison,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
    WorldDomain,
)
from investigation_world.portable_contract import (
    PortableOperationalContract,
    compile_operational_episode,
)
from investigation_world.trajectory import (
    ArtifactIdentity,
    EvaluationRecord,
    ResourceCallSummary,
    StateDigest,
    StateDigestScope,
    TaskIdentity,
    TrajectoryEvent,
    TrajectoryV2,
    VerifierIdentity,
    VisibilityClass,
    WorldIdentity,
)


def _episode(*, approved_value: str = "approved") -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="semantic-episode-001",
        world_id="semantic-world-001",
        task=TaskContract(
            task_id="semantic-task-001",
            world_id="semantic-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve the valid order.",
            role="operations_controller",
            permitted_systems=["ERP"],
            available_actions=[
                PublicActionSpec(
                    name="approve_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Approve an order.",
                    parameter_names=["order_id"],
                    cost=3,
                )
            ],
            constraints=["Do not delete the order."],
            success_description="The order is approved.",
        ),
        records=[
            OperationalRecord(
                record_id="record-001",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={"status": "pending"},
                searchable_text="pending order",
                source_authority="authoritative",
                freshness="current",
            )
        ],
        oracle=HiddenOracle(
            task_id="semantic-task-001",
            initial_state={
                "order.status": "pending",
                "evaluator.secret": "SEMANTIC-PRIVATE-OMEGA",
            },
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value=approved_value,
                )
            ],
            invariants=[
                OperationalInvariant(
                    invariant_id="order-not-deleted",
                    description="The order must not be deleted.",
                    assertion=StateAssertion(
                        object_id="order",
                        field_name="status",
                        expected_value="deleted",
                        comparison=AssertionComparison.NOT_EQUAL,
                    ),
                    severity="critical",
                    scope="always",
                )
            ],
            required_actions=["approve_order"],
            required_action_order=["approve_order"],
            required_action_counts={"approve_order": 1},
            required_evidence_ids=["record-001"],
            action_effects=[
                HiddenActionEffect(
                    action_name="approve_order",
                    required_parameters={"order_id": "ORDER-001"},
                    set_state={"order.status": approved_value},
                    emitted_side_effects=["approval_written"],
                )
            ],
            max_cost=9,
            max_tool_calls=5,
        ),
    )


def _trajectory(
    contract: PortableOperationalContract,
    *,
    prose_only: bool = False,
) -> TrajectoryV2:
    verifier = VerifierIdentity(verifier_id="verifier:semantic", version="1")
    events = (
        TrajectoryEvent(
            step=0,
            event_type="tool_call",
            payload=(
                {"message": "approve_order"}
                if prose_only
                else {
                    "method": "open_record",
                    "arguments": {"record_id": "record-001"},
                }
            ),
            state_before=StateDigest(digest="state-0"),
            state_after=StateDigest(digest="state-0"),
            cost=1.0,
        ),
    )
    if not prose_only:
        events = (
            *events,
            TrajectoryEvent(
                step=1,
                event_type="action",
                payload={
                    "method": "approve_order",
                    "arguments": {"order_id": "ORDER-001"},
                },
                state_before=StateDigest(digest="state-0"),
                state_after=StateDigest(digest="state-1"),
                cost=3.0,
            ),
        )

    return TrajectoryV2(
        world=WorldIdentity(
            environment_id="environment:semantic",
            environment_version="1",
            world_id="semantic-world-001",
            world_version="1",
            portable_operational_contract=ArtifactIdentity(
                artifact_id="portable-contract:semantic",
                digest=contract.contract_id,
                visibility=VisibilityClass.EVALUATOR_PRIVATE,
            ),
        ),
        task=TaskIdentity(
            task_id="semantic-task-001",
            taskset_version="1",
            split="test",
        ),
        verifier=verifier,
        initial_state=StateDigest(digest="state-0"),
        events=events,
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={
                "outcome": 1.0,
                "state": 1.0,
                "constraints": 1.0,
                "side_effects": 1.0,
                "process": 1.0,
                "efficiency": 1.0,
                "evidence": 1.0,
            },
            reward=1.0,
        ),
        final_state=StateDigest(digest="state-1" if not prose_only else "state-0"),
        capability_tags=("operational_control",),
    )


def _replace_trajectory(trajectory: TrajectoryV2, **changes: object) -> TrajectoryV2:
    payload = trajectory.model_dump(mode="python")
    payload.update(changes)
    payload["trajectory_id"] = ""
    return TrajectoryV2.model_validate(payload)


def test_compiler_derives_structured_semantics_deterministically() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract)

    first = compile_semantic_annotations(trajectory, contract)
    second = compile_semantic_annotations(trajectory, contract)

    assert first.bundle_id == second.bundle_id
    assert first.trajectory_id == trajectory.trajectory_id
    assert first.contract_id == contract.contract_id
    assert first.public_contract_id == contract.public.public_id

    evidence_event = first.event_annotations[0]
    assert evidence_event.invocation.kind is SemanticInvocationKind.OPERATION
    assert evidence_event.invocation.name == "open_record"
    assert evidence_event.evidence_flow.status is SemanticDerivationStatus.DERIVED
    assert evidence_event.evidence_flow.consumed_ids == ("record-001",)

    action_event = first.event_annotations[1]
    assert action_event.invocation.kind is SemanticInvocationKind.ACTION
    assert action_event.invocation.name == "approve_order"
    assert action_event.state_transition.changed is True
    assert action_event.process_requirement.required is True
    assert action_event.process_requirement.required_count == 1
    assert action_event.invariant_effect.affected_invariant_ids == ("order-not-deleted",)
    assert set(action_event.verifier_relevance.component_names) >= {
        "constraints",
        "efficiency",
        "process",
        "side_effects",
        "state",
    }

    assert any(span.span_type == "capability_candidate" for span in first.spans)
    assert any(span.span_type == "subgoal_candidate" for span in first.spans)
    assert any(record.record_type == "subgoal" for record in first.structural_records)


def test_compiler_does_not_infer_action_identity_from_prose() -> None:
    contract = compile_operational_episode(_episode())
    bundle = compile_semantic_annotations(_trajectory(contract, prose_only=True), contract)

    annotation = bundle.event_annotations[0]
    assert annotation.invocation.status is SemanticDerivationStatus.UNKNOWN
    assert annotation.invocation.name is None
    assert annotation.process_requirement.status is SemanticDerivationStatus.UNKNOWN


def test_private_resource_call_semantics_do_not_widen_into_public_output() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract, prose_only=True)
    trajectory = _replace_trajectory(
        trajectory,
        resource_calls=(
            ResourceCallSummary(
                call_index=0,
                resource_id="record_id:record-001",
                operation="open_record",
                success=True,
                visibility=VisibilityClass.EVALUATOR_PRIVATE,
                public_metadata={"source_event_step": 0},
            ),
        ),
    )

    bundle = compile_semantic_annotations(trajectory, contract)
    annotation = bundle.event_annotations[0]

    assert annotation.invocation.name == "open_record"
    assert annotation.invocation.visibility is VisibilityClass.EVALUATOR_PRIVATE
    assert annotation.evidence_flow.consumed_ids == ("record-001",)
    assert annotation.evidence_flow.visibility is VisibilityClass.EVALUATOR_PRIVATE

    public_payload = bundle.public_payload()
    public_event = public_payload["event_annotations"][0]
    assert "invocation" not in public_event
    assert "evidence_flow" not in public_event
    assert all(
        span["span_type"] != "semantic_invocation"
        for span in public_payload["spans"]
    )
    assert all(
        record["attributes"].get("relation") != "evidence_flow"
        for record in public_payload["structural_records"]
    )


@pytest.mark.parametrize("success", [False, None])
def test_failed_or_unknown_resource_read_does_not_become_consumed_evidence(
    success: bool | None,
) -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract, prose_only=True)
    trajectory = _replace_trajectory(
        trajectory,
        resource_calls=(
            ResourceCallSummary(
                call_index=0,
                resource_id="record_id:record-001",
                operation="open_record",
                success=success,
                public_metadata={"source_event_step": 0},
            ),
        ),
    )

    bundle = compile_semantic_annotations(trajectory, contract)
    evidence = bundle.event_annotations[0].evidence_flow

    assert evidence.consumed_ids == ()
    assert evidence.created_ids == ()
    assert evidence.status is SemanticDerivationStatus.NOT_APPLICABLE
    assert not any(
        record.attributes.get("relation") == "evidence_flow"
        for record in bundle.structural_records
    )


def test_requested_created_evidence_ids_do_not_prove_creation() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract)
    action = trajectory.events[1].model_dump(mode="python")
    action["payload"] = {
        "method": "approve_order",
        "arguments": {
            "order_id": "ORDER-001",
            "created_evidence_ids": ["record-001"],
            "emitted_evidence_ids": ["record-001"],
        },
    }
    trajectory = _replace_trajectory(
        trajectory,
        events=(trajectory.events[0], TrajectoryEvent.model_validate(action)),
    )

    bundle = compile_semantic_annotations(trajectory, contract)
    evidence = bundle.event_annotations[1].evidence_flow

    assert evidence.created_ids == ()
    assert evidence.consumed_ids == ()
    assert evidence.status is SemanticDerivationStatus.NOT_APPLICABLE


def test_state_digest_domain_mismatch_is_unknown() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract, prose_only=True)
    event = trajectory.events[0].model_dump(mode="python")
    event["state_before"] = StateDigest(
        digest="same",
        algorithm="sha256",
        scope=StateDigestScope.PUBLIC,
    )
    event["state_after"] = StateDigest(
        digest="same",
        algorithm="blake3",
        scope=StateDigestScope.SEMANTIC,
    )
    trajectory = _replace_trajectory(
        trajectory,
        events=(TrajectoryEvent.model_validate(event),),
        final_state=event["state_after"],
    )

    bundle = compile_semantic_annotations(trajectory, contract)
    state = bundle.event_annotations[0].state_transition

    assert state.status is SemanticDerivationStatus.UNKNOWN
    assert state.changed is None
    assert state.state_before_algorithm == "sha256"
    assert state.state_before_scope is StateDigestScope.PUBLIC
    assert state.state_after_algorithm == "blake3"
    assert state.state_after_scope is StateDigestScope.SEMANTIC
    assert not any(
        record.attributes.get("relation") == "state_digest_transition"
        for record in bundle.structural_records
    )


def test_public_projection_does_not_widen_private_contract_semantics() -> None:
    contract = compile_operational_episode(_episode())
    bundle = compile_semantic_annotations(_trajectory(contract), contract)

    payload = bundle.public_payload()
    text = repr(payload)

    assert contract.contract_id not in text
    assert contract.private.evaluator.semantics_id not in text
    assert "SEMANTIC-PRIVATE-OMEGA" not in text
    assert payload["public_contract_id"] == contract.public.public_id
    assert "process_requirement" not in payload["event_annotations"][1]
    assert "invariant_effect" not in payload["event_annotations"][1]
    assert "verifier_relevance" not in payload["event_annotations"][1]
    assert all(
        span["span_type"] != "subgoal_candidate"
        for span in payload["spans"]
    )


def test_changed_contract_identity_cannot_annotate_old_trajectory_binding() -> None:
    original = compile_operational_episode(_episode())
    changed = compile_operational_episode(_episode(approved_value="reviewed"))
    trajectory = _trajectory(original)

    with pytest.raises(SemanticAnnotationError, match="digest does not match"):
        compile_semantic_annotations(trajectory, changed)


def test_stale_copied_contract_semantics_fail_closed() -> None:
    contract = compile_operational_episode(_episode())
    transition = contract.private.transitions[0].model_copy(
        update={"set_state": {"order.status": "tampered"}}
    )
    private = contract.private.model_copy(update={"transitions": (transition,)})
    stale_contract = contract.model_copy(update={"private": private})

    with pytest.raises(SemanticAnnotationError, match="invalid portable operational contract"):
        compile_semantic_annotations(_trajectory(contract), stale_contract)


def test_composition_rejects_fresh_bundle_with_mismatched_contract_authority() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract)
    experience = MachineExperience(trajectory=trajectory)
    bundle = compile_semantic_annotations(trajectory, contract)
    payload = bundle.model_dump(mode="python")
    payload["bundle_id"] = ""
    payload["contract_id"] = "POC-FORGED"
    forged = SemanticAnnotationBundle.model_validate(payload)

    with pytest.raises(SemanticAnnotationError, match="contract identity"):
        apply_semantic_annotations(experience, forged)


def test_composition_rejects_fresh_bundle_with_mismatched_verifier_authority() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract)
    experience = MachineExperience(trajectory=trajectory)
    bundle = compile_semantic_annotations(trajectory, contract)
    payload = bundle.model_dump(mode="python")
    payload["bundle_id"] = ""
    payload["trajectory_verifier_version"] = "forged-version"
    forged = SemanticAnnotationBundle.model_validate(payload)

    with pytest.raises(SemanticAnnotationError, match="verifier identity/version"):
        apply_semantic_annotations(experience, forged)


def test_composition_rejects_fresh_bundle_with_mismatched_event_binding() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract)
    experience = MachineExperience(trajectory=trajectory)
    bundle = compile_semantic_annotations(trajectory, contract)
    payload = bundle.model_dump(mode="python")
    payload["bundle_id"] = ""
    event_payload = payload["event_annotations"][0]
    event_payload["annotation_id"] = ""
    event_payload["event_type"] = "forged-event-type"
    forged = SemanticAnnotationBundle.model_validate(payload)

    with pytest.raises(SemanticAnnotationError, match="event binding"):
        apply_semantic_annotations(experience, forged)


def test_annotation_composition_is_immutable_and_preserves_experience_identity() -> None:
    contract = compile_operational_episode(_episode())
    trajectory = _trajectory(contract)
    original = MachineExperience(trajectory=trajectory)
    bundle = compile_semantic_annotations(trajectory, contract)

    enriched = apply_semantic_annotations(original, bundle)

    assert original.spans == ()
    assert original.structural_records == ()
    assert original.derivation_references == ()
    assert enriched.experience_id == original.experience_id
    assert enriched.trajectory.trajectory_id == original.trajectory.trajectory_id
    assert len(enriched.spans) == len(bundle.spans)
    assert len(enriched.structural_records) == len(bundle.structural_records)
    assert enriched.derivation_references[-1].reference_id == bundle.bundle_id
    assert enriched.derivation_references[-1].visibility is VisibilityClass.EVALUATOR_PRIVATE
    assert bundle.bundle_id not in repr(enriched.public_payload())
    assert contract.contract_id not in repr(enriched.public_payload())