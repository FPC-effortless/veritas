from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from investigation_world.foundry.models import stable_hash


class CalibrationSourceKind(StrEnum):
    PUBLIC_DATASET = "public_dataset"
    REGULATORY_FILINGS = "regulatory_filings"
    OPERATIONAL_DOCUMENTS = "operational_documents"
    RESEARCH_CORPUS = "research_corpus"
    EXPERT_KNOWLEDGE = "expert_knowledge"
    TELEMETRY = "telemetry"
    SYNTHETIC_PRIOR = "synthetic_prior"


class CalibrationSource(BaseModel):
    source_id: str
    kind: CalibrationSourceKind
    name: str
    version: str = "unspecified"
    schema_ref: str | None = None
    population: str | None = None
    fields: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    quality_notes: list[str] = Field(default_factory=list)


class DistributionTarget(BaseModel):
    target_id: str
    object_type: str
    attribute: str
    statistic: str
    expected_value: float | int | str | list[Any] | dict[str, Any]
    tolerance: float | None = None
    conditioning: dict[str, Any] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)


class DependencyTarget(BaseModel):
    target_id: str
    cause: str
    effect: str
    relationship: str
    strength: float | None = None
    lag: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class ProcedurePrior(BaseModel):
    procedure_id: str
    name: str
    preconditions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    common_failures: list[str] = Field(default_factory=list)
    recovery_patterns: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class WorldCalibrationSpec(BaseModel):
    calibration_id: str
    version: str = "1"
    domain: str
    sources: list[CalibrationSource] = Field(default_factory=list)
    distribution_targets: list[DistributionTarget] = Field(default_factory=list)
    dependency_targets: list[DependencyTarget] = Field(default_factory=list)
    procedure_priors: list[ProcedurePrior] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CalibrationReport(BaseModel):
    calibration_id: str
    world_manifest_id: str
    target_scores: dict[str, float] = Field(default_factory=dict)
    failed_targets: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.failed_targets


def calibration_fingerprint(spec: WorldCalibrationSpec) -> str:
    return stable_hash(spec.model_dump(mode="json"))


def validate_calibration_report(report: CalibrationReport, *, minimum_score: float = 0.8) -> CalibrationReport:
    failed = sorted(
        target_id for target_id, score in report.target_scores.items() if score < minimum_score
    )
    return report.model_copy(update={"failed_targets": sorted(set(report.failed_targets) | set(failed))})


def world_manifest_id(spec: WorldCalibrationSpec, generator_parameters: dict[str, Any]) -> str:
    payload = {
        "calibration": calibration_fingerprint(spec),
        "generator_parameters": generator_parameters,
    }
    return f"world-{stable_hash(payload)[:20]}"
