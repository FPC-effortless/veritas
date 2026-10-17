from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification.maturity import GateOutcome
from investigation_world.qualification.verifier_suite import (
    VerifierQualificationReport,
)


class Applicability(StrEnum):
    REQUIRED = "REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Gold10TaskBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    split: str = Field(min_length=1)
    task_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_target_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Gold10ApplicabilityRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    gate: str = Field(min_length=1)
    applicability: Applicability
    rationale: str = Field(min_length=1)


class Gold10TaskVerifierQualification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = ""
    binding: Gold10TaskBinding
    report: VerifierQualificationReport
    applicability: tuple[Gold10ApplicabilityRecord, ...] = ()

    @model_validator(mode="after")
    def validate_record(self) -> "Gold10TaskVerifierQualification":
        gates = {gate.name: gate for gate in self.report.gates}
        applicability_by_gate = {item.gate: item for item in self.applicability}
        if len(applicability_by_gate) != len(self.applicability):
            raise ValueError("duplicate applicability gate")
        unknown_required = [
            gate.name
            for gate in self.report.gates
            if gate.outcome == GateOutcome.UNKNOWN
            and applicability_by_gate.get(
                gate.name,
                Gold10ApplicabilityRecord(
                    gate=gate.name,
                    applicability=Applicability.REQUIRED,
                    rationale="required by default",
                ),
            ).applicability
            == Applicability.REQUIRED
        ]
        if self.report.status == GateOutcome.PASS and unknown_required:
            raise ValueError("PASS report cannot retain required UNKNOWN gates")
        for item in self.applicability:
            if item.gate not in gates:
                raise ValueError(f"applicability references unknown gate: {item.gate}")
            if item.applicability == Applicability.NOT_APPLICABLE:
                gate = gates[item.gate]
                if gate.outcome == GateOutcome.FAIL:
                    raise ValueError("NOT_APPLICABLE cannot erase a FAIL gate")

        payload = {
            "binding": self.binding.model_dump(mode="json"),
            "report_id": self.report.report_id,
            "applicability": [
                item.model_dump(mode="json")
                for item in sorted(self.applicability, key=lambda value: value.gate)
            ],
        }
        expected = f"G10VQTASK-{stable_hash(payload)[:24].upper()}"
        if self.record_id and self.record_id != expected:
            raise ValueError("Gold-10 task qualification record ID does not match contents")
        object.__setattr__(self, "record_id", expected)
        return self

    @property
    def effective_status(self) -> GateOutcome:
        if self.report.status == GateOutcome.FAIL:
            return GateOutcome.FAIL
        applicability_by_gate = {item.gate: item for item in self.applicability}
        for gate in self.report.gates:
            if gate.outcome != GateOutcome.UNKNOWN:
                continue
            item = applicability_by_gate.get(gate.name)
            if item is None or item.applicability == Applicability.REQUIRED:
                return GateOutcome.UNKNOWN
        return GateOutcome.PASS


class Gold10VerifierQualification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    qualification_id: str = ""
    pilot_id: str = Field(min_length=1)
    taskset_version: str = Field(min_length=1)
    verifier_target_contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    task_records: tuple[Gold10TaskVerifierQualification, ...]
    status: GateOutcome

    @model_validator(mode="after")
    def validate_qualification(self) -> "Gold10VerifierQualification":
        if len(self.task_records) != 10:
            raise ValueError("Gold-10 qualification requires exactly ten task records")
        case_ids = [item.binding.case_id for item in self.task_records]
        task_ids = [item.binding.task_id for item in self.task_records]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Gold-10 qualification contains duplicate case IDs")
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Gold-10 qualification contains duplicate task IDs")
        if any(
            item.binding.verifier_target_contract_sha256
            != self.verifier_target_contract_sha256
            for item in self.task_records
        ):
            raise ValueError("task qualification uses a different verifier target contract")

        statuses = tuple(item.effective_status for item in self.task_records)
        expected_status = (
            GateOutcome.FAIL
            if GateOutcome.FAIL in statuses
            else GateOutcome.UNKNOWN
            if GateOutcome.UNKNOWN in statuses
            else GateOutcome.PASS
        )
        if self.status != expected_status:
            raise ValueError("candidate status does not match per-task qualification states")

        payload = {
            "pilot_id": self.pilot_id,
            "taskset_version": self.taskset_version,
            "verifier_target_contract_sha256": self.verifier_target_contract_sha256,
            "task_records": [
                item.record_id
                for item in sorted(self.task_records, key=lambda value: value.binding.case_id)
            ],
            "status": self.status.value,
        }
        expected = f"G10VQ-{stable_hash(payload)[:24].upper()}"
        if self.qualification_id and self.qualification_id != expected:
            raise ValueError("Gold-10 qualification ID does not match contents")
        object.__setattr__(self, "qualification_id", expected)
        return self
