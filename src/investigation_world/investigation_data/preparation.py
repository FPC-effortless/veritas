from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pypdf import PdfReader, PdfWriter

from .models import (
    AIUsePolicy,
    ArtifactReceipt,
    DocumentPageExposure,
    DocumentPreparationPlan,
    DocumentPreparationResult,
    DocumentSliceSpec,
    PreparedDocumentSlice,
    SourceCatalog,
)


class PreparationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractedMember:
    path: str
    byte_count: int
    sha256: str


def safe_extract_zip(
    archive: Path,
    destination: Path,
    *,
    max_members: int = 100_000,
    max_uncompressed_bytes: int = 20 * 1024 * 1024 * 1024,
    max_compression_ratio: float = 1000.0,
) -> tuple[ExtractedMember, ...]:
    """Extract a ZIP without allowing traversal, links, encryption, or zip bombs."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[ExtractedMember] = []

    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > max_members:
            raise PreparationError(
                f"archive has {len(members)} members, exceeding max_members={max_members}"
            )

        total_declared = 0
        normalized_members: set[str] = set()
        for info in members:
            relative = _safe_member_path(info.filename)
            collision_key = relative.as_posix().casefold()
            if collision_key in normalized_members:
                raise PreparationError(
                    f"duplicate normalized ZIP member path is not allowed: {info.filename}"
                )
            normalized_members.add(collision_key)
            if info.flag_bits & 0x1:
                raise PreparationError(f"encrypted ZIP member is not allowed: {info.filename}")
            if _is_symlink(info):
                raise PreparationError(f"symbolic-link ZIP member is not allowed: {info.filename}")
            if info.is_dir():
                continue
            total_declared += info.file_size
            if total_declared > max_uncompressed_bytes:
                raise PreparationError(
                    "archive declared uncompressed size exceeds configured limit"
                )
            if info.compress_size == 0 and info.file_size > 0:
                raise PreparationError(f"invalid compressed size for member: {info.filename}")
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_compression_ratio:
                    raise PreparationError(
                        f"compression ratio {ratio:.1f} exceeds limit for {info.filename}"
                    )
            _assert_within(destination, destination / relative)

        actual_total = 0
        for info in members:
            relative = _safe_member_path(info.filename)
            target = (destination / relative).resolve()
            _assert_within(destination, target)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            byte_count = 0
            temp_path = target.with_name(f".{target.name}.part")
            try:
                with bundle.open(info, "r") as source, temp_path.open("wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        byte_count += len(chunk)
                        actual_total += len(chunk)
                        if actual_total > max_uncompressed_bytes:
                            raise PreparationError(
                                "archive extracted bytes exceed configured limit"
                            )
                        if byte_count > info.file_size:
                            raise PreparationError(
                                f"member exceeded declared size while extracting: {info.filename}"
                            )
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if byte_count != info.file_size:
                    raise PreparationError(
                        f"member size mismatch for {info.filename}: "
                        f"declared={info.file_size}, extracted={byte_count}"
                    )
                os.replace(temp_path, target)
            finally:
                temp_path.unlink(missing_ok=True)
            extracted.append(
                ExtractedMember(
                    path=relative.as_posix(),
                    byte_count=byte_count,
                    sha256=digest.hexdigest(),
                )
            )

    return tuple(extracted)


def deterministic_stratified_select(
    rows: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    stratum_field: str,
    quotas: Mapping[str, int],
    salt: str,
) -> tuple[Mapping[str, Any], ...]:
    """Select rows reproducibly within declared strata using stable SHA-256 ordering."""
    if not salt:
        raise ValueError("salt must be non-empty")
    if any(quota < 0 for quota in quotas.values()):
        raise ValueError("quotas must be non-negative")

    grouped: dict[str, list[Mapping[str, Any]]] = {stratum: [] for stratum in quotas}
    seen_ids: set[str] = set()
    for row in rows:
        if id_field not in row or stratum_field not in row:
            raise ValueError(f"row must contain {id_field!r} and {stratum_field!r}")
        identity = str(row[id_field])
        if identity in seen_ids:
            raise ValueError(f"duplicate source-case identity: {identity}")
        seen_ids.add(identity)
        stratum = str(row[stratum_field])
        if stratum in grouped:
            grouped[stratum].append(row)

    selected: list[Mapping[str, Any]] = []
    for stratum in sorted(quotas):
        quota = quotas[stratum]
        candidates = sorted(
            grouped[stratum],
            key=lambda row: _selection_digest(salt, str(row[id_field])),
        )
        if len(candidates) < quota:
            raise PreparationError(
                f"stratum {stratum!r} has {len(candidates)} eligible rows; quota requires {quota}"
            )
        selected.extend(candidates[:quota])
    return tuple(selected)


def copy_with_sha256(source: Path, destination: Path) -> str:
    """Copy a normalized artifact atomically while computing its content identity."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f".{destination.name}.part")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as input_file, temp_path.open("wb") as output_file:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output_file.write(chunk)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
    return digest.hexdigest()


