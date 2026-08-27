from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

import investigation_world.operational.models as operational_models_module
from investigation_world.operational.models import (
    EpisodeSubmission,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
    VerificationBreakdown,
)
from investigation_world.portable_contract.errors import UnsupportedOperationalSemanticError
from investigation_world.portable_contract.identity import content_id, normalize_json_value
from investigation_world.portable_contract.models import (
    InteractionMode,
    PortableActionDefinition,
    PortableBudgetContract,
    PortableEvaluatorBinding,
    PortableEvidenceContract,
    PortableEvidenceRecord,
    PortableInvariant,
    PortableOperationalContract,
    PortablePrivateContract,
    PortableProcessContract,
    PortableProvenance,
    PortablePublicContract,
    PortableResourceCharge,
    PortableResourceLimit,
    PortableRewardComponent,
    PortableRewardContract,
    PortableRuntimeContract,
    PortableRuntimeOperation,
    PortableSearchContract,
    PortableStateAssertion,
    PortableStateContract,
    PortableTaskIdentity,
    PortableTerminationContract,
    PortableTransitionContract,
    SemanticStateProjection,
)
from investigation_world.portable_contract.validation import (
    assert_operational_semantic_equivalence,
)

CONTRACT_SCHEMA_VERSION = "1.0.0"
COMPILER_ID = "investigation_world.portable_contract.compile_operational_episode"
COMPILER_VERSION = "1"
SOURCE_COMMIT = "98500d7e081e48f8e291be51ba360ff851aa88fe"
SOURCE_MODEL_BLOB = "69877f041a74826a480e7d8d6ab6f459eee1ddcb"
SOURCE_RUNTIME_BLOB = "c82dfd6845a6f33f9bc636874d5cc23b59c37d3f"
SOURCE_VERIFIER_BLOB = "37c344287cb19b8e22bd705235bcfab67989065e"
VERIFIER_ENTRYPOINT = (
    "investigation_world.operational.verifier:verify_operational_episode"
)
VERIFIER_SEMANTICS_ID = f"git-blob-sha1:{SOURCE_VERIFIER_BLOB}"


