from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from pypdf import PdfReader, PdfWriter

from investigation_world.foundry.models import stable_hash

_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")


class DocumentExposure(StrEnum):
    PUBLIC = "public"
    VERIFIER = "verifier"
    IGNORE = "ignore"


class PageRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> PageRange:
        if self.end_page < self.start_page:
            raise ValueError("end_page must be greater than or equal to start_page")
        return self

    def pages(self) -> range:
        return range(self.start_page, self.end_page + 1)


class DocumentSliceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slice_id: str
    title: str
    exposure: DocumentExposure
    page_ranges: list[PageRange] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_internal_overlap(self) -> DocumentSliceRule:
        pages = [page for page_range in self.page_ranges for page in page_range.pages()]
        if len(pages) != len(set(pages)):
            raise ValueError(f"slice {self.slice_id} contains overlapping page ranges")
        return self


class DocumentDepthPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    version: str
    source_id: str
    source_case_id: str
    public_title: str
    jurisdiction: str
    domain: str
    event_date: date
    objective: str
    source_url: HttpUrl
    expected_page_count: int = Field(ge=1, le=5000)
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    forbidden_public_patterns: list[str] = Field(default_factory=list)
    slices: list[DocumentSliceRule] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_page_partition(self) -> DocumentDepthPlan:
        slice_ids = [item.slice_id for item in self.slices]
        if len(slice_ids) != len(set(slice_ids)):
            raise ValueError("document slice_id values must be unique")
        if not any(item.exposure == DocumentExposure.PUBLIC for item in self.slices):
            raise ValueError("document plan requires at least one public slice")
        if not any(item.exposure == DocumentExposure.VERIFIER for item in self.slices):
            raise ValueError("document plan requires at least one verifier slice")

        owner_by_page: dict[int, str] = {}
        for item in self.slices:
            for page_range in item.page_ranges:
                if page_range.end_page > self.expected_page_count:
                    raise ValueError(
                        f"slice {item.slice_id} exceeds expected_page_count="
                        f"{self.expected_page_count}"
                    )
                for page in page_range.pages():
                    previous = owner_by_page.get(page)
                    if previous is not None:
                        raise ValueError(
                            f"page {page} is assigned to both {previous} and {item.slice_id}"
                        )
                    owner_by_page[page] = item.slice_id

        expected = set(range(1, self.expected_page_count + 1))
        missing = sorted(expected - set(owner_by_page))
        if missing:
            raise ValueError(f"document plan leaves pages unclassified: {missing}")

        for pattern in self.forbidden_public_patterns:
            try:
                re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"invalid forbidden public pattern: {pattern!r}") from exc
        return self


class MaterializedDocumentSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slice_id: str
    title: str
    local_path: str
    page_count: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=1)


class DocumentDepthMaterializationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    public_case_id: str
    source_id: str
    source_sha256: str
    source_page_count: int = Field(ge=1)
    public_slices: list[MaterializedDocumentSlice]
    verifier_slices: list[MaterializedDocumentSlice]
    ignored_page_count: int = Field(ge=0)
    public_manifest: str
    verifier_manifest: str | None = None


def load_document_depth_plan(path: Path) -> DocumentDepthPlan:
    return DocumentDepthPlan.model_validate_json(path.read_text(encoding="utf-8"))


