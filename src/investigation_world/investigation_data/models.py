from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AcquisitionPolicy(str, Enum):
    APPROVED = "approved"
    REVIEW_REQUIRED = "review_required"
    METADATA_ONLY = "metadata_only"
    BLOCKED = "blocked"


class RedistributionPolicy(str, Enum):
    ALLOWED = "allowed"
    ATTRIBUTION_REQUIRED = "attribution_required"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class AIUsePolicy(str, Enum):
    ALLOWED = "allowed"
    ALLOWED_WITH_CONDITIONS = "allowed_with_conditions"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class TruthStrength(str, Enum):
    CONTROLLED = "controlled"
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class ArtifactMethod(str, Enum):
    HTTP_FILE = "http_file"
    API = "api"
    FORM = "form"
    MANUAL = "manual"


class ArtifactClass(str, Enum):
    DATA = "data"
    DOCUMENT = "document"
    METADATA = "metadata"
    BINARY_FORENSIC = "binary_forensic"


class RightsPolicy(StrictModel):
    acquisition: AcquisitionPolicy
    redistribution: RedistributionPolicy
    ai_use: AIUsePolicy
    license_expression: str
    terms_url: str
    attribution_required: bool = False
    review_notes: str = ""

    @model_validator(mode="after")
    def validate_terms(self) -> "RightsPolicy":
        parsed = urlparse(self.terms_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("terms_url must be an absolute HTTPS URL")
        if self.acquisition is AcquisitionPolicy.BLOCKED and not self.review_notes.strip():
            raise ValueError("blocked sources require review_notes")
        return self


class TruthSemantics(StrictModel):
    strength: TruthStrength
    basis: str
    official_findings_are_ground_truth: bool = False
    verifier_use: Literal["private_truth", "evidence_reference", "context_only"]
    limitations: tuple[str, ...] = ()


class AcquisitionArtifact(StrictModel):
    artifact_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    label: str
    method: ArtifactMethod
    url: str
    artifact_class: ArtifactClass
    filename: str | None = None
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    notes: str = ""

    @model_validator(mode="after")
    def validate_url_and_filename(self) -> "AcquisitionArtifact":
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("artifact url must be an absolute HTTPS URL")
        if self.filename:
            candidate = PurePosixPath(self.filename)
            if candidate.name != self.filename or self.filename in {".", ".."}:
                raise ValueError("filename must be a single safe path component")
        return self


class SeedSelection(StrictModel):
    selection_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    label: str
    target_episodes: int = Field(ge=1)
    selection_method: str
    selectors: tuple[str, ...] = ()
    strata: tuple[str, ...] = ()
    notes: str = ""


class SourceSpec(StrictModel):
    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    name: str
    publisher: str
    domains: tuple[str, ...]
    homepage: str
    allowed_hosts: tuple[str, ...]
    rights: RightsPolicy
    truth: TruthSemantics
    artifacts: tuple[AcquisitionArtifact, ...] = ()
    seed_selections: tuple[SeedSelection, ...] = ()
    requires_identified_user_agent: bool = False
    contains_personal_data: bool = False
    requires_redaction_review: bool = False

    @model_validator(mode="after")
    def validate_source(self) -> "SourceSpec":
        parsed = urlparse(self.homepage)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("homepage must be an absolute HTTPS URL")
        hosts = {host.lower() for host in self.allowed_hosts}
        if not hosts:
            raise ValueError("allowed_hosts cannot be empty")
        artifact_ids: set[str] = set()
        for artifact in self.artifacts:
            if artifact.artifact_id in artifact_ids:
                raise ValueError(f"duplicate artifact_id: {artifact.artifact_id}")
            artifact_ids.add(artifact.artifact_id)
            host = (urlparse(artifact.url).hostname or "").lower()
            if not _host_allowed(host, hosts):
                raise ValueError(f"artifact host {host!r} is not allowed for {self.source_id}")
        selection_ids = [item.selection_id for item in self.seed_selections]
        if len(selection_ids) != len(set(selection_ids)):
            raise ValueError(f"duplicate seed selection id in {self.source_id}")
        if self.rights.acquisition is AcquisitionPolicy.BLOCKED and self.artifacts:
            raise ValueError("blocked sources cannot declare acquisition artifacts")
        return self


class SourceCatalog(StrictModel):
    schema_version: Literal["1.0"]
    reviewed_at: date
    sources: tuple[SourceSpec, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> "SourceCatalog":
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("source_id values must be unique")
        return self


class Sensitivity(str, Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"
    SEALED = "sealed"


class EvidenceProvenance(StrictModel):
    source_id: str
    source_artifact_id: str
    locator: str
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    acquired_at: datetime | None = None


class EvidenceItem(StrictModel):
    evidence_id: str
    kind: str
    provenance: tuple[EvidenceProvenance, ...]
    observed_at: datetime | None = None
    available_from: datetime | None = None
    reliability: Literal["high", "medium", "low", "unknown"] = "unknown"
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    content_ref: str


class Actor(StrictModel):
    actor_id: str
    role: str
    public_attributes: dict[str, Any] = Field(default_factory=dict)


class PublicInvestigationEpisode(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    episode_id: str
    domain: str
    source_case_ids: tuple[str, ...]
    initial_public_state: dict[str, Any]
    actors: tuple[Actor, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    available_actions: tuple[str, ...]
    constraints: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_sealed_public_evidence(self) -> "PublicInvestigationEpisode":
        sealed = [
            item.evidence_id
            for item in self.evidence
            if item.sensitivity is Sensitivity.SEALED
        ]
        if sealed:
            raise ValueError(f"public episode contains sealed evidence: {sealed}")
        return self


class TruthClaim(StrictModel):
    claim_id: str
    proposition: str
    truth_status: Literal["true", "false", "unknown"]
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()


class OfficialFinding(StrictModel):
    finding_id: str
    authority: str
    finding: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_evidence_ids: tuple[str, ...] = ()


class PrivateInvestigationOracle(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    episode_id: str
    ground_truth_claims: tuple[TruthClaim, ...]
    official_findings: tuple[OfficialFinding, ...] = ()
    actual_timeline: tuple[dict[str, Any], ...] = ()
    causal_edges: tuple[tuple[str, str], ...] = ()
    verifier_targets: dict[str, Any] = Field(default_factory=dict)


class InvestigationEpisodeBundle(StrictModel):
    public: PublicInvestigationEpisode
    oracle: PrivateInvestigationOracle

    @model_validator(mode="after")
    def match_episode_ids(self) -> "InvestigationEpisodeBundle":
        if self.public.episode_id != self.oracle.episode_id:
            raise ValueError("public/oracle episode IDs must match")
        return self


class ArtifactReceipt(StrictModel):
    receipt_version: Literal["1.0"] = "1.0"
    source_id: str
    artifact_id: str
    source_url: str
    resolved_url: str
    retrieved_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=0)
    content_type: str | None = None
    local_path: str
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rights_review_id: str | None = None

    @classmethod
    def now(cls, **kwargs: Any) -> "ArtifactReceipt":
        return cls(retrieved_at=datetime.now(timezone.utc), **kwargs)


def _host_allowed(host: str, allowed_hosts: set[str]) -> bool:
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts)
