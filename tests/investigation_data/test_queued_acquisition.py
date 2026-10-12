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
    QueuedAcquisitionError,
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


def _make_symlink(link: Path, target: Path, *, target_is_directory: bool = False) -> None:
    try:
        link.symlink_to(target, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks unavailable in this test environment: {exc}")


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
    sentinel = output_root / "caller-owned.txt"
    output_root.mkdir(parents=True)
    sentinel.write_text("preserve me", encoding="utf-8")
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
    assert sentinel.read_text(encoding="utf-8") == "preserve me"

    raw_files = [
        path
        for path in output_root.rglob("*")
        if path.is_file()
        and not path.name.endswith(".provenance.json")
        and path != sentinel
    ]
    assert raw_files == []
    provenance_files = list(output_root.rglob("*.provenance.json"))
    assert len(provenance_files) == 1
    assert artifact["receipt_sha256"] == hashlib.sha256(
        provenance_files[0].read_bytes()
    ).hexdigest()


def test_queue_receipt_preserves_and_binds_canonical_and_acquisition_urls(
    tmp_path: Path,
) -> None:
    canonical_url = "https://www.csb.gov/file.aspx?DocumentId=5917"
    acquisition_url = "https://www.csb.gov/assets/1/20/chevron-final.pdf"
    payload = b"%PDF-1.7\ncanonical-and-transport\n"
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    write_queue(
        queue_path,
        source_url=canonical_url,
        acquisition_url=acquisition_url,
        sha256=payload_sha256,
    )

    bundle = acquire_queue_receipts(
        queue_path,
        output_root,
        receipts_out,
        delay_seconds=0,
        transport=FakeTransport({acquisition_url: payload}),
    )

    artifact = bundle["artifacts"][0]
    provenance_path = next(output_root.rglob("*.provenance.json"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    authority = {
        "source_id": "uscsb",
        "case_id": "2005-04-I-TX",
        "artifact_id": "csb-test-final-report",
        "canonical_source_url": canonical_url,
        "acquisition_url": acquisition_url,
        "expected_sha256": payload_sha256,
    }
    expected_spec_sha256 = hashlib.sha256(
        json.dumps(
            authority,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    for retained in (artifact, provenance):
        assert retained["source_url"] == acquisition_url
        assert retained["canonical_source_url"] == canonical_url
        assert retained["acquisition_url"] == acquisition_url
        assert retained["expected_sha256"] == payload_sha256
        assert retained["queue_sha256"] == bundle["queue_sha256"]
        assert retained["acquisition_spec_sha256"] == expected_spec_sha256

    assert artifact["sha256"] == payload_sha256


def test_acquisition_spec_identity_changes_when_canonical_source_changes(
    tmp_path: Path,
) -> None:
    acquisition_url = "https://www.csb.gov/assets/1/20/stable-report.pdf"
    payload = b"%PDF-1.7\nstable-transport-bytes\n"
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    catalog_digests: list[str] = []
    spec_digests: list[str] = []

    for index, canonical_url in enumerate(
        (
            "https://www.csb.gov/file.aspx?DocumentId=1001",
            "https://www.csb.gov/file.aspx?DocumentId=1002",
        )
    ):
        run_root = tmp_path / f"run-{index}"
        queue_path = run_root / "queue.json"
        receipts_out = run_root / "receipts" / "bundle.json"
        effective_catalog_out = run_root / "receipts" / "effective-catalog.json"
        queue_path.parent.mkdir(parents=True, exist_ok=True)
        write_queue(
            queue_path,
            source_url=canonical_url,
            acquisition_url=acquisition_url,
            sha256=payload_sha256,
        )

        bundle = acquire_queue_receipts(
            queue_path,
            run_root / "raw",
            receipts_out,
            effective_catalog_out=effective_catalog_out,
            delay_seconds=0,
            transport=FakeTransport({acquisition_url: payload}),
        )
        catalog_digests.append(bundle["effective_catalog_sha256"])
        spec_digests.append(bundle["artifacts"][0]["acquisition_spec_sha256"])

    assert catalog_digests[0] == catalog_digests[1]
    assert spec_digests[0] != spec_digests[1]


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


def test_known_hash_mismatch_preserves_unrelated_caller_file(tmp_path: Path) -> None:
    source_url = "https://www.csb.gov/test-report.pdf"
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    effective_catalog_out = tmp_path / "receipts" / "effective-catalog.json"
    sentinel = output_root / "caller-owned.txt"
    output_root.mkdir(parents=True)
    sentinel.write_text("preserve me", encoding="utf-8")
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

    assert sentinel.read_text(encoding="utf-8") == "preserve me"
    assert [
        path
        for path in output_root.rglob("*")
        if path.is_file() and path != sentinel
    ] == []
    assert not receipts_out.exists()
    assert not effective_catalog_out.exists()


def test_queue_acquisition_refuses_to_overwrite_existing_owned_target(tmp_path: Path) -> None:
    source_url = "https://www.csb.gov/test-report.pdf"
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    raw_target = (
        output_root
        / "uscsb"
        / "csb-test-final-report"
        / "csb-test-final-report.pdf"
    )
    raw_target.parent.mkdir(parents=True)
    raw_target.write_bytes(b"caller-owned-existing-bytes")
    write_queue(queue_path, source_url=source_url)

    with pytest.raises(QueuedAcquisitionError, match="refusing to overwrite pre-existing"):
        acquire_queue_receipts(
            queue_path,
            output_root,
            receipts_out,
            delay_seconds=0,
            transport=FakeTransport({source_url: b"new bytes"}),
        )

    assert raw_target.read_bytes() == b"caller-owned-existing-bytes"
    assert not receipts_out.exists()


def test_queue_acquisition_rejects_dangling_raw_symlink(tmp_path: Path) -> None:
    source_url = "https://www.csb.gov/test-report.pdf"
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    raw_target = (
        output_root
        / "uscsb"
        / "csb-test-final-report"
        / "csb-test-final-report.pdf"
    )
    outside_target = tmp_path / "outside-raw.pdf"
    raw_target.parent.mkdir(parents=True)
    _make_symlink(raw_target, outside_target)
    assert raw_target.is_symlink()
    assert not raw_target.exists()
    write_queue(queue_path, source_url=source_url)

    with pytest.raises(QueuedAcquisitionError, match="refusing to overwrite pre-existing"):
        acquire_queue_receipts(
            queue_path,
            output_root,
            receipts_out,
            delay_seconds=0,
            transport=FakeTransport({source_url: b"new bytes"}),
        )

    assert raw_target.is_symlink()
    assert not outside_target.exists()
    assert not receipts_out.exists()


def test_queue_acquisition_rejects_dangling_provenance_symlink(tmp_path: Path) -> None:
    source_url = "https://www.csb.gov/test-report.pdf"
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    raw_target = (
        output_root
        / "uscsb"
        / "csb-test-final-report"
        / "csb-test-final-report.pdf"
    )
    receipt_target = raw_target.with_name(raw_target.name + ".provenance.json")
    outside_target = tmp_path / "outside-provenance.json"
    receipt_target.parent.mkdir(parents=True)
    _make_symlink(receipt_target, outside_target)
    assert receipt_target.is_symlink()
    assert not receipt_target.exists()
    write_queue(queue_path, source_url=source_url)

    with pytest.raises(QueuedAcquisitionError, match="refusing to overwrite pre-existing"):
        acquire_queue_receipts(
            queue_path,
            output_root,
            receipts_out,
            delay_seconds=0,
            transport=FakeTransport({source_url: b"new bytes"}),
        )

    assert receipt_target.is_symlink()
    assert not outside_target.exists()
    assert not receipts_out.exists()


def test_queue_acquisition_rejects_symlinked_output_ancestor(tmp_path: Path) -> None:
    source_url = "https://www.csb.gov/test-report.pdf"
    queue_path = tmp_path / "queue.json"
    output_root = tmp_path / "raw"
    receipts_out = tmp_path / "receipts" / "bundle.json"
    outside_dir = tmp_path / "outside-dir"
    source_dir = output_root / "uscsb"
    output_root.mkdir(parents=True)
    outside_dir.mkdir()
    _make_symlink(source_dir, outside_dir, target_is_directory=True)
    write_queue(queue_path, source_url=source_url)

    with pytest.raises(QueuedAcquisitionError, match="refusing symlinked output directory"):
        acquire_queue_receipts(
            queue_path,
            output_root,
            receipts_out,
            delay_seconds=0,
            transport=FakeTransport({source_url: b"new bytes"}),
        )

    assert source_dir.is_symlink()
    assert list(outside_dir.iterdir()) == []
    assert not receipts_out.exists()