def _git_blob_sha1(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def _require_supported_source_files() -> None:
    models_path = Path(str(operational_models_module.__file__))
    expected = {
        models_path: SOURCE_MODEL_BLOB,
        models_path.with_name("runtime.py"): SOURCE_RUNTIME_BLOB,
        models_path.with_name("verifier.py"): SOURCE_VERIFIER_BLOB,
    }
    for path, expected_blob in expected.items():
        if not path.is_file():
            raise UnsupportedOperationalSemanticError(
                code="SOURCE_SEMANTICS_UNAVAILABLE",
                path=str(path),
                detail="required operational source file is unavailable",
            )
        actual_blob = _git_blob_sha1(path)
        if actual_blob != expected_blob:
            raise UnsupportedOperationalSemanticError(
                code="SOURCE_SEMANTICS_CHANGED",
                path=str(path),
                detail=(
                    f"expected git blob {expected_blob}, got {actual_blob}; "
                    "update the portable compiler explicitly before compiling"
                ),
            )


_EXPECTED_MODEL_FIELDS: dict[type[Any], set[str]] = {
    OperationalEpisode: {
        "episode_id",
        "world_id",
        "task",
        "records",
        "oracle",
        "metadata",
    },
    TaskContract: {
        "task_id",
        "world_id",
        "domain",
        "objective",
        "role",
        "permitted_systems",
        "available_actions",
        "constraints",
        "success_description",
        "metadata",
    },
    PublicActionSpec: {
        "name",
        "kind",
        "system",
        "description",
        "parameter_names",
        "cost",
    },
    OperationalRecord: {
        "record_id",
        "system",
        "record_type",
        "object_id",
        "fields",
        "related_object_ids",
        "searchable_text",
        "observed_at",
        "valid_from",
        "valid_to",
        "source_authority",
        "confidence",
        "freshness",
        "provenance_ids",
    },
    StateAssertion: {
        "object_id",
        "field_name",
        "expected_value",
        "tolerance",
        "comparison",
    },
    OperationalInvariant: {
        "invariant_id",
        "description",
        "assertion",
        "severity",
        "scope",
    },
    HiddenActionEffect: {
        "action_name",
        "required_parameters",
        "required_state",
        "required_prior_actions",
        "set_state",
        "observable_result",
        "blocked_observable_result",
        "emitted_side_effects",
        "forbidden",
        "consequence_severity",
    },
    HiddenOracle: {
        "task_id",
        "initial_state",
        "target_state",
        "invariants",
        "required_actions",
        "required_action_order",
        "required_action_counts",
        "forbidden_actions",
        "required_evidence_ids",
        "action_effects",
        "max_cost",
        "max_tool_calls",
        "metadata",
    },
    EpisodeSubmission: {
        "conclusion",
        "claimed_state",
        "evidence_ids",
        "confidence",
    },
    VerificationBreakdown: {
        "outcome",
        "state",
        "constraints",
        "side_effects",
        "process",
        "efficiency",
        "evidence",
        "overall_reward",
        "target_assertions_met",
        "target_assertions_total",
        "invariant_violations",
        "missing_required_actions",
        "forbidden_actions_taken",
        "missing_evidence_ids",
        "tool_calls",
        "cost_spent",
        "process_violations",
    },
}

_PRIVATE_STRUCTURAL_KEYS = {
    "oracle",
    "initial_state",
    "target_state",
    "invariants",
    "required_actions",
    "required_action_order",
    "required_action_counts",
    "forbidden_actions",
    "required_evidence_ids",
    "action_effects",
    "hidden_state",
    "hidden_transition_effects",
    "target_truth",
    "private_evidence_locators",
    "private_evaluator_bytes",
    "expected_answer",
    "expected_answers",
}


def _require_supported_source_shape() -> None:
    for model, expected in _EXPECTED_MODEL_FIELDS.items():
        actual = set(model.model_fields)
        if actual != expected:
            added = sorted(actual - expected)
            removed = sorted(expected - actual)
            raise UnsupportedOperationalSemanticError(
                code="SOURCE_MODEL_SHAPE_CHANGED",
                path=f"{model.__module__}.{model.__name__}",
                detail=f"added={added}, removed={removed}",
            )


def _reject_private_keys(value: Any, *, path: str) -> None:
    if isinstance(value, list):
        for index, item in enumerate(value):
            _reject_private_keys(item, path=f"{path}[{index}]")
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key.casefold() in _PRIVATE_STRUCTURAL_KEYS:
            raise UnsupportedOperationalSemanticError(
                code="PUBLIC_PRIVATE_KEY_COLLISION",
                path=f"{path}.{key}",
                detail="public source data uses a reserved evaluator-private semantic key",
            )
        _reject_private_keys(item, path=f"{path}.{key}")


def _validate_source_episode(episode: OperationalEpisode) -> None:
    _require_supported_source_files()
    _require_supported_source_shape()
    try:
        OperationalEpisode.model_validate(episode.model_dump(mode="python"))
    except ValidationError as exc:
        raise UnsupportedOperationalSemanticError(
            code="SOURCE_EPISODE_INVALID",
            path="episode",
            detail=str(exc),
        ) from exc
    source = normalize_json_value(
        episode.model_dump(mode="python"),
        path="episode",
    )
    for action_index, action in enumerate(episode.task.available_actions):
        if len(action.parameter_names) != len(set(action.parameter_names)):
            raise UnsupportedOperationalSemanticError(
                code="DUPLICATE_ACTION_PARAMETER_NAME",
                path=f"episode.task.available_actions[{action_index}].parameter_names",
                detail=(
                    "duplicate parameter names affect current runtime error behavior "
                    "but cannot be represented by a valid JSON Schema required array"
                ),
            )
    public_source = {
        "episode_id": source["episode_id"],
        "world_id": source["world_id"],
        "task": source["task"],
        "records": source["records"],
        "metadata": source["metadata"],
    }
    _reject_private_keys(public_source, path="episode.public_payload")


def _assertion(assertion: StateAssertion) -> PortableStateAssertion:
    return PortableStateAssertion(
        object_id=assertion.object_id,
        field_name=assertion.field_name,
        expected_value=normalize_json_value(
            assertion.expected_value,
            path=f"assertion.{assertion.key()}.expected_value",
        ),
        tolerance=assertion.tolerance,
        comparison=assertion.comparison.value,
    )


def _invariant(invariant: OperationalInvariant) -> PortableInvariant:
    return PortableInvariant(
        invariant_id=invariant.invariant_id,
        description=invariant.description,
        assertion=_assertion(invariant.assertion),
        severity=invariant.severity,
        scope=invariant.scope,
        trajectory_wide=invariant.scope == "always",
    )


def _record_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "record_id",
            "system",
            "record_type",
            "object_id",
            "fields",
            "related_object_ids",
            "searchable_text",
            "observed_at",
            "valid_from",
            "valid_to",
            "source_authority",
            "confidence",
            "freshness",
            "provenance_ids",
        ],
        "properties": {
            "record_id": {"type": "string"},
            "system": {"type": "string"},
            "record_type": {"type": "string"},
            "object_id": {"type": "string"},
            "fields": {"type": "object"},
            "related_object_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "searchable_text": {"type": "string"},
            "observed_at": {"type": ["string", "null"]},
            "valid_from": {"type": ["string", "null"]},
            "valid_to": {"type": ["string", "null"]},
            "source_authority": {
                "enum": ["low", "medium", "high", "authoritative"],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "freshness": {
                "enum": ["current", "recent", "stale", "historical", "unknown"],
            },
            "provenance_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }


def _observation_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["episode_id", "world_id", "task", "records", "metadata"],
        "properties": {
            "episode_id": {"type": "string"},
            "world_id": {"type": "string"},
            "task": {"type": "object"},
            "records": {
                "type": "array",
                "items": _record_schema(),
            },
            "metadata": {"type": "object"},
        },
    }


def _action_input_schema(action: PublicActionSpec) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {} for name in action.parameter_names},
        "required": list(action.parameter_names),
        "additionalProperties": True,
    }


