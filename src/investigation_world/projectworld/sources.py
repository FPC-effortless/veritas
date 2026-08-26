from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceKind(StrEnum):
    BIM_IFC = "BIM_IFC"
    BIM_BENCHMARK = "BIM_BENCHMARK"
    SAFETY = "SAFETY"
    PROCUREMENT = "PROCUREMENT"
    WEATHER = "WEATHER"
    TERRAIN = "TERRAIN"
    GEOSPATIAL = "GEOSPATIAL"
    BUILDING_PERFORMANCE = "BUILDING_PERFORMANCE"
    PROCEDURAL_TRANSCRIPT = "PROCEDURAL_TRANSCRIPT"
    STANDARD_TEST = "STANDARD_TEST"


class FusionTarget(StrEnum):
    SITE = "site"
    BUILDING = "building"
    DESIGN = "design"
    ACTIVITY = "activity"
    RESOURCE = "resource"
    WORK_PACKAGE = "work_package"
    SUPPLIER = "supplier"
    CONTRACT = "contract"
    COST = "cost"
    SAFETY_EVENT = "safety_event"
    WEATHER_EVENT = "weather_event"
    REQUIREMENT = "requirement"
    PROCEDURE = "procedure"
    EVIDENCE = "evidence"


class ExternalSourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    name: str
    kind: SourceKind
    canonical_url: str
    license: str
    attribution: str
    fusion_targets: list[FusionTarget]
    authority_rank: int = Field(default=50, ge=0, le=100)
    freshness: str = "variable"
    access_mode: str = "download_or_api"
    schema_notes: str = ""
    transform_notes: str = ""
    enabled_by_default: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class TranscriptSourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    title: str
    publisher: str
    url: str | None = None
    published: str | None = None
    duration_minutes: int | None = None
    topics: list[str] = Field(default_factory=list)
    ingestion_mode: str = "authorized_local_transcript"
    transcript_text_included: bool = False
    notes: str = ""


class SourceCorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest_id: str
    version: str
    generated_at: datetime
    sources: list[ExternalSourceSpec]
    transcript_sources: list[TranscriptSourceSpec]
    fusion_policy_version: str = "opw-fusion-v1"
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    canonical_type: FusionTarget
    canonical_id: str
    field_name: str
    value: Any
    observed_at: datetime | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    authority_rank: int = Field(default=50, ge=0, le=100)
    provenance: dict[str, Any] = Field(default_factory=dict)

    def key(self) -> tuple[str, str, str]:
        return self.canonical_type.value, self.canonical_id, self.field_name


class FusedSourceField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_type: FusionTarget
    canonical_id: str
    field_name: str
    value: Any
    winning_source_id: str
    confidence: float
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


class TranscriptChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    source_id: str
    sequence: int
    text: str
    token_estimate: int = Field(ge=1)
    topics: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


