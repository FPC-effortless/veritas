from __future__ import annotations

import copy
import hashlib
import json
import random
from pathlib import Path

import pytest

from investigation_world.integrations.woyengi import (
    WorldBundleAdapterError,
    adapt_pinned_world_bundle_fixture,
    compile_pinned_world_bundle_contract,
)
from investigation_world.integrations.woyengi.action_schema import (
    WORLD_BUNDLE_ACTION_SCHEMA_KIND,
    _action_schema_bindings,
    _assert_action_schema_projection,
    _compile_action_schema_contract,
)
from investigation_world.operational.runtime import OperationalRuntime
from investigation_world.portable_contract import (
    compile_operational_episode,
    serialize_public_contract,
)


PINNED_SHA256 = "62172d94b6e5d34774714b3c3da7c3fc61d71c61d7798f71d5a94a8243177a86"
LEGACY_SHA256 = "3577aa29266dac59921c31e65d22ad657c4b7a9191011e9f5448aed32781e10b"
PINNED_ARTIFACT_ID = (
    "world-bundle-artifact:sha256:41e6c9b1b583112161d244de00d470a6fa5155f709c74782eb9117a060981462"
)
FIXTURE = Path(__file__).parent / "fixtures" / "veritas-adapter-v0.1.json"
LEGACY_FIXTURE = (
    Path(__file__).parent / "fixtures" / "veritas-adapter-pre-action-schema-v0.1.json"
)


def _root() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _schema_member(root: dict, action_ref: str) -> dict:
    return next(
        member
        for member in root["members"]
        if member.get("kind") == WORLD_BUNDLE_ACTION_SCHEMA_KIND
        and member.get("payload", {}).get("actionRef") == action_ref
    )


def _episode():
    return adapt_pinned_world_bundle_fixture(
        FIXTURE.read_bytes(),
        expected_sha256=PINNED_SHA256,
    )


def test_exact_a1_fixture_pin_and_action_schema_projection():
    raw = FIXTURE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINNED_SHA256

    root = json.loads(raw)
    assert root["artifactId"] == PINNED_ARTIFACT_ID
    contract = compile_pinned_world_bundle_contract(
        raw,
        expected_sha256=PINNED_SHA256,
    )

    actions = {action.name: action for action in contract.public.actions}
    request = actions["world-action:request-approval"]
    source = _schema_member(root, request.name)["payload"]

    assert tuple(request.parameter_names) == ("requested_role", "supplier_id")
    assert request.input_schema == source["inputSchema"]
    assert request.output_schema == source["outputSchema"]
    assert request.input_schema["required"] == ["requested_role", "supplier_id"]
    assert request.input_schema["properties"]["requested_role"] == {"type": "string"}
    assert request.output_schema["required"] == ["evidence_id", "status"]
    assert request.additional_parameters_allowed is False
    assert request.missing_parameter_behavior == "reject_missing_json_schema_required_properties"


def test_required_optional_and_types_come_only_from_public_schema():
    episode = _episode()
    root = _root()
    request_schema = _schema_member(root, "world-action:request-approval")["payload"]["inputSchema"]

    # The action still advertises both accepted parameter names. Only the schema's
    # explicit required set determines which one is mandatory, and the declared type
    # is consumed as-is rather than inferred from the parameter name.
    request_schema["required"] = ["supplier_id"]
    request_schema["properties"]["requested_role"] = {"type": "integer"}

    contract = _compile_action_schema_contract(episode, root)
    request = next(
        action
        for action in contract.public.actions
        if action.name == "world-action:request-approval"
    )

    assert request.parameter_names == ("requested_role", "supplier_id")
    assert request.input_schema["required"] == ["supplier_id"]
    assert request.input_schema["properties"]["requested_role"] == {"type": "integer"}
    assert request.additional_parameters_allowed is False


def test_duplicate_action_schema_is_rejected():
    root = _root()
    root["members"].append(
        copy.deepcopy(_schema_member(root, "world-action:inspect-supplier"))
    )

    with pytest.raises(WorldBundleAdapterError, match="duplicate ACTION_SCHEMA"):
        _action_schema_bindings(root)


def test_unknown_action_ref_is_rejected():
    root = _root()
    member = _schema_member(root, "world-action:inspect-supplier")
    member["payload"]["actionRef"] = "world-action:unknown"

    with pytest.raises(WorldBundleAdapterError, match="unknown public action"):
        _action_schema_bindings(root)


def test_missing_schema_for_executable_action_is_rejected():
    root = _root()
    root["members"] = [
        member
        for member in root["members"]
        if not (
            member.get("kind") == WORLD_BUNDLE_ACTION_SCHEMA_KIND
            and member.get("payload", {}).get("actionRef")
            == "world-action:activate-supplier"
        )
    ]

    with pytest.raises(WorldBundleAdapterError, match="has no ACTION_SCHEMA binding"):
        _action_schema_bindings(root)


def test_type_parameter_surface_mismatch_is_rejected():
    root = _root()
    input_schema = _schema_member(
        root, "world-action:request-approval"
    )["payload"]["inputSchema"]
    del input_schema["properties"]["requested_role"]
    input_schema["required"] = ["supplier_id"]

    with pytest.raises(WorldBundleAdapterError, match="must exactly match"):
        _action_schema_bindings(root)


