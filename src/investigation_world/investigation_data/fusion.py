from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from .models import (
    AIUsePolicy,
    AcquisitionPolicy,
    Actor,
    EvidenceItem,
    EvidenceProvenance,
    InvestigationEpisodeBundle,
    OfficialFinding,
    PrivateInvestigationOracle,
    PublicInvestigationEpisode,
    Sensitivity,
    SourceCatalog,
    SourceSpec,
    StrictModel,
    TruthClaim,
)


class FusionError(ValueError):
    """Raised when evidence cannot be fused without weakening policy or provenance."""


class EvidenceModality(str, Enum):
    STRUCTURED = "structured"
    DOCUMENT = "document"
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    SENSOR = "sensor"
    TRANSCRIPT = "transcript"
    FORENSIC = "forensic"
    DERIVED = "derived"


class EpistemicRole(str, Enum):
    PRIMARY_EVIDENCE = "primary_evidence"
    TESTIMONY = "testimony"
    OFFICIAL_FINDING = "official_finding"
    PRIVATE_TRUTH = "private_truth"
    CONTEXT = "context"
    DERIVED = "derived"
    SYNTHETIC = "synthetic"


class DerivationKind(str, Enum):
    ORIGINAL = "original"
    EXTRACTED = "extracted"
    TRANSFORMED = "transformed"
    SYNTHETIC = "synthetic"


def _require_aware(value: datetime | None, *, field_name: str) -> None:
    if value is not None and value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset")


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _host_allowed(host: str, allowed_hosts: tuple[str, ...]) -> bool:
    normalized = host.rstrip(".").lower()
    return any(
        normalized == allowed.rstrip(".").lower()
        or normalized.endswith(f".{allowed.rstrip('.').lower()}")
        for allowed in allowed_hosts
    )


class EvidenceFragment(StrictModel):
    """A provenance-bearing, temporally gated unit of multimodal evidence."""

    fragment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    source_id: str
    source_artifact_id: str
    case_ids: tuple[str, ...] = Field(min_length=1)
    modality: EvidenceModality
    epistemic_role: EpistemicRole
    derivation: DerivationKind = DerivationKind.ORIGINAL
    sensitivity: Sensitivity = Sensitivity.PUBLIC
    locator: str
    content_ref: str
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime | None = None
    available_from: datetime | None = None
    timeless: bool = False
    reliability: Literal["high", "medium", "low", "unknown"] = "unknown"
    segment_start_seconds: float | None = Field(default=None, ge=0.0)
    segment_end_seconds: float | None = Field(default=None, ge=0.0)
    parent_fragment_ids: tuple[str, ...] = ()
    supports_claim_ids: tuple[str, ...] = ()
    contradicts_claim_ids: tuple[str, ...] = ()
    transform_notes: str = ""
    rights_review_id: str | None = None

    @model_validator(mode="after")
    def validate_fragment(self) -> "EvidenceFragment":
        _require_aware(self.observed_at, field_name="observed_at")
        _require_aware(self.available_from, field_name="available_from")
        if self.timeless and self.available_from is not None:
            raise ValueError("timeless evidence must not set available_from")
        if self.timeless and self.epistemic_role is not EpistemicRole.CONTEXT:
            raise ValueError("only context evidence may bypass temporal gating")
        if (
            not self.timeless
            and self.available_from is None
            and self.sensitivity is not Sensitivity.SEALED
        ):
            raise ValueError("timed public/restricted evidence requires available_from")
        if (
            self.observed_at is not None
            and self.available_from is not None
            and self.available_from < self.observed_at
        ):
            raise ValueError("available_from cannot precede observed_at")
        if (self.segment_start_seconds is None) != (self.segment_end_seconds is None):
            raise ValueError("media segment start/end must be provided together")
        if (
            self.segment_start_seconds is not None
            and self.segment_end_seconds is not None
            and self.segment_end_seconds <= self.segment_start_seconds
        ):
            raise ValueError("media segment end must be greater than start")
        if self.derivation in {DerivationKind.EXTRACTED, DerivationKind.TRANSFORMED}:
            if not self.parent_fragment_ids:
                raise ValueError("extracted/transformed evidence requires parent_fragment_ids")
        if self.epistemic_role is EpistemicRole.PRIVATE_TRUTH:
            if self.sensitivity is not Sensitivity.SEALED:
                raise ValueError("private truth must be sealed")
        if (
            self.epistemic_role is EpistemicRole.DERIVED
            and self.derivation is DerivationKind.ORIGINAL
        ):
            raise ValueError("derived epistemic role cannot use original derivation")
        if (
            self.epistemic_role is EpistemicRole.SYNTHETIC
            and self.derivation is not DerivationKind.SYNTHETIC
        ):
            raise ValueError("synthetic epistemic role requires synthetic derivation")
        if self.rights_review_id is not None and not self.rights_review_id.strip():
            raise ValueError("rights_review_id must be non-empty when supplied")
        return self


