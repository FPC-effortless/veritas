import json

from investigation_world.operational.models import (
    ActionKind,
    AssertionComparison,
    EpisodeSubmission,
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
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.portable_contract import (
    PortableOperationalContract,
    PortablePublicContract,
    compile_operational_episode,
)
from investigation_world.portable_runtime import (
    PortableInvocationKind,
    PortableOperationalRuntime,
    PortableRuntimeFailureCode,
    PortableStepRequest,
)


def _episode(*, max_cost: int = 10, max_tool_calls: int = 8) -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="portable-runtime-episode-001",
        world_id="portable-runtime-world-001",
        task=TaskContract(
            task_id="portable-runtime-task-001",
            world_id="portable-runtime-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve the valid order without violating the risk control.",
            role="operations_controller",
            permitted_systems=["ERP"],
            available_actions=[
                PublicActionSpec(
                    name="prepare_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Prepare the order for approval.",
                    parameter_names=[],
                    cost=1,
                ),
                PublicActionSpec(
                    name="approve_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Approve a prepared order.",
                    parameter_names=["order_id", "note"],
                    cost=2,
                ),
                PublicActionSpec(
                    name="delete_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Delete an order.",
                    parameter_names=["order_id"],
                    cost=1,
                ),
            ],
            constraints=["Keep order risk at or below one."],
            success_description="The order is approved after preparation.",
            metadata={"fixture": "portable-runtime"},
        ),
        records=[
            OperationalRecord(
                record_id="record-001",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={"status": "pending", "risk": 0},
                searchable_text="pending order normal risk",
                source_authority="authoritative",
                freshness="current",
            )
        ],
        oracle=HiddenOracle(
            task_id="portable-runtime-task-001",
            initial_state={
                "order.status": "pending",
                "order.risk": 0,
                "evaluator.secret": "PRIVATE-RUNTIME-OMEGA",
            },
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value="approved",
                )
            ],
            invariants=[
                OperationalInvariant(
                    invariant_id="risk-safe",
                    description="Risk remains bounded.",
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
            required_action_order=["prepare_order", "approve_order"],
            forbidden_actions=["delete_order"],
            required_evidence_ids=["record-001"],
            action_effects=[
                HiddenActionEffect(
                    action_name="prepare_order",
                    required_state=[
                        StateAssertion(
                            object_id="order",
                            field_name="status",
                            expected_value="pending",
                        )
                    ],
                    set_state={"order.status": "ready"},
                    observable_result={"accepted": True, "status": "ready"},
                ),
                HiddenActionEffect(
                    action_name="approve_order",
                    required_parameters={"order_id": "ORDER-001"},
                    required_state=[
                        StateAssertion(
                            object_id="order",
                            field_name="status",
                            expected_value="ready",
                        )
                    ],
                    required_prior_actions=["prepare_order"],
                    set_state={"order.status": "approved"},
                    observable_result={
                        "accepted": True,
                        "receipt": "approval-recorded",
                    },
                    blocked_observable_result={
                        "accepted": False,
                        "reason": "order_not_ready",
                    },
                ),
                HiddenActionEffect(
                    action_name="delete_order",
                    required_parameters={"order_id": "ORDER-001"},
                    set_state={"order.risk": 5},
                    observable_result={"accepted": True},
                    forbidden=True,
                    consequence_severity=1.0,
                ),
            ],
            max_cost=max_cost,
            max_tool_calls=max_tool_calls,
            metadata={"expected_answer": "PRIVATE-ANSWER-OMEGA"},
        ),
        metadata={"public_episode": True},
    )


def _runtime(
    *,
    max_cost: int = 10,
    max_tool_calls: int = 8,
) -> PortableOperationalRuntime:
    return PortableOperationalRuntime(
        compile_operational_episode(
            _episode(max_cost=max_cost, max_tool_calls=max_tool_calls)
        )
    )


