from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from investigation_world.conformance.certificate import (
    ConformanceAdapterReference,
    ConformanceCertificateStatus,
    ConformanceParity,
    PortableContractReference,
    TargetRuntimeReference,
    certify_adapter_conformance,
)
from investigation_world.conformance.compatibility import (
    AdapterCompatibilityBinding,
    CompatibilityValidationState,
    ConformanceBindingStatus,
    ObservedRuntimeInterface,
    RuntimeCompatibilityError,
    RuntimeCompatibilityMatrix,
    RuntimeCompatibilityPolicy,
    RuntimeCompatibilityStatus,
    TestedVersionRange,
    evaluate_compatibility_matrix,
    evaluate_runtime_compatibility,
    require_tested_interface_match,
    serialize_compatibility_matrix,
    serialize_compatibility_report,
)
from investigation_world.conformance.models import AdapterConformanceReport

BASE_COMMIT = "f12b46faba0f32d8ef696583bfff9b978f324039"
ADAPTER_DIGEST = "a" * 64
INTERFACE_DIGEST = "b" * 64


def _binding(
    *,
    name: str = "hud",
    version: str = "1",
    digest: str | None = ADAPTER_DIGEST,
) -> AdapterCompatibilityBinding:
    return AdapterCompatibilityBinding(
        adapter_name=name,
        adapter_version=version,
        content_sha256=digest,
    )


def _policy(**updates) -> RuntimeCompatibilityPolicy:
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
        "known_unsupported_semantics": ("parallel-tool-calls",),
        "known_semantic_losses": (),
        "evidence_gaps": (),
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


def _conformance_certificate(*, semantic_losses=(), runtime_version="0.6.15"):
    report = AdapterConformanceReport(
        mapped_fields={"state": "state"},
        preserved_fields=("state", "reward", "termination", "evidence"),
        generated_fields=(),
        excluded_private_fields=("private.oracle",),
        unsupported_fields=(),
        semantic_losses=semantic_losses,
        test_vector_hash="c" * 64,
    )
    return certify_adapter_conformance(
        report,
        source_contract=PortableContractReference(
            schema_version="1.0.0",
            public_contract_id="POPC-PUBLIC-COMPAT",
            public_content_sha256="d" * 64,
        ),
        adapter=ConformanceAdapterReference(
            adapter_name="hud",
            adapter_version="1",
            content_sha256=ADAPTER_DIGEST,
        ),
        target_runtime=TargetRuntimeReference(
            runtime_name="hud",
            runtime_version=runtime_version,
            content_sha256="e" * 64,
        ),
        parity=ConformanceParity(
            state=True,
            reward=True,
            termination=True,
            evidence=True,
        ),
    )


def test_exact_tested_runtime_protocol_and_interface_match() -> None:
    report = evaluate_runtime_compatibility(_policy(), _observed())

    assert report.status == RuntimeCompatibilityStatus.TESTED_INTERFACE_MATCH
    assert report.interface_matches_tested_support
    assert report.known_unsupported_semantics == ("parallel-tool-calls",)
    assert report.conformance_binding == ConformanceBindingStatus.NOT_PROVIDED
    assert report.conformance_status is None


def test_semver_range_rejects_unvalidated_major_version() -> None:
    policy = _policy(
        tested_versions=TestedVersionRange(
            minimum_version="0.6.0",
            maximum_version="0.6.99",
        )
    )

    matching = evaluate_runtime_compatibility(
        policy,
        _observed(runtime_version="0.6.20"),
    )
    major_drift = evaluate_runtime_compatibility(
        policy,
        _observed(runtime_version="1.0.0"),
    )

    assert matching.status == RuntimeCompatibilityStatus.TESTED_INTERFACE_MATCH
    assert major_drift.status == RuntimeCompatibilityStatus.VERSION_OUT_OF_RANGE


def test_protocol_version_mismatch_fails_closed() -> None:
    report = evaluate_runtime_compatibility(
        _policy(),
        _observed(protocol_version="hud/2.0"),
    )

    assert report.status == RuntimeCompatibilityStatus.PROTOCOL_MISMATCH


def test_interface_snapshot_drift_downgrades_support_and_ci_gate_fails() -> None:
    report = evaluate_runtime_compatibility(
        _policy(),
        _observed(interface_snapshot_sha256="f" * 64),
    )

    assert report.status == RuntimeCompatibilityStatus.INTERFACE_DRIFT
    with pytest.raises(RuntimeCompatibilityError, match="INTERFACE_DRIFT"):
        require_tested_interface_match(report)


def test_adapter_and_portable_contract_bindings_are_exact() -> None:
    adapter_mismatch = evaluate_runtime_compatibility(
        _policy(),
        _observed(adapter=_binding(version="2")),
    )
    contract_mismatch = evaluate_runtime_compatibility(
        _policy(),
        _observed(portable_contract_schema_version="2.0.0"),
    )

    assert adapter_mismatch.status == RuntimeCompatibilityStatus.ADAPTER_MISMATCH
    assert (
        contract_mismatch.status
        == RuntimeCompatibilityStatus.PORTABLE_CONTRACT_MISMATCH
    )