def _timestamp_key(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def fuse_records(records: list[NormalizedSourceRecord]) -> list[FusedSourceField]:
    """Fuse heterogeneous source facts while preserving disagreement and provenance."""
    grouped: dict[tuple[str, str, str], list[NormalizedSourceRecord]] = defaultdict(list)
    for record in records:
        grouped[record.key()].append(record)

    fused: list[FusedSourceField] = []
    for key, candidates in sorted(grouped.items()):
        ordered = sorted(
            candidates,
            key=lambda item: (
                item.authority_rank,
                item.confidence,
                _timestamp_key(item.observed_at),
                item.source_id,
            ),
            reverse=True,
        )
        winner = ordered[0]
        provenance = [
            {
                "source_id": item.source_id,
                "observed_at": None if item.observed_at is None else item.observed_at.isoformat(),
                "confidence": item.confidence,
                "authority_rank": item.authority_rank,
                **item.provenance,
            }
            for item in ordered
        ]
        alternatives = [
            {
                "source_id": item.source_id,
                "value": item.value,
                "confidence": item.confidence,
                "authority_rank": item.authority_rank,
            }
            for item in ordered[1:]
            if item.value != winner.value
        ]
        fused.append(
            FusedSourceField(
                canonical_type=winner.canonical_type,
                canonical_id=winner.canonical_id,
                field_name=winner.field_name,
                value=winner.value,
                winning_source_id=winner.source_id,
                confidence=winner.confidence,
                provenance=provenance,
                alternatives=alternatives,
            )
        )
    return fused


def chunk_transcript(
    source: TranscriptSourceSpec,
    text: str,
    *,
    words_per_chunk: int = 450,
    overlap_words: int = 60,
) -> list[TranscriptChunk]:
    """Convert an authorized transcript export into provenance-preserving training chunks."""
    if words_per_chunk < 50:
        raise ValueError("words_per_chunk must be at least 50")
    if overlap_words < 0 or overlap_words >= words_per_chunk:
        raise ValueError("overlap_words must be in [0, words_per_chunk)")
    words = text.split()
    if not words:
        return []
    stride = words_per_chunk - overlap_words
    chunks: list[TranscriptChunk] = []
    for sequence, start in enumerate(range(0, len(words), stride), start=1):
        payload = words[start : start + words_per_chunk]
        if not payload:
            break
        chunk_text = " ".join(payload)
        digest = hashlib.sha256(
            f"{source.source_id}:{sequence}:{chunk_text}".encode("utf-8")
        ).hexdigest()[:20]
        chunks.append(
            TranscriptChunk(
                chunk_id=f"yt-{digest}",
                source_id=source.source_id,
                sequence=sequence,
                text=chunk_text,
                token_estimate=max(1, int(len(payload) * 1.35)),
                topics=list(source.topics),
                provenance={
                    "title": source.title,
                    "publisher": source.publisher,
                    "url": source.url,
                    "ingestion_mode": source.ingestion_mode,
                },
            )
        )
        if start + words_per_chunk >= len(words):
            break
    return chunks


def construction_source_manifest() -> SourceCorpusManifest:
    """Curated public-source registry for ConstructionProjectWorld calibration and fusion."""
    sources = [
        ExternalSourceSpec(
            source_id="gni-bim-2026",
            name="GNI BIM Dataset",
            kind=SourceKind.BIM_IFC,
            canonical_url="https://doi.org/10.5281/zenodo.19722012",
            license="CC BY 4.0",
            attribution="Technical University of Munich, Georg Nemetschek Institute",
            fusion_targets=[FusionTarget.BUILDING, FusionTarget.DESIGN, FusionTarget.EVIDENCE],
            authority_rank=85,
            freshness="2026-04-24 release",
            schema_notes="224 anonymized IFC models; IFC2x3/IFC4; multidisciplinary subset",
            transform_notes=(
                "Parse IFC spatial hierarchy, element types, properties, quantities and relationships; "
                "retain source GUID provenance; derive design graph and quantity priors."
            ),
        ),
        ExternalSourceSpec(
            source_id="buildingsmart-official-samples",
            name="buildingSMART Official Sample/Test Files",
            kind=SourceKind.STANDARD_TEST,
            canonical_url="https://github.com/buildingSMART/Sample-Test-Files",
            license="repository license / per-file terms",
            attribution="buildingSMART International",
            fusion_targets=[FusionTarget.DESIGN, FusionTarget.REQUIREMENT, FusionTarget.EVIDENCE],
            authority_rank=95,
            schema_notes="Official IFC sample/test files across schema concepts.",
            transform_notes="Use as conformance fixtures and verifier regression cases, not population priors.",
        ),
        ExternalSourceSpec(
            source_id="buildingsmart-community-samples",
            name="buildingSMART Community Sample/Test Files",
            kind=SourceKind.BIM_IFC,
            canonical_url="https://github.com/buildingSMART/Community-Sample-Test-Files",
            license="CC BY 4.0",
            attribution="buildingSMART community contributors",
            fusion_targets=[FusionTarget.BUILDING, FusionTarget.DESIGN, FusionTarget.EVIDENCE],
            authority_rank=65,
            schema_notes="Community IFC/BCF/IDS examples; quality varies.",
            transform_notes="Validate before ingestion; use invalid/edge cases for adversarial scenarios.",
        ),
        ExternalSourceSpec(
            source_id="ifc-bench-v1",
            name="IFC-Bench",
            kind=SourceKind.BIM_BENCHMARK,
            canonical_url="https://github.com/sylvainHellin/ifc-bench",
            license="see dataset license files",
            attribution="IFC-Bench authors",
            fusion_targets=[FusionTarget.DESIGN, FusionTarget.ACTIVITY, FusionTarget.EVIDENCE],
            authority_rank=80,
            schema_notes="BIM QA pairs covering spatial, property, system and sequencing reasoning.",
            transform_notes="Map questions to project evidence tasks; reserve a subset for held-out evaluation.",
        ),
        ExternalSourceSpec(
            source_id="osha-severe-injury",
            name="OSHA Severe Injury Reports",
            kind=SourceKind.SAFETY,
            canonical_url="https://www.osha.gov/severeinjury",
            license="U.S. federal public data",
            attribution="Occupational Safety and Health Administration",
            fusion_targets=[FusionTarget.SAFETY_EVENT, FusionTarget.PROCEDURE, FusionTarget.EVIDENCE],
            authority_rank=95,
            freshness="periodically updated",
            schema_notes="Reported hospitalizations, amputations and eye losses with coded narratives.",
            transform_notes=(
                "Filter construction NAICS; normalize incident mechanisms and task context into hazard/event priors; "
                "never infer worker identity."
            ),
        ),
        ExternalSourceSpec(
            source_id="osha-enforcement-data",
            name="OSHA Data and Enforcement Downloads",
            kind=SourceKind.SAFETY,
            canonical_url="https://www.osha.gov/data",
            license="U.S. federal public data",
            attribution="Occupational Safety and Health Administration",
            fusion_targets=[FusionTarget.SAFETY_EVENT, FusionTarget.REQUIREMENT, FusionTarget.EVIDENCE],
            authority_rank=95,
            transform_notes="Calibrate inspection, citation and violation distributions by construction activity.",
        ),
        ExternalSourceSpec(
            source_id="usaspending-contracts",
            name="USAspending Federal Contract Awards",
            kind=SourceKind.PROCUREMENT,
            canonical_url="https://api.usaspending.gov/",
            license="U.S. federal public data",
            attribution="USAspending.gov",
            fusion_targets=[FusionTarget.SUPPLIER, FusionTarget.CONTRACT, FusionTarget.COST, FusionTarget.WORK_PACKAGE],
            authority_rank=80,
            schema_notes="Award/contract transactions, agencies, recipients, locations and amounts.",
            transform_notes=(
                "Filter construction NAICS/PSC; aggregate award lines into synthetic supplier/package/cost priors; "
                "do not copy real companies into private scenario ground truth without explicit provenance."
            ),
        ),
        ExternalSourceSpec(
            source_id="noaa-ghcnh",
            name="NOAA Global Historical Climatology Network Hourly",
            kind=SourceKind.WEATHER,
            canonical_url="https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly",
            license="NOAA public data; review dataset-specific attribution",
            attribution="NOAA National Centers for Environmental Information",
            fusion_targets=[FusionTarget.WEATHER_EVENT, FusionTarget.SITE, FusionTarget.ACTIVITY],
            authority_rank=95,
            schema_notes="Global hourly/synoptic surface observations; bulk download available.",
            transform_notes=(
                "Join site to nearest quality-controlled station; derive rainfall, heat, wind and visibility work-stop priors."
            ),
        ),
        ExternalSourceSpec(
            source_id="usgs-3dep",
            name="USGS 3D Elevation Program",
            kind=SourceKind.TERRAIN,
            canonical_url="https://www.usgs.gov/3d-elevation-program",
            license="public domain / no use restrictions for USGS data products",
            attribution="U.S. Geological Survey",
            fusion_targets=[FusionTarget.SITE, FusionTarget.DESIGN, FusionTarget.EVIDENCE],
            authority_rank=95,
            schema_notes="National elevation, lidar and terrain products.",
            transform_notes="Derive slope, grade, drainage and earthwork features for U.S. site scenarios.",
        ),
        ExternalSourceSpec(
            source_id="openstreetmap",
            name="OpenStreetMap",
            kind=SourceKind.GEOSPATIAL,
            canonical_url="https://www.openstreetmap.org/copyright",
            license="ODbL 1.0",
            attribution="OpenStreetMap contributors",
            fusion_targets=[FusionTarget.SITE, FusionTarget.RESOURCE, FusionTarget.SUPPLIER],
            authority_rank=70,
            schema_notes="Road, building, amenity and infrastructure graph via planet extracts/Overpass.",
            transform_notes=(
                "Use for access/logistics/site context; retain ODbL attribution and isolate derived-database obligations."
            ),
        ),
    ]

    transcripts = [
        TranscriptSourceSpec(
            source_id="yt-construction-management-2026-simplilearn",
            title="Construction Management Full Course 2026 | Construction Project Management Tutorial",
            publisher="Simplilearn",
            url="https://www.youtube.com/watch?v=Z6eQjEOEL78",
            published="2026-05-26",
            duration_minutes=65,
            topics=[
                "project lifecycle",
                "planning",
                "scheduling",
                "resource management",
                "cost estimation",
                "procurement",
                "contracts",
                "BIM",
                "risk",
                "closeout",
                "handover",
            ],
            notes="Registry contains metadata only; ingest transcript only from an authorized/local export.",
        ),
        TranscriptSourceSpec(
            source_id="yt-bim-coordination-fundamentals",
            title="Learn BIM Coordination Fundamentals [FULL COURSE]",
            publisher="BIM Accelerator",
            url="https://www.youtube.com/watch?v=Pph7h0qP7DM",
            published="2024-07-31",
            duration_minutes=35,
            topics=["BIM coordination", "MEP coordination", "plantroom access", "RCP coordination"],
            notes="Use procedural structure and authorized transcript chunks for coordination task priors.",
        ),
        TranscriptSourceSpec(
            source_id="yt-primavera-p6-complete-course",
            title="Primavera P6 Complete Course (3 Hours) | Full Project Management Tutorial",
            publisher="cadadda",
            duration_minutes=171,
            topics=[
                "WBS",
                "activities",
                "dependencies",
                "critical path",
                "resources",
                "risk",
                "baselines",
                "progress",
                "reporting",
            ],
            notes="Title/chapters verified from public video metadata; URL omitted until canonical ID is resolved.",
        ),
        TranscriptSourceSpec(
            source_id="yt-p6-pipeline-construction",
            title="Primavera p6 Free Course for Pipeline Construction Project | Planning Scheduling P6",
            publisher="Learn with EngrWaqas",
            published="2025-11-19",
            topics=[
                "EPC lifecycle",
                "WBS",
                "procurement planning",
                "construction planning",
                "resources",
                "productivity",
                "progress",
                "delays",
            ],
            notes="Metadata seed; ingest only authorized transcript text.",
        ),
        TranscriptSourceSpec(
            source_id="yt-preconstruction-costs-sto",
            title="How Preconstruction Saves Millions in Construction Costs",
            publisher="Building Conversations / STO Building Group",
            duration_minutes=49,
            topics=[
                "preconstruction",
                "schedule certainty",
                "cost predictability",
                "risk mitigation",
                "IPD",
                "value engineering",
                "procurement",
                "BIM/VDC",
                "4D planning",
            ],
            notes="Public podcast/video metadata; transcript text is not bundled.",
        ),
        TranscriptSourceSpec(
            source_id="yt-quantity-surveying-evolving-skills",
            title="EP 12 - The Evolving Skills of the Quantity Surveyor",
            publisher="The Quantity Surveying Podcast",
            published="2025-05-31",
            duration_minutes=21,
            topics=["quantity surveying", "4D BIM", "procurement analytics", "cost control"],
            notes="Public podcast metadata; transcript text is not bundled.",
        ),
    ]
    return SourceCorpusManifest(
        manifest_id="construction-projectworld-public-corpus",
        version="2026.08.26",
        generated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        sources=sources,
        transcript_sources=transcripts,
        metadata={
            "principle": "calibrate from public evidence, preserve provenance, reserve benchmark holdouts",
            "transcript_hours_from_duration_known": round(
                sum(item.duration_minutes or 0 for item in transcripts) / 60.0, 2
            ),
            "transcript_copyright_policy": (
                "Only user-authorized/local transcript text is chunked; public video metadata is safe to bundle."
            ),
        },
    )
