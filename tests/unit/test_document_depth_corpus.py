from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter

from investigation_world.foundry.document_depth_corpus import (
    DocumentDepthPlan,
    DocumentExposure,
    DocumentSliceRule,
    PageRange,
    materialize_document_depth_case,
)


def _make_pdf(path: Path, pages: int = 6) -> None:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    with path.open("wb") as handle:
        writer.write(handle)


def _plan() -> DocumentDepthPlan:
    return DocumentDepthPlan(
        plan_id="test-depth-plan",
        version="1.0.0",
        source_id="test_authority",
        source_case_id="PUBLIC-SOURCE-ID-42",
        public_title="Example investigation",
        jurisdiction="Test jurisdiction",
        domain="test_failure",
        event_date=date(2025, 1, 2),
        objective="Determine the supported cause from factual material.",
        source_url="https://authority.example/investigation.pdf",
        expected_page_count=6,
        slices=[
            DocumentSliceRule(
                slice_id="front-matter",
                title="Front matter",
                exposure=DocumentExposure.IGNORE,
                page_ranges=[PageRange(start_page=1, end_page=1)],
            ),
            DocumentSliceRule(
                slice_id="facts",
                title="Summary of facts",
                exposure=DocumentExposure.PUBLIC,
                page_ranges=[PageRange(start_page=2, end_page=4)],
            ),
            DocumentSliceRule(
                slice_id="findings",
                title="Findings and opinion",
                exposure=DocumentExposure.VERIFIER,
                page_ranges=[PageRange(start_page=5, end_page=6)],
            ),
        ],
    )


def test_document_plan_requires_complete_nonoverlapping_page_partition() -> None:
    payload = _plan().model_dump(mode="json")
    payload["slices"][0]["page_ranges"] = [{"start_page": 1, "end_page": 2}]

    with pytest.raises(ValidationError, match="assigned to both"):
        DocumentDepthPlan.model_validate(payload)

    payload = _plan().model_dump(mode="json")
    payload["slices"][0]["page_ranges"] = [{"start_page": 1, "end_page": 1}]
    payload["slices"][1]["page_ranges"] = [{"start_page": 3, "end_page": 4}]

    with pytest.raises(ValidationError, match="leaves pages unclassified"):
        DocumentDepthPlan.model_validate(payload)


def test_document_materializer_physically_separates_public_and_verifier(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_pdf(source)
    public_root = tmp_path / "public"
    verifier_root = tmp_path / "sealed"

    result = materialize_document_depth_case(
        _plan(),
        source,
        public_root=public_root,
        verifier_root=verifier_root,
    )

    assert len(result.public_slices) == 1
    assert len(result.verifier_slices) == 1
    assert result.ignored_page_count == 1
    public_slice = public_root / result.public_slices[0].local_path
    verifier_slice = verifier_root / result.verifier_slices[0].local_path
    assert len(PdfReader(public_slice).pages) == 3
    assert len(PdfReader(verifier_slice).pages) == 2
    assert not (public_root / result.verifier_slices[0].local_path).exists()

    public_manifest = json.loads((public_root / "manifest.json").read_text(encoding="utf-8"))
    serialized = json.dumps(public_manifest, sort_keys=True)
    assert "PUBLIC-SOURCE-ID-42" not in serialized
    assert "authority.example" not in serialized
    assert "page_ranges" not in serialized
    assert "findings" not in serialized
    assert public_manifest["slices"][0]["slice_id"] == "facts"

    verifier_manifest = json.loads(
        (verifier_root / "manifest.json").read_text(encoding="utf-8")
    )
    assert verifier_manifest["source_case_id"] == "PUBLIC-SOURCE-ID-42"
    assert verifier_manifest["source_url"].startswith("https://authority.example/")
    assert verifier_manifest["page_policy"][2]["exposure"] == "verifier"


def test_document_materializer_does_not_emit_verifier_by_default(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_pdf(source)
    public_root = tmp_path / "public"

    result = materialize_document_depth_case(
        _plan(),
        source,
        public_root=public_root,
    )

    assert result.verifier_slices == []
    assert result.verifier_manifest is None
    assert not (tmp_path / "sealed").exists()


def test_document_materializer_rejects_page_count_drift(tmp_path: Path) -> None:
    source = tmp_path / "changed.pdf"
    _make_pdf(source, pages=7)

    with pytest.raises(ValueError, match="page count changed"):
        materialize_document_depth_case(
            _plan(),
            source,
            public_root=tmp_path / "public",
        )


def test_document_materializer_rejects_sha_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_pdf(source)
    plan = _plan().model_copy(update={"expected_sha256": "0" * 64})

    with pytest.raises(ValueError, match="SHA-256"):
        materialize_document_depth_case(
            plan,
            source,
            public_root=tmp_path / "public",
        )
