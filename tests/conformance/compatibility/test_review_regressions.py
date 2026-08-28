from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from investigation_world.conformance.compatibility import (
    AdapterCompatibilityBinding,
    CompatibilityValidationState,
    ObservedRuntimeInterface,
    RuntimeCompatibilityError,
    RuntimeCompatibilityPolicy,
    RuntimeCompatibilityStatus,
    TestedVersionRange,
    evaluate_runtime_compatibility,
    require_tested_interface_match,
)

BASE_COMMIT = "f12b46faba0f32d8ef696583bfff9b978f324039"
ADAPTER_DIGEST = "a" * 64
INTERFACE_DIGEST = "b" * 64


def _binding() -> AdapterCompatibilityBinding:
    return AdapterCompatibilityBinding(
        adapter_name="hud",
        adapter_version="1",
        content_sha256=ADAPTER_DIGEST,
    )


def _validated_policy(**updates) -> RuntimeCompatibilityPolicy:
    values = {
        "adapter": _binding(),
        "portable_contract_schema_version": "1.0.0",
        "runtime_name": "hud",
        "tested_versions": TestedVersionRange(exact_versions=("0.6.15",)),
        "tested_protocol_versions": ("hud/1.0",),
        "interface_snapshot_sha256": INTERFACE_DIGEST,
        "validated_commit_sha": BASE_COMMIT,
        "validated_on": date(2026, 8, 28),
        "validation_state": CompatibilityValidationState.VALIDATED,
    }
    values.update(updates)
    return RuntimeCompatibilityPolicy(**values)


def _observed(**updates) -> ObservedRuntimeInterface:
    values = {
        "adapter": _binding(),
        "portable_contract_schema_version": "1.0.0",
        "runtime_name": "hud",
        "runtime_version": "0.6.15",
        "protocol_version": "hud/1.0",
        "interface_snapshot_sha256": INTERFACE_DIGEST,
    }
    values.update(updates)
    return ObservedRuntimeInterface(**values)


def test_empty_tested_protocol_set_does_not_wildcard_observed_protocol() -> None:
    policy = _validated_policy(tested_protocol_versions=())
    report = evaluate_runtime_compatibility(
        policy,
        _observed(protocol_version="hud/never-tested"),
    )

    assert report.status == RuntimeCompatibilityStatus.PROTOCOL_MISMATCH
    with pytest.raises(RuntimeCompatibilityError, match="PROTOCOL_MISMATCH"):
        require_tested_interface_match(report)


def test_protocol_absence_must_be_explicit_on_both_policy_and_observation() -> None:
    policy = _validated_policy(tested_protocol_versions=())

    report = evaluate_runtime_compatibility(
        policy,
        _observed(protocol_version=None),
    )

    assert report.status == RuntimeCompatibilityStatus.TESTED_INTERFACE_MATCH


def test_validated_policy_cannot_declare_evidence_gaps() -> None:
    with pytest.raises(ValidationError, match="cannot declare evidence_gaps"):
        _validated_policy(evidence_gaps=("missing target protocol probe",))


def test_stale_validated_policy_with_evidence_gaps_is_rejected_at_boundary() -> None:
    policy = _validated_policy()
    stale = policy.model_copy(update={"evidence_gaps": ("missing target protocol probe",)})

    with pytest.raises(ValidationError, match="cannot declare evidence_gaps"):
        evaluate_runtime_compatibility(stale, _observed())
