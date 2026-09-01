from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request

import pytest

from investigation_world.investigation_data.acquisition import AcquisitionError, plan_artifact
from investigation_world.investigation_data.catalog import find_source, load_catalog
from investigation_world.investigation_data.queued_acquisition import (
    acquire_queue_receipts,
    build_queue_catalog,
    load_acquisition_queue,
)


class FakeResponse:
    def __init__(self, url: str, payload: bytes, content_type: str = "application/pdf"):
        self._url = url
        self._body = io.BytesIO(payload)
        self.headers = {
            "Content-Length": str(len(payload)),
            "Content-Type": content_type,
        }

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeTransport:
    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads

    def open(self, request: Request, timeout: float) -> FakeResponse:
        del timeout
        return FakeResponse(request.full_url, self.payloads[request.full_url])


def write_queue(
    path: Path,
    *,
    source_url: str,
    sha256: str | None = None,
    acquisition_url: str | None = None,
) -> None:
    artifact = {
        "case_id": "2005-04-I-TX",
        "artifact_id": "csb-test-final-report",
        "source_url": source_url,
        "sha256": sha256,
    }
    if acquisition_url is not None:
        artifact["acquisition_url"] = acquisition_url
    value = {
        "schema_version": "1.0",
        "corpus_id": "test-corpus",
        "source_id": "uscsb",
        "artifacts": [artifact],
    }
    path.write_text(json.dumps(value), encoding="utf-8")


