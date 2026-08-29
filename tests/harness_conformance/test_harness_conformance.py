from __future__ import annotations

import pytest
from pydantic import ValidationError

from investigation_world.harness_conformance import (
    CapabilitySupport,
    HarnessCapability,
    HarnessCapabilityDeclaration,
    HarnessCapabilityObservation,
    HarnessConformanceError,
    HarnessConformanceReport,
    HarnessConformanceStatus,
    HarnessDeclaration,
    HarnessFixtureObservation,
    HarnessIdentity,
    HarnessTraceField,
    evaluate_harness_conformance,
    require_harness_conformance,
    serialize_harness_declaration,
    serialize_harness_report,
)

CONFIG_DIGEST = "a" * 64
IMPLEMENTATION_DIGEST = "b" * 64
FIXTURE_DIGEST = "c" * 64
RUN_DIGEST = "d" * 64


def _identity(**updates) -> HarnessIdentity:
    values = {
        "harness_id": "fixture-harness",
        "version": "1.2.3",
        "config_sha256": CONFIG_DIGEST,
        "implementation_sha256": IMPLEMENTATION_DIGEST,
    }
    values.update(updates)
    return HarnessIdentity(**values)


def _declaration(
    *,
    overrides: dict[HarnessCapability, HarnessCapabilityDeclaration] | None = None,
    identity: HarnessIdentity | None = None,
) -> HarnessDeclaration:
    overrides = overrides or {}
    capabilities: list[HarnessCapabilityDeclaration] = []
    for capability in HarnessCapability:
        if capability in overrides:
            capabilities.append(overrides[capability])
            continue
        if capability == HarnessCapability.PARALLEL_TOOL_BEHAVIOR:
            capabilities.append(
                HarnessCapabilityDeclaration(
                    capability=capability,
                    support=CapabilitySupport.UNSUPPORTED,
                    limitations=("parallel tool calls are rejected",),
                )
            )
            continue
        capabilities.append(
            HarnessCapabilityDeclaration(
                capability=capability,
                support=CapabilitySupport.SUPPORTED,
                semantics=(f"{capability.value}:fixture-semantics-v1",),
            )
        )
    return HarnessDeclaration(
        identity=identity or _identity(),
        capabilities=tuple(capabilities),
    )


def _observation(
    declaration: HarnessDeclaration,
    *,
    identity: HarnessIdentity | None = None,
    emitted_trace_fields: tuple[HarnessTraceField, ...] | None = None,
    fixture_run_sha256: tuple[str, ...] = (RUN_DIGEST, RUN_DIGEST),
    overrides: dict[HarnessCapability, HarnessCapabilityObservation] | None = None,
) -> HarnessFixtureObservation:
    overrides = overrides or {}
    observations: list[HarnessCapabilityObservation] = []
    for capability in HarnessCapability:
        if capability in overrides:
            observations.append(overrides[capability])
            continue
        declared = declaration.capability(capability)
        observations.append(
            HarnessCapabilityObservation(
                capability=capability,
                observed_support=declared.support,
                semantic_facts=(*declared.semantics, *declared.limitations),
                evidence_gaps=declared.evidence_gaps,
            )
        )
    return HarnessFixtureObservation(
        identity=identity or declaration.identity,
        fixture_id="canonical-harness-fixture-v1",
        fixture_sha256=FIXTURE_DIGEST,
        capability_observations=tuple(observations),
        emitted_trace_fields=(
            tuple(HarnessTraceField)
            if emitted_trace_fields is None
            else emitted_trace_fields
        ),
        fixture_run_sha256=fixture_run_sha256,
    )


def test_explicitly_unsupported_parallel_behavior_can_conform() -> None:
    declaration = _declaration()
    observation = _observation(declaration)

    report = evaluate_harness_conformance(declaration, observation)

    assert report.status == HarnessConformanceStatus.PASS
    assert report.capability_completeness == 1.0
    assert report.trace_completeness == 1.0
    assert report.deterministic_fixture_replay is True
    assert (
        declaration.capability(HarnessCapability.PARALLEL_TOOL_BEHAVIOR).support
        == CapabilitySupport.UNSUPPORTED
    )
    require_harness_conformance(report)


def test_unsupported_capability_requires_observed_limitation_evidence() -> None:
    declaration = _declaration()
    observation = _observation(
        declaration,
        overrides={
            HarnessCapability.PARALLEL_TOOL_BEHAVIOR: HarnessCapabilityObservation(
                capability=HarnessCapability.PARALLEL_TOOL_BEHAVIOR,
                observed_support=CapabilitySupport.UNSUPPORTED,
            )
        },
    )

    report = evaluate_harness_conformance(declaration, observation)

    assert report.status == HarnessConformanceStatus.FAIL
    assert any(
        "capability limitations not observed: parallel_tool_behavior"
        in item
        for item in report.failures
    )


