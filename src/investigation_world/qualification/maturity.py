from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from re import fullmatch
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash


class EnvironmentMaturity(StrEnum):
    DRAFT = "DRAFT"
    EXECUTABLE = "EXECUTABLE"
    VERIFIER_VALIDATED = "VERIFIER_VALIDATED"
    SCIENTIFICALLY_QUALIFIED = "SCIENTIFICALLY_QUALIFIED"
    FRONTIER_QUALIFIED = "FRONTIER_QUALIFIED"
    TRAINING_VALIDATED = "TRAINING_VALIDATED"
    COMMERCIAL_RELEASE = "COMMERCIAL_RELEASE"


MATURITY_ORDER = tuple(EnvironmentMaturity)


class GateOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


class EnvironmentIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    environment_id: str = Field(min_length=1)
    environment_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_content_digest(self) -> "EnvironmentIdentity":
        _validate_sha256(self.content_sha256, field_name="environment content_sha256")
        return self


class VerifierIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    verifier_id: str = Field(min_length=1)
    verifier_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_content_digest(self) -> "VerifierIdentity":
        _validate_sha256(self.content_sha256, field_name="verifier content_sha256")
        return self


class MaturityGateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    gate: str = Field(min_length=1)
    outcome: GateOutcome
    evidence_id: str | None = None
    content_sha256: str | None = None
    environment_content_sha256: str
    verifier_content_sha256: str
    qualification_policy_version: str = Field(min_length=1)
    observed_at: datetime
    provenance: dict[str, Any] = Field(min_length=1)
    detail: str = ""

    @model_validator(mode="after")
    def validate_evidence_identity(self) -> "MaturityGateEvidence":
        _validate_sha256(
            self.environment_content_sha256,
            field_name="evidence environment_content_sha256",
        )
        _validate_sha256(
            self.verifier_content_sha256,
            field_name="evidence verifier_content_sha256",
        )
        if (self.evidence_id is None) != (self.content_sha256 is None):
            raise ValueError("evidence_id and content_sha256 must be supplied together")
        if self.content_sha256 is not None:
            _validate_sha256(self.content_sha256, field_name="evidence content_sha256")
        if self.outcome != GateOutcome.UNKNOWN and self.evidence_id is None:
            raise ValueError("PASS and FAIL outcomes require content-addressed evidence")
        return self


class MaturityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_id: str = ""
    policy_version: str = Field(min_length=1)
    requirements: dict[EnvironmentMaturity, tuple[str, ...]]

    @model_validator(mode="after")
    def validate_policy(self) -> "MaturityPolicy":
        if set(self.requirements) != set(MATURITY_ORDER):
            raise ValueError("maturity policy must define every canonical maturity state")
        if self.requirements[EnvironmentMaturity.DRAFT]:
            raise ValueError("DRAFT cannot require qualification evidence")

        seen: set[str] = set()
        for status in MATURITY_ORDER[1:]:
            gates = self.requirements[status]
            if not gates:
                raise ValueError(f"{status.value} must define at least one evidence gate")
            if len(gates) != len(set(gates)):
                raise ValueError(f"{status.value} contains duplicate evidence gates")
            overlap = seen.intersection(gates)
            if overlap:
                raise ValueError(
                    "evidence gates must belong to exactly one maturity transition: "
                    + ", ".join(sorted(overlap))
                )
            seen.update(gates)

        payload = {
            "policy_version": self.policy_version,
            "requirements": [
                [status.value, list(self.requirements[status])] for status in MATURITY_ORDER
            ],
        }
        expected = f"MPOL-{stable_hash(payload)[:24].upper()}"
        if self.policy_id and self.policy_id != expected:
            raise ValueError("maturity policy ID does not match immutable contents")
        object.__setattr__(self, "policy_id", expected)
        return self

    def required_through(self, target: EnvironmentMaturity) -> tuple[str, ...]:
        target_index = MATURITY_ORDER.index(target)
        return tuple(
            gate
            for status in MATURITY_ORDER[: target_index + 1]
            for gate in self.requirements[status]
        )


