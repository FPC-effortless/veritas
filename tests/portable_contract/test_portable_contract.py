import json

import pytest
from pydantic import ValidationError

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
    PortableBudgetContract,
    PortableOperationalContract,
    PortableResourceLimit,
    SemanticRoundTripError,
    SemanticStateProjection,
    UnsupportedOperationalSemanticError,
    assert_operational_semantic_equivalence,
    compile_operational_episode,
    serialize_portable_contract,
    serialize_public_contract,
)


def _episode() -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="portable-episode-001",
        world_id="portable-world-001",
        task=TaskContract(
            task_id="portable-task-001",
            world_id="portable-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve the valid order while preserving the risk control.",
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
                ),
                PublicActionSpec(
                    name="notify_owner",
                    kind=ActionKind.COMMUNICATE,
                    system="ERP",
                    description="Notify the order owner.",
                    cost=1,
                ),
                PublicActionSpec(
                    name="delete_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Delete an order.",
                    cost=2,
                ),
            ],
            constraints=["Preserve the risk control."],
            success_description="The valid order is approved and the owner is notified.",
            metadata={"public_fixture": "portable-contract"},
        ),
        records=[
            OperationalRecord(
                record_id="record-001",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={
                    "status": "pending",
                    "risk_class": "normal",
                },
                searchable_text="pending order normal risk",
                source_authority="authoritative",
                freshness="current",
                provenance_ids=["source-001"],
            )
        ],
        oracle=HiddenOracle(
            task_id="portable-task-001",
            initial_state={
                "order.status": "pending",
                "order.risk": 0,
                "evaluator.secret": "HIDDEN-STATE-OMEGA",
            },
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value="TARGET-TRUTH-OMEGA",
                )
            ],
            invariants=[
                OperationalInvariant(
                    invariant_id="risk-remains-safe",
                    description="Risk must remain bounded throughout the trajectory.",
                    assertion=StateAssertion(
                        object_id="order",
                        field_name="risk",
                        expected_value=1,
                        comparison=AssertionComparison.LESS_THAN_OR_EQUAL,
                    ),
                    severity="critical",
                    scope="always",
                )
            ],
            required_actions=["approve_order"],
            required_action_order=["approve_order", "notify_owner"],
            required_action_counts={"notify_owner": 2},
            forbidden_actions=["delete_order"],
            required_evidence_ids=["record-001"],
            action_effects=[
                HiddenActionEffect(
                    action_name="approve_order",
                    required_parameters={"order_id": "ORDER-001"},
                    required_state=[
                        StateAssertion(
                            object_id="order",
                            field_name="status",
                            expected_value="pending",
                        )
                    ],
                    required_prior_actions=[],
                    set_state={"order.status": "TARGET-TRUTH-OMEGA"},
                    observable_result={"receipt": "HIDDEN-EFFECT-OMEGA"},
                    blocked_observable_result={
                        "accepted": False,
                        "reason": "order_not_pending",
                    },
                    emitted_side_effects=["approval_written"],
                    consequence_severity=0.1,
                )
            ],
            max_cost=9,
            max_tool_calls=5,
            metadata={
                "expected_answer": "EXPECTED-ANSWER-OMEGA",
                "private_evaluator_bytes": "PRIVATE-EVALUATOR-BYTES-OMEGA",
            },
        ),
        metadata={"public_episode": True},
    )


def _private_keys(value: object) -> set[str]:
    if isinstance(value, list):
        result: set[str] = set()
        for item in value:
            result |= _private_keys(item)
        return result
    if not isinstance(value, dict):
        return set()
    result = {str(key) for key in value}
    for item in value.values():
        result |= _private_keys(item)
    return result


def test_contract_identity_and_bytes_are_deterministic() -> None:
    first_episode = _episode()
    second_episode = _episode()
    second_episode.oracle.initial_state = {
        "evaluator.secret": "HIDDEN-STATE-OMEGA",
        "order.risk": 0,
        "order.status": "pending",
    }
    second_episode.records[0].fields = {
        "risk_class": "normal",
        "status": "pending",
    }

    first = compile_operational_episode(first_episode)
    second = compile_operational_episode(second_episode)

    assert first.contract_id == second.contract_id
    assert first.public.public_id == second.public.public_id
    assert serialize_portable_contract(first) == serialize_portable_contract(second)
    assert serialize_public_contract(first) == serialize_public_contract(second)
    assert first.private.reset_identity == second.private.reset_identity


def test_private_semantic_changes_change_full_identity_not_public_identity() -> None:
    baseline = compile_operational_episode(_episode())

    transition_episode = _episode()
    transition_episode.oracle.action_effects[0].set_state["order.status"] = "changed"
    transition = compile_operational_episode(transition_episode)

    budget_episode = _episode()
    budget_episode.oracle.max_cost = 10
    budget = compile_operational_episode(budget_episode)

    changed_evaluator = baseline.private.evaluator.model_copy(
        update={"semantics_id": "test-verifier-semantics-v2"}
    )
    evaluator_private = baseline.private.model_copy(
        update={"evaluator": changed_evaluator}
    )
    evaluator = PortableOperationalContract(
        schema_version=baseline.schema_version,
        public=baseline.public,
        private=evaluator_private,
    )

    assert transition.contract_id != baseline.contract_id
    assert budget.contract_id != baseline.contract_id
    assert evaluator.contract_id != baseline.contract_id
    assert transition.public.public_id == baseline.public.public_id
    assert budget.public.public_id == baseline.public.public_id
    assert evaluator.public.public_id == baseline.public.public_id


