from __future__ import annotations

from copy import deepcopy

import pytest

from investigation_world.conformance import (
    REQUIRED_SEMANTIC_FIELDS,
    SemanticSnapshot,
    compare_adapter_semantics,
    compute_test_vector_hash,
)


VECTOR = {
    "schema_version": "test-vector-v1",
    "seed": 17,
    "actions": [
        {"kind": "action", "name": "approve", "arguments": {"order_id": "ORDER-001"}}
    ],
}


def _values() -> dict:
    return {
        "observations": [{"status": "pending"}, {"accepted": True}],
        "state_digests": ["digest-0", "digest-1"],
        "evidence": {"declared_records": [{"record_id": "record-001"}]},
        "action_parameters": {
            "invocations": [
                {
                    "kind": "action",
                    "name": "approve",
                    "arguments": {"order_id": "ORDER-001"},
                }
            ]
        },
        "action_outcomes": {"executed": [{"accepted": True}]},
        "termination": {"results": [True]},
        "truncation": [False],
        "budgets": {"contract": {"cost": 10}, "status": [{"remaining": 9}]},
        "invariants": [{"invariant_id": "risk-safe", "maximum": 1}],
        "target_assertions": [{"field": "status", "expected": "approved"}],
        "process_requirements": {"required_actions": ["approve"]},
        "evidence_requirements": ["record-001"],
        "reward_weights": {"outcome": 0.4, "state": 0.6},
        "verifier_components": {"outcome": 1.0, "state": 1.0},
        "aggregate_reward": 1.0,
    }


def _compare(actual_values: dict):
    mapping = {field: f"native.{field}" for field in REQUIRED_SEMANTIC_FIELDS}
    return compare_adapter_semantics(
        SemanticSnapshot(values=_values()),
        SemanticSnapshot(values=actual_values),
        test_vector=VECTOR,
        mapped_fields=mapping,
    )


def _mutate_reward_weight(values: dict) -> None:
    values["reward_weights"]["outcome"] = 0.5


def _mutate_action_parameter(values: dict) -> None:
    values["action_parameters"]["invocations"][0]["arguments"]["order_id"] = "ORDER-999"


def _mutate_observable_result(values: dict) -> None:
    values["action_outcomes"]["executed"][0]["accepted"] = False


def _mutate_termination(values: dict) -> None:
    values["termination"]["results"][0] = False


def _mutate_invariant(values: dict) -> None:
    values["invariants"][0]["maximum"] = 2


def _mutate_budget(values: dict) -> None:
    values["budgets"]["contract"]["cost"] = 11


def _mutate_evidence_requirement(values: dict) -> None:
    values["evidence_requirements"] = ["record-999"]


@pytest.mark.parametrize(
    ("field", "mutator"),
    [
        ("reward_weights", _mutate_reward_weight),
        ("action_parameters", _mutate_action_parameter),
        ("action_outcomes", _mutate_observable_result),
        ("termination", _mutate_termination),
        ("invariants", _mutate_invariant),
        ("budgets", _mutate_budget),
        ("evidence_requirements", _mutate_evidence_requirement),
    ],
)
def test_required_falsifiers_are_detected(field, mutator) -> None:
    actual = deepcopy(_values())
    mutator(actual)

    report = _compare(actual)

    assert report.passed is False
    assert report.semantic_losses
    assert any(loss.startswith(f"{field}:semantic_mismatch:") for loss in report.semantic_losses)


def test_identical_snapshot_passes_with_no_semantic_losses() -> None:
    report = _compare(deepcopy(_values()))

    assert report.passed is True
    assert report.semantic_losses == ()
    assert report.unsupported_fields == ()
    assert set(report.preserved_fields) == set(REQUIRED_SEMANTIC_FIELDS)


def test_sdk_inability_to_express_required_semantic_is_a_failure() -> None:
    actual = deepcopy(_values())
    actual.pop("invariants")

    report = _compare(actual)

    assert report.passed is False
    assert report.unsupported_fields == ("invariants",)
    assert "invariants:unsupported_required" in report.semantic_losses


def test_missing_mapping_is_a_semantic_loss_even_when_value_matches() -> None:
    mapping = {field: f"native.{field}" for field in REQUIRED_SEMANTIC_FIELDS}
    mapping.pop("budgets")
    report = compare_adapter_semantics(
        SemanticSnapshot(values=_values()),
        SemanticSnapshot(values=deepcopy(_values())),
        test_vector=VECTOR,
        mapped_fields=mapping,
    )

    assert report.passed is False
    assert "budgets:mapping_missing" in report.semantic_losses


def test_vector_hash_is_order_independent_and_change_sensitive() -> None:
    reordered = {
        "actions": VECTOR["actions"],
        "seed": VECTOR["seed"],
        "schema_version": VECTOR["schema_version"],
    }
    changed = deepcopy(VECTOR)
    changed["seed"] = 18

    assert compute_test_vector_hash(reordered) == compute_test_vector_hash(VECTOR)
    assert compute_test_vector_hash(changed) != compute_test_vector_hash(VECTOR)
