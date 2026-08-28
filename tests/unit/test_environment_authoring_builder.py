from __future__ import annotations

import pytest

from investigation_world.authoring import EnvironmentBuilder
from investigation_world.operational import (
    ActionKind,
    AssertionComparison,
    StateAssertion,
    WorldDomain,
)
from investigation_world.portable_contract import serialize_public_contract
from investigation_world.portable_runtime import (
    PortableInvocationKind,
    PortableOperationalRuntime,
    PortableStepRequest,
)


def _builder() -> EnvironmentBuilder:
    return (
        EnvironmentBuilder(
            name="supplier-approval",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve and activate the supplier without bypassing authority.",
            role="procurement operator",
        )
        .system("procurement")
        .action(
            "request_approval",
            kind=ActionKind.ESCALATE,
            system="procurement",
            description="Request finance approval.",
            parameters=("supplier_id",),
        )
        .action(
            "activate_supplier",
            kind=ActionKind.WRITE,
            system="procurement",
            description="Activate an approved supplier.",
            parameters=("supplier_id",),
        )
        .record(
            "evidence:approval-decision",
            system="procurement",
            record_type="approval",
            object_id="supplier-42",
            fields={"status": "pending"},
            searchable_text="Supplier approval decision",
        )
        .initial_state(
            **{
                "supplier-42.status": "pending",
                "supplier-42.approved": False,
            }
        )
        .transition(
            "request_approval",
            required_parameters={"supplier_id": "supplier-42"},
            set_state={"supplier-42.approved": True},
            observable_result={"approval": "granted"},
        )
        .transition(
            "activate_supplier",
            required_parameters={"supplier_id": "supplier-42"},
            required_state=(
                StateAssertion(
                    object_id="supplier-42",
                    field_name="approved",
                    expected_value=True,
                ),
            ),
            required_prior_actions=("request_approval",),
            set_state={"supplier-42.status": "active"},
            observable_result={"status": "active"},
            blocked_observable_result={"status": "approval_required"},
        )
        .target("supplier-42", "status", "active")
        .invariant(
            "approval-before-activation",
            description="Supplier activation requires approval.",
            object_id="supplier-42",
            field_name="approved",
            expected_value=True,
            comparison=AssertionComparison.EQUAL,
            scope="final",
        )
        .require_action("request_approval")
        .require_action("activate_supplier")
        .require_order("request_approval", "activate_supplier")
        .require_evidence("evidence:approval-decision")
        .constraint("Do not activate the supplier before approval.")
        .success("The supplier is active with approval preserved.")
        .budgets(max_cost=10, max_tool_calls=8)
        .metadata(
            public={"capability": "authority-sensitive-procurement"},
            private={"PRIVATE_MARKER": "operator-only"},
        )
    )


def test_builder_produces_valid_deterministic_operational_episode() -> None:
    first = _builder().build()
    second = _builder().build()

    assert first == second
    assert first.world_id.startswith("WORLD-")
    assert first.task.task_id.startswith("TASK-")
    assert first.episode_id.startswith("EP-")
    assert first.task.permitted_systems == ["procurement"]


def test_builder_public_payload_does_not_expose_private_metadata() -> None:
    episode = _builder().build()
    payload = episode.public_payload()

    assert "oracle" not in payload
    assert "PRIVATE_MARKER" not in str(payload)
    assert "PRIVATE_MARKER" in episode.oracle.metadata


def test_builder_compiles_through_canonical_portable_contract() -> None:
    contract = _builder().compile()
    public_bytes = serialize_public_contract(contract)

    assert contract.public.objective.startswith("Approve and activate")
    assert b"PRIVATE_MARKER" not in public_bytes
    assert contract.private.process.required_action_order == (
        "request_approval",
        "activate_supplier",
    )


def test_builder_runtime_semantics_delegate_to_existing_portable_runtime() -> None:
    contract = _builder().compile()
    runtime = PortableOperationalRuntime(contract)
    reset = runtime.reset(seed=7)

    blocked = runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind.ACTION,
            name="activate_supplier",
            arguments={"supplier_id": "supplier-42"},
        )
    )
    approved = runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind.ACTION,
            name="request_approval",
            arguments={"supplier_id": "supplier-42"},
        )
    )
    activated = runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind.ACTION,
            name="activate_supplier",
            arguments={"supplier_id": "supplier-42"},
        )
    )

    assert reset.state_digest
    assert blocked.observation["result"]["status"] == "approval_required"
    assert approved.observation["result"]["approval"] == "granted"
    assert activated.observation["result"]["status"] == "active"


def test_action_requires_declared_system() -> None:
    builder = EnvironmentBuilder(
        name="invalid",
        domain=WorldDomain.ENTERPRISE_OPERATIONS,
        objective="Do work.",
        role="operator",
    )

    with pytest.raises(ValueError, match="undeclared system"):
        builder.action(
            "do_work",
            kind=ActionKind.WRITE,
            system="missing",
            description="Do work.",
        )


def test_transition_cannot_reference_unknown_action() -> None:
    builder = EnvironmentBuilder(
        name="invalid",
        domain=WorldDomain.ENTERPRISE_OPERATIONS,
        objective="Do work.",
        role="operator",
    ).system("system")

    with pytest.raises(ValueError, match="undeclared action"):
        builder.transition("missing")


def test_required_evidence_must_be_agent_observable_record() -> None:
    builder = (
        EnvironmentBuilder(
            name="invalid",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Do work.",
            role="operator",
        )
        .system("system")
        .action(
            "do_work",
            kind=ActionKind.WRITE,
            system="system",
            description="Do work.",
        )
    )

    with pytest.raises(ValueError, match="undeclared record"):
        builder.require_evidence("private://hidden")


def test_required_action_cannot_become_forbidden() -> None:
    builder = (
        EnvironmentBuilder(
            name="invalid",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Do work.",
            role="operator",
        )
        .system("system")
        .action(
            "do_work",
            kind=ActionKind.WRITE,
            system="system",
            description="Do work.",
        )
        .require_action("do_work")
    )

    with pytest.raises(ValueError, match="both required and forbidden"):
        builder.forbid_action("do_work")