def test_output_schema_cannot_expose_hidden_state():
    root = _root()
    output_schema = _schema_member(
        root, "world-action:request-approval"
    )["payload"]["outputSchema"]
    output_schema["properties"]["hidden_state"] = {"type": "string"}

    with pytest.raises(WorldBundleAdapterError, match="evaluator-private schema property"):
        _action_schema_bindings(root)


def test_malformed_or_unsupported_upstream_schema_fails_closed():
    bad_contract = _root()
    member = _schema_member(bad_contract, "world-action:inspect-supplier")
    member["payload"]["contract"] = "woyengi.world-bundle.action-schema.v0.2"
    with pytest.raises(WorldBundleAdapterError, match="unsupported value"):
        _action_schema_bindings(bad_contract)

    unsupported_keyword = _root()
    schema = _schema_member(
        unsupported_keyword, "world-action:inspect-supplier"
    )["payload"]["inputSchema"]
    schema["oneOf"] = []
    with pytest.raises(WorldBundleAdapterError, match="unsupported JSON Schema keyword oneOf"):
        _action_schema_bindings(unsupported_keyword)


def test_private_schema_values_are_rejected_even_when_shape_is_public():
    root = _root()
    output_schema = _schema_member(
        root, "world-action:request-approval"
    )["payload"]["outputSchema"]
    output_schema["properties"]["status"] = {
        "type": "string",
        "privateEffect": {"type": "string"},
    }

    with pytest.raises(WorldBundleAdapterError, match="unsupported JSON Schema keyword"):
        _action_schema_bindings(root)


def test_public_portable_contract_does_not_leak_private_evaluator_material():
    contract = compile_pinned_world_bundle_contract(
        FIXTURE.read_bytes(),
        expected_sha256=PINNED_SHA256,
    )
    public_text = serialize_public_contract(contract).decode("utf-8")

    for private_value in (
        "target-assertion:supplier-active",
        "evaluator-invariant:approval-ledger-consistency",
        "hidden-effect:approval-transition",
        "evaluator-evidence:approval-ledger",
        "private://approval-ledger/supplier-42",
        PINNED_ARTIFACT_ID,
        PINNED_SHA256,
    ):
        assert private_value not in public_text


def test_portable_contract_compilation_is_deterministic_and_replay_stays_deterministic():
    first_contract = compile_pinned_world_bundle_contract(
        FIXTURE.read_bytes(),
        expected_sha256=PINNED_SHA256,
    )
    second_contract = compile_pinned_world_bundle_contract(
        FIXTURE.read_bytes(),
        expected_sha256=PINNED_SHA256,
    )
    assert first_contract.canonical_bytes() == second_contract.canonical_bytes()
    assert first_contract.contract_id == second_contract.contract_id
    assert first_contract.public.public_id == second_contract.public.public_id

    first_episode = _episode()
    second_episode = _episode()
    seed = 2718
    action_names = [
        "world-action:inspect-supplier",
        "world-action:request-approval",
        "world-action:activate-supplier",
    ]
    first_rng = random.Random(seed)
    second_rng = random.Random(seed)
    assert [first_rng.choice(action_names) for _ in range(8)] == [
        second_rng.choice(action_names) for _ in range(8)
    ]

    sequence = [
        ("world-action:inspect-supplier", {"supplier_id": "supplier-42"}),
        (
            "world-action:request-approval",
            {"requested_role": "finance-approver", "supplier_id": "supplier-42"},
        ),
        ("world-action:activate-supplier", {"supplier_id": "supplier-42"}),
    ]
    first_runtime = OperationalRuntime(first_episode)
    second_runtime = OperationalRuntime(second_episode)
    first_results = [first_runtime.act(name, **parameters) for name, parameters in sequence]
    second_results = [second_runtime.act(name, **parameters) for name, parameters in sequence]
    assert first_results == second_results
    assert first_runtime.trace() == second_runtime.trace()


def test_projection_falsifier_detects_schema_loss_after_canonical_compilation():
    episode = _episode()
    root = _root()
    bindings = _action_schema_bindings(root)
    baseline = compile_operational_episode(episode)
    contract = _compile_action_schema_contract(episode, root)

    first = contract.public.actions[0]
    broken = first.model_copy(update={"output_schema": {"type": "string"}})
    broken_public = contract.public.model_copy(
        update={"actions": (broken, *contract.public.actions[1:])}
    )
    broken_contract = contract.model_copy(update={"public": broken_public})

    with pytest.raises(WorldBundleAdapterError, match="output schema changed"):
        _assert_action_schema_projection(
            episode,
            baseline,
            broken_contract,
            bindings,
        )


def test_pre_action_schema_fixture_compatibility_is_explicit_and_episode_only():
    legacy_raw = LEGACY_FIXTURE.read_bytes()
    assert hashlib.sha256(legacy_raw).hexdigest() == LEGACY_SHA256

    # Existing v0.1 episode adaptation remains intentionally compatible.
    legacy_episode = adapt_pinned_world_bundle_fixture(
        legacy_raw,
        expected_sha256=LEGACY_SHA256,
    )
    assert legacy_episode.task.objective == (
        "Activate supplier 42 only after verified finance approval."
    )

    # The new typed portable path never silently invents schemas for that old pin.
    with pytest.raises(WorldBundleAdapterError, match="has no ACTION_SCHEMA binding"):
        compile_pinned_world_bundle_contract(
            legacy_raw,
            expected_sha256=LEGACY_SHA256,
        )