def test_public_serialization_has_no_oracle_material() -> None:
    contract = compile_operational_episode(_episode())
    encoded = serialize_public_contract(contract)
    text = encoded.decode("utf-8")
    payload = json.loads(text)

    assert "private" not in payload
    assert "contract_id" not in payload
    assert "evaluator_private" not in text
    for secret in (
        "HIDDEN-STATE-OMEGA",
        "TARGET-TRUTH-OMEGA",
        "HIDDEN-EFFECT-OMEGA",
        "EXPECTED-ANSWER-OMEGA",
        "PRIVATE-EVALUATOR-BYTES-OMEGA",
    ):
        assert secret not in text

    keys = _private_keys(payload)
    assert "oracle" not in keys
    assert "initial_state" not in keys
    assert "target_state" not in keys
    assert "action_effects" not in keys
    assert "required_evidence_ids" not in keys
    assert "evaluator" not in keys


def test_action_transition_semantics_cannot_be_dropped() -> None:
    episode = _episode()
    contract = compile_operational_episode(episode)
    tampered_private = contract.private.model_copy(update={"transitions": ()})
    tampered = contract.model_copy(update={"private": tampered_private})

    with pytest.raises(SemanticRoundTripError, match="private.transitions"):
        assert_operational_semantic_equivalence(episode, tampered)


def test_invariants_are_structured_and_cannot_become_prose_only() -> None:
    contract = compile_operational_episode(_episode())
    invariant = contract.private.semantic_state.invariants[0]

    assert invariant.trajectory_wide is True
    assert invariant.scope == "always"
    assert invariant.assertion.object_id == "order"
    assert invariant.assertion.field_name == "risk"
    assert invariant.assertion.comparison == "less_than_or_equal"
    assert invariant.assertion.expected_value == 1

    with pytest.raises(ValidationError):
        SemanticStateProjection(
            initial_state={},
            target_assertions=(),
            invariants=("risk should stay safe",),
        )


def test_budget_units_cannot_be_silently_merged() -> None:
    with pytest.raises(ValidationError, match="incompatible units"):
        PortableBudgetContract(
            limits=(
                PortableResourceLimit(
                    resource="cost",
                    unit="cost_units",
                    maximum=10,
                    exhaustion_rule="reject_if_post_charge_usage_gt_maximum",
                ),
                PortableResourceLimit(
                    resource="cost",
                    unit="calls",
                    maximum=10,
                    exhaustion_rule="reject_if_post_charge_usage_gt_maximum",
                ),
            )
        )


def test_unsupported_non_json_semantics_fail_closed() -> None:
    episode = _episode()
    episode.oracle.initial_state["tuple-valued-state"] = (1, 2)

    with pytest.raises(UnsupportedOperationalSemanticError) as captured:
        compile_operational_episode(episode)

    assert captured.value.code == "NON_JSON_SEMANTIC"
    assert captured.value.path == "episode.oracle.initial_state.tuple-valued-state"


def test_public_private_key_collision_fails_closed() -> None:
    episode = _episode()
    episode.task.metadata["target_state"] = {"leak": True}

    with pytest.raises(UnsupportedOperationalSemanticError) as captured:
        compile_operational_episode(episode)

    assert captured.value.code == "PUBLIC_PRIVATE_KEY_COLLISION"
    assert captured.value.path.endswith(".task.metadata.target_state")


def test_semantic_roundtrip_detects_action_schema_loss() -> None:
    episode = _episode()
    contract = compile_operational_episode(episode)
    first_action = contract.public.actions[0].model_copy(update={"input_schema": {}})
    tampered_public = contract.public.model_copy(
        update={"actions": (first_action, *contract.public.actions[1:])}
    )
    tampered = contract.model_copy(update={"public": tampered_public})

    with pytest.raises(SemanticRoundTripError, match="input_schema"):
        assert_operational_semantic_equivalence(episode, tampered)


def test_reset_identity_is_deterministic_and_bound_to_hidden_initial_state() -> None:
    baseline = compile_operational_episode(_episode())
    changed_episode = _episode()
    changed_episode.oracle.initial_state["order.risk"] = 1
    changed = compile_operational_episode(changed_episode)

    assert changed.private.reset_identity != baseline.private.reset_identity
    assert changed.contract_id != baseline.contract_id
    assert changed.public.public_id == baseline.public.public_id


def test_models_are_frozen_at_the_contract_boundary() -> None:
    contract = compile_operational_episode(_episode())

    with pytest.raises(ValidationError):
        contract.public.objective = "mutated"


def test_identity_bearing_json_values_are_recursively_immutable() -> None:
    episode = _episode()
    episode.task.metadata["nested"] = {"values": [1, 2]}
    contract = compile_operational_episode(episode)
    original_id = contract.contract_id
    original_public_id = contract.public.public_id
    original_bytes = serialize_portable_contract(contract)

    with pytest.raises(TypeError, match="immutable"):
        contract.public.task_metadata["new"] = "mutation"
    with pytest.raises(TypeError, match="immutable"):
        contract.public.task_metadata["nested"]["new"] = "mutation"
    with pytest.raises(TypeError):
        contract.public.task_metadata["nested"]["values"][0] = 9
    with pytest.raises(TypeError, match="immutable"):
        contract.private.semantic_state.initial_state["order.status"] = "changed"

    assert contract.contract_id == original_id
    assert contract.public.public_id == original_public_id
    assert serialize_portable_contract(contract) == original_bytes
