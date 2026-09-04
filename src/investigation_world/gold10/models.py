from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.tasks.spec import TaskSpec


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EpistemicClaimKind(StrEnum):
    FACT = "fact"
    ALLEGATION = "allegation"
    INSTITUTIONAL_FINDING = "institutional_finding"
    HYPOTHESIS = "hypothesis"
    UNCERTAINTY = "uncertainty"


class EvidenceRecord(CanonicalModel):
    evidence_id: str
    source_id: str
    source_artifact_id: str
    modality: str
    epistemic_role: str
    reliability: str
    locator: str
    content_ref: str
    available_from: str | None = None


class InstitutionalFinding(CanonicalModel):
    finding_id: str
    authority: str
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_evidence_ids: tuple[str, ...]


class PilotContract(CanonicalModel):
    schema_version: str
    pilot_id: str
    taskset_version: str
    world_id: str
    world_version: str
    verifier_id: str
    verifier_version: str
    evidence_coverage_target: int = Field(ge=1)
    calibration_min_uncertainty_mass: float = Field(ge=0.0, le=1.0)


class Gold10Task(CanonicalModel):
    case_id: str
    slug: str
    split: str
    task: TaskSpec
    calibration_required: bool
    public_temporal_cut: dict[str, str]
    available_actions: tuple[str, ...]
    available_evidence: tuple[EvidenceRecord, ...]
    available_findings: tuple[InstitutionalFinding, ...]
    capability_targets: tuple[str, ...]
    manifest_sha256: str

    @model_validator(mode="after")
    def validate_task(self) -> "Gold10Task":
        if self.task.task_id != f"GOLD10-{self.case_id}":
            raise ValueError("Gold-10 task identity does not match case identity")
        evidence_ids = [item.evidence_id for item in self.available_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Gold-10 available evidence ids must be unique")
        available = set(evidence_ids)
        for finding in self.available_findings:
            if not set(finding.source_evidence_ids).issubset(available):
                raise ValueError("institutional finding cites evidence unavailable at the cut")
        return self


class EpistemicClaim(CanonicalModel):
    claim_id: str
    statement: str
    kind: EpistemicClaimKind
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def require_evidence(self) -> "EpistemicClaim":
        if not self.evidence_ids:
            raise ValueError("epistemic claims require at least one evidence reference")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("epistemic claim evidence ids must be unique")
        return self


class Gold10Submission(CanonicalModel):
    primary_hypothesis: str = Field(min_length=1)
    alternative_hypothesis: str = Field(min_length=1)
    primary_confidence: float = Field(ge=0.0, le=1.0)
    alternative_confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: tuple[str, ...]
    claims: tuple[EpistemicClaim, ...] = ()
    unresolved_questions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_submission(self) -> "Gold10Submission":
        if self.primary_hypothesis.strip() == self.alternative_hypothesis.strip():
            raise ValueError("primary and alternative hypotheses must be distinct")
        if self.primary_confidence + self.alternative_confidence > 1.0:
            raise ValueError("hypothesis confidence leaves no coherent probability mass")
        if not self.evidence_ids:
            raise ValueError("Gold-10 submissions require cited evidence")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("submission evidence ids must be unique")
        return self

    @property
    def uncertainty_mass(self) -> float:
        return 1.0 - self.primary_confidence - self.alternative_confidence


class Gold10Score(CanonicalModel):
    reward: float = Field(ge=0.0, le=1.0)
    component_scores: dict[str, float]
    hard_failures: tuple[str, ...] = ()
