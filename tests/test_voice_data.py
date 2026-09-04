from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from investigation_world.commercial.voice_data import (
    ABCDLikeRecord,
    VoiceSourceProvenance,
    VoiceSourceUsePolicy,
    adapt_abcd_record,
    apply_schema_surface_variant,
    compile_voice_scenario,
)
from investigation_world.commercial.voice_qualification import (
    VoicePressure,
    VoiceScenarioFamily,
    qualification_submission,
)
from investigation_world.operational.runtime import OperationalRuntime


def _source(
    use_policy: VoiceSourceUsePolicy = VoiceSourceUsePolicy.COMMERCIAL_OK,
) -> VoiceSourceProvenance:
    return VoiceSourceProvenance(
        source_name="ABCD-shaped fixture",
        source_version="fixture-v1",
        record_id="abcd-fixture-001",
        source_uri="fixture://abcd/001",
        license_id="MIT",
        use_policy=use_policy,
        attribution_required=True,
    )


def _refund_record() -> dict[str, object]:
    return {
        "scenario_id": "abcd-refund-001",
        "flow": "refund_eligible",
        "utterance": "I need a refund for the order I placed yesterday.",
        "action_sequence": [
            "verify_identity",
            "issue_refund",
            "close_case",
        ],
        "locale": "en-US",
        "metadata": {"fixture": True},
    }


def _record_object_id(episode, record_type: str) -> str:
    return next(
        record.object_id
        for record in episode.records
        if record.record_type == record_type
    )


def test_abcd_adapter_and_compiler_are_deterministic() -> None:
    spec = adapt_abcd_record(
        _refund_record(),
        source=_source(),
        variant=0,
        pressure=VoicePressure.NORMAL,
    )

    first = compile_voice_scenario(spec, seed=73)
    second = compile_voice_scenario(spec, seed=73)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.task.domain.value == "enterprise_operations"
    assert first.metadata["source_scenario_id"] == "abcd-refund-001"
    assert first.metadata["voice_source_provenance"]["license_id"] == "MIT"
    assert first.metadata["voice_source_provenance"]["use_policy"] == "commercial_ok"


def test_public_payload_contains_source_context_but_not_oracle() -> None:
    spec = adapt_abcd_record(_refund_record(), source=_source())
    episode = compile_voice_scenario(spec)
    payload = episode.public_payload()
    serialized = json.dumps(payload, sort_keys=True)

    assert "oracle" not in payload
    assert "initial_state" not in serialized
    assert "canonical_action_mapping" not in serialized
    source_record = next(
        record
        for record in payload["records"]
        if record["record_type"] == "source_dialogue_context"
    )
    assert source_record["fields"]["customer_utterance"].startswith("I need a refund")
    assert source_record["provenance_ids"] == ["abcd-fixture-001"]


def test_abcd_adapter_rejects_unknown_or_mismatched_policy_actions() -> None:
    unknown = _refund_record()
    unknown["action_sequence"] = ["verify_identity", "wire_money", "close_case"]
    with pytest.raises(ValueError, match="unsupported source action"):
        adapt_abcd_record(unknown, source=_source())

    mismatched = _refund_record()
    mismatched["action_sequence"] = ["verify_identity", "close_case"]
    with pytest.raises(ValueError, match="trusted flow mapping"):
        adapt_abcd_record(mismatched, source=_source())

    unsupported = _refund_record()
    unsupported["flow"] = "unmapped_dataset_flow"
    with pytest.raises(ValueError, match="unsupported ABCD-style flow"):
        adapt_abcd_record(unsupported, source=_source())


def test_adapter_input_cannot_supply_hidden_truth_fields() -> None:
    poisoned = _refund_record()
    poisoned["expected_state"] = {"refund": "force_success"}

    with pytest.raises(ValidationError):
        ABCDLikeRecord.model_validate(poisoned)


def test_research_only_source_fails_closed_for_commercial_compile() -> None:
    spec = adapt_abcd_record(
        _refund_record(),
        source=_source(VoiceSourceUsePolicy.RESEARCH_ONLY),
    )

    with pytest.raises(ValueError, match="not authorized for commercial compilation"):
        compile_voice_scenario(spec)