def _action_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["action", "system", "submitted"],
        "properties": {
            "action": {},
            "system": {},
            "submitted": {},
        },
        "additionalProperties": True,
    }


def _submission_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "conclusion": {"type": "string", "default": ""},
            "claimed_state": {"type": "object", "default": {}},
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
                "default": [],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.0,
            },
        },
    }


def _verification_schema() -> dict[str, Any]:
    score = {"type": "number", "minimum": 0.0, "maximum": 1.0}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(VerificationBreakdown.model_fields),
        "properties": {
            "outcome": score,
            "state": score,
            "constraints": score,
            "side_effects": score,
            "process": score,
            "efficiency": score,
            "evidence": score,
            "overall_reward": score,
            "target_assertions_met": {"type": "integer", "minimum": 0},
            "target_assertions_total": {"type": "integer", "minimum": 0},
            "invariant_violations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "missing_required_actions": {
                "type": "array",
                "items": {"type": "string"},
            },
            "forbidden_actions_taken": {
                "type": "array",
                "items": {"type": "string"},
            },
            "missing_evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "tool_calls": {"type": "integer", "minimum": 0},
            "cost_spent": {"type": "integer", "minimum": 0},
            "process_violations": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    }


def _charges(cost: int) -> tuple[PortableResourceCharge, ...]:
    return (
        PortableResourceCharge(
            resource="cost",
            unit="cost_units",
            amount=cost,
        ),
        PortableResourceCharge(
            resource="tool_calls",
            unit="calls",
            amount=1,
        ),
    )