def prepare_zip_artifact(
    receipt_path: Path,
    acquisition_root: Path,
    prepared_root: Path,
    *,
    max_members: int = 100_000,
    max_uncompressed_bytes: int = 20 * 1024 * 1024 * 1024,
    max_compression_ratio: float = 1000.0,
) -> Path:
    """Verify an acquisition receipt, safely extract its ZIP, and write a hash manifest."""
    from .acquisition import verify_receipt

    receipt_bytes = receipt_path.read_bytes()
    receipt = ArtifactReceipt.model_validate_json(receipt_bytes)
    if not verify_receipt(acquisition_root, receipt):
        raise PreparationError("acquired artifact does not match its provenance receipt")

    archive = (acquisition_root.resolve() / receipt.local_path).resolve()
    root = acquisition_root.resolve()
    if root not in archive.parents:
        raise PreparationError("receipt artifact path escaped acquisition root")

    destination = (
        prepared_root.resolve() / receipt.source_id / receipt.artifact_id / receipt.sha256[:16]
    )
    members = safe_extract_zip(
        archive,
        destination,
        max_members=max_members,
        max_uncompressed_bytes=max_uncompressed_bytes,
        max_compression_ratio=max_compression_ratio,
    )
    manifest = {
        "schema_version": "1.0",
        "source_id": receipt.source_id,
        "artifact_id": receipt.artifact_id,
        "artifact_sha256": receipt.sha256,
        "catalog_sha256": receipt.catalog_sha256,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "members": [
            {
                "path": member.path,
                "byte_count": member.byte_count,
                "sha256": member.sha256,
            }
            for member in members
        ],
    }
    manifest_path = destination / "extraction_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def prepare_document_artifact(
    receipt_path: Path,
    acquisition_root: Path,
    prepared_root: Path,
    plan: DocumentPreparationPlan,
    *,
    oracle_root: Path | None = None,
    catalog: SourceCatalog | None = None,
    max_bytes: int = 512 * 1024 * 1024,
) -> DocumentPreparationResult:
    """Split a receipt-verified PDF into physically separate public and oracle page slices."""
    from .acquisition import verify_receipt
    from .catalog import find_source

    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    receipt_bytes = receipt_path.read_bytes()
    receipt = ArtifactReceipt.model_validate_json(receipt_bytes)
    if not verify_receipt(acquisition_root, receipt):
        raise PreparationError("acquired artifact does not match its provenance receipt")
    if receipt.source_id != plan.source_id or receipt.artifact_id != plan.artifact_id:
        raise PreparationError("document plan source/artifact identity does not match receipt")
    if plan.expected_sha256 is not None and plan.expected_sha256 != receipt.sha256:
        raise PreparationError("document source SHA-256 does not match the preparation plan")

    if catalog is not None:
        source = find_source(catalog, plan.source_id)
        if not any(item.artifact_id == plan.artifact_id for item in source.artifacts):
            raise PreparationError("document plan artifact is absent from the current source catalog")
        if source.rights.ai_use is AIUsePolicy.BLOCKED:
            raise PreparationError("current source policy blocks AI use")
        if source.rights.ai_use is AIUsePolicy.REVIEW_REQUIRED and not receipt.rights_review_id:
            raise PreparationError("current source policy requires an AI-use review identifier")

    acquisition = acquisition_root.resolve()
    source_path = (acquisition / receipt.local_path).resolve()
    if acquisition not in source_path.parents:
        raise PreparationError("receipt artifact path escaped acquisition root")
    if source_path.stat().st_size > max_bytes:
        raise PreparationError(f"document exceeds max_bytes={max_bytes}")
    with source_path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise PreparationError("document artifact is not a PDF")

    public_base = prepared_root.resolve()
    oracle_base = oracle_root.resolve() if oracle_root is not None else None
    if oracle_base is not None:
        _assert_separate_roots(public_base, oracle_base)
    public_destination = public_base / plan.plan_id / receipt.sha256[:16]
    oracle_destination = (
        oracle_base / plan.plan_id / receipt.sha256[:16]
        if oracle_base is not None
        else None
    )
    if public_destination.exists():
        raise PreparationError(f"public document destination already exists: {public_destination}")
    if oracle_destination is not None and oracle_destination.exists():
        raise PreparationError(f"oracle document destination already exists: {oracle_destination}")

    reader = PdfReader(source_path)
    if reader.is_encrypted:
        raise PreparationError("encrypted PDF documents are not accepted")
    if len(reader.pages) != plan.expected_page_count:
        raise PreparationError(
            f"document page count changed: expected {plan.expected_page_count}, "
            f"got {len(reader.pages)}"
        )

    public_pages = _pages_for_exposure(plan, DocumentPageExposure.PUBLIC)
    _scan_public_pages(reader, public_pages, plan)

    public_destination.mkdir(parents=True, exist_ok=False)
    if oracle_destination is not None:
        oracle_destination.mkdir(parents=True, exist_ok=False)

    public_slices = _write_exposure_slices(
        reader,
        plan,
        DocumentPageExposure.PUBLIC,
        public_destination,
    )
    oracle_slices: tuple[PreparedDocumentSlice, ...] = ()
    if oracle_destination is not None:
        oracle_slices = _write_exposure_slices(
            reader,
            plan,
            DocumentPageExposure.ORACLE,
            oracle_destination,
        )

    ignored_pages = len(_pages_for_exposure(plan, DocumentPageExposure.IGNORE))
    public_manifest_path = public_destination / "manifest.json"
    public_manifest = {
        "schema_version": "1.0",
        "plan_id": plan.plan_id,
        "plan_version": plan.version,
        "source_id": plan.source_id,
        "artifact_id": plan.artifact_id,
        "source_sha256": receipt.sha256,
        "catalog_sha256": receipt.catalog_sha256,
        "public_title": plan.public_title,
        "domain": plan.domain,
        "event_date": plan.event_date.isoformat(),
        "objective": plan.objective,
        "text_scan": {
            "required": plan.text_scan_required,
            "pages_scanned": len(public_pages),
            "passed": True,
        },
        "slices": [item.model_dump(mode="json") for item in public_slices],
    }
    _write_json(public_manifest_path, public_manifest)

    oracle_manifest_path: Path | None = None
    if oracle_destination is not None:
        oracle_manifest_path = oracle_destination / "manifest.json"
        oracle_manifest = {
            "schema_version": "1.0",
            "plan": plan.model_dump(mode="json"),
            "source_case_id": plan.source_case_id,
            "source_url": receipt.source_url,
            "resolved_url": receipt.resolved_url,
            "source_sha256": receipt.sha256,
            "source_byte_count": receipt.byte_count,
            "catalog_sha256": receipt.catalog_sha256,
            "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "rights_review_id": receipt.rights_review_id,
            "public_slices": [item.model_dump(mode="json") for item in public_slices],
            "oracle_slices": [item.model_dump(mode="json") for item in oracle_slices],
            "ignored_page_count": ignored_pages,
        }
        _write_json(oracle_manifest_path, oracle_manifest)

    return DocumentPreparationResult(
        plan_id=plan.plan_id,
        source_sha256=receipt.sha256,
        public_slices=public_slices,
        oracle_slices=oracle_slices,
        ignored_page_count=ignored_pages,
        public_manifest=str(public_manifest_path),
        oracle_manifest=str(oracle_manifest_path) if oracle_manifest_path is not None else None,
    )


