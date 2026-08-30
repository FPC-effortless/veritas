from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

HARNESS_CONFORMANCE_SCHEMA_VERSION = "veritas.harness-conformance.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CapabilitySupport(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class HarnessCapability(StrEnum):
    MODEL_TRANSPORT = "model_transport"
    TOOL_CAPABILITY_TRANSPORT = "tool_capability_transport"
    CONTEXT_ASSEMBLY = "context_assembly"
    ARTIFACT_VISIBILITY_ACCESS = "artifact_visibility_access"
    PARALLEL_TOOL_BEHAVIOR = "parallel_tool_behavior"
    TIMEOUT_RETRY = "timeout_retry"
    SYSTEM_SKILL_INJECTION = "system_skill_injection"
    STATE_RESET_VISIBILITY = "state_reset_visibility"
    TRAJECTORY_EVENT_EMISSION = "trajectory_event_emission"
    USAGE_ACCOUNTING = "usage_accounting"
    FAILURE_REPORTING = "failure_reporting"


class HarnessTraceField(StrEnum):
    MODEL_REQUEST = "model_request"
    MODEL_RESPONSE = "model_response"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    PROVIDER_REQUEST_ID = "provider_request_id"
    PROVIDER_ERROR = "provider_error"
    RETRY_ATTEMPT = "retry_attempt"
    TIMEOUT = "timeout"
    RESET = "reset"
    ARTIFACT_ACCESS = "artifact_access"
    TOKEN_USAGE = "token_usage"
    COST_USAGE = "cost_usage"
    TIME_USAGE = "time_usage"
    FAILURE_CLASSIFICATION = "failure_classification"


class HarnessConformanceStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class HarnessConformanceError(RuntimeError):
    pass


class _CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="json"))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(child) for key, child in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_sha256(value: str, *, field_name: str) -> None:
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _normalized_strings(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted({value.strip() for value in values if value.strip()}))
    if len(normalized) != len(values):
        raise ValueError(f"{field_name} must contain unique non-empty values")
    return normalized


def _normalized_trace_fields(
    values: tuple[HarnessTraceField, ...],
) -> tuple[HarnessTraceField, ...]:
    if len(values) != len(set(values)):
        raise ValueError("trace fields must be unique")
    return tuple(sorted(values, key=lambda item: item.value))


class HarnessIdentity(_CanonicalModel):
    """Exact harness/version/config identity used for comparison."""

    harness_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    config_sha256: str
    implementation_sha256: str | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> "HarnessIdentity":
        _require_sha256(self.config_sha256, field_name="config_sha256")
        if self.implementation_sha256 is not None:
            _require_sha256(
                self.implementation_sha256,
                field_name="implementation_sha256",
            )
        return self


class HarnessCapabilityDeclaration(_CanonicalModel):
    capability: HarnessCapability
    support: CapabilitySupport
    semantics: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    expected_trace_fields: tuple[HarnessTraceField, ...] = ()
    evidence_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_capability(self) -> "HarnessCapabilityDeclaration":
        semantics = _normalized_strings(self.semantics, field_name="semantics")
        limitations = _normalized_strings(self.limitations, field_name="limitations")
        evidence_gaps = _normalized_strings(self.evidence_gaps, field_name="evidence_gaps")
        trace_fields = _normalized_trace_fields(self.expected_trace_fields)
        object.__setattr__(self, "semantics", semantics)
        object.__setattr__(self, "limitations", limitations)
        object.__setattr__(self, "evidence_gaps", evidence_gaps)
        object.__setattr__(self, "expected_trace_fields", trace_fields)

        if self.support == CapabilitySupport.SUPPORTED:
            if not semantics:
                raise ValueError("SUPPORTED capability must declare observable semantics")
            if evidence_gaps:
                raise ValueError("SUPPORTED capability cannot retain evidence_gaps")
        elif self.support == CapabilitySupport.UNSUPPORTED:
            if not limitations:
                raise ValueError("UNSUPPORTED capability must state its limitation")
            if evidence_gaps:
                raise ValueError("UNSUPPORTED capability cannot retain evidence_gaps")
        elif not evidence_gaps:
            raise ValueError("UNKNOWN capability must state evidence_gaps")
        return self


