from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from investigation_world.investigation_data.acquisition import (
    AcquisitionError,
    acquire_artifact,
    plan_artifact,
    verify_receipt,
)
from investigation_world.investigation_data.catalog import find_source, load_catalog
from investigation_world.investigation_data.models import (
    Actor,
    EvidenceItem,
    EvidenceProvenance,
    InvestigationEpisodeBundle,
    PrivateInvestigationOracle,
    PublicInvestigationEpisode,
    Sensitivity,
    TruthClaim,
)
from investigation_world.investigation_data.serialization import write_episode_bundle


class Headers(dict[str, str]):
    pass


class FakeResponse:
    def __init__(self, body: bytes, url: str, headers: dict[str, str] | None = None):
        self.body = body
        self.url = url
        self.headers = Headers(headers or {})
        self.offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class FakeTransport:
    def __init__(self, response: FakeResponse):
        self.response = response

    def open(self, request, timeout: float):
        return self.response


def test_catalog_loads_and_blocked_source_has_no_artifacts():
    catalog = load_catalog()
    assert len(catalog.sources) >= 8
    acled = find_source(catalog, "acled")
    assert acled.rights.acquisition.value == "blocked"
    assert acled.artifacts == ()


def test_review_required_source_is_explicit():
    catalog = load_catalog()
    source = find_source(catalog, "digital-corpora")
    assert source.rights.acquisition.value == "review_required"
    assert source.rights.redistribution.value == "review_required"


def test_ucdp_and_ntsb_direct_artifacts_are_acquirable():
    catalog = load_catalog()
    assert plan_artifact(catalog, "ucdp-ged-26.1", "ged-26.1-csv").allowed
    assert plan_artifact(catalog, "ntsb-aviation-census", "avall-2026-08").allowed


def test_non_http_artifact_refuses_generic_downloader():
    catalog = load_catalog()
    plan = plan_artifact(catalog, "sec-edgar-aaer", "edgar-api")
    assert not plan.allowed
    assert "generic downloader" in plan.reason


def test_acquisition_hashes_and_writes_receipt(tmp_path: Path):
    catalog = load_catalog()
    body = b"example investigation data\n"
    response = FakeResponse(
        body,
        "https://ucdp.uu.se/downloads/ged/ged261-csv.zip",
        {"Content-Length": str(len(body)), "Content-Type": "application/zip"},
    )
    receipt = acquire_artifact(
        catalog,
        "ucdp-ged-26.1",
        "ged-26.1-csv",
        tmp_path,
        max_bytes=1024,
        transport=FakeTransport(response),
    )
    assert receipt.sha256 == hashlib.sha256(body).hexdigest()
    assert receipt.byte_count == len(body)
    assert verify_receipt(tmp_path, receipt)
    receipt_file = tmp_path / receipt.local_path
    sidecar = receipt_file.with_name(receipt_file.name + ".provenance.json")
    assert sidecar.is_file()
    assert json.loads(sidecar.read_text())["catalog_sha256"] == receipt.catalog_sha256


def test_acquisition_rejects_redirect_to_non_allowlisted_host(tmp_path: Path):
    catalog = load_catalog()
    response = FakeResponse(b"x", "https://evil.example/payload.zip")
    with pytest.raises(AcquisitionError, match="allowlisted"):
        acquire_artifact(
            catalog,
            "ucdp-ged-26.1",
            "ged-26.1-csv",
            tmp_path,
            max_bytes=1024,
            transport=FakeTransport(response),
        )


def test_acquisition_enforces_streaming_size_limit(tmp_path: Path):
    catalog = load_catalog()
    response = FakeResponse(
        b"123456789",
        "https://ucdp.uu.se/downloads/ged/ged261-csv.zip",
    )
    with pytest.raises(AcquisitionError, match="exceeded"):
        acquire_artifact(
            catalog,
            "ucdp-ged-26.1",
            "ged-26.1-csv",
            tmp_path,
            max_bytes=4,
            transport=FakeTransport(response),
        )


def test_public_and_private_episode_outputs_are_sealed(tmp_path: Path):
    public = PublicInvestigationEpisode(
        episode_id="case-1",
        domain="digital_forensics",
        source_case_ids=("source-case-1",),
        initial_public_state={"brief": "Investigate the device"},
        actors=(Actor(actor_id="investigator", role="investigator"),),
        evidence=(
            EvidenceItem(
                evidence_id="e1",
                kind="disk_image",
                provenance=(
                    EvidenceProvenance(
                        source_id="nist-cfreds",
                        source_artifact_id="case-image",
                        locator="logical://image/1",
                    ),
                ),
                sensitivity=Sensitivity.PUBLIC,
                content_ref="evidence/e1",
            ),
        ),
        available_actions=("inspect", "search", "form_hypothesis"),
    )
    oracle = PrivateInvestigationOracle(
        episode_id="case-1",
        ground_truth_claims=(
            TruthClaim(
                claim_id="c1",
                proposition="Artifact X exists",
                truth_status="true",
                confidence=1.0,
                supporting_evidence_ids=("e1",),
            ),
        ),
        actual_timeline=({"t": 1, "event": "artifact created"},),
    )
    bundle = InvestigationEpisodeBundle(public=public, oracle=oracle)
    public_path = tmp_path / "public.json"
    oracle_path = tmp_path / "oracle.json"
    write_episode_bundle(bundle, public_path, oracle_path)
    public_text = public_path.read_text()
    oracle_text = oracle_path.read_text()
    assert "ground_truth_claims" not in public_text
    assert "actual_timeline" not in public_text
    assert "ground_truth_claims" in oracle_text


def test_public_episode_rejects_sealed_evidence():
    with pytest.raises(ValueError, match="sealed evidence"):
        PublicInvestigationEpisode(
            episode_id="case-1",
            domain="test",
            source_case_ids=("s",),
            initial_public_state={},
            evidence=(
                EvidenceItem(
                    evidence_id="secret",
                    kind="answer_key",
                    provenance=(
                        EvidenceProvenance(
                            source_id="s", source_artifact_id="a", locator="logical://secret"
                        ),
                    ),
                    sensitivity=Sensitivity.SEALED,
                    content_ref="private/secret",
                ),
            ),
            available_actions=("inspect",),
        )
