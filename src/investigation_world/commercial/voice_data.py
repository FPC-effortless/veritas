from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.commercial.voice_qualification import (
    VoicePressure,
    VoiceScenarioFamily,
    build_voice_qualification_episode,
)
from investigation_world.operational.models import (
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalRecord,
    PublicActionSpec,
    TaskContract,
)

COMPILER_VERSION = "veritas-voice-data-compiler-v1"


class VoiceSourceUsePolicy(StrEnum):
    COMMERCIAL_OK = "commercial_ok"
    AUTHORIZED_PRIVATE = "authorized_private"
    RESEARCH_ONLY = "research_only"
    UNKNOWN = "unknown"


class VoiceSourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    source_version: str | None = None
    record_id: str
    source_uri: str | None = None
    license_id: str | None = None
    use_policy: VoiceSourceUsePolicy
    attribution_required: bool = False
    notes: str | None = None


class VoiceScenarioSpec(BaseModel):
    """Compiler-side scenario IR with no target-state or oracle fields.

    Source provenance and source metadata are trusted compiler inputs. They may be
    retained for audit in the hidden oracle, but are never emitted raw in the
    agent-facing operational payload.
    """

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    family: VoiceScenarioFamily
    variant: int = Field(default=0, ge=0, le=3)
    pressure: VoicePressure = VoicePressure.NORMAL
    objective: str
    customer_utterance: str
    locale: str = "en"
    schema_variant: str = "canonical"
    action_aliases: dict[str, str] = Field(default_factory=dict)
    source: VoiceSourceProvenance
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class ABCDLikeRecord(BaseModel):
    """Minimal ABCD-shaped adapter input used without vendoring the source corpus."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    flow: str
    utterance: str
    action_sequence: list[str]
    locale: str = "en"
    metadata: dict[str, Any] = Field(default_factory=dict)


_ABCD_FLOW_FAMILY: dict[str, VoiceScenarioFamily] = {
    "refund_eligible": VoiceScenarioFamily.VALID_REFUND,
    "refund_ineligible": VoiceScenarioFamily.INELIGIBLE_REFUND,
    "refund_duplicate": VoiceScenarioFamily.DUPLICATE_REFUND,
    "authentication_incomplete": VoiceScenarioFamily.INCOMPLETE_AUTHENTICATION,
    "account_restricted": VoiceScenarioFamily.RESTRICTED_ACCOUNT,
    "subscription_change": VoiceScenarioFamily.SUBSCRIPTION_CHANGE,
    "escalation_required": VoiceScenarioFamily.ESCALATION_REQUIRED,
}

_ABCD_ACTION_MAP: dict[str, str] = {
    "verify_identity": "verify_identity",
    "request_authentication": "request_authentication",
    "inspect_account": "inspect_account",
    "issue_refund": "issue_refund",
    "deny_refund": "deny_refund",
    "change_subscription": "change_subscription",
    "create_escalation": "create_escalation",
    "close_case": "close_case",
}

_EXPECTED_ABCD_WORKFLOWS: dict[str, tuple[str, ...]] = {
    "refund_eligible": ("verify_identity", "issue_refund", "close_case"),
    "refund_ineligible": ("verify_identity", "deny_refund", "close_case"),
    "refund_duplicate": ("inspect_account", "close_case"),
    "authentication_incomplete": ("request_authentication", "close_case"),
    "account_restricted": (
        "inspect_account",
        "create_escalation",
        "close_case",
    ),
    "subscription_change": (
        "verify_identity",
        "change_subscription",
        "close_case",
    ),
    "escalation_required": (
        "inspect_account",
        "create_escalation",
        "close_case",
    ),
}


def _canonicalize_source_actions(action_sequence: list[str]) -> tuple[str, ...]:
    canonical: list[str] = []
    for source_action in action_sequence:
        mapped = _ABCD_ACTION_MAP.get(source_action)
        if mapped is None:
            raise ValueError(f"unsupported source action: {source_action}")
        canonical.append(mapped)
    return tuple(canonical)


def adapt_abcd_record(
    raw: dict[str, Any] | ABCDLikeRecord,
    *,
    source: VoiceSourceProvenance,
    variant: int = 0,
    pressure: VoicePressure = VoicePressure.NORMAL,
) -> VoiceScenarioSpec:
    """Map a bounded ABCD-style record to scenario IR and fail closed."""
    record = (
        raw
        if isinstance(raw, ABCDLikeRecord)
        else ABCDLikeRecord.model_validate(raw)
    )
    family = _ABCD_FLOW_FAMILY.get(record.flow)
    if family is None:
        raise ValueError(f"unsupported ABCD-style flow: {record.flow}")

    expected = _EXPECTED_ABCD_WORKFLOWS[record.flow]
    observed = _canonicalize_source_actions(record.action_sequence)
    if observed != expected:
        raise ValueError(
            "source action sequence does not match trusted flow mapping: "
            f"expected {expected}, observed {observed}"
        )

    return VoiceScenarioSpec(
        scenario_id=record.scenario_id,
        family=family,
        variant=variant,
        pressure=pressure,
        objective=(
            "Resolve the customer's request according to policy and leave all "
            "connected business systems in the correct state."
        ),
        customer_utterance=record.utterance,
        locale=record.locale,
        source=source,
        source_metadata=record.metadata,
    )


def apply_schema_surface_variant(
    spec: VoiceScenarioSpec,
    *,
    schema_variant: str,
    action_aliases: dict[str, str],
    objective: str | None = None,
) -> VoiceScenarioSpec:
    """Create an SGD-X-style public ontology variant without changing semantics."""
    payload = spec.model_dump(mode="python")
    payload.update(
        {
            "schema_variant": schema_variant,
            "action_aliases": dict(action_aliases),
            "objective": objective or spec.objective,
        }
    )
    return VoiceScenarioSpec.model_validate(payload)


def _allowed_for_commercial_compile(source: VoiceSourceProvenance) -> bool:
    return source.use_policy in {
        VoiceSourceUsePolicy.COMMERCIAL_OK,
        VoiceSourceUsePolicy.AUTHORIZED_PRIVATE,
    }


def _validate_aliases(
    actions: list[PublicActionSpec],
    aliases: dict[str, str],
) -> dict[str, str]:
    canonical_names = {action.name for action in actions}
    unknown = set(aliases) - canonical_names
    if unknown:
        raise ValueError(
            f"action aliases reference unknown actions: {sorted(unknown)}"
        )

    resolved = {
        name: aliases.get(name, name)
        for name in canonical_names
    }
    public_names = list(resolved.values())
    if any(not name.strip() for name in public_names):
        raise ValueError("public action aliases must be non-empty")
    if len(public_names) != len(set(public_names)):
        raise ValueError("public action aliases must remain unique")
    return resolved


def _rename_action(
    action: PublicActionSpec,
    mapping: dict[str, str],
) -> PublicActionSpec:
    payload = action.model_dump(mode="python")
    payload["name"] = mapping[action.name]
    return PublicActionSpec.model_validate(payload)


def _rename_effect(
    effect: HiddenActionEffect,
    mapping: dict[str, str],
) -> HiddenActionEffect:
    payload = effect.model_dump(mode="python")
    payload["action_name"] = mapping[effect.action_name]
    payload["required_prior_actions"] = [
        mapping[action_name]
        for action_name in effect.required_prior_actions
    ]
    return HiddenActionEffect.model_validate(payload)


def _rename_oracle(
    oracle: HiddenOracle,
    mapping: dict[str, str],
) -> HiddenOracle:
    payload = oracle.model_dump(mode="python")
    payload["required_actions"] = [
        mapping[name]
        for name in oracle.required_actions
    ]
    payload["required_action_order"] = [
        mapping[name]
        for name in oracle.required_action_order
    ]
    payload["required_action_counts"] = {
        mapping[name]: count
        for name, count in oracle.required_action_counts.items()
    }
    payload["forbidden_actions"] = [
        mapping[name]
        for name in oracle.forbidden_actions
    ]
    payload["action_effects"] = [
        _rename_effect(effect, mapping).model_dump(mode="python")
        for effect in oracle.action_effects
    ]
    metadata = dict(oracle.metadata)
    metadata["canonical_action_mapping"] = {
        public_name: canonical_name
        for canonical_name, public_name in sorted(mapping.items())
    }
    metadata["voice_data_compiler"] = COMPILER_VERSION
    payload["metadata"] = metadata
    return HiddenOracle.model_validate(payload)


def _attach_private_source_provenance(
    oracle: HiddenOracle,
    spec: VoiceScenarioSpec,
) -> HiddenOracle:
    payload = oracle.model_dump(mode="python")
    metadata = dict(oracle.metadata)
    metadata.update(
        {
            "voice_source_provenance": spec.source.model_dump(mode="json"),
            "voice_source_metadata": dict(spec.source_metadata),
        }
    )
    payload["metadata"] = metadata
    return HiddenOracle.model_validate(payload)


def _source_record(
    spec: VoiceScenarioSpec,
    episode: OperationalEpisode,
) -> OperationalRecord:
    customer_id = next(
        record.object_id
        for record in episode.records
        if record.record_type == "customer_account"
    )
    return OperationalRecord(
        record_id=f"source-{spec.scenario_id}",
        system="SUPPORT",
        record_type="source_dialogue_context",
        object_id=customer_id,
        fields={
            "customer_utterance": spec.customer_utterance,
            "locale": spec.locale,
            "schema_variant": spec.schema_variant,
        },
        searchable_text=spec.customer_utterance,
        provenance_ids=[f"voice-scenario:{spec.scenario_id}"],
        source_authority="medium",
        freshness="unknown",
    )


def compile_voice_scenario(
    spec: VoiceScenarioSpec,
    *,
    seed: int = 42,
    allow_restricted_source: bool = False,
) -> OperationalEpisode:
    """Compile scenario IR into an independently verified operational world."""
    if (
        not allow_restricted_source
        and not _allowed_for_commercial_compile(spec.source)
    ):
        raise ValueError(
            "source is not authorized for commercial compilation: "
            f"{spec.source.use_policy.value}"
        )

    base = build_voice_qualification_episode(
        spec.family,
        seed=seed,
        variant=spec.variant,
        pressure=spec.pressure,
    )
    mapping = _validate_aliases(
        base.task.available_actions,
        spec.action_aliases,
    )

    task_payload = base.task.model_dump(mode="python")
    task_payload["objective"] = spec.objective
    task_payload["available_actions"] = [
        _rename_action(action, mapping).model_dump(mode="python")
        for action in base.task.available_actions
    ]
    task_metadata = dict(base.task.metadata)
    task_metadata.update(
        {
            "source_scenario_id": spec.scenario_id,
            "schema_variant": spec.schema_variant,
            "locale": spec.locale,
            "voice_data_compiler": COMPILER_VERSION,
        }
    )
    task_payload["metadata"] = task_metadata
    task = TaskContract.model_validate(task_payload)

    oracle = _rename_oracle(base.oracle, mapping)
    oracle = _attach_private_source_provenance(oracle, spec)
    source_record = _source_record(spec, base)

    episode_payload = base.model_dump(mode="python")
    episode_payload["task"] = task.model_dump(mode="python")
    episode_payload["oracle"] = oracle.model_dump(mode="python")
    episode_payload["records"] = [
        *[
            record.model_dump(mode="python")
            for record in base.records
        ],
        source_record.model_dump(mode="python"),
    ]
    episode_metadata = dict(base.metadata)
    episode_metadata.update(
        {
            "source_scenario_id": spec.scenario_id,
            "schema_variant": spec.schema_variant,
            "locale": spec.locale,
            "voice_data_compiler": COMPILER_VERSION,
        }
    )
    episode_payload["metadata"] = episode_metadata
    return OperationalEpisode.model_validate(episode_payload)