class HarnessDeclaration(_CanonicalModel):
    schema_version: str = HARNESS_CONFORMANCE_SCHEMA_VERSION
    declaration_id: str = ""
    content_sha256: str = ""
    identity: HarnessIdentity
    capabilities: tuple[HarnessCapabilityDeclaration, ...]
    public_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_declaration(self) -> "HarnessDeclaration":
        if self.schema_version != HARNESS_CONFORMANCE_SCHEMA_VERSION:
            raise ValueError("unsupported harness declaration schema version")
        capabilities = tuple(
            sorted(self.capabilities, key=lambda item: item.capability.value)
        )
        keys = [item.capability for item in capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("harness capabilities must be unique")
        missing = set(HarnessCapability) - set(keys)
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise ValueError(f"harness declaration omits required capabilities: {names}")
        notes = _normalized_strings(self.public_notes, field_name="public_notes")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "public_notes", notes)

        payload = self.model_dump(
            mode="json",
            exclude={"declaration_id", "content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"HARNESS-{digest[:24].upper()}"
        if self.content_sha256 and self.content_sha256 != digest:
            raise ValueError("harness declaration digest does not match contents")
        if self.declaration_id and self.declaration_id != identifier:
            raise ValueError("harness declaration ID does not match contents")
        object.__setattr__(self, "content_sha256", digest)
        object.__setattr__(self, "declaration_id", identifier)
        return self

    def capability(self, capability: HarnessCapability) -> HarnessCapabilityDeclaration:
        return next(item for item in self.capabilities if item.capability == capability)


class HarnessCapabilityObservation(_CanonicalModel):
    capability: HarnessCapability
    observed_support: CapabilitySupport
    semantic_facts: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_observation(self) -> "HarnessCapabilityObservation":
        facts = _normalized_strings(self.semantic_facts, field_name="semantic_facts")
        gaps = _normalized_strings(self.evidence_gaps, field_name="evidence_gaps")
        object.__setattr__(self, "semantic_facts", facts)
        object.__setattr__(self, "evidence_gaps", gaps)
        if self.observed_support == CapabilitySupport.UNKNOWN:
            if not gaps:
                raise ValueError("UNKNOWN observed capability must state evidence_gaps")
        elif gaps:
            raise ValueError("resolved observed capability cannot retain evidence_gaps")
        return self


class HarnessFixtureObservation(_CanonicalModel):
    schema_version: str = HARNESS_CONFORMANCE_SCHEMA_VERSION
    observation_id: str = ""
    content_sha256: str = ""
    identity: HarnessIdentity
    fixture_id: str = Field(min_length=1)
    fixture_sha256: str
    capability_observations: tuple[HarnessCapabilityObservation, ...]
    emitted_trace_fields: tuple[HarnessTraceField, ...] = ()
    fixture_run_sha256: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_fixture_observation(self) -> "HarnessFixtureObservation":
        if self.schema_version != HARNESS_CONFORMANCE_SCHEMA_VERSION:
            raise ValueError("unsupported harness observation schema version")
        _require_sha256(self.fixture_sha256, field_name="fixture_sha256")
        for digest in self.fixture_run_sha256:
            _require_sha256(digest, field_name="fixture_run_sha256")
        observations = tuple(
            sorted(self.capability_observations, key=lambda item: item.capability.value)
        )
        keys = [item.capability for item in observations]
        if len(keys) != len(set(keys)):
            raise ValueError("observed harness capabilities must be unique")
        traces = _normalized_trace_fields(self.emitted_trace_fields)
        object.__setattr__(self, "capability_observations", observations)
        object.__setattr__(self, "emitted_trace_fields", traces)

        payload = self.model_dump(
            mode="json",
            exclude={"observation_id", "content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"HARNESSOBS-{digest[:24].upper()}"
        if self.content_sha256 and self.content_sha256 != digest:
            raise ValueError("harness observation digest does not match contents")
        if self.observation_id and self.observation_id != identifier:
            raise ValueError("harness observation ID does not match contents")
        object.__setattr__(self, "content_sha256", digest)
        object.__setattr__(self, "observation_id", identifier)
        return self

    def capability(
        self,
        capability: HarnessCapability,
    ) -> HarnessCapabilityObservation | None:
        return next(
            (item for item in self.capability_observations if item.capability == capability),
            None,
        )


_DEFAULT_TRACE_FIELDS = tuple(HarnessTraceField)
_DEFAULT_CAPABILITIES = tuple(HarnessCapability)


class HarnessConformancePolicy(_CanonicalModel):
    schema_version: str = HARNESS_CONFORMANCE_SCHEMA_VERSION
    policy_id: str = ""
    content_sha256: str = ""
    required_capabilities: tuple[HarnessCapability, ...] = _DEFAULT_CAPABILITIES
    required_trace_fields: tuple[HarnessTraceField, ...] = _DEFAULT_TRACE_FIELDS
    minimum_fixture_runs: int = Field(default=2, ge=2)

    @model_validator(mode="after")
    def validate_policy(self) -> "HarnessConformancePolicy":
        if self.schema_version != HARNESS_CONFORMANCE_SCHEMA_VERSION:
            raise ValueError("unsupported harness conformance policy schema version")
        if len(self.required_capabilities) != len(set(self.required_capabilities)):
            raise ValueError("required capabilities must be unique")
        if len(self.required_trace_fields) != len(set(self.required_trace_fields)):
            raise ValueError("trace fields must be unique")

        # HARNESS-001 defines these as an irreducible observation baseline.
        # A harness-specific policy may add requirements, but it cannot remove
        # canonical capability or trace obligations supplied by this schema.
        capabilities = tuple(
            sorted(
                set(_DEFAULT_CAPABILITIES) | set(self.required_capabilities),
                key=lambda item: item.value,
            )
        )
        traces = tuple(
            sorted(
                set(_DEFAULT_TRACE_FIELDS) | set(self.required_trace_fields),
                key=lambda item: item.value,
            )
        )
        object.__setattr__(self, "required_capabilities", capabilities)
        object.__setattr__(self, "required_trace_fields", traces)

        payload = self.model_dump(
            mode="json",
            exclude={"policy_id", "content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"HARNESSPOL-{digest[:24].upper()}"
        if self.content_sha256 and self.content_sha256 != digest:
            raise ValueError("harness conformance policy digest does not match contents")
        if self.policy_id and self.policy_id != identifier:
            raise ValueError("harness conformance policy ID does not match contents")
        object.__setattr__(self, "content_sha256", digest)
        object.__setattr__(self, "policy_id", identifier)
        return self


class HarnessConformanceReport(_CanonicalModel):
    schema_version: str = HARNESS_CONFORMANCE_SCHEMA_VERSION
    report_id: str = ""
    content_sha256: str = ""
    declaration: HarnessDeclaration
    observation: HarnessFixtureObservation
    policy: HarnessConformancePolicy
    status: HarnessConformanceStatus | None = None
    failures: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    capability_completeness: float | None = Field(default=None, ge=0.0, le=1.0)
    trace_completeness: float | None = Field(default=None, ge=0.0, le=1.0)
    deterministic_fixture_replay: bool | None = None

    @model_validator(mode="after")
    def validate_report(self) -> "HarnessConformanceReport":
        declaration = _validated_declaration(self.declaration)
        observation = _validated_observation(self.observation)
        policy = _validated_policy(self.policy)
        assessment = _assess(declaration, observation, policy)

        supplied = (
            self.status,
            self.failures,
            self.unknowns,
            self.capability_completeness,
            self.trace_completeness,
            self.deterministic_fixture_replay,
        )
        expected = (
            assessment[0],
            assessment[1],
            assessment[2],
            assessment[3],
            assessment[4],
            assessment[5],
        )
        if self.status is not None and supplied != expected:
            raise ValueError("harness conformance report does not match validated inputs")

        object.__setattr__(self, "declaration", declaration)
        object.__setattr__(self, "observation", observation)
        object.__setattr__(self, "policy", policy)
        object.__setattr__(self, "status", assessment[0])
        object.__setattr__(self, "failures", assessment[1])
        object.__setattr__(self, "unknowns", assessment[2])
        object.__setattr__(self, "capability_completeness", assessment[3])
        object.__setattr__(self, "trace_completeness", assessment[4])
        object.__setattr__(self, "deterministic_fixture_replay", assessment[5])

        payload = self.model_dump(
            mode="json",
            exclude={"report_id", "content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"HARNESSREPORT-{digest[:24].upper()}"
        if self.content_sha256 and self.content_sha256 != digest:
            raise ValueError("harness conformance report digest does not match contents")
        if self.report_id and self.report_id != identifier:
            raise ValueError("harness conformance report ID does not match contents")
        object.__setattr__(self, "content_sha256", digest)
        object.__setattr__(self, "report_id", identifier)
        return self


def _validated_declaration(declaration: HarnessDeclaration) -> HarnessDeclaration:
    return HarnessDeclaration.model_validate(declaration.model_dump(mode="python"))


def _validated_observation(observation: HarnessFixtureObservation) -> HarnessFixtureObservation:
    return HarnessFixtureObservation.model_validate(observation.model_dump(mode="python"))


def _validated_policy(policy: HarnessConformancePolicy) -> HarnessConformancePolicy:
    return HarnessConformancePolicy.model_validate(policy.model_dump(mode="python"))


def _assess(
    declaration: HarnessDeclaration,
    observation: HarnessFixtureObservation,
    policy: HarnessConformancePolicy,
) -> tuple[
    HarnessConformanceStatus,
    tuple[str, ...],
    tuple[str, ...],
    float,
    float,
    bool | None,
]:
    failures: list[str] = []
    unknowns: list[str] = []

    if declaration.identity != observation.identity:
        failures.append("observed harness identity/version/config does not match declaration")

    resolved_capabilities = 0
    for capability in policy.required_capabilities:
        declared = declaration.capability(capability)
        observed = observation.capability(capability)
        if observed is None:
            failures.append(f"missing observed capability: {capability.value}")
            continue
        if declared.support == CapabilitySupport.UNKNOWN:
            unknowns.append(f"declared capability remains UNKNOWN: {capability.value}")
            continue
        if observed.observed_support == CapabilitySupport.UNKNOWN:
            unknowns.append(f"observed capability remains UNKNOWN: {capability.value}")
            continue
        resolved_capabilities += 1
        if declared.support != observed.observed_support:
            failures.append(f"capability support mismatch: {capability.value}")
            continue
        missing_semantics = set(declared.semantics) - set(observed.semantic_facts)
        if missing_semantics:
            failures.append(
                "capability semantics not observed: "
                f"{capability.value} -> {', '.join(sorted(missing_semantics))}"
            )
        if declared.support == CapabilitySupport.UNSUPPORTED:
            missing_limitations = set(declared.limitations) - set(observed.semantic_facts)
            if missing_limitations:
                failures.append(
                    "capability limitations not observed: "
                    f"{capability.value} -> {', '.join(sorted(missing_limitations))}"
                )

    required_trace_fields = set(policy.required_trace_fields)
    for item in declaration.capabilities:
        required_trace_fields.update(item.expected_trace_fields)
    emitted = set(observation.emitted_trace_fields)
    missing_trace_fields = required_trace_fields - emitted
    if missing_trace_fields:
        failures.append(
            "required trace fields missing: "
            + ", ".join(sorted(item.value for item in missing_trace_fields))
        )

    capability_completeness = resolved_capabilities / len(policy.required_capabilities)
    trace_completeness = (
        len(required_trace_fields & emitted) / len(required_trace_fields)
        if required_trace_fields
        else 1.0
    )

    deterministic: bool | None
    runs = observation.fixture_run_sha256
    if len(runs) < policy.minimum_fixture_runs:
        deterministic = None
        unknowns.append(
            "insufficient deterministic fixture replays: "
            f"{len(runs)} < {policy.minimum_fixture_runs}"
        )
    else:
        deterministic = len(set(runs)) == 1
        if not deterministic:
            failures.append("deterministic fixture replay digests diverged")

    if failures:
        status = HarnessConformanceStatus.FAIL
    elif unknowns:
        status = HarnessConformanceStatus.UNKNOWN
    else:
        status = HarnessConformanceStatus.PASS

    return (
        status,
        tuple(sorted(failures)),
        tuple(sorted(unknowns)),
        capability_completeness,
        trace_completeness,
        deterministic,
    )


def evaluate_harness_conformance(
    declaration: HarnessDeclaration,
    observation: HarnessFixtureObservation,
    *,
    policy: HarnessConformancePolicy | None = None,
) -> HarnessConformanceReport:
    return HarnessConformanceReport(
        declaration=declaration,
        observation=observation,
        policy=policy or HarnessConformancePolicy(),
    )


def require_harness_conformance(report: HarnessConformanceReport) -> None:
    validated = HarnessConformanceReport.model_validate(report.model_dump(mode="python"))
    if validated.status != HarnessConformanceStatus.PASS:
        detail = "; ".join((*validated.failures, *validated.unknowns))
        raise HarnessConformanceError(
            f"harness conformance is {validated.status}: {detail or 'no PASS evidence'}"
        )


def serialize_harness_declaration(declaration: HarnessDeclaration) -> bytes:
    validated = _validated_declaration(declaration)
    return _canonical_json(validated).encode("utf-8")


def serialize_harness_report(report: HarnessConformanceReport) -> bytes:
    validated = HarnessConformanceReport.model_validate(report.model_dump(mode="python"))
    return _canonical_json(validated).encode("utf-8")