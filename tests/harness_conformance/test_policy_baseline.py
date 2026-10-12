from __future__ import annotations

from investigation_world.harness_conformance import (
    CapabilitySupport,
    HarnessCapability,
    HarnessCapabilityDeclaration,
    HarnessCapabilityObservation,
    HarnessConformancePolicy,
    HarnessConformanceStatus,
    HarnessDeclaration,
    HarnessFixtureObservation,
    HarnessIdentity,
    HarnessTraceField,
    evaluate_harness_conformance,
)


def _declaration() -> HarnessDeclaration:
    capabilities = []
    for capability in HarnessCapability:
        if capability == HarnessCapability.PARALLEL_TOOL_BEHAVIOR:
            capabilities.append(
                HarnessCapabilityDeclaration(
                    capability=capability,
                    support=CapabilitySupport.UNSUPPORTED,
                    limitations=("parallel tool calls are rejected",),
                )
            )
        else:
            capabilities.append(
                HarnessCapabilityDeclaration(
                    capability=capability,
                    support=CapabilitySupport.SUPPORTED,
                    semantics=(f"{capability.value}:fixture-semantics-v1",),
                )
            )
    return HarnessDeclaration(
        identity=HarnessIdentity(
            harness_id="fixture-harness",
            version="1.2.3",
            config_sha256="a" * 64,
            implementation_sha256="b" * 64,
        ),
        capabilities=tuple(capabilities),
    )


def test_custom_policy_cannot_remove_harness_baseline_obligations() -> None:
    declaration = _declaration()
    observations = []
    for capability in HarnessCapability:
        declared = declaration.capability(capability)
        if capability == HarnessCapability.FAILURE_REPORTING:
            observations.append(
                HarnessCapabilityObservation(
                    capability=capability,
                    observed_support=CapabilitySupport.UNKNOWN,
                    evidence_gaps=("failure classification was not captured",),
                )
            )
        else:
            observations.append(
                HarnessCapabilityObservation(
                    capability=capability,
                    observed_support=declared.support,
                    semantic_facts=declared.semantics,
                )
            )

    observation = HarnessFixtureObservation(
        identity=declaration.identity,
        fixture_id="baseline-cannot-be-weakened",
        fixture_sha256="c" * 64,
        capability_observations=tuple(observations),
        emitted_trace_fields=(HarnessTraceField.MODEL_REQUEST,),
        fixture_run_sha256=("d" * 64, "d" * 64),
    )
    weak_policy = HarnessConformancePolicy(
        required_capabilities=(HarnessCapability.MODEL_TRANSPORT,),
        required_trace_fields=(HarnessTraceField.MODEL_REQUEST,),
    )

    report = evaluate_harness_conformance(
        declaration,
        observation,
        policy=weak_policy,
    )

    assert set(report.policy.required_capabilities) == set(HarnessCapability)
    assert set(report.policy.required_trace_fields) == set(HarnessTraceField)
    assert report.status == HarnessConformanceStatus.FAIL
    assert any("failure_reporting" in item for item in report.unknowns)
    assert any("provider_error" in item for item in report.failures)
    assert any("retry_attempt" in item for item in report.failures)
    assert any("token_usage" in item for item in report.failures)
    assert any("cost_usage" in item for item in report.failures)
    assert any("time_usage" in item for item in report.failures)
    assert any("failure_classification" in item for item in report.failures)