def _safe_component(value: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("-", value).strip(".-")
    if not cleaned:
        raise ValueError("document identifiers must contain a safe filename component")
    return cleaned


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _public_case_id(plan: DocumentDepthPlan) -> str:
    identity = stable_hash(
        {
            "plan_id": plan.plan_id,
            "version": plan.version,
            "source_id": plan.source_id,
            "event_date": plan.event_date.isoformat(),
        }
    )[:16]
    return f"{_safe_component(plan.source_id)}-{identity}"


def _rule_pages(rule: DocumentSliceRule) -> list[int]:
    return [page for page_range in rule.page_ranges for page in page_range.pages()]


def _scan_public_pages(
    reader: PdfReader,
    plan: DocumentDepthPlan,
    *,
    max_extracted_chars_per_page: int,
) -> None:
    patterns = [
        re.compile(pattern, re.IGNORECASE) for pattern in plan.forbidden_public_patterns
    ]
    if not patterns:
        return
    for rule in plan.slices:
        if rule.exposure != DocumentExposure.PUBLIC:
            continue
        for page_number in _rule_pages(rule):
            try:
                text = reader.pages[page_number - 1].extract_text() or ""
            except Exception as exc:
                raise ValueError(
                    f"could not inspect public page {page_number} for leakage"
                ) from exc
            if len(text) > max_extracted_chars_per_page:
                raise ValueError(
                    f"public page {page_number} exceeds extracted text safety cap"
                )
            for pattern in patterns:
                if pattern.search(text):
                    raise ValueError(
                        f"public page {page_number} matched forbidden pattern "
                        f"{pattern.pattern!r}"
                    )


def _write_slice(
    reader: PdfReader,
    rule: DocumentSliceRule,
    *,
    root: Path,
    public_case_id: str,
) -> MaterializedDocumentSlice:
    writer = PdfWriter()
    for page_number in _rule_pages(rule):
        page = reader.pages[page_number - 1]
        page.pop("/Annots", None)
        writer.add_page(page)
    writer.add_metadata({})

    relative_path = (
        Path(_safe_component(public_case_id)) / f"{_safe_component(rule.slice_id)}.pdf"
    )
    destination = root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        writer.write(handle)
    byte_count = destination.stat().st_size
    if byte_count <= 0:
        raise ValueError(f"materialized document slice is empty: {rule.slice_id}")
    return MaterializedDocumentSlice(
        slice_id=rule.slice_id,
        title=rule.title,
        local_path=relative_path.as_posix(),
        page_count=len(_rule_pages(rule)),
        sha256=_file_sha256(destination),
        byte_count=byte_count,
    )


def _public_manifest_payload(
    plan: DocumentDepthPlan,
    result: DocumentDepthMaterializationResult,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "veritas-document-depth-public-v1",
        "plan_id": plan.plan_id,
        "version": plan.version,
        "case_id": result.public_case_id,
        "source_id": plan.source_id,
        "title": plan.public_title,
        "jurisdiction": plan.jurisdiction,
        "domain": plan.domain,
        "event_date": plan.event_date.isoformat(),
        "objective": plan.objective,
        "slices": [item.model_dump(mode="json") for item in result.public_slices],
    }
    payload["content_hash"] = stable_hash(payload)
    return payload


def _verifier_manifest_payload(
    plan: DocumentDepthPlan,
    result: DocumentDepthMaterializationResult,
) -> dict[str, object]:
    return {
        "schema_version": "veritas-document-depth-verifier-v1",
        "plan_id": plan.plan_id,
        "version": plan.version,
        "public_case_id": result.public_case_id,
        "source_id": plan.source_id,
        "source_case_id": plan.source_case_id,
        "source_url": str(plan.source_url),
        "source_sha256": result.source_sha256,
        "source_page_count": result.source_page_count,
        "page_policy": [item.model_dump(mode="json") for item in plan.slices],
        "verifier_slices": [
            item.model_dump(mode="json") for item in result.verifier_slices
        ],
        "ignored_page_count": result.ignored_page_count,
    }


def materialize_document_depth_case(
    plan: DocumentDepthPlan,
    source_pdf: Path,
    *,
    public_root: Path,
    verifier_root: Path | None = None,
    max_bytes: int = 256 * 1024 * 1024,
    max_pages: int = 1000,
    max_extracted_chars_per_page: int = 1_000_000,
) -> DocumentDepthMaterializationResult:
    if max_bytes < 1 or max_pages < 1 or max_extracted_chars_per_page < 1:
        raise ValueError("document safety limits must be positive")
    byte_count = source_pdf.stat().st_size
    if byte_count > max_bytes:
        raise ValueError(f"source PDF exceeds max_bytes={max_bytes}")

    source_sha256 = _file_sha256(source_pdf)
    if plan.expected_sha256 is not None and source_sha256 != plan.expected_sha256:
        raise ValueError("source PDF SHA-256 does not match document plan")

    try:
        reader = PdfReader(str(source_pdf), strict=False)
    except Exception as exc:
        raise ValueError("source PDF could not be parsed") from exc
    if reader.is_encrypted:
        raise ValueError("encrypted PDFs are not permitted in document depth corpora")
    page_count = len(reader.pages)
    if page_count > max_pages:
        raise ValueError(f"source PDF exceeds max_pages={max_pages}")
    if page_count != plan.expected_page_count:
        raise ValueError(
            f"source PDF page count changed: expected {plan.expected_page_count}, "
            f"found {page_count}"
        )

    _scan_public_pages(
        reader,
        plan,
        max_extracted_chars_per_page=max_extracted_chars_per_page,
    )

    public_case_id = _public_case_id(plan)
    public_root.mkdir(parents=True, exist_ok=True)
    if verifier_root is not None:
        verifier_root.mkdir(parents=True, exist_ok=True)

    public_slices: list[MaterializedDocumentSlice] = []
    verifier_slices: list[MaterializedDocumentSlice] = []
    ignored_page_count = 0
    for rule in plan.slices:
        if rule.exposure == DocumentExposure.IGNORE:
            ignored_page_count += len(_rule_pages(rule))
            continue
        if rule.exposure == DocumentExposure.PUBLIC:
            public_slices.append(
                _write_slice(
                    reader,
                    rule,
                    root=public_root,
                    public_case_id=public_case_id,
                )
            )
            continue
        if verifier_root is not None:
            verifier_slices.append(
                _write_slice(
                    reader,
                    rule,
                    root=verifier_root,
                    public_case_id=public_case_id,
                )
            )

    public_manifest_path = public_root / "manifest.json"
    provisional = DocumentDepthMaterializationResult(
        plan_id=plan.plan_id,
        public_case_id=public_case_id,
        source_id=plan.source_id,
        source_sha256=source_sha256,
        source_page_count=page_count,
        public_slices=public_slices,
        verifier_slices=verifier_slices,
        ignored_page_count=ignored_page_count,
        public_manifest=str(public_manifest_path),
        verifier_manifest=(
            None if verifier_root is None else str(verifier_root / "manifest.json")
        ),
    )
    public_manifest_path.write_text(
        json.dumps(_public_manifest_payload(plan, provisional), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    if verifier_root is not None:
        verifier_manifest_path = verifier_root / "manifest.json"
        verifier_manifest_path.write_text(
            json.dumps(
                _verifier_manifest_payload(plan, provisional),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return provisional