def _optional_note_contract() -> PortableOperationalContract:
    baseline = compile_operational_episode(_episode())
    public_payload = baseline.public.model_dump(
        mode="python",
        exclude={"public_id"},
    )
    actions = list(public_payload["actions"])
    approve = dict(actions[1])
    approve["input_schema"] = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["order_id"],
        "additionalProperties": False,
    }
    approve["additional_parameters_allowed"] = False
    actions[1] = approve
    public_payload["actions"] = tuple(actions)
    public = PortablePublicContract(**public_payload)
    return PortableOperationalContract(
        schema_version=baseline.schema_version,
        public=public,
        private=baseline.private,
    )


def _budget_map(
    runtime: PortableOperationalRuntime,
) -> dict[str, tuple[int, int]]:
    return {
        item.resource: (item.used, item.remaining)
        for item in runtime.budget_state().resources
    }


def test_same_task_and_seed_reset_is_deterministic() -> None:
    runtime = _runtime()
    first = runtime.reset(seed=17)
    runtime.step("prepare_order")
    second = runtime.reset(seed=17)

    assert second.state_digest == first.state_digest
    assert second.observation == first.observation
    assert _budget_map(runtime) == {
        "cost": (0, 10),
        "tool_calls": (0, 8),
    }


def test_public_state_and_reset_result_do_not_expose_evaluator_private_state() -> None:
    runtime = _runtime()
    reset = runtime.reset(seed=5)
    encoded = reset.model_dump_json()
    public_encoded = json.dumps(runtime.public_state(), sort_keys=True)

    for secret in (
        "PRIVATE-RUNTIME-OMEGA",
        "PRIVATE-ANSWER-OMEGA",
        "evaluator.secret",
    ):
        assert secret not in encoded
        assert secret not in public_encoded
    assert "oracle" not in public_encoded
    assert "initial_state" not in public_encoded


def test_invalid_action_and_invalid_input_are_structured_and_non_mutating() -> None:
    runtime = _runtime()
    initial = runtime.reset(seed=1)
    initial_budget = _budget_map(runtime)

    unknown = runtime.step("not_a_real_action")
    missing = runtime.step("approve_order", {"order_id": "ORDER-001"})

    assert unknown.failure is not None
    assert unknown.failure.code == PortableRuntimeFailureCode.INVALID_ACTION
    assert missing.failure is not None
    assert missing.failure.code == PortableRuntimeFailureCode.INVALID_ACTION_INPUT
    assert unknown.state_digest == initial.state_digest
    assert missing.state_digest == initial.state_digest
    assert _budget_map(runtime) == initial_budget


def test_precondition_rejection_does_not_mutate_state() -> None:
    runtime = _runtime()
    initial = runtime.reset(seed=2)

    result = runtime.step(
        "approve_order",
        {"order_id": "ORDER-001", "note": "approve"},
    )

    assert result.failure is not None
    assert result.failure.code == PortableRuntimeFailureCode.PRECONDITION_REJECTED
    assert result.observation == {
        "action": "approve_order",
        "system": "ERP",
        "submitted": True,
        "accepted": False,
        "reason": "order_not_ready",
    }
    assert result.state_digest == initial.state_digest
    assert result.terminated is False
    assert result.truncated is False
    assert "state:" not in result.model_dump_json()
    assert "prior_action:" not in result.model_dump_json()


def test_budget_exhaustion_is_explicit_truncation_not_termination() -> None:
    runtime = _runtime(max_cost=1)
    initial = runtime.reset(seed=3)

    result = runtime.step(
        "approve_order",
        {"order_id": "ORDER-001", "note": "approve"},
    )

    assert result.failure is not None
    assert result.failure.code == PortableRuntimeFailureCode.BUDGET_EXHAUSTED
    assert result.terminated is False
    assert result.truncated is True
    assert result.reward is None
    assert result.state_digest == initial.state_digest
    assert result.budget_status.exhausted is True
    assert "cost" in result.budget_status.exhausted_resources

    scored = runtime.submit({"evidence_ids": ["record-001"]})
    assert scored.terminated is False
    assert scored.truncated is True
    assert scored.reward is not None
    assert scored.reward_components is not None


