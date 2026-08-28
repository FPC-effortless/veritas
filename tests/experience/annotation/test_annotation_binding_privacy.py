from __future__ import annotations

import pytest

from investigation_world.experience.annotation import (
    SemanticAnnotationError,
    compile_semantic_annotations,
)
from investigation_world.operational.models import (
    ActionKind,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
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
    StateDigest,
    TaskIdentity,
    TrajectoryEvent,
    TrajectoryV2,
    VerifierIdentity,
    VisibilityClass,
    WorldIdentity,
)


def _contract(*, final_status: str = "approved") -> PortableOperationalContract:
    episode = OperationalEpisode(
        episode_id="binding-episode-001",
        world_id="binding-world-001",
        task=TaskContract(
            task_id="binding-task-001",
            world_id="binding-world-001",
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
                    cost=1,
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
            task_id="binding-task-001",
            initial_state={"order.status": "pending"},
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value=final_status,
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
                    set_state={"order.status": final_status},
                )
            ],
            max_cost=5,
            max_tool_calls=3,
        ),
    )
    return compile_operational_episode(episode)


def _trajectory(
    contract: PortableOperationalContract,
    *,
    binding: str,
) -> TrajectoryV2:
    verifier = VerifierIdentity(verifier_id="verifier:binding", version="1")
    contract_reference: ArtifactIdentity | None
    if binding == "full":
        contract_reference = ArtifactIdentity(
            artifact_id="portable-contract:binding",
            digest=contract.contract_id,
            visibility=VisibilityClass.EVALUATOR_PRIVATE,
        )
    elif binding == "public":
        contract_reference = ArtifactIdentity(
            artifact_id="portable-contract:binding-public",
            digest=contract.public.public_id,
            visibility=VisibilityClass.PUBLIC,
        )
    elif binding == "missing":
        contract_reference = None
    else:
        raise ValueError(f"unsupported binding fixture: {binding}")

    return TrajectoryV2(
        world=WorldIdentity(
            environment_id="environment:binding",
            environment_version="1",
            world_id="binding-world-001",
            world_version="1",
            portable_operational_contract=contract_reference,
        ),
        task=TaskIdentity(
            task_id="binding-task-001",
            taskset_version="1",
            split="test",
        ),
        verifier=verifier,
        initial_state=StateDigest(digest="state-0"),
        events=(
            TrajectoryEvent(
                step=0,
                event_type="action",
                payload={
                    "method": "approve_order",
                    "arguments": {"order_id": "ORDER-001"},
                },
                state_before=StateDigest(digest="state-0"),
                state_after=StateDigest(digest="state-1"),
                cost=1.0,
            ),
        ),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={"outcome": 1.0},
            reward=1.0,
        ),
        final_state=StateDigest(digest="state-1"),
    )


def test_missing_contract_binding_cannot_authorize_private_semantics() -> None:
    contract = _contract()

    with pytest.raises(SemanticAnnotationError, match="exact full portable contract"):
        compile_semantic_annotations(_trajectory(contract, binding="missing"), contract)


def test_public_contract_binding_cannot_authorize_private_semantics() -> None:
    contract = _contract()

    with pytest.raises(SemanticAnnotationError, match="public-only portable-contract"):
        compile_semantic_annotations(_trajectory(contract, binding="public"), contract)


def test_same_public_contract_cannot_swap_private_evaluator_semantics() -> None:
    original = _contract(final_status="approved")
    changed_private = _contract(final_status="reviewed")

    assert original.public.public_id == changed_private.public.public_id
    assert original.contract_id != changed_private.contract_id

    public_bound = _trajectory(original, binding="public")
    with pytest.raises(SemanticAnnotationError, match="public-only portable-contract"):
        compile_semantic_annotations(public_bound, changed_private)


def test_safe_projection_omits_private_bound_bundle_identity() -> None:
    contract = _contract()
    bundle = compile_semantic_annotations(_trajectory(contract, binding="full"), contract)

    assert bundle.bundle_id.startswith("SEMBUNDLE-")
    assert "bundle_id" not in bundle.public_payload()
    assert "bundle_id" not in bundle.buyer_safe_payload()
    assert "contract_id" not in bundle.public_payload()
    assert "evaluator_semantics_id" not in bundle.public_payload()