class EvidenceRelation(StrictModel):
    relation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    source_fragment_id: str
    target_fragment_id: str
    relation: Literal[
        "supports",
        "contradicts",
        "corroborates",
        "derived_from",
        "same_event",
        "same_actor",
    ]


class FusionManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    episode_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    domain: str = Field(min_length=1)
    source_case_ids: tuple[str, ...] = Field(min_length=1)
    simulation_start: datetime
    simulation_as_of: datetime
    initial_public_state: dict[str, Any]
    actors: tuple[Actor, ...] = ()
    available_actions: tuple[str, ...] = Field(min_length=1)
    constraints: dict[str, Any] = Field(default_factory=dict)
    fragments: tuple[EvidenceFragment, ...]
    relations: tuple[EvidenceRelation, ...] = ()
    ground_truth_claims: tuple[TruthClaim, ...] = ()
    official_findings: tuple[OfficialFinding, ...] = ()
    actual_timeline: tuple[dict[str, Any], ...] = ()
    causal_edges: tuple[tuple[str, str], ...] = ()
    verifier_targets: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_manifest(self) -> "FusionManifest":
        _require_aware(self.simulation_start, field_name="simulation_start")
        _require_aware(self.simulation_as_of, field_name="simulation_as_of")
        if self.simulation_as_of < self.simulation_start:
            raise ValueError("simulation_as_of cannot precede simulation_start")

        fragment_ids = [item.fragment_id for item in self.fragments]
        if len(fragment_ids) != len(set(fragment_ids)):
            raise ValueError("fragment_id values must be unique")
        relation_ids = [item.relation_id for item in self.relations]
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("relation_id values must be unique")

        known_fragments = set(fragment_ids)
        source_cases = set(self.source_case_ids)
        for item in self.fragments:
            if not source_cases.intersection(item.case_ids):
                raise ValueError(
                    f"fragment {item.fragment_id!r} has no case link to this episode"
                )
            missing_parents = set(item.parent_fragment_ids) - known_fragments
            if missing_parents:
                raise ValueError(
                    f"fragment {item.fragment_id!r} has missing parents: "
                    f"{sorted(missing_parents)}"
                )

        by_id = {item.fragment_id: item for item in self.fragments}
        for item in self.fragments:
            for parent_id in item.parent_fragment_ids:
                parent = by_id[parent_id]
                if (
                    item.available_from is not None
                    and parent.available_from is not None
                    and item.available_from < parent.available_from
                ):
                    raise ValueError(
                        f"fragment {item.fragment_id!r} becomes available before parent "
                        f"{parent_id!r}"
                    )
        for relation in self.relations:
            if relation.source_fragment_id not in known_fragments:
                raise ValueError(f"unknown relation source: {relation.source_fragment_id}")
            if relation.target_fragment_id not in known_fragments:
                raise ValueError(f"unknown relation target: {relation.target_fragment_id}")

        self._validate_lineage()
        return self

    def _validate_lineage(self) -> None:
        by_id = {item.fragment_id: item for item in self.fragments}
        visiting: set[str] = set()
        visited: set[str] = set()

        def walk(fragment_id: str) -> bool:
            if fragment_id in visiting:
                raise ValueError(f"evidence lineage cycle at {fragment_id}")
            if fragment_id in visited:
                return by_id[fragment_id].sensitivity is Sensitivity.SEALED
            visiting.add(fragment_id)
            fragment = by_id[fragment_id]
            sealed_ancestor = fragment.sensitivity is Sensitivity.SEALED
            for parent_id in fragment.parent_fragment_ids:
                if walk(parent_id):
                    sealed_ancestor = True
            visiting.remove(fragment_id)
            visited.add(fragment_id)
            if fragment.sensitivity is not Sensitivity.SEALED and sealed_ancestor:
                raise ValueError(
                    f"public/restricted fragment {fragment_id!r} depends on sealed lineage"
                )
            return sealed_ancestor

        for fragment_id in by_id:
            walk(fragment_id)


class FusionReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    episode_id: str
    simulation_as_of: datetime
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_fragment_ids: tuple[str, ...]
    withheld_future_fragment_ids: tuple[str, ...]
    sealed_fragment_ids: tuple[str, ...]
    reviewed_fragment_ids: tuple[str, ...]
    modalities: dict[str, int]
    source_ids: tuple[str, ...]
    relation_count: int = Field(ge=0)


class FusionResult(StrictModel):
    bundle: InvestigationEpisodeBundle
    report: FusionReport


def manifest_digest(manifest: FusionManifest) -> str:
    return _stable_hash(manifest.model_dump(mode="json"))


def catalog_digest(catalog: SourceCatalog) -> str:
    return _stable_hash(catalog.model_dump(mode="json"))