def test_queue_overlay_reuses_catalog_policy(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    write_queue(queue_path, source_url="https://www.csb.gov/test-report.pdf")

    queue = load_acquisition_queue(queue_path)
    catalog = build_queue_catalog(load_catalog(), queue)
    plan = plan_artifact(catalog, "uscsb", "csb-test-final-report")

    assert plan.allowed is True
    assert plan.source_url == "https://www.csb.gov/test-report.pdf"


def test_queue_overlay_uses_separate_acquisition_url_without_changing_checksum(
    tmp_path: Path,
) -> None:
    source_url = "https://www.csb.gov/file.aspx?DocumentId=5917"
    acquisition_url = "https://www.csb.gov/assets/1/20/chevron-final.pdf"
    canonical_sha256 = "5f3c9b829de0a0394448a9babaaeacae467ef810be16ce409c50e04115a454d1"
    queue_path = tmp_path / "queue.json"
    write_queue(
        queue_path,
        source_url=source_url,
        acquisition_url=acquisition_url,
        sha256=canonical_sha256,
    )

    catalog = build_queue_catalog(load_catalog(), load_acquisition_queue(queue_path))
    source = find_source(catalog, "uscsb")
    artifact = next(
        item for item in source.artifacts if item.artifact_id == "csb-test-final-report"
    )
    plan = plan_artifact(catalog, "uscsb", "csb-test-final-report")

    assert plan.source_url == acquisition_url
    assert artifact.expected_sha256 == canonical_sha256


def test_queue_overlay_preserves_declared_checksum_without_runtime_transition(
    tmp_path: Path,
) -> None:
    source_url = "https://www.csb.gov/file.aspx?DocumentId=5661"
    canonical_sha256 = "f933649ecbfebb1be7cb3707298d4c3c247f6f65653e666e9115861eb0abfdbc"
    queue_path = tmp_path / "queue.json"
    value = {
        "schema_version": "1.0",
        "corpus_id": "test-corpus",
        "source_id": "uscsb",
        "artifacts": [
            {
                "case_id": "2008-03-I-FL",
                "artifact_id": "csb-2008-03-i-fl-final-report",
                "source_url": source_url,
                "sha256": canonical_sha256,
            }
        ],
    }
    queue_path.write_text(json.dumps(value), encoding="utf-8")

    catalog = build_queue_catalog(load_catalog(), load_acquisition_queue(queue_path))
    source = find_source(catalog, "uscsb")
    artifact = next(
        item
        for item in source.artifacts
        if item.artifact_id == "csb-2008-03-i-fl-final-report"
    )

    assert artifact.expected_sha256 == canonical_sha256


def test_receipt_only_acquisition_binds_retained_effective_catalog(tmp_path: Path) -> None:
    source_url = "https://www.csb.gov/test-report.pdf"
    payload = b"%PDF-1.7\ncontrolled-test-report\n"
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    effective_catalog_out = tmp_path / "receipts" / "effective-catalog.json"
    write_queue(queue_path, source_url=source_url)

    bundle = acquire_queue_receipts(
        queue_path,
        output_root,
        receipts_out,
        effective_catalog_out=effective_catalog_out,
        delay_seconds=0,
        transport=FakeTransport({source_url: payload}),
    )

    artifact = bundle["artifacts"][0]
    catalog_sha256 = hashlib.sha256(effective_catalog_out.read_bytes()).hexdigest()
    reconstructed = load_catalog(effective_catalog_out)
    reconstructed_plan = plan_artifact(reconstructed, "uscsb", "csb-test-final-report")

    assert artifact["sha256"] == hashlib.sha256(payload).hexdigest()
    assert artifact["byte_count"] == len(payload)
    assert artifact["catalog_sha256"] == catalog_sha256
    assert bundle["catalog_sha256"] == catalog_sha256
    assert bundle["effective_catalog_sha256"] == catalog_sha256
    assert reconstructed_plan.allowed is True
    assert reconstructed_plan.source_url == source_url
    assert bundle["raw_payloads_retained"] is False
    assert receipts_out.is_file()
    assert effective_catalog_out.is_file()

    raw_files = [
        path
        for path in output_root.rglob("*")
        if path.is_file() and not path.name.endswith(".provenance.json")
    ]
    assert raw_files == []
    provenance_files = list(output_root.rglob("*.provenance.json"))
    assert len(provenance_files) == 1
    assert artifact["receipt_sha256"] == hashlib.sha256(
        provenance_files[0].read_bytes()
    ).hexdigest()


def test_effective_catalog_identity_changes_on_material_queue_mutation(tmp_path: Path) -> None:
    payload = b"%PDF-1.7\nstable-payload\n"
    digests: list[str] = []

    for index, source_url in enumerate(
        (
            "https://www.csb.gov/test-report-a.pdf",
            "https://www.csb.gov/test-report-b.pdf",
        )
    ):
        run_root = tmp_path / f"run-{index}"
        queue_path = run_root / "queue.json"
        receipts_out = run_root / "receipts" / "bundle.json"
        effective_catalog_out = run_root / "receipts" / "effective-catalog.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        write_queue(queue_path, source_url=source_url)

        bundle = acquire_queue_receipts(
            queue_path,
            run_root / "raw",
            receipts_out,
            effective_catalog_out=effective_catalog_out,
            delay_seconds=0,
            transport=FakeTransport({source_url: payload}),
        )
        digest = hashlib.sha256(effective_catalog_out.read_bytes()).hexdigest()
        assert bundle["catalog_sha256"] == digest
        assert bundle["artifacts"][0]["catalog_sha256"] == digest
        digests.append(digest)

    assert digests[0] != digests[1]


def test_known_hash_mismatch_fails_and_leaves_no_raw_payload(tmp_path: Path) -> None:
    source_url = "https://www.csb.gov/test-report.pdf"
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    effective_catalog_out = tmp_path / "receipts" / "effective-catalog.json"
    write_queue(queue_path, source_url=source_url, sha256="0" * 64)

    with pytest.raises(AcquisitionError, match="checksum mismatch"):
        acquire_queue_receipts(
            queue_path,
            output_root,
            receipts_out,
            effective_catalog_out=effective_catalog_out,
            delay_seconds=0,
            transport=FakeTransport({source_url: b"different bytes"}),
        )

    assert [path for path in output_root.rglob("*") if path.is_file()] == []
    assert not receipts_out.exists()
    assert not effective_catalog_out.exists()
