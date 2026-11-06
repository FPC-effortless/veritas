from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from pydantic import BaseModel

from investigation_world.portable_contract import PortableOperationalContract

from .models import AdapterConformanceReport, SemanticSnapshot


REQUIRED_SEMANTIC_FIELDS: tuple[str, ...] = (
    "observations",
    "state_digests",
    "evidence",
    "action_parameters",
    "action_outcomes",
    "termination",
    "truncation",
    "budgets",
    "invariants",
    "target_assertions",
    "process_requirements",
    "evidence_requirements",
    "reward_weights",
    "verifier_components",
    "aggregate_reward",
)

# These semantics are evaluator-private on the agent-facing surface, but they remain required
# operator-side conformance evidence. Exclusion from the public surface never means exclusion from
# semantic comparison.
EVALUATOR_PRIVATE_FIELDS: tuple[str, ...] = (
    "private.semantic_state.initial_state",
    "private.semantic_state.target_assertions",
    "private.semantic_state.invariants",
    "private.transitions",
    "private.process",
    "private.required_evidence_ids",
    "private.budgets",
    "private.evaluator",
    "private.oracle_metadata",
)


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return _canonicalize(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (set, frozenset)):
        items = [_canonicalize(item) for item in value]
        return sorted(items, key=_canonical_json)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_canonicalize(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def compute_test_vector_hash(vector: Any) -> str:
    """Hash a test vector independently of object/dict insertion ordering."""

    return hashlib.sha256(_canonical_json(vector).encode("utf-8")).hexdigest()


def _payload(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise TypeError(f"semantic result must be a mapping or BaseModel, got {type(value)!r}")
    return _canonicalize(payload)


def build_semantic_snapshot(
    contract: PortableOperationalContract,
    invocations: Sequence[Mapping[str, Any]],
    reset_result: Any,
    step_results: Sequence[Any],
) -> SemanticSnapshot:
    """Normalize portable semantics from an adapter/operator execution trace.

    Callers are expected to translate the adapter's native envelope into result mappings whose
    fields have portable meaning. This function deliberately mixes public execution evidence with
    operator-private contract evidence so an SDK cannot pass merely by hiding a required semantic.
    """

    if len(invocations) != len(step_results):
        raise ValueError("invocations and step_results must have the same length")

    reset = _payload(reset_result)
    steps = [_payload(item) for item in step_results]
    calls = [_canonicalize(dict(item)) for item in invocations]

    retrieval_names = {
        operation.name
        for operation in contract.public.runtime.builtin_operations
        if operation.interaction_mode.value == "retrieval"
    }
    retrieval_observations = [
        result["observation"]
        for call, result in zip(calls, steps, strict=True)
        if call.get("kind") == "operation" and call.get("name") in retrieval_names
    ]
    action_outcomes = [
        result["observation"]
        for call, result in zip(calls, steps, strict=True)
        if call.get("kind") == "action"
    ]

    public_action_schemas = {
        action.name: action.input_schema for action in contract.public.actions
    }
    transition_parameters = [
        {
            "action_name": transition.action_name,
            "required_parameters": transition.required_parameters,
            "parameter_match_rule": transition.parameter_match_rule,
        }
        for transition in contract.private.transitions
    ]
    transition_outcomes = [
        {
            "action_name": transition.action_name,
            "observable_result": transition.observable_result,
            "blocked_observable_result": transition.blocked_observable_result,
        }
        for transition in contract.private.transitions
    ]

    terminal = steps[-1] if steps else None
    values = {
        "observations": [reset["observation"], *[item["observation"] for item in steps]],
        "state_digests": [reset["state_digest"], *[item["state_digest"] for item in steps]],
        "evidence": {
            "declared_records": contract.public.evidence.records,
            "retrieval_observations": retrieval_observations,
        },
        "action_parameters": {
            "invocations": calls,
            "public_input_schemas": public_action_schemas,
            "transition_requirements": transition_parameters,
        },
        "action_outcomes": {
            "executed": action_outcomes,
            "transition_contract": transition_outcomes,
        },
        "termination": {
            "contract": contract.public.runtime.termination,
            "results": [item["terminated"] for item in steps],
        },
        "truncation": [item["truncated"] for item in steps],
        "budgets": {
            "contract": contract.private.budgets,
            "status": [reset["budget_status"], *[item["budget_status"] for item in steps]],
        },
        "invariants": contract.private.semantic_state.invariants,
        "target_assertions": contract.private.semantic_state.target_assertions,
        "process_requirements": contract.private.process,
        "evidence_requirements": contract.private.required_evidence_ids,
        "reward_weights": contract.private.evaluator.reward,
        "verifier_components": None if terminal is None else terminal.get("reward_components"),
        "aggregate_reward": None if terminal is None else terminal.get("reward"),
    }
    return SemanticSnapshot(values=_canonicalize(values))


def _difference_path(expected: Any, actual: Any, path: str = "$") -> str | None:
    expected = _canonicalize(expected)
    actual = _canonicalize(actual)
    if type(expected) is not type(actual):
        return path
    if isinstance(expected, dict):
        if set(expected) != set(actual):
            differing = sorted(set(expected) ^ set(actual))
            return f"{path}.{differing[0]}" if differing else path
        for key in sorted(expected):
            difference = _difference_path(expected[key], actual[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return f"{path}.length"
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            difference = _difference_path(expected_item, actual_item, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    return None if expected == actual else path


def compare_adapter_semantics(
    expected: SemanticSnapshot,
    actual: SemanticSnapshot,
    *,
    test_vector: Any,
    mapped_fields: Mapping[str, str],
    generated_fields: Sequence[str] = (),
    excluded_private_fields: Sequence[str] = EVALUATOR_PRIVATE_FIELDS,
    required_fields: Sequence[str] = REQUIRED_SEMANTIC_FIELDS,
) -> AdapterConformanceReport:
    """Compare one adapter snapshot with fail-closed loss accounting."""

    required = tuple(dict.fromkeys(required_fields))
    expected_values = expected.values
    actual_values = actual.values
    preserved: list[str] = []
    unsupported: list[str] = []
    losses: list[str] = []

    for field in required:
        if field not in expected_values:
            raise ValueError(f"baseline snapshot is missing required semantic field {field!r}")
        if field not in mapped_fields:
            losses.append(f"{field}:mapping_missing")
        if field not in actual_values:
            unsupported.append(field)
            losses.append(f"{field}:unsupported_required")
            continue
        difference = _difference_path(expected_values[field], actual_values[field])
        if difference is None:
            preserved.append(field)
        else:
            # Never include values in a loss string: a mismatch path is sufficient evidence and
            # cannot accidentally serialize evaluator-private truth.
            losses.append(f"{field}:semantic_mismatch:{difference}")

    extras = sorted(set(actual_values) - set(expected_values))
    generated = tuple(sorted(set(generated_fields) | set(extras)))
    return AdapterConformanceReport(
        mapped_fields=dict(sorted(mapped_fields.items())),
        preserved_fields=tuple(sorted(preserved)),
        generated_fields=generated,
        excluded_private_fields=tuple(sorted(set(excluded_private_fields))),
        unsupported_fields=tuple(sorted(unsupported)),
        semantic_losses=tuple(sorted(set(losses))),
        test_vector_hash=compute_test_vector_hash(test_vector),
    )