def _pages_for_exposure(
    plan: DocumentPreparationPlan,
    exposure: DocumentPageExposure,
) -> tuple[int, ...]:
    pages: list[int] = []
    for item in plan.slices:
        if item.exposure is not exposure:
            continue
        for page_range in item.page_ranges:
            pages.extend(range(page_range.start_page, page_range.end_page + 1))
    return tuple(pages)


def _scan_public_pages(
    reader: PdfReader,
    public_pages: tuple[int, ...],
    plan: DocumentPreparationPlan,
) -> None:
    patterns: list[re.Pattern[str]] = []
    for index, expression in enumerate(plan.forbidden_public_patterns, start=1):
        try:
            patterns.append(re.compile(expression, re.IGNORECASE | re.MULTILINE))
        except re.error as exc:
            raise PreparationError(f"invalid forbidden public pattern #{index}") from exc

    for page_number in public_pages:
        try:
            text = reader.pages[page_number - 1].extract_text() or ""
        except Exception as exc:
            raise PreparationError(f"could not extract text from public page {page_number}") from exc
        if plan.text_scan_required and not text.strip():
            raise PreparationError(f"public page {page_number} has no extractable text")
        for pattern_index, pattern in enumerate(patterns, start=1):
            if pattern.search(text):
                raise PreparationError(
                    f"public page {page_number} matched forbidden pattern #{pattern_index}"
                )