def test_unvalidated_entry_never_becomes_supported_from_partial_metadata() -> None:
    policy = RuntimeCompatibilityPolicy(
        adapter=AdapterCompatibilityBinding(
            adapter_name="openenv",
            adapter_version="openenv-operational-v1",
        ),
        portable_contract_schema_version="1.0.0",
        runtime_name="openenv",
        tested_versions=TestedVersionRange(exact_versions=("0.1.0",)),
        evidence_gaps=("external interface snapshot not preserved",),
    )
    observed = ObservedRuntimeInterface(
        adapter=AdapterCompatibilityBinding(
            adapter_name="openenv",
            adapter_version="openenv-operational-v1",
        ),
        portable_contract_schema_version="1.0.0",
        runtime_name="openenv",
        runtime_version="0.1.0",
        interface_snapshot_sha256="1" * 64,
    )

    report = evaluate_runtime_compatibility(policy, observed)

    assert report.status == RuntimeCompatibilityStatus.UNVALIDATED
    assert report.evidence_gaps == ("external interface snapshot not preserved",)


def test_validated_policy_requires_commit_date_adapter_and_interface_evidence() -> None:
    with pytest.raises(ValidationError, match="missing evidence"):
        RuntimeCompatibilityPolicy(
            adapter=AdapterCompatibilityBinding(
                adapter_name="nemo",
                adapter_version="veritas-native-nemo-gymnasium-v1",
            ),
            portable_contract_schema_version="1.0.0",
            runtime_name="nemo-gym",
            tested_versions=TestedVersionRange(exact_versions=("1.0.0",)),
            validation_state=CompatibilityValidationState.VALIDATED,
        )


def test_compatibility_and_semantic_conformance_remain_separate() -> None:
    certificate = _conformance_certificate(
        semantic_losses=("reward:semantic_mismatch:$.reward",)
    )

    report = evaluate_runtime_compatibility(
        _policy(known_semantic_losses=("reward semantics differ",)),
        _observed(),
        conformance_certificate=certificate,
    )

    assert report.status == RuntimeCompatibilityStatus.TESTED_INTERFACE_MATCH
    assert report.conformance_binding == ConformanceBindingStatus.MATCH
    assert report.conformance_status == ConformanceCertificateStatus.FAIL
    assert report.known_semantic_losses == ("reward semantics differ",)


def test_mismatched_conformance_certificate_is_not_attributed_to_observation() -> None:
    certificate = _conformance_certificate(runtime_version="0.6.14")

    report = evaluate_runtime_compatibility(
        _policy(),
        _observed(),
        conformance_certificate=certificate,
    )

    assert report.status == RuntimeCompatibilityStatus.TESTED_INTERFACE_MATCH
    assert report.conformance_binding == ConformanceBindingStatus.MISMATCH
    assert report.conformance_status is None


def test_matrix_is_deterministic_and_missing_policy_is_machine_readable() -> None:
    hud = _policy()
    openenv = RuntimeCompatibilityPolicy(
        adapter=AdapterCompatibilityBinding(
            adapter_name="openenv",
            adapter_version="openenv-operational-v1",
        ),
        portable_contract_schema_version="1.0.0",
        runtime_name="openenv",
        evidence_gaps=("target package version not recorded",),
    )
    first = RuntimeCompatibilityMatrix(policies=(openenv, hud))
    second = RuntimeCompatibilityMatrix(policies=(hud, openenv))

    assert first.matrix_id == second.matrix_id
    report = evaluate_compatibility_matrix(
        first,
        ObservedRuntimeInterface(
            adapter=AdapterCompatibilityBinding(
                adapter_name="prime",
                adapter_version="prime-verifiers-v1-operational",
            ),
            portable_contract_schema_version="1.0.0",
            runtime_name="prime-verifiers",
            runtime_version="1.0.0",
            interface_snapshot_sha256="2" * 64,
        ),
    )
    assert report.status == RuntimeCompatibilityStatus.NO_POLICY


def test_matrix_rejects_duplicate_adapter_runtime_authority() -> None:
    with pytest.raises(ValidationError, match="one policy per adapter/runtime pair"):
        RuntimeCompatibilityMatrix(
            policies=(
                _policy(),
                _policy(adapter=_binding(version="2")),
            )
        )


def test_stale_model_copy_cannot_survive_matrix_or_report_boundaries() -> None:
    policy = _policy()
    stale_policy = policy.model_copy(update={"runtime_name": "hud-v2"})
    matrix = RuntimeCompatibilityMatrix(policies=(policy,))
    stale_matrix = matrix.model_copy(update={"policies": (stale_policy,)})

    with pytest.raises(ValidationError, match="compatibility policy"):
        serialize_compatibility_matrix(stale_matrix)

    report = evaluate_runtime_compatibility(policy, _observed())
    stale_report = report.model_copy(
        update={"status": RuntimeCompatibilityStatus.INTERFACE_DRIFT}
    )
    with pytest.raises(ValidationError, match="status does not match"):
        serialize_compatibility_report(stale_report)


def test_stale_observation_copy_is_revalidated_before_evaluation() -> None:
    observed = _observed()
    stale = observed.model_copy(update={"runtime_version": "9.9.9"})

    with pytest.raises(ValidationError, match="runtime observation"):
        evaluate_runtime_compatibility(_policy(), stale)