def test_unknown_behavior_never_becomes_pass() -> None:
    unknown_declaration = HarnessCapabilityDeclaration(
        capability=HarnessCapability.CONTEXT_ASSEMBLY,
        support=CapabilitySupport.UNKNOWN,
        evidence_gaps=("context truncation behavior has not been probed",),
    )
    declaration = _declaration(
        overrides={HarnessCapability.CONTEXT_ASSEMBLY: unknown_declaration}
    )
    observation = _observation(
        declaration,
        overrides={
            HarnessCapability.CONTEXT_ASSEMBLY: HarnessCapabilityObservation(
                capability=HarnessCapability.CONTEXT_ASSEMBLY,
                observed_support=CapabilitySupport.UNKNOWN,
                evidence_gaps=("context truncation behavior has not been probed",),
            )
        },
    )

    report = evaluate_harness_conformance(declaration, observation)

    assert report.status == HarnessConformanceStatus.UNKNOWN
    assert any("context_assembly" in item for item in report.unknowns)
    with pytest.raises(HarnessConformanceError, match="UNKNOWN"):
        require_harness_conformance(report)


def test_exact_harness_version_and_config_identity_is_required() -> None:
    declaration = _declaration()
    observation = _observation(
        declaration,
        identity=_identity(config_sha256="e" * 64),
    )

    report = evaluate_harness_conformance(declaration, observation)

    assert report.status == HarnessConformanceStatus.FAIL
    assert any("identity/version/config" in item for item in report.failures)


def test_provider_errors_retries_and_usage_cannot_disappear_from_trace() -> None:
    declaration = _declaration()
    emitted = tuple(
        item
        for item in HarnessTraceField
        if item
        not in {
            HarnessTraceField.PROVIDER_ERROR,
            HarnessTraceField.RETRY_ATTEMPT,
            HarnessTraceField.TOKEN_USAGE,
        }
    )
    observation = _observation(declaration, emitted_trace_fields=emitted)

    report = evaluate_harness_conformance(declaration, observation)

    assert report.status == HarnessConformanceStatus.FAIL
    assert report.trace_completeness < 1.0
    assert any("provider_error" in item for item in report.failures)
    assert any("retry_attempt" in item for item in report.failures)
    assert any("token_usage" in item for item in report.failures)


def test_capability_semantics_must_be_observed_not_only_declared() -> None:
    declaration = _declaration()
    observation = _observation(
        declaration,
        overrides={
            HarnessCapability.TIMEOUT_RETRY: HarnessCapabilityObservation(
                capability=HarnessCapability.TIMEOUT_RETRY,
                observed_support=CapabilitySupport.SUPPORTED,
                semantic_facts=("timeout_retry:different-behavior",),
            )
        },
    )

    report = evaluate_harness_conformance(declaration, observation)

    assert report.status == HarnessConformanceStatus.FAIL
    assert any("timeout_retry" in item for item in report.failures)


def test_deterministic_fixture_requires_repeat_evidence() -> None:
    declaration = _declaration()

    insufficient = evaluate_harness_conformance(
        declaration,
        _observation(declaration, fixture_run_sha256=(RUN_DIGEST,)),
    )
    divergent = evaluate_harness_conformance(
        declaration,
        _observation(
            declaration,
            fixture_run_sha256=(RUN_DIGEST, "f" * 64),
        ),
    )

    assert insufficient.status == HarnessConformanceStatus.UNKNOWN
    assert insufficient.deterministic_fixture_replay is None
    assert divergent.status == HarnessConformanceStatus.FAIL
    assert divergent.deterministic_fixture_replay is False


def test_declaration_requires_every_behavior_dimension() -> None:
    declaration = _declaration()
    incomplete = tuple(
        item
        for item in declaration.capabilities
        if item.capability != HarnessCapability.FAILURE_REPORTING
    )

    with pytest.raises(ValidationError, match="omits required capabilities"):
        HarnessDeclaration(identity=_identity(), capabilities=incomplete)


def test_supported_and_unknown_capability_evidence_rules_are_fail_closed() -> None:
    with pytest.raises(ValidationError, match="observable semantics"):
        HarnessCapabilityDeclaration(
            capability=HarnessCapability.MODEL_TRANSPORT,
            support=CapabilitySupport.SUPPORTED,
        )

    with pytest.raises(ValidationError, match="evidence_gaps"):
        HarnessCapabilityDeclaration(
            capability=HarnessCapability.CONTEXT_ASSEMBLY,
            support=CapabilitySupport.UNKNOWN,
        )


def test_stale_copied_declaration_is_revalidated_before_evaluation() -> None:
    declaration = _declaration()
    stale_identity = declaration.identity.model_copy(update={"version": "9.9.9"})
    stale = declaration.model_copy(update={"identity": stale_identity})

    with pytest.raises(ValidationError, match="declaration digest"):
        evaluate_harness_conformance(stale, _observation(declaration))


def test_stale_copied_report_cannot_be_serialized() -> None:
    declaration = _declaration()
    report = evaluate_harness_conformance(declaration, _observation(declaration))
    stale = report.model_copy(update={"status": HarnessConformanceStatus.FAIL})

    with pytest.raises(ValidationError, match="does not match validated inputs"):
        serialize_harness_report(stale)


def test_serialization_is_deterministic_and_content_bound() -> None:
    first = _declaration()
    second = HarnessDeclaration(
        identity=first.identity,
        capabilities=tuple(reversed(first.capabilities)),
    )

    assert first.declaration_id == second.declaration_id
    assert first.content_sha256 == second.content_sha256
    assert serialize_harness_declaration(first) == serialize_harness_declaration(second)

    first_report = evaluate_harness_conformance(first, _observation(first))
    second_report = HarnessConformanceReport.model_validate(
        first_report.model_dump(mode="python")
    )
    assert serialize_harness_report(first_report) == serialize_harness_report(second_report)