def _write_exposure_slices(
    reader: PdfReader,
    plan: DocumentPreparationPlan,
    exposure: DocumentPageExposure,
    destination: Path,
) -> tuple[PreparedDocumentSlice, ...]:
    written: list[PreparedDocumentSlice] = []
    for index, item in enumerate(plan.slices, start=1):
        if item.exposure is not exposure:
            continue
        page_numbers = _pages_for_slice(item)
        relative_path = Path("slices") / f"{index:03d}-{item.slice_id}.pdf"
        output_path = destination / relative_path
        digest = _write_pdf_slice(reader, page_numbers, output_path)
        written.append(
            PreparedDocumentSlice(
                slice_id=item.slice_id,
                title=item.title,
                exposure=exposure,
                page_count=len(page_numbers),
                local_path=relative_path.as_posix(),
                sha256=digest,
            )
        )
    return tuple(written)


def _pages_for_slice(item: DocumentSliceSpec) -> tuple[int, ...]:
    pages: list[int] = []
    for page_range in item.page_ranges:
        pages.extend(range(page_range.start_page, page_range.end_page + 1))
    return tuple(pages)


def _write_pdf_slice(reader: PdfReader, page_numbers: tuple[int, ...], destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for page_number in page_numbers:
        page = reader.pages[page_number - 1]
        page.pop("/Annots", None)
        writer.add_page(page)
    writer.add_metadata(
        {
            "/Title": "",
            "/Author": "",
            "/Subject": "",
            "/Keywords": "",
            "/Creator": "",
        }
    )
    temp_path = destination.with_name(f".{destination.name}.part")
    try:
        with temp_path.open("wb") as handle:
            writer.write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
    return _sha256_file(destination)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assert_separate_roots(public_root: Path, oracle_root: Path) -> None:
    if (
        public_root == oracle_root
        or public_root in oracle_root.parents
        or oracle_root in public_root.parents
    ):
        raise PreparationError("oracle output root must be separate from the public preparation root")


def _selection_digest(salt: str, identity: str) -> bytes:
    return hashlib.sha256(f"{salt}\0{identity}".encode()).digest()


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts:
        raise PreparationError(f"unsafe ZIP member path: {name}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise PreparationError(f"unsafe ZIP member path: {name}")
    if ":" in path.parts[0]:
        raise PreparationError(f"drive-qualified ZIP member path is not allowed: {name}")
    return path


def _assert_within(root: Path, candidate: Path) -> None:
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise PreparationError(f"archive member escaped extraction root: {candidate}")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK
