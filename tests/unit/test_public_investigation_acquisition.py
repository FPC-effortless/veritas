from __future__ import annotations

from pathlib import Path

import pytest

from investigation_world.foundry.public_investigation_acquisition import (
    materialize_public_investigation_dataset,
    validate_dataset_registry,
)
from investigation_world.foundry.public_investigation_data import (
    PublicInvestigationDataset,
    load_public_investigation_dataset,
    load_source_registry,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "datasets/public_investigations/source_registry.json"
SEED_PATH = REPO_ROOT / "datasets/public_investigations/seeds/seed_v1.json"


def _fake_fetcher(artifact, allowed_hosts, timeout_seconds, max_bytes):
    assert allowed_hosts
    assert timeout_seconds > 0
    assert max_bytes > 0
    return f"frozen:{artifact.artifact_id}".encode()


def test_materializer_freezes_public_without_verifier(tmp_path: Path) -> None:
    registry = load_source_registry(REGISTRY_PATH)
    dataset = load_public_investigation_dataset(SEED_PATH)

    result = materialize_public_investigation_dataset(
        dataset,
        registry,
        public_root=tmp_path / "public",
        fetcher=_fake_fetcher,
    )

    assert result.public_artifacts_downloaded == 13
    assert result.verifier_artifacts_downloaded == 0
    assert result.reference_only_artifacts == 3
    assert (tmp_path / "public/materialization.json").exists()
    assert not (tmp_path / "verifier").exists()
    assert all(not case.verifier_artifacts for case in result.cases)


def test_materializer_keeps_verifier_files_in_separate_root(tmp_path: Path) -> None:
    registry = load_source_registry(REGISTRY_PATH)
    dataset = load_public_investigation_dataset(SEED_PATH)

    result = materialize_public_investigation_dataset(
        dataset,
        registry,
        public_root=tmp_path / "public",
        verifier_root=tmp_path / "verifier",
        fetcher=_fake_fetcher,
    )

    assert result.verifier_artifacts_downloaded == 4
    assert (tmp_path / "verifier/materialization.json").exists()
    public_inventory = (tmp_path / "public/materialization.json").read_text()
    assert "verifier_artifacts" not in public_inventory
    assert "RRD23MR005-final-report" not in public_inventory
    assert "2005-04-I-TX-final-report" not in public_inventory
    assert all(case.verifier_artifacts for case in result.cases)
    for case in result.cases:
        for artifact in case.verifier_artifacts:
            assert artifact.local_path is not None
            assert (tmp_path / "verifier" / artifact.local_path).exists()
            assert not (tmp_path / "public" / artifact.local_path).exists()


def test_registry_validation_rejects_unknown_sources() -> None:
    registry = load_source_registry(REGISTRY_PATH)
    dataset = load_public_investigation_dataset(SEED_PATH)
    payload = dataset.model_dump(mode="json")
    payload["cases"][0]["source_id"] = "unknown-source"
    modified = PublicInvestigationDataset.model_validate(payload)

    with pytest.raises(ValueError, match="unknown source ids"):
        validate_dataset_registry(modified, registry)


def test_registry_validation_rejects_registry_identity_mismatch() -> None:
    registry = load_source_registry(REGISTRY_PATH)
    dataset = load_public_investigation_dataset(SEED_PATH).model_copy(
        update={"source_registry_id": "different-registry"}
    )

    with pytest.raises(ValueError, match="does not match"):
        validate_dataset_registry(dataset, registry)


def test_materializer_rejects_unregistered_download_host(tmp_path: Path) -> None:
    registry = load_source_registry(REGISTRY_PATH)
    dataset = load_public_investigation_dataset(SEED_PATH)
    payload = dataset.model_dump(mode="json")
    payload["cases"][0]["public_evidence"][0]["url"] = "https://example.com/evidence.pdf"
    modified = PublicInvestigationDataset.model_validate(payload)

    with pytest.raises(ValueError, match="not authorized"):
        materialize_public_investigation_dataset(
            modified,
            registry,
            public_root=tmp_path / "public",
            fetcher=_fake_fetcher,
        )


def test_materializer_rejects_non_https_artifact_url(tmp_path: Path) -> None:
    registry = load_source_registry(REGISTRY_PATH)
    dataset = load_public_investigation_dataset(SEED_PATH)
    payload = dataset.model_dump(mode="json")
    payload["cases"][0]["public_evidence"][0]["url"] = (
        "http://data.ntsb.gov/evidence.pdf"
    )
    modified = PublicInvestigationDataset.model_validate(payload)

    with pytest.raises(ValueError, match="must use https"):
        materialize_public_investigation_dataset(
            modified,
            registry,
            public_root=tmp_path / "public",
            fetcher=_fake_fetcher,
        )
