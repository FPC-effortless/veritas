from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.conformance.certificate import (
    ConformanceCertificate,
    ConformanceCertificateStatus,
)

COMPATIBILITY_SCHEMA_VERSION = "veritas.runtime-compatibility.v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha256(value: str, *, field_name: str) -> None:
    if _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _semver(value: str) -> tuple[int, int, int]:
    match = _SEMVER_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"{value!r} is not a strict MAJOR.MINOR.PATCH version")
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch)


def _clean_tokens(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted({value.strip() for value in values if value.strip()}))
    if len(normalized) != len(values):
        raise ValueError(f"{field_name} must contain unique non-empty values")
    return normalized


class CompatibilityValidationState(StrEnum):
    VALIDATED = "VALIDATED"
    UNVALIDATED = "UNVALIDATED"


class RuntimeCompatibilityStatus(StrEnum):
    TESTED_INTERFACE_MATCH = "TESTED_INTERFACE_MATCH"
    NO_POLICY = "NO_POLICY"
    UNVALIDATED = "UNVALIDATED"
    ADAPTER_MISMATCH = "ADAPTER_MISMATCH"
    PORTABLE_CONTRACT_MISMATCH = "PORTABLE_CONTRACT_MISMATCH"
    RUNTIME_MISMATCH = "RUNTIME_MISMATCH"
    VERSION_OUT_OF_RANGE = "VERSION_OUT_OF_RANGE"
    PROTOCOL_MISMATCH = "PROTOCOL_MISMATCH"
    INTERFACE_DRIFT = "INTERFACE_DRIFT"


class ConformanceBindingStatus(StrEnum):
    NOT_PROVIDED = "NOT_PROVIDED"
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


class TestedVersionRange(BaseModel):
    """Exact opaque versions and/or one strict semantic-version interval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    exact_versions: tuple[str, ...] = ()
    minimum_version: str | None = None
    maximum_version: str | None = None
    include_minimum: bool = True
    include_maximum: bool = True

    @model_validator(mode="after")
    def validate_range(self) -> "TestedVersionRange":
        exact_versions = _clean_tokens(self.exact_versions, field_name="exact_versions")
        object.__setattr__(self, "exact_versions", exact_versions)
        if not exact_versions and self.minimum_version is None and self.maximum_version is None:
            raise ValueError(
                "tested version range must declare an exact version or semantic interval"
            )

        minimum = _semver(self.minimum_version) if self.minimum_version is not None else None
        maximum = _semver(self.maximum_version) if self.maximum_version is not None else None
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum_version must not exceed maximum_version")
        return self

    def contains(self, version: str) -> bool:
        if version in self.exact_versions:
            return True
        if self.minimum_version is None and self.maximum_version is None:
            return False
        try:
            parsed = _semver(version)
        except ValueError:
            return False
        if self.minimum_version is not None:
            minimum = _semver(self.minimum_version)
            if parsed < minimum or (parsed == minimum and not self.include_minimum):
                return False
        if self.maximum_version is not None:
            maximum = _semver(self.maximum_version)
            if parsed > maximum or (parsed == maximum and not self.include_maximum):
                return False
        return True


class AdapterCompatibilityBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    content_sha256: str | None = None

    @model_validator(mode="after")
    def validate_binding(self) -> "AdapterCompatibilityBinding":
        if self.content_sha256 is not None:
            _require_sha256(self.content_sha256, field_name="adapter content_sha256")
        return self


class RuntimeCompatibilityPolicy(BaseModel):
    """One fail-closed tested-version declaration for an adapter/runtime pair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = COMPATIBILITY_SCHEMA_VERSION
    policy_id: str = ""
    policy_content_sha256: str = ""
    adapter: AdapterCompatibilityBinding
    portable_contract_schema_version: str = Field(min_length=1)
    runtime_name: str = Field(min_length=1)
    tested_versions: TestedVersionRange | None = None
    tested_protocol_versions: tuple[str, ...] = ()
    interface_snapshot_sha256: str | None = None
    validated_commit_sha: str | None = None
    validated_on: date | None = None
    validation_state: CompatibilityValidationState = CompatibilityValidationState.UNVALIDATED
    known_unsupported_semantics: tuple[str, ...] = ()
    known_semantic_losses: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_policy(self) -> "RuntimeCompatibilityPolicy":
        if self.schema_version != COMPATIBILITY_SCHEMA_VERSION:
            raise ValueError("unsupported runtime compatibility schema version")

        protocols = _clean_tokens(
            self.tested_protocol_versions,
            field_name="tested_protocol_versions",
        )
        unsupported = _clean_tokens(
            self.known_unsupported_semantics,
            field_name="known_unsupported_semantics",
        )
        losses = _clean_tokens(
            self.known_semantic_losses,
            field_name="known_semantic_losses",
        )
        evidence_gaps = _clean_tokens(self.evidence_gaps, field_name="evidence_gaps")
        object.__setattr__(self, "tested_protocol_versions", protocols)
        object.__setattr__(self, "known_unsupported_semantics", unsupported)
        object.__setattr__(self, "known_semantic_losses", losses)
        object.__setattr__(self, "evidence_gaps", evidence_gaps)

        if self.interface_snapshot_sha256 is not None:
            _require_sha256(
                self.interface_snapshot_sha256,
                field_name="interface_snapshot_sha256",
            )
        if self.validated_commit_sha is not None and (
            _COMMIT_RE.fullmatch(self.validated_commit_sha) is None
        ):
            raise ValueError("validated_commit_sha must be a lowercase 40-character commit SHA")

        if self.validation_state == CompatibilityValidationState.VALIDATED:
            missing: list[str] = []
            if self.adapter.content_sha256 is None:
                missing.append("adapter.content_sha256")
            if self.tested_versions is None:
                missing.append("tested_versions")
            if self.interface_snapshot_sha256 is None:
                missing.append("interface_snapshot_sha256")
            if self.validated_commit_sha is None:
                missing.append("validated_commit_sha")
            if self.validated_on is None:
                missing.append("validated_on")
            if missing:
                raise ValueError(
                    "VALIDATED compatibility policy is missing evidence: "
                    + ", ".join(missing)
                )

        payload = self.model_dump(
            mode="json",
            exclude={"policy_id", "policy_content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"COMPAT-{digest[:24].upper()}"
        if self.policy_content_sha256 and self.policy_content_sha256 != digest:
            raise ValueError("compatibility policy digest does not match immutable contents")
        if self.policy_id and self.policy_id != identifier:
            raise ValueError("compatibility policy ID does not match immutable contents")
        object.__setattr__(self, "policy_content_sha256", digest)
        object.__setattr__(self, "policy_id", identifier)
        return self


class ObservedRuntimeInterface(BaseModel):
    """Observed runtime/protocol/interface identity supplied by a probe or fixture."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    observation_id: str = ""
    observation_content_sha256: str = ""
    adapter: AdapterCompatibilityBinding
    portable_contract_schema_version: str = Field(min_length=1)
    runtime_name: str = Field(min_length=1)
    runtime_version: str = Field(min_length=1)
    protocol_version: str | None = None
    interface_snapshot_sha256: str

    @model_validator(mode="after")
    def validate_observation(self) -> "ObservedRuntimeInterface":
        _require_sha256(
            self.interface_snapshot_sha256,
            field_name="interface_snapshot_sha256",
        )
        payload = self.model_dump(
            mode="json",
            exclude={"observation_id", "observation_content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"COMPATOBS-{digest[:24].upper()}"
        if self.observation_content_sha256 and self.observation_content_sha256 != digest:
            raise ValueError("runtime observation digest does not match immutable contents")
        if self.observation_id and self.observation_id != identifier:
            raise ValueError("runtime observation ID does not match immutable contents")
        object.__setattr__(self, "observation_content_sha256", digest)
        object.__setattr__(self, "observation_id", identifier)
        return self


def _validated_policy(policy: RuntimeCompatibilityPolicy) -> RuntimeCompatibilityPolicy:
    return RuntimeCompatibilityPolicy.model_validate(policy.model_dump(mode="python"))


def _validated_observation(observed: ObservedRuntimeInterface) -> ObservedRuntimeInterface:
    return ObservedRuntimeInterface.model_validate(observed.model_dump(mode="python"))


def _compatibility_assessment(
    policy: RuntimeCompatibilityPolicy | None,
    observed: ObservedRuntimeInterface,
) -> tuple[RuntimeCompatibilityStatus, tuple[str, ...]]:
    if policy is None:
        return RuntimeCompatibilityStatus.NO_POLICY, (
            "no compatibility policy matches the observed adapter/runtime pair",
        )

    reasons: list[str] = []
    adapter = policy.adapter
    observed_adapter = observed.adapter
    if (
        adapter.adapter_name != observed_adapter.adapter_name
        or adapter.adapter_version != observed_adapter.adapter_version
        or (
            adapter.content_sha256 is not None
            and adapter.content_sha256 != observed_adapter.content_sha256
        )
    ):
        reasons.append("observed adapter identity/version/content does not match policy")
        return RuntimeCompatibilityStatus.ADAPTER_MISMATCH, tuple(reasons)

    if policy.portable_contract_schema_version != observed.portable_contract_schema_version:
        reasons.append("portable contract schema version is outside the validated binding")
        return RuntimeCompatibilityStatus.PORTABLE_CONTRACT_MISMATCH, tuple(reasons)

    if policy.runtime_name != observed.runtime_name:
        reasons.append("observed target runtime does not match policy")
        return RuntimeCompatibilityStatus.RUNTIME_MISMATCH, tuple(reasons)

    if policy.validation_state != CompatibilityValidationState.VALIDATED:
        reasons.append("adapter/runtime pair has no complete validation evidence")
        return RuntimeCompatibilityStatus.UNVALIDATED, tuple(reasons)

    if policy.tested_versions is None or not policy.tested_versions.contains(
        observed.runtime_version
    ):
        reasons.append("observed runtime version is outside the tested version set/range")
        return RuntimeCompatibilityStatus.VERSION_OUT_OF_RANGE, tuple(reasons)

    if policy.tested_protocol_versions and (
        observed.protocol_version not in policy.tested_protocol_versions
    ):
        reasons.append("observed protocol version is outside the tested protocol set")
        return RuntimeCompatibilityStatus.PROTOCOL_MISMATCH, tuple(reasons)

    if policy.interface_snapshot_sha256 != observed.interface_snapshot_sha256:
        reasons.append("observed target interface snapshot differs from validated snapshot")
        return RuntimeCompatibilityStatus.INTERFACE_DRIFT, tuple(reasons)

    return RuntimeCompatibilityStatus.TESTED_INTERFACE_MATCH, ()


def _conformance_binding(
    certificate: ConformanceCertificate | None,
    policy: RuntimeCompatibilityPolicy | None,
    observed: ObservedRuntimeInterface,
) -> tuple[
    ConformanceCertificate | None,
    ConformanceBindingStatus,
    ConformanceCertificateStatus | None,
]:
    if certificate is None:
        return None, ConformanceBindingStatus.NOT_PROVIDED, None
    validated = ConformanceCertificate.model_validate(certificate.model_dump(mode="python"))
    if policy is None:
        return validated, ConformanceBindingStatus.MISMATCH, None

    adapter = policy.adapter
    certificate_adapter = validated.adapter
    target = validated.target_runtime
    source = validated.source_contract
    matches = (
        certificate_adapter.adapter_name == adapter.adapter_name
        and certificate_adapter.adapter_version == adapter.adapter_version
        and (
            adapter.content_sha256 is None
            or certificate_adapter.content_sha256 == adapter.content_sha256
        )
        and target.runtime_name == observed.runtime_name
        and target.runtime_version == observed.runtime_version
        and source.schema_version == observed.portable_contract_schema_version
    )
    if not matches:
        return validated, ConformanceBindingStatus.MISMATCH, None
    return validated, ConformanceBindingStatus.MATCH, validated.status


class RuntimeCompatibilityReport(BaseModel):
    """Compatibility is version/interface evidence, not semantic conformance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = COMPATIBILITY_SCHEMA_VERSION
    report_id: str = ""
    report_content_sha256: str = ""
    policy: RuntimeCompatibilityPolicy | None = None
    observed: ObservedRuntimeInterface
    status: RuntimeCompatibilityStatus | None = None
    reasons: tuple[str, ...] = ()
    conformance_certificate: ConformanceCertificate | None = None
    conformance_binding: ConformanceBindingStatus = ConformanceBindingStatus.NOT_PROVIDED
    conformance_status: ConformanceCertificateStatus | None = None
    known_unsupported_semantics: tuple[str, ...] = ()
    known_semantic_losses: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_report(self) -> "RuntimeCompatibilityReport":
        if self.schema_version != COMPATIBILITY_SCHEMA_VERSION:
            raise ValueError("unsupported runtime compatibility report schema version")

        policy = _validated_policy(self.policy) if self.policy is not None else None
        observed = _validated_observation(self.observed)
        status, reasons = _compatibility_assessment(policy, observed)
        certificate, binding, conformance_status = _conformance_binding(
            self.conformance_certificate,
            policy,
            observed,
        )
        unsupported = policy.known_unsupported_semantics if policy is not None else ()
        losses = policy.known_semantic_losses if policy is not None else ()
        evidence_gaps = policy.evidence_gaps if policy is not None else ()

        if self.status is not None and self.status != status:
            raise ValueError("compatibility report status does not match validated inputs")
        if self.reasons and self.reasons != reasons:
            raise ValueError("compatibility report reasons do not match validated inputs")
        if self.conformance_binding != ConformanceBindingStatus.NOT_PROVIDED and (
            self.conformance_binding != binding
        ):
            raise ValueError("conformance binding state does not match certificate inputs")
        if self.conformance_status is not None and self.conformance_status != conformance_status:
            raise ValueError("conformance status does not match bound certificate")
        if self.known_unsupported_semantics and self.known_unsupported_semantics != unsupported:
            raise ValueError("known unsupported semantics do not match compatibility policy")
        if self.known_semantic_losses and self.known_semantic_losses != losses:
            raise ValueError("known semantic losses do not match compatibility policy")
        if self.evidence_gaps and self.evidence_gaps != evidence_gaps:
            raise ValueError("evidence gaps do not match compatibility policy")

        object.__setattr__(self, "policy", policy)
        object.__setattr__(self, "observed", observed)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "conformance_certificate", certificate)
        object.__setattr__(self, "conformance_binding", binding)
        object.__setattr__(self, "conformance_status", conformance_status)
        object.__setattr__(self, "known_unsupported_semantics", unsupported)
        object.__setattr__(self, "known_semantic_losses", losses)
        object.__setattr__(self, "evidence_gaps", evidence_gaps)

        payload = self.model_dump(
            mode="json",
            exclude={"report_id", "report_content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"COMPATREPORT-{digest[:24].upper()}"
        if self.report_content_sha256 and self.report_content_sha256 != digest:
            raise ValueError("compatibility report digest does not match immutable contents")
        if self.report_id and self.report_id != identifier:
            raise ValueError("compatibility report ID does not match immutable contents")
        object.__setattr__(self, "report_content_sha256", digest)
        object.__setattr__(self, "report_id", identifier)
        return self

    @property
    def interface_matches_tested_support(self) -> bool:
        return self.status == RuntimeCompatibilityStatus.TESTED_INTERFACE_MATCH


class RuntimeCompatibilityMatrix(BaseModel):
    """Deterministic set of compatibility policies, one per adapter/runtime pair."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = COMPATIBILITY_SCHEMA_VERSION
    matrix_id: str = ""
    matrix_content_sha256: str = ""
    policies: tuple[RuntimeCompatibilityPolicy, ...] = ()

    @model_validator(mode="after")
    def validate_matrix(self) -> "RuntimeCompatibilityMatrix":
        if self.schema_version != COMPATIBILITY_SCHEMA_VERSION:
            raise ValueError("unsupported runtime compatibility matrix schema version")
        policies = tuple(_validated_policy(policy) for policy in self.policies)
        policies = tuple(
            sorted(
                policies,
                key=lambda policy: (policy.adapter.adapter_name, policy.runtime_name),
            )
        )
        keys = [(policy.adapter.adapter_name, policy.runtime_name) for policy in policies]
        if len(keys) != len(set(keys)):
            raise ValueError("compatibility matrix permits one policy per adapter/runtime pair")
        object.__setattr__(self, "policies", policies)

        payload = self.model_dump(
            mode="json",
            exclude={"matrix_id", "matrix_content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"COMPATMATRIX-{digest[:24].upper()}"
        if self.matrix_content_sha256 and self.matrix_content_sha256 != digest:
            raise ValueError("compatibility matrix digest does not match immutable contents")
        if self.matrix_id and self.matrix_id != identifier:
            raise ValueError("compatibility matrix ID does not match immutable contents")
        object.__setattr__(self, "matrix_content_sha256", digest)
        object.__setattr__(self, "matrix_id", identifier)
        return self

    def policy_for(
        self,
        *,
        adapter_name: str,
        runtime_name: str,
    ) -> RuntimeCompatibilityPolicy | None:
        return next(
            (
                policy
                for policy in self.policies
                if policy.adapter.adapter_name == adapter_name
                and policy.runtime_name == runtime_name
            ),
            None,
        )


class RuntimeCompatibilityError(RuntimeError):
    pass


def evaluate_runtime_compatibility(
    policy: RuntimeCompatibilityPolicy | None,
    observed: ObservedRuntimeInterface,
    *,
    conformance_certificate: ConformanceCertificate | None = None,
) -> RuntimeCompatibilityReport:
    return RuntimeCompatibilityReport(
        policy=policy,
        observed=observed,
        conformance_certificate=conformance_certificate,
    )


def evaluate_compatibility_matrix(
    matrix: RuntimeCompatibilityMatrix,
    observed: ObservedRuntimeInterface,
    *,
    conformance_certificate: ConformanceCertificate | None = None,
) -> RuntimeCompatibilityReport:
    validated_matrix = RuntimeCompatibilityMatrix.model_validate(
        matrix.model_dump(mode="python")
    )
    validated_observed = _validated_observation(observed)
    policy = validated_matrix.policy_for(
        adapter_name=validated_observed.adapter.adapter_name,
        runtime_name=validated_observed.runtime_name,
    )
    return evaluate_runtime_compatibility(
        policy,
        validated_observed,
        conformance_certificate=conformance_certificate,
    )


def require_tested_interface_match(report: RuntimeCompatibilityReport) -> None:
    validated = RuntimeCompatibilityReport.model_validate(report.model_dump(mode="python"))
    if not validated.interface_matches_tested_support:
        reason = "; ".join(validated.reasons) or validated.status.value
        raise RuntimeCompatibilityError(
            f"runtime compatibility gate failed with {validated.status.value}: {reason}"
        )


def serialize_compatibility_matrix(matrix: RuntimeCompatibilityMatrix) -> bytes:
    validated = RuntimeCompatibilityMatrix.model_validate(matrix.model_dump(mode="python"))
    return _canonical_bytes(validated.model_dump(mode="json"))


def serialize_compatibility_report(report: RuntimeCompatibilityReport) -> bytes:
    validated = RuntimeCompatibilityReport.model_validate(report.model_dump(mode="python"))
    return _canonical_bytes(validated.model_dump(mode="json"))