def test_verifier_component_vector_and_aggregate_match_native_runtime() -> None:
    episode = _episode()
    portable = PortableOperationalRuntime(compile_operational_episode(episode))
    native = OperationalRuntime(_episode())
    portable.reset(seed=11)

    assert portable.step("prepare_order").failure is None
    native.act("prepare_order")
    arguments = {"order_id": "ORDER-001", "note": "approve"}
    assert portable.step("approve_order", arguments).failure is None
    native.act("approve_order", **arguments)

    submission = {
        "conclusion": "Order approved.",
        "claimed_state": {"order.status": "approved"},
        "evidence_ids": ["record-001"],
        "confidence": 0.9,
    }
    portable_result = portable.submit(submission)
    native_result = native.submit(EpisodeSubmission(**submission))

    assert portable_result.terminated is True
    assert portable_result.truncated is False
    assert portable_result.failure is None
    assert portable_result.reward == native_result.overall_reward
    assert portable_result.reward_components is not None
    assert portable_result.reward_components.model_dump() == {
        "outcome": native_result.outcome,
        "state": native_result.state,
        "constraints": native_result.constraints,
        "side_effects": native_result.side_effects,
        "process": native_result.process,
        "efficiency": native_result.efficiency,
        "evidence": native_result.evidence,
    }


def test_reset_after_completed_run_clears_state_events_and_budget() -> None:
    runtime = _runtime()
    initial = runtime.reset(seed=23)
    runtime.step("prepare_order")
    runtime.step(
        "approve_order",
        {"order_id": "ORDER-001", "note": "approve"},
    )
    completed = runtime.submit({"evidence_ids": ["record-001"]})
    assert completed.terminated is True

    reset = runtime.reset(seed=23)
    assert reset.state_digest == initial.state_digest
    assert _budget_map(runtime) == {
        "cost": (0, 10),
        "tool_calls": (0, 8),
    }

    rejected = runtime.step(
        "approve_order",
        {"order_id": "ORDER-001", "note": "approve"},
    )
    assert rejected.failure is not None
    assert rejected.failure.code == PortableRuntimeFailureCode.PRECONDITION_REJECTED


def test_step_dispatches_public_retrieval_operations_through_native_runtime() -> None:
    runtime = _runtime()
    initial = runtime.reset(seed=29)
    result = runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind.OPERATION,
            name="search",
            arguments={"system": "ERP", "query": "pending order"},
        )
    )

    assert result.failure is None
    assert len(result.observation) == 1
    assert result.observation[0]["record_id"] == "record-001"
    assert result.state_digest == initial.state_digest
    assert _budget_map(runtime) == {
        "cost": (1, 9),
        "tool_calls": (1, 7),
    }


def test_portable_schema_controls_optional_and_typed_action_inputs() -> None:
    runtime = PortableOperationalRuntime(_optional_note_contract())
    runtime.reset(seed=31)
    assert runtime.step("prepare_order").failure is None
    before = runtime.state_digest()
    before_budget = _budget_map(runtime)

    wrong_type = runtime.step(
        "approve_order",
        {"order_id": "ORDER-001", "note": 7},
    )
    assert wrong_type.failure is not None
    assert wrong_type.failure.code == PortableRuntimeFailureCode.INVALID_ACTION_INPUT
    assert wrong_type.state_digest == before
    assert _budget_map(runtime) == before_budget

    accepted = runtime.step("approve_order", {"order_id": "ORDER-001"})
    assert accepted.failure is None
    assert accepted.observation["accepted"] is True


def test_verify_is_submit_alias_and_post_terminal_step_is_rejected() -> None:
    runtime = _runtime()
    runtime.reset(seed=37)
    result = runtime.verify({"evidence_ids": ["record-001"]})
    assert result.terminated is True
    assert result.truncated is False

    after = runtime.step("prepare_order")
    assert after.failure is not None
    assert after.failure.code == PortableRuntimeFailureCode.EPISODE_TERMINATED
