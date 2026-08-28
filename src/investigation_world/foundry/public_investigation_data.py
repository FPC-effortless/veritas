from __future__ import annotations

import json
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from investigation_world.foundry.models import stable_hash


class DatasetSplit(StrEnum):
    TRAIN_REFERENCE = "train_reference"
    CALIBRATION = "calibration"
    HOLDOUT_CANDIDATE = "holdout_candidate"


class InvestigationStatus(StrEnum):
    COMPLETED = "completed"
    ACTIVE = "active"
    UNKNOWN = "unknown"


class ArtifactRole(StrEnum):
    INITIAL_REPORT = "initial_report"
    FACTUAL_REPORT = "factual_report"
    INTERVIEW = "interview"
    TRANSCRIPT = "transcript"
    TELEMETRY = "telemetry"
    PHOTO = "photo"
    VIDEO = "video"
    AUDIO = "audio"
    PROCEDURE = "procedure"
    REGULATION = "regulation"
    PARTY_SUBMISSION = "party_submission"
    OTHER_EVIDENCE = "other_evidence"
    VERIFIER_REFERENCE = "verifier_reference"


class AccessMethod(StrEnum):
    API = "api"
    BULK_DOWNLOAD = "bulk_download"
    SEARCH_EXPORT = "search_export"
    CASE_INDEX = "case_index"
    DOCKET = "docket"


class SourceArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    title: str
    url: HttpUrl
    role: ArtifactRole
    media_type: str = "text/html"
    source_published_date: date | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    metadata: dict[str, Any] = Field(default_factory=dict)


class PublicSourceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    organization: str
    jurisdiction: str
    domains: list[str]
    access_methods: list[AccessMethod]
    index_url: HttpUrl
    bulk_url: HttpUrl | None = None
    case_url_template: str | None = None
    docket_url_template: str | None = None
    media_index_url: HttpUrl | None = None
    evidence_types: list[str] = Field(default_factory=list)
    truth_products: list[str] = Field(default_factory=list)
    acquisition_notes: list[str] = Field(default_factory=list)


class PublicSourceRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_id: str
    version: str
    as_of: date
    sources: list[PublicSourceDefinition]

    @model_validator(mode="after")
    def validate_unique_sources(self):
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source_id values must be unique")
        return self


class PublicInvestigationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    source_id: str
    title: str
    jurisdiction: str
    domain: str
    event_date: date
    location: str | None = None
    status: InvestigationStatus = InvestigationStatus.UNKNOWN
    split: DatasetSplit = DatasetSplit.TRAIN_REFERENCE
    objective: str
    public_evidence: list[SourceArtifact] = Field(default_factory=list)
    verifier_references: list[SourceArtifact] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_projection_boundary(self):
        public_ids = [artifact.artifact_id for artifact in self.public_evidence]
        private_ids = [artifact.artifact_id for artifact in self.verifier_references]
        if len(public_ids) != len(set(public_ids)):
            raise ValueError(f"duplicate public artifact ids in {self.case_id}")
        if len(private_ids) != len(set(private_ids)):
            raise ValueError(f"duplicate verifier artifact ids in {self.case_id}")
        overlap = set(public_ids) & set(private_ids)
        if overlap:
            raise ValueError(
                f"public/verifier artifact overlap in {self.case_id}: {sorted(overlap)}"
            )
        if any(item.role == ArtifactRole.VERIFIER_REFERENCE for item in self.public_evidence):
            raise ValueError("verifier references may not appear in public_evidence")
        if any(item.role != ArtifactRole.VERIFIER_REFERENCE for item in self.verifier_references):
            raise ValueError("verifier_references must use role=verifier_reference")
        return self

    def public_projection(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source_id": self.source_id,
            "title": self.title,
            "jurisdiction": self.jurisdiction,
            "domain": self.domain,
            "event_date": self.event_date.isoformat(),
            "location": self.location,
            "status": self.status.value,
            "split": self.split.value,
            "objective": self.objective,
            "public_evidence": [
                _public_artifact_projection(artifact) for artifact in self.public_evidence
            ],
            "metadata": _sanitize_public_metadata(self.metadata),
        }

    def verifier_projection(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source_id": self.source_id,
            "split": self.split.value,
            "verifier_references": [
                artifact.model_dump(mode="json") for artifact in self.verifier_references
            ],
        }


class PublicInvestigationDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    version: str
    as_of: date
    source_registry_id: str
    cases: list[PublicInvestigationCase]
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_cases(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id values must be unique")
        return self

    def public_projection(self) -> dict[str, Any]:
        cases = [case.public_projection() for case in self.cases]
        payload = {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "as_of": self.as_of.isoformat(),
            "source_registry_id": self.source_registry_id,
            "cases": cases,
        }
        payload["content_hash"] = stable_hash(payload)
        return payload

    def verifier_projection(self) -> dict[str, Any]:
        cases = [case.verifier_projection() for case in self.cases]
        payload = {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "as_of": self.as_of.isoformat(),
            "source_registry_id": self.source_registry_id,
            "cases": cases,
            "notes": self.notes,
        }
        payload["content_hash"] = stable_hash(payload)
        return payload


_PUBLIC_METADATA_DENYLIST = {
    "answer",
    "causal_findings",
    "contributing_factors",
    "final_findings",
    "official_findings",
    "probable_cause",
    "recommendations",
    "root_cause",
    "verifier",
    "verifier_truth",
}


def _sanitize_public_metadata(value: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, item in value.items():
        if key.casefold() in _PUBLIC_METADATA_DENYLIST:
            continue
        if isinstance(item, dict):
            output[key] = _sanitize_public_metadata(item)
        elif isinstance(item, list):
            output[key] = [
                _sanitize_public_metadata(child) if isinstance(child, dict) else child
                for child in item
            ]
        else:
            output[key] = item
    return output


def _public_artifact_projection(artifact: SourceArtifact) -> dict[str, Any]:
    payload = artifact.model_dump(mode="json")
    payload["metadata"] = _sanitize_public_metadata(artifact.metadata)
    return payload


def load_source_registry(path: Path) -> PublicSourceRegistry:
    return PublicSourceRegistry.model_validate_json(path.read_text(encoding="utf-8"))


def load_public_investigation_dataset(path: Path) -> PublicInvestigationDataset:
    return PublicInvestigationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def write_dataset_projections(
    dataset: PublicInvestigationDataset,
    *,
    public_output: Path,
    verifier_output: Path | None = None,
) -> dict[str, Any]:
    public_payload = dataset.public_projection()
    public_output.parent.mkdir(parents=True, exist_ok=True)
    public_output.write_text(
        json.dumps(public_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result: dict[str, Any] = {
        "dataset_id": dataset.dataset_id,
        "cases": len(dataset.cases),
        "public_output": str(public_output),
        "public_hash": public_payload["content_hash"],
        "verifier_output": None,
        "verifier_hash": None,
    }
    if verifier_output is not None:
        verifier_payload = dataset.verifier_projection()
        verifier_output.parent.mkdir(parents=True, exist_ok=True)
        verifier_output.write_text(
            json.dumps(verifier_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result["verifier_output"] = str(verifier_output)
        result["verifier_hash"] = verifier_payload["content_hash"]
    return result
