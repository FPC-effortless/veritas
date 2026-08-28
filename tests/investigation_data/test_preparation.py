from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from investigation_world.investigation_data.models import ArtifactReceipt
from investigation_world.investigation_data.preparation import (
    PreparationError,
    deterministic_stratified_select,
    prepare_zip_artifact,
    safe_extract_zip,
)


def test_safe_zip_extraction_rejects_path_traversal(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "no")
    with pytest.raises(PreparationError, match="unsafe ZIP member path"):
        safe_extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_safe_zip_extraction_hashes_members(tmp_path: Path):
    archive = tmp_path / "ok.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("nested/data.csv", "case_id,value\n1,x\n")
    extracted = safe_extract_zip(archive, tmp_path / "out", max_uncompressed_bytes=1024)
    assert len(extracted) == 1
    assert extracted[0].path == "nested/data.csv"
    assert extracted[0].sha256 == hashlib.sha256(b"case_id,value\n1,x\n").hexdigest()


def test_deterministic_stratified_selection_is_order_independent():
    rows = [
        {"case_id": "a", "stratum": "human"},
        {"case_id": "b", "stratum": "human"},
        {"case_id": "c", "stratum": "system"},
        {"case_id": "d", "stratum": "system"},
    ]
    kwargs = {
        "id_field": "case_id",
        "stratum_field": "stratum",
        "quotas": {"human": 1, "system": 1},
        "salt": "catalog-v1:gold",
    }
    first = deterministic_stratified_select(rows, **kwargs)
    second = deterministic_stratified_select(list(reversed(rows)), **kwargs)
    assert [row["case_id"] for row in first] == [row["case_id"] for row in second]


def test_deterministic_selection_fails_closed_on_underfilled_stratum():
    with pytest.raises(PreparationError, match="quota requires"):
        deterministic_stratified_select(
            [{"case_id": "a", "stratum": "human"}],
            id_field="case_id",
            stratum_field="stratum",
            quotas={"human": 2},
            salt="catalog-v1:gold",
        )


def test_prepare_zip_requires_receipt_integrity(tmp_path: Path):
    acquisition_root = tmp_path / "raw"
    artifact_dir = acquisition_root / "source" / "artifact"
    artifact_dir.mkdir(parents=True)
    archive = artifact_dir / "data.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("data.csv", "id,value\n1,x\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    receipt = ArtifactReceipt.now(
        source_id="source",
        artifact_id="artifact",
        source_url="https://example.test/data.zip",
        resolved_url="https://example.test/data.zip",
        sha256=digest,
        byte_count=archive.stat().st_size,
        content_type="application/zip",
        local_path="source/artifact/data.zip",
        catalog_sha256="0" * 64,
    )
    receipt_path = archive.with_name("data.zip.provenance.json")
    receipt_path.write_text(receipt.model_dump_json())
    archive.write_bytes(b"tampered")
    with pytest.raises(PreparationError, match="does not match"):
        prepare_zip_artifact(receipt_path, acquisition_root, tmp_path / "prepared")


def test_prepare_zip_writes_member_hash_manifest(tmp_path: Path):
    acquisition_root = tmp_path / "raw"
    artifact_dir = acquisition_root / "source" / "artifact"
    artifact_dir.mkdir(parents=True)
    archive = artifact_dir / "data.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("data.csv", "id,value\n1,x\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    receipt = ArtifactReceipt.now(
        source_id="source",
        artifact_id="artifact",
        source_url="https://example.test/data.zip",
        resolved_url="https://example.test/data.zip",
        sha256=digest,
        byte_count=archive.stat().st_size,
        content_type="application/zip",
        local_path="source/artifact/data.zip",
        catalog_sha256="0" * 64,
    )
    receipt_path = archive.with_name("data.zip.provenance.json")
    receipt_path.write_text(receipt.model_dump_json())
    manifest_path = prepare_zip_artifact(
        receipt_path, acquisition_root, tmp_path / "prepared", max_uncompressed_bytes=1024
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["artifact_sha256"] == digest
    assert manifest["members"][0]["path"] == "data.csv"
    assert manifest["members"][0]["sha256"] == hashlib.sha256(b"id,value\n1,x\n").hexdigest()