def _runtime(permitted_systems: tuple[str, ...]) -> PortableRuntimeContract:
    record_array = {
        "type": "array",
        "items": _record_schema(),
    }
    operations = (
        PortableRuntimeOperation(
            name="search",
            interaction_mode=InteractionMode.RETRIEVAL,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["system", "query"],
                "properties": {
                    "system": {
                        "type": "string",
                        "enum": list(permitted_systems),
                    },
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 10,
                    },
                },
            },
            output_schema=record_array,
            charges=_charges(1),
            permission_failure_behavior="return_empty_without_charge",
            permission_check_precedes_open_check=True,
        ),
        PortableRuntimeOperation(
            name="search_all",
            interaction_mode=InteractionMode.RETRIEVAL,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 10,
                    },
                },
            },
            output_schema=record_array,
            charges=_charges(2),
        ),
        PortableRuntimeOperation(
            name="open_record",
            interaction_mode=InteractionMode.RETRIEVAL,
            input_schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["record_id"],
                "properties": {
                    "record_id": {"type": "string"},
                },
            },
            output_schema=_record_schema(),
            charges=_charges(1),
            missing_resource_behavior="charge_then_raise_key_error",
        ),
        PortableRuntimeOperation(
            name="submit",
            interaction_mode=InteractionMode.SUBMISSION,
            input_schema=_submission_schema(),
            output_schema=_verification_schema(),
        ),
    )
    return PortableRuntimeContract(
        interaction_modes=(
            InteractionMode.RETRIEVAL,
            InteractionMode.ACTION,
            InteractionMode.SUBMISSION,
        ),
        builtin_operations=operations,
        search=PortableSearchContract(),
        termination=PortableTerminationContract(),
    )


def _public_action(action: PublicActionSpec) -> PortableActionDefinition:
    return PortableActionDefinition(
        name=action.name,
        kind=action.kind.value,
        system=action.system,
        description=action.description,
        parameter_names=tuple(action.parameter_names),
        input_schema=_action_input_schema(action),
        output_schema=_action_output_schema(),
        cost=action.cost,
        charges=_charges(action.cost),
    )


def _evidence_record(record: OperationalRecord) -> PortableEvidenceRecord:
    return PortableEvidenceRecord(
        record_id=record.record_id,
        system=record.system,
        record_type=record.record_type,
        object_id=record.object_id,
        fields=normalize_json_value(
            record.fields,
            path=f"record[{record.record_id}].fields",
        ),
        related_object_ids=tuple(record.related_object_ids),
        searchable_text=record.searchable_text,
        observed_at=record.observed_at,
        valid_from=record.valid_from,
        valid_to=record.valid_to,
        source_authority=record.source_authority,
        confidence=record.confidence,
        freshness=record.freshness,
        provenance_ids=tuple(record.provenance_ids),
    )


def _transition(
    effect: HiddenActionEffect,
    declaration_index: int,
) -> PortableTransitionContract:
    return PortableTransitionContract(
        declaration_index=declaration_index,
        action_name=effect.action_name,
        required_parameters=normalize_json_value(
            effect.required_parameters,
            path=f"oracle.action_effects[{declaration_index}].required_parameters",
        ),
        required_state=tuple(_assertion(item) for item in effect.required_state),
        required_prior_actions=tuple(effect.required_prior_actions),
        set_state=normalize_json_value(
            effect.set_state,
            path=f"oracle.action_effects[{declaration_index}].set_state",
        ),
        observable_result=normalize_json_value(
            effect.observable_result,
            path=f"oracle.action_effects[{declaration_index}].observable_result",
        ),
        blocked_observable_result=normalize_json_value(
            effect.blocked_observable_result,
            path=(
                f"oracle.action_effects[{declaration_index}]"
                ".blocked_observable_result"
            ),
        ),
        emitted_side_effects=tuple(effect.emitted_side_effects),
        forbidden=effect.forbidden,
        consequence_severity=effect.consequence_severity,
    )


def _reward() -> PortableRewardContract:
    return PortableRewardContract(
        components=(
            PortableRewardComponent(name="outcome", weight=0.30),
            PortableRewardComponent(name="state", weight=0.20),
            PortableRewardComponent(name="constraints", weight=0.15),
            PortableRewardComponent(name="side_effects", weight=0.10),
            PortableRewardComponent(name="process", weight=0.10),
            PortableRewardComponent(name="efficiency", weight=0.05),
            PortableRewardComponent(name="evidence", weight=0.10),
        )
    )


