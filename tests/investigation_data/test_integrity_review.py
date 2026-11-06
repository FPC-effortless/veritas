from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from investigation_world.investigation_data.acquisition import verify_receipt
from investigation_world.investigation_data.models import ArtifactReceipt
from investigation_world.investigation_data.preparation import (
    PreparationError,
    prepare_zip_artifact,
    safe_extract_zip,
)


def _receipt_for(
    archive: Path, root: Path, *, byte_count: int | None = None
) -> ArtifactReceipt:
    return ArtifactReceipt.now(
        source_id="source",
        artifact_id="artifact",
        source_url="https://example.test/data.zip",
        resolved_url="https://example.test/data.zip",
        sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        byte_count=archive.stat().st_size if byte_count is None else byte_count,
        content_type="application/zip",
        local_path=str(archive.relative_to(root)),
        catalog_sha256="0" * 64,
    )


def test_receipt_verification_checks_byte_count(tmp_path: Path):
    artifact = tmp_path / "source" / "artifact" / "data.zip"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"abc")
    receipt = _receipt_for(artifact, tmp_path, byte_count=4)
    assert not verify_receipt(tmp_path, receipt)


def test_zip_rejects_casefolded_duplicate_paths(tmp_path: Path):
    archive = tmp_path / "duplicate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("Data.csv", "a")
        bundle.writestr("data.csv", "b")
    with pytest.raises(PreparationError, match="duplicate normalized"):
        safe_extract_zip(archive, tmp_path / "out")


def test_extraction_manifest_contains_receipt_hash_not_host_path(tmp_path: Path):
    root = tmp_path / "raw"
    artifact = root / "source" / "artifact" / "data.zip"
    artifact.parent.mkdir(parents=True)
    with zipfile.ZipFile(artifact, "w") as bundle:
        bundle.writestr("data.csv", "a,b\n1,2\n")
    receipt = _receipt_for(artifact, root)
    receipt_path = artifact.with_name("data.zip.provenance.json")
    receipt_path.write_text(receipt.model_dump_json())
    manifest_path = prepare_zip_artifact(receipt_path, root, tmp_path / "prepared")
    manifest = json.loads(manifest_path.read_text())
    assert "receipt_sha256" in manifest
    assert "receipt_path" not in manifest
    assert str(tmp_path) not in manifest_path.read_text()