def _validate_source_policy(
    fragment: EvidenceFragment,
    source: SourceSpec,
) -> None:
    if source.rights.acquisition is AcquisitionPolicy.BLOCKED:
        raise FusionError(f"source {source.source_id!r} is blocked for acquisition")
    if source.rights.ai_use is AIUsePolicy.BLOCKED:
        raise FusionError(f"source {source.source_id!r} is blocked for AI use")

    requires_review = (
        source.rights.acquisition is AcquisitionPolicy.REVIEW_REQUIRED
        or source.rights.ai_use is AIUsePolicy.REVIEW_REQUIRED
    )
    if requires_review and fragment.rights_review_id is None:
        raise FusionError(
            f"fragment {fragment.fragment_id!r} requires a rights_review_id for "
            f"source {source.source_id!r}"
        )

    parsed = urlparse(fragment.locator)
    if parsed.scheme == "http":
        raise FusionError(
            f"fragment {fragment.fragment_id!r} uses an insecure HTTP locator"
        )
    if parsed.scheme == "https":
        host = (parsed.hostname or "").lower()
        if not host:
            raise FusionError(
                f"fragment {fragment.fragment_id!r} has an invalid HTTPS locator"
            )
        if not _host_allowed(host, source.allowed_hosts):
            if fragment.rights_review_id is None:
                raise FusionError(
                    f"fragment {fragment.fragment_id!r} uses external host {host!r}; "
                    "a rights_review_id is required"
                )


def validate_fusion_sources(
    manifest: FusionManifest,
    catalog: SourceCatalog,
) -> None:
    """Fail closed when a fusion input is absent from or disallowed by the catalog."""

    sources = {source.source_id: source for source in catalog.sources}
    for fragment in manifest.fragments:
        source = sources.get(fragment.source_id)
        if source is None:
            raise FusionError(
                f"fragment {fragment.fragment_id!r} references unknown source "
                f"{fragment.source_id!r}"
            )
        _validate_source_policy(fragment, source)


def fuse_manifest(
    manifest: FusionManifest,
    catalog: SourceCatalog,
) -> FusionResult:
    """Compile one temporally correct multimodal manifest into public + sealed artifacts."""

    validate_fusion_sources(manifest, catalog)
    public_fragments: list[EvidenceFragment] = []
    withheld: list[str] = []
    sealed: list[str] = []

    for fragment in manifest.fragments:
        if fragment.sensitivity is Sensitivity.SEALED:
            sealed.append(fragment.fragment_id)
            continue
        if not fragment.timeless:
            assert fragment.available_from is not None  # guaranteed by model validation
            if fragment.available_from > manifest.simulation_as_of:
                withheld.append(fragment.fragment_id)
                continue
        public_fragments.append(fragment)

    public_items = tuple(_to_evidence_item(item) for item in public_fragments)
    public = PublicInvestigationEpisode(
        episode_id=manifest.episode_id,
        domain=manifest.domain,
        source_case_ids=manifest.source_case_ids,
        initial_public_state=manifest.initial_public_state,
        actors=manifest.actors,
        evidence=public_items,
        available_actions=manifest.available_actions,
        constraints=manifest.constraints,
    )
    oracle = PrivateInvestigationOracle(
        episode_id=manifest.episode_id,
        ground_truth_claims=manifest.ground_truth_claims,
        official_findings=manifest.official_findings,
        actual_timeline=manifest.actual_timeline,
        causal_edges=manifest.causal_edges,
        verifier_targets=manifest.verifier_targets,
    )
    bundle = InvestigationEpisodeBundle(public=public, oracle=oracle)
    counts = Counter(item.modality.value for item in manifest.fragments)
    report = FusionReport(
        episode_id=manifest.episode_id,
        simulation_as_of=manifest.simulation_as_of,
        manifest_sha256=manifest_digest(manifest),
        catalog_sha256=catalog_digest(catalog),
        public_fragment_ids=tuple(item.fragment_id for item in public_fragments),
        withheld_future_fragment_ids=tuple(withheld),
        sealed_fragment_ids=tuple(sealed),
        reviewed_fragment_ids=tuple(
            item.fragment_id
            for item in manifest.fragments
            if item.rights_review_id is not None
        ),
        modalities=dict(sorted(counts.items())),
        source_ids=tuple(sorted({item.source_id for item in manifest.fragments})),
        relation_count=len(manifest.relations),
    )
    return FusionResult(bundle=bundle, report=report)


def _to_evidence_item(fragment: EvidenceFragment) -> EvidenceItem:
    acquired_at = fragment.available_from if not fragment.timeless else None
    provenance = EvidenceProvenance(
        source_id=fragment.source_id,
        source_artifact_id=fragment.source_artifact_id,
        locator=fragment.locator,
        sha256=fragment.sha256,
        acquired_at=acquired_at,
    )
    return EvidenceItem(
        evidence_id=fragment.fragment_id,
        kind=f"{fragment.modality.value}:{fragment.epistemic_role.value}",
        provenance=(provenance,),
        observed_at=fragment.observed_at,
        available_from=fragment.available_from,
        reliability=fragment.reliability,
        sensitivity=fragment.sensitivity,
        content_ref=fragment.content_ref,
    )