def _compile_operational_episode_unchecked(
    episode: OperationalEpisode,
) -> PortableOperationalContract:
    _validate_source_episode(episode)

    identity = PortableTaskIdentity(
        episode_id=episode.episode_id,
        world_id=episode.world_id,
        task_id=episode.task.task_id,
        domain=episode.task.domain.value,
    )
    provenance = PortableProvenance(
        source_model="investigation_world.operational.models:OperationalEpisode",
        source_commit=SOURCE_COMMIT,
        source_model_git_blob_sha1=SOURCE_MODEL_BLOB,
        source_runtime_git_blob_sha1=SOURCE_RUNTIME_BLOB,
        source_verifier_git_blob_sha1=SOURCE_VERIFIER_BLOB,
        compiler=COMPILER_ID,
        compiler_version=COMPILER_VERSION,
    )
    public = PortablePublicContract(
        schema_version=CONTRACT_SCHEMA_VERSION,
        identity=identity,
        provenance=provenance,
        objective=episode.task.objective,
        role=episode.task.role,
        permitted_systems=tuple(episode.task.permitted_systems),
        constraints=tuple(episode.task.constraints),
        success_description=episode.task.success_description,
        task_metadata=normalize_json_value(
            episode.task.metadata,
            path="episode.task.metadata",
        ),
        episode_metadata=normalize_json_value(
            episode.metadata,
            path="episode.metadata",
        ),
        state=PortableStateContract(
            observation_schema=_observation_schema(),
        ),
        actions=tuple(_public_action(action) for action in episode.task.available_actions),
        evidence=PortableEvidenceContract(
            records=tuple(_evidence_record(record) for record in episode.records),
        ),
        runtime=_runtime(tuple(episode.task.permitted_systems)),
    )

    initial_state = normalize_json_value(
        episode.oracle.initial_state,
        path="episode.oracle.initial_state",
    )
    reset_identity = content_id(
        "poc-reset-v1",
        {
            "identity": identity.model_dump(mode="python"),
            "initial_state": initial_state,
        },
    )
    private = PortablePrivateContract(
        oracle_task_id=episode.oracle.task_id,
        semantic_state=SemanticStateProjection(
            initial_state=initial_state,
            target_assertions=tuple(
                _assertion(assertion)
                for assertion in episode.oracle.target_state
            ),
            invariants=tuple(
                _invariant(invariant)
                for invariant in episode.oracle.invariants
            ),
        ),
        transitions=tuple(
            _transition(effect, index)
            for index, effect in enumerate(episode.oracle.action_effects)
        ),
        process=PortableProcessContract(
            required_actions=tuple(episode.oracle.required_actions),
            forbidden_actions=tuple(episode.oracle.forbidden_actions),
            required_action_order=tuple(episode.oracle.required_action_order),
            required_action_counts=dict(episode.oracle.required_action_counts),
        ),
        required_evidence_ids=tuple(episode.oracle.required_evidence_ids),
        budgets=PortableBudgetContract(
            limits=(
                PortableResourceLimit(
                    resource="cost",
                    unit="cost_units",
                    maximum=episode.oracle.max_cost,
                    exhaustion_rule="reject_if_post_charge_usage_gt_maximum",
                ),
                PortableResourceLimit(
                    resource="tool_calls",
                    unit="calls",
                    maximum=episode.oracle.max_tool_calls,
                    exhaustion_rule=(
                        "reject_if_current_usage_gte_maximum_before_charge"
                    ),
                ),
            )
        ),
        reset_identity=reset_identity,
        evaluator=PortableEvaluatorBinding(
            entrypoint=VERIFIER_ENTRYPOINT,
            semantics_id=VERIFIER_SEMANTICS_ID,
            source_git_blob_sha1=SOURCE_VERIFIER_BLOB,
            deterministic=True,
            reward=_reward(),
        ),
        oracle_metadata=normalize_json_value(
            episode.oracle.metadata,
            path="episode.oracle.metadata",
        ),
    )
    return PortableOperationalContract(
        schema_version=CONTRACT_SCHEMA_VERSION,
        public=public,
        private=private,
    )


def compile_operational_episode(
    episode: OperationalEpisode,
) -> PortableOperationalContract:
    """Project an OperationalEpisode into the canonical portable operational IR.

    Compilation is pure. Unsupported or non-canonical source semantics fail closed
    instead of being defaulted, coerced, or represented as prose.
    """
    contract = _compile_operational_episode_unchecked(episode)
    assert_operational_semantic_equivalence(episode, contract)
    return contract
