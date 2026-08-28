from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import Field, model_validator

from .catalog import find_source
from .models import AcquisitionPolicy, AIUsePolicy, SourceCatalog, StrictModel


class CorpusEvidenceRelease(StrictModel):
    """A dated official source surface that can seed a later fusion manifest."""

    release_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    title: str = Field(min_length=1)
    release_date: date
    modality: Literal["document", "video"]
    phase: Literal["pre_final", "final", "post_final"]
    role: Literal[
        "preliminary_finding",
        "final_finding",
        "surveillance",
        "damage_documentation",
        "visual_reconstruction",
    ]
    url: str

    @model_validator(mode="after")
    def validate_release_url(self) -> "CorpusEvidenceRelease":
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("corpus evidence releases require a valid HTTPS URL")
        return self


class CorpusCaseSpec(StrictModel):
    case_id: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-I-[A-Z]{2}$")
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    title: str = Field(min_length=1)
    location: str = Field(min_length=1)
    accident_date: date
    final_report_date: date
    investigation_url: str
    capability_tags: tuple[str, ...] = Field(min_length=1)
    evidence_releases: tuple[CorpusEvidenceRelease, ...] = Field(min_length=1)
    notes: str = ""

    @model_validator(mode="after")
    def validate_case(self) -> "CorpusCaseSpec":
        if self.final_report_date < self.accident_date:
            raise ValueError("final_report_date cannot precede accident_date")
        parsed = urlparse(self.investigation_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("investigation_url must be a valid HTTPS URL")

        release_ids = [release.release_id for release in self.evidence_releases]
        if len(release_ids) != len(set(release_ids)):
            raise ValueError(f"duplicate release_id in {self.case_id}")
        for release in self.evidence_releases:
            if release.release_date < self.accident_date:
                raise ValueError(
                    f"release {release.release_id!r} predates accident {self.case_id}"
                )
            if release.phase == "pre_final" and release.release_date >= self.final_report_date:
                raise ValueError(
                    f"pre_final release {release.release_id!r} is not before final report"
                )
            if release.phase == "post_final" and release.release_date <= self.final_report_date:
                raise ValueError(
                    f"post_final release {release.release_id!r} is not after final report"
                )
        return self


class FusionCorpusIndex(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    corpus_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    source_id: str
    reviewed_on: date
    target_cases: int = Field(gt=0)
    date_only_availability_policy: Literal["next_day_12z"] = "next_day_12z"
    selection_policy: str = Field(min_length=1)
    cases: tuple[CorpusCaseSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_index(self) -> "FusionCorpusIndex":
        if len(self.cases) != self.target_cases:
            raise ValueError(
                f"corpus declares {self.target_cases} target cases but contains {len(self.cases)}"
            )
        case_ids = [case.case_id for case in self.cases]
        slugs = [case.slug for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique")
        if len(slugs) != len(set(slugs)):
            raise ValueError("case slugs must be unique")
        phases = {
            release.phase
            for case in self.cases
            for release in case.evidence_releases
        }
        if "pre_final" not in phases or "post_final" not in phases:
            raise ValueError("corpus must contain both pre-final and post-final evidence")
        return self


def load_fusion_corpus(path: Path) -> FusionCorpusIndex:
    return FusionCorpusIndex.model_validate_json(path.read_text(encoding="utf-8"))


def corpus_digest(index: FusionCorpusIndex) -> str:
    payload: Any = index.model_dump(mode="json")
    encoded = json.dumps(
        payload,
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


def validate_fusion_corpus_sources(
    index: FusionCorpusIndex,
    catalog: SourceCatalog,
) -> None:
    """Require the corpus index to stay inside its cataloged source boundary."""

    source = find_source(catalog, index.source_id)
    if source.rights.acquisition is AcquisitionPolicy.BLOCKED:
        raise ValueError(f"source {source.source_id!r} is blocked for acquisition")
    if source.rights.ai_use is AIUsePolicy.BLOCKED:
        raise ValueError(f"source {source.source_id!r} is blocked for AI use")

    urls = [case.investigation_url for case in index.cases]
    urls.extend(
        release.url
        for case in index.cases
        for release in case.evidence_releases
    )
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        if not _host_allowed(host, source.allowed_hosts):
            raise ValueError(
                f"corpus URL host {host!r} is outside source {source.source_id!r} allowlist"
            )