def test_schema_variant_changes_public_action_ontology_not_semantics() -> None:
    base_spec = adapt_abcd_record(_refund_record(), source=_source())
    canonical = compile_voice_scenario(base_spec, seed=81)
    shifted_spec = apply_schema_surface_variant(
        base_spec,
        schema_variant="sgdx-style-v3",
        action_aliases={
            "verify_identity": "confirm_caller",
            "issue_refund": "credit_purchase",
            "close_case": "finish_interaction",
        },
        objective="Resolve the reimbursement request using the available service APIs.",
    )
    shifted = compile_voice_scenario(shifted_spec, seed=81)

    canonical_actions = {action.name for action in canonical.task.available_actions}
    shifted_actions = {action.name for action in shifted.task.available_actions}
    assert "verify_identity" in canonical_actions
    assert "verify_identity" not in shifted_actions
    assert {"confirm_caller", "credit_purchase", "finish_interaction"} <= shifted_actions

    assert canonical.oracle.initial_state == shifted.oracle.initial_state
    assert canonical.oracle.target_state == shifted.oracle.target_state
    assert canonical.oracle.invariants == shifted.oracle.invariants
    assert [effect.set_state for effect in canonical.oracle.action_effects] == [
        effect.set_state for effect in shifted.oracle.action_effects
    ]
    assert shifted.oracle.metadata["canonical_action_mapping"]["confirm_caller"] == (
        "verify_identity"
    )


def test_schema_shifted_refund_executes_through_same_verifier() -> None:
    spec = adapt_abcd_record(_refund_record(), source=_source())
    spec = apply_schema_surface_variant(
        spec,
        schema_variant="sgdx-style-v4",
        action_aliases={
            "verify_identity": "confirm_caller",
            "issue_refund": "credit_purchase",
            "close_case": "finish_interaction",
        },
    )
    episode = compile_voice_scenario(spec, seed=91)
    customer_id = _record_object_id(episode, "customer_account")
    order_id = _record_object_id(episode, "order")
    runtime = OperationalRuntime(episode)

    runtime.act("confirm_caller", customer_id=customer_id, method="otp")
    runtime.act("credit_purchase", order_id=order_id, amount_usd=80)
    runtime.act("finish_interaction", customer_id=customer_id)
    result = runtime.submit(qualification_submission(episode))

    assert result.outcome == 1.0
    assert result.state == 1.0
    assert result.constraints == 1.0
    assert result.side_effects == 1.0
    assert result.process == 1.0
    assert result.evidence == 1.0


def test_schema_aliases_fail_closed_on_unknown_or_colliding_actions() -> None:
    spec = adapt_abcd_record(_refund_record(), source=_source())
    unknown = apply_schema_surface_variant(
        spec,
        schema_variant="bad-unknown",
        action_aliases={"not_a_real_action": "other_name"},
    )
    with pytest.raises(ValueError, match="unknown actions"):
        compile_voice_scenario(unknown)

    collision = apply_schema_surface_variant(
        spec,
        schema_variant="bad-collision",
        action_aliases={"verify_identity": "issue_refund"},
    )
    with pytest.raises(ValueError, match="remain unique"):
        compile_voice_scenario(collision)


def test_private_authorized_source_can_compile_without_public_hidden_truth() -> None:
    source = VoiceSourceProvenance(
        source_name="Customer private workflow export",
        source_version="2026-09-04",
        record_id="customer-private-001",
        use_policy=VoiceSourceUsePolicy.AUTHORIZED_PRIVATE,
    )
    spec = adapt_abcd_record(_refund_record(), source=source)
    episode = compile_voice_scenario(spec)

    assert episode.metadata["voice_source_provenance"]["use_policy"] == (
        "authorized_private"
    )
    assert "oracle" not in episode.public_payload()
    assert spec.family == VoiceScenarioFamily.VALID_REFUND
