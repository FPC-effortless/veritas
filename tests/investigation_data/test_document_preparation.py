from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject

from investigation_world.investigation_data.models import (
    ArtifactReceipt,
    DocumentPageExposure,
    DocumentPreparationPlan,
    DocumentSliceSpec,
    PageRange,
)
from investigation_world.investigation_data.preparation import (
    PreparationError,
    prepare_document_artifact,
)


def _write_pdf(path: Path, pages: int = 6) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


def _write_receipt(acquisition_root: Path, source_path: Path) -> Path:
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    receipt = ArtifactReceipt(
        source_id="test-source",
        artifact_id="test-document",
        source_url="https://authority.example/report.pdf",
        resolved_url="https://authority.example/report.pdf",
        retrieved_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
        sha256=digest,
        byte_count=source_path.stat().st_size,
        content_type="application/pdf",
        local_path=str(source_path.relative_to(acquisition_root)),
        catalog_sha256="a" * 64,
    )
    receipt_path = source_path.with_name(source_path.name + ".provenance.json")
    receipt_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt_path


def _plan(
    *,
    page_count: int = 6,
    text_scan_required: bool = False,
    forbidden_public_patterns: tuple[str, ...] = (),
) -> DocumentPreparationPlan:
    return DocumentPreparationPlan(
        plan_id="test-document-depth",
        version="1.0.0",
        source_id="test-source",
        artifact_id="test-document",
        source_case_id="SOURCE-CASE-42",
        public_title="Example investigation",
        domain="test_failure",
        event_date=date(2025, 1, 2),
        objective="Determine the best-supported cause from the available factual record.",
        expected_page_count=page_count,
        slices=(
            DocumentSliceSpec(
                slice_id="front-matter",
                title="Front matter",
                exposure=DocumentPageExposure.IGNORE,
                page_ranges=(PageRange(start_page=1, end_page=1),),
            ),
            DocumentSliceSpec(
                slice_id="facts",
                title="Factual record",
                exposure=DocumentPageExposure.PUBLIC,
                page_ranges=(PageRange(start_page=2, end_page=4),),
            ),
            DocumentSliceSpec(
                slice_id="findings",
                title="Findings and opinion",
                exposure=DocumentPageExposure.ORACLE,
                page_ranges=(PageRange(start_page=5, end_page=page_count),),
            ),
        ),
        forbidden_public_patterns=forbidden_public_patterns,
        text_scan_required=text_scan_required,
    )


def _source_fixture(tmp_path: Path, pages: int = 6) -> tuple[Path, Path, Path]:
    acquisition_root = tmp_path / "acquired"
    source_path = acquisition_root / "test-source" / "test-document" / "report.pdf"
    _write_pdf(source_path, pages=pages)
    receipt_path = _write_receipt(acquisition_root, source_path)
    return acquisition_root, source_path, receipt_path


def test_document_plan_requires_complete_nonoverlapping_partition() -> None:
    payload = _plan().model_dump(mode="json")
    payload["slices"][0]["page_ranges"] = [{"start_page": 1, "end_page": 2}]
    with pytest.raises(ValidationError, match="assigned to both"):
        DocumentPreparationPlan.model_validate(payload)

    payload = _plan().model_dump(mode="json")
    payload["slices"][1]["page_ranges"] = [{"start_page": 3, "end_page": 4}]
    with pytest.raises(ValidationError, match="leaves pages unclassified"):
        DocumentPreparationPlan.model_validate(payload)


def test_document_preparation_physically_separates_public_and_oracle(tmp_path: Path) -> None:
    acquisition_root, _, receipt_path = _source_fixture(tmp_path)
    public_root = tmp_path / "public"
    oracle_root = tmp_path / "oracle"

    result = prepare_document_artifact(
        receipt_path,
        acquisition_root,
        public_root,
        _plan(),
        oracle_root=oracle_root,
    )

    assert len(result.public_slices) == 1
    assert len(result.oracle_slices) == 1
    assert result.ignored_page_count == 1

    public_manifest_path = Path(result.public_manifest)
    oracle_manifest_path = Path(result.oracle_manifest or "")
    public_pdf = public_manifest_path.parent / result.public_slices[0].local_path
    oracle_pdf = oracle_manifest_path.parent / result.oracle_slices[0].local_path
    assert len(PdfReader(public_pdf).pages) == 3
    assert len(PdfReader(oracle_pdf).pages) == 2

    public_manifest = json.loads(public_manifest_path.read_text(encoding="utf-8"))
    serialized_public = json.dumps(public_manifest, sort_keys=True)
    assert "SOURCE-CASE-42" not in serialized_public
    assert "authority.example" not in serialized_public
    assert "page_ranges" not in serialized_public
    assert "oracle_slices" not in serialized_public
    assert public_manifest["text_scan"]["passed"] is True

    oracle_manifest = json.loads(oracle_manifest_path.read_text(encoding="utf-8"))
    assert oracle_manifest["source_case_id"] == "SOURCE-CASE-42"
    assert oracle_manifest["source_url"].startswith("https://authority.example/")
    assert oracle_manifest["plan"]["slices"][2]["exposure"] == "oracle"


def test_document_preparation_defaults_to_public_only(tmp_path: Path) -> None:
    acquisition_root, _, receipt_path = _source_fixture(tmp_path)

    result = prepare_document_artifact(
        receipt_path,
        acquisition_root,
        tmp_path / "public",
        _plan(),
    )

    assert result.oracle_slices == ()
    assert result.oracle_manifest is None


def test_document_preparation_rejects_nested_oracle_root(tmp_path: Path) -> None:
    acquisition_root, _, receipt_path = _source_fixture(tmp_path)
    public_root = tmp_path / "public"

    with pytest.raises(PreparationError, match="must be separate"):
        prepare_document_artifact(
            receipt_path,
            acquisition_root,
            public_root,
            _plan(),
            oracle_root=public_root / "sealed",
        )


def test_document_preparation_rejects_page_count_drift(tmp_path: Path) -> None:
    acquisition_root, _, receipt_path = _source_fixture(tmp_path, pages=7)

    with pytest.raises(PreparationError, match="page count changed"):
        prepare_document_artifact(
            receipt_path,
            acquisition_root,
            tmp_path / "public",
            _plan(page_count=6),
        )


def test_document_preparation_rejects_tampered_acquired_bytes(tmp_path: Path) -> None:
    acquisition_root, source_path, receipt_path = _source_fixture(tmp_path)
    with source_path.open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(PreparationError, match="provenance receipt"):
        prepare_document_artifact(
            receipt_path,
            acquisition_root,
            tmp_path / "public",
            _plan(),
        )


def test_document_preparation_rejects_answer_pattern_on_public_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquisition_root, _, receipt_path = _source_fixture(tmp_path)
    monkeypatch.setattr(
        PageObject,
        "extract_text",
        lambda self, *args, **kwargs: "The board found by a preponderance of evidence that X.",
    )

    with pytest.raises(PreparationError, match="forbidden pattern #1"):
        prepare_document_artifact(
            receipt_path,
            acquisition_root,
            tmp_path / "public",
            _plan(
                text_scan_required=True,
                forbidden_public_patterns=(r"preponderance of evidence",),
            ),
        )