DEFAULT_MATURITY_POLICY = MaturityPolicy(
    policy_version="veritas-environment-maturity-v1",
    requirements={
        EnvironmentMaturity.DRAFT: (),
        EnvironmentMaturity.EXECUTABLE: (
            "environment_contract_valid",
            "runtime_smoke",
            "deterministic_reset",
        ),
        EnvironmentMaturity.VERIFIER_VALIDATED: (
            "verifier_qualification",
            "falsifier_fixtures",
            "reward_hack_resistance",
        ),
        EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED: (
            "scientific_qualification",
            "leakage_and_contamination",
            "reproducible_qualification_panel",
        ),
        EnvironmentMaturity.FRONTIER_QUALIFIED: (
            "frontier_non_saturation",
            "capability_separation",
            "frontier_failure_diversity",
        ),
        EnvironmentMaturity.TRAINING_VALIDATED: (
            "held_out_training_improvement",
            "multi_seed_stability",
            "reward_exploitation_regression",
        ),
        EnvironmentMaturity.COMMERCIAL_RELEASE: (
            "procurement_package",
            "security_and_privacy",
            "release_attestation",
            "license_and_release_authority",
        ),
    },
)


def _qualification_payload(
    *,
    environment_identity: EnvironmentIdentity,
    verifier_identity: VerifierIdentity,
    policy: MaturityPolicy,
    target_status: EnvironmentMaturity,
    required_evidence: tuple[str, ...],
    evaluated_evidence: tuple[MaturityGateEvidence, ...],
    completed_evidence: tuple[MaturityGateEvidence, ...],
    failed_gates: tuple[str, ...],
    unknown_gates: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "environment_identity": environment_identity.model_dump(mode="json"),
        "verifier_identity": verifier_identity.model_dump(mode="json"),
        "qualification_policy_id": policy.policy_id,
        "target_status": target_status.value,
        "required_evidence": list(required_evidence),
        "evaluated_evidence": [
            item.model_dump(mode="json", exclude={"observed_at", "provenance", "detail"})
            for item in evaluated_evidence
        ],
        "completed_evidence": [
            item.evidence_id for item in completed_evidence
        ],
        "failed_gates": list(failed_gates),
        "unknown_gates": list(unknown_gates),
    }


class MaturityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    record_id: str = ""
    status: EnvironmentMaturity
    previous_status: EnvironmentMaturity | None = None
    previous_record_id: str | None = None
    target_status: EnvironmentMaturity
    qualification_policy_version: str
    qualification_policy_id: str
    qualification_policy_requirements: dict[EnvironmentMaturity, tuple[str, ...]]
    required_evidence: tuple[str, ...]
    evaluated_evidence: tuple[MaturityGateEvidence, ...]
    completed_evidence: tuple[MaturityGateEvidence, ...]
    failed_gates: tuple[str, ...]
    unknown_gates: tuple[str, ...]
    qualification_identity: str = ""
    environment_identity: EnvironmentIdentity
    verifier_identity: VerifierIdentity
    evaluated_at: datetime
    provenance: dict[str, Any] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_record(self) -> "MaturityRecord":
        policy = MaturityPolicy(
            policy_id=self.qualification_policy_id,
            policy_version=self.qualification_policy_version,
            requirements=self.qualification_policy_requirements,
        )
        expected_required = policy.required_through(self.target_status)
        if self.required_evidence != expected_required:
            raise ValueError("required evidence does not match the target policy snapshot")

        if (self.previous_status is None) != (self.previous_record_id is None):
            raise ValueError("previous_status and previous_record_id must be supplied together")

        evaluated_gates = tuple(item.gate for item in self.evaluated_evidence)
        if len(evaluated_gates) != len(set(evaluated_gates)):
            raise ValueError("evaluated evidence contains duplicate gates")
        if not set(evaluated_gates).issubset(self.required_evidence):
            raise ValueError("evaluated evidence contains a gate outside the policy target")

        completed_gates = tuple(item.gate for item in self.completed_evidence)
        if len(completed_gates) != len(set(completed_gates)):
            raise ValueError("completed evidence contains duplicate gates")
        if any(item.outcome != GateOutcome.PASS for item in self.completed_evidence):
            raise ValueError("completed_evidence may contain only PASS outcomes")
        if len(self.failed_gates) != len(set(self.failed_gates)):
            raise ValueError("failed_gates contains duplicates")
        if len(self.unknown_gates) != len(set(self.unknown_gates)):
            raise ValueError("unknown_gates contains duplicates")

        evaluated_by_gate = {item.gate: item for item in self.evaluated_evidence}
        expected_completed = tuple(
            gate
            for gate in self.required_evidence
            if gate in evaluated_by_gate
            and evaluated_by_gate[gate].outcome == GateOutcome.PASS
        )
        expected_failed = tuple(
            gate
            for gate in self.required_evidence
            if gate in evaluated_by_gate
            and evaluated_by_gate[gate].outcome == GateOutcome.FAIL
        )
        expected_unknown = tuple(
            gate
            for gate in self.required_evidence
            if gate not in evaluated_by_gate
            or evaluated_by_gate[gate].outcome == GateOutcome.UNKNOWN
        )
        if completed_gates != expected_completed:
            raise ValueError("completed_evidence does not match evaluated PASS outcomes")
        if self.failed_gates != expected_failed:
            raise ValueError("failed_gates does not match evaluated FAIL outcomes")
        if self.unknown_gates != expected_unknown:
            raise ValueError("unknown_gates does not match missing and UNKNOWN outcomes")

        classified = set(completed_gates) | set(self.failed_gates) | set(self.unknown_gates)
        if classified != set(self.required_evidence):
            raise ValueError("every required gate must be classified as PASS, FAIL, or UNKNOWN")
        if (
            set(completed_gates) & set(self.failed_gates)
            or set(completed_gates) & set(self.unknown_gates)
            or set(self.failed_gates) & set(self.unknown_gates)
        ):
            raise ValueError("gate outcome classifications must be disjoint")

        for evidence in self.evaluated_evidence:
            if evidence.environment_content_sha256 != self.environment_identity.content_sha256:
                raise ValueError("completed evidence belongs to a different environment version")
            if evidence.verifier_content_sha256 != self.verifier_identity.content_sha256:
                raise ValueError("completed evidence belongs to a different verifier version")
            if evidence.qualification_policy_version != self.qualification_policy_version:
                raise ValueError("completed evidence belongs to a different qualification policy")

        passed = set(completed_gates)
        achieved = EnvironmentMaturity.DRAFT
        target_index = MATURITY_ORDER.index(self.target_status)
        for candidate in MATURITY_ORDER[1 : target_index + 1]:
            if set(policy.requirements[candidate]).issubset(passed):
                achieved = candidate
            else:
                break
        if self.status != achieved:
            raise ValueError(
                f"claimed status {self.status.value} does not match evidence-derived status "
                f"{achieved.value}"
            )

        qualification_payload = _qualification_payload(
            environment_identity=self.environment_identity,
            verifier_identity=self.verifier_identity,
            policy=policy,
            target_status=self.target_status,
            required_evidence=self.required_evidence,
            evaluated_evidence=self.evaluated_evidence,
            completed_evidence=self.completed_evidence,
            failed_gates=self.failed_gates,
            unknown_gates=self.unknown_gates,
        )
        expected_qualification = f"MQUAL-{stable_hash(qualification_payload)[:24].upper()}"
        if self.qualification_identity and self.qualification_identity != expected_qualification:
            raise ValueError("qualification identity does not match immutable evidence")
        object.__setattr__(self, "qualification_identity", expected_qualification)

        record_payload = {
            "qualification_identity": expected_qualification,
            "status": self.status.value,
            "previous_status": self.previous_status.value if self.previous_status else None,
            "previous_record_id": self.previous_record_id,
            "evaluated_at": self.evaluated_at.isoformat(),
            "provenance": self.provenance,
        }
        expected_record = f"MREC-{stable_hash(record_payload)[:24].upper()}"
        if self.record_id and self.record_id != expected_record:
            raise ValueError("maturity record ID does not match immutable contents")
        object.__setattr__(self, "record_id", expected_record)
        return self


class MaturityHistory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    environment_id: str = Field(min_length=1)
    records: tuple[MaturityRecord, ...]

    @model_validator(mode="after")
    def validate_history(self) -> "MaturityHistory":
        if not self.records:
            raise ValueError("maturity history requires at least one record")
        for index, record in enumerate(self.records):
            if record.environment_identity.environment_id != self.environment_id:
                raise ValueError("maturity history cannot mix environment identities")
            if index == 0:
                if record.previous_record_id is not None:
                    raise ValueError("first maturity record cannot reference unavailable history")
                continue
            previous = self.records[index - 1]
            if record.previous_record_id != previous.record_id:
                raise ValueError("maturity history record lineage is not contiguous")
            if record.previous_status != previous.status:
                raise ValueError("maturity history previous_status does not match prior record")
        return self


def assess_environment_maturity(
    *,
    environment_identity: EnvironmentIdentity,
    verifier_identity: VerifierIdentity,
    evidence: tuple[MaturityGateEvidence, ...] | list[MaturityGateEvidence],
    provenance: dict[str, Any],
    target_status: EnvironmentMaturity = EnvironmentMaturity.COMMERCIAL_RELEASE,
    policy: MaturityPolicy = DEFAULT_MATURITY_POLICY,
    previous_record: MaturityRecord | None = None,
    evaluated_at: datetime | None = None,
) -> MaturityRecord:
    if not provenance:
        raise ValueError("maturity assessment requires provenance")
    if previous_record and (
        previous_record.environment_identity.environment_id
        != environment_identity.environment_id
    ):
        raise ValueError("previous maturity record belongs to a different environment")

    required = policy.required_through(target_status)
    by_gate: dict[str, MaturityGateEvidence] = {}
    for item in evidence:
        if item.gate in by_gate:
            raise ValueError(f"duplicate maturity evidence for gate: {item.gate}")
        if item.gate not in required:
            raise ValueError(f"evidence gate is outside the requested policy target: {item.gate}")
        if item.environment_content_sha256 != environment_identity.content_sha256:
            raise ValueError(f"evidence for {item.gate} belongs to a different environment version")
        if item.verifier_content_sha256 != verifier_identity.content_sha256:
            raise ValueError(f"evidence for {item.gate} belongs to a different verifier version")
        if item.qualification_policy_version != policy.policy_version:
            raise ValueError(f"evidence for {item.gate} belongs to a different policy version")
        by_gate[item.gate] = item

    completed = tuple(
        by_gate[gate]
        for gate in required
        if gate in by_gate and by_gate[gate].outcome == GateOutcome.PASS
    )
    failed = tuple(
        gate
        for gate in required
        if gate in by_gate and by_gate[gate].outcome == GateOutcome.FAIL
    )
    unknown = tuple(
        gate
        for gate in required
        if gate not in by_gate or by_gate[gate].outcome == GateOutcome.UNKNOWN
    )
    evaluated = tuple(by_gate[gate] for gate in required if gate in by_gate)

    passed = {item.gate for item in completed}
    status = EnvironmentMaturity.DRAFT
    target_index = MATURITY_ORDER.index(target_status)
    for candidate in MATURITY_ORDER[1 : target_index + 1]:
        if set(policy.requirements[candidate]).issubset(passed):
            status = candidate
        else:
            break

    return MaturityRecord(
        status=status,
        previous_status=previous_record.status if previous_record else None,
        previous_record_id=previous_record.record_id if previous_record else None,
        target_status=target_status,
        qualification_policy_version=policy.policy_version,
        qualification_policy_id=policy.policy_id,
        qualification_policy_requirements=policy.requirements,
        required_evidence=required,
        evaluated_evidence=evaluated,
        completed_evidence=completed,
        failed_gates=failed,
        unknown_gates=unknown,
        environment_identity=environment_identity,
        verifier_identity=verifier_identity,
        evaluated_at=evaluated_at or datetime.now(timezone.utc),
        provenance=provenance,
    )
