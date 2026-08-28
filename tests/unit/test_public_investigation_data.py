from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from investigation_world.foundry.public_investigation_data import (
    PublicInvestigationDataset,
    load_public_investigation_dataset,
    load_source_registry,
    write_dataset_projections,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "datasets/public_investigations/source_registry.json"
SEED_PATH = REPO_ROOT / "datasets/public_investigations/seeds/seed_v1.json"


def test_seed_registry_and_dataset_validate() -> None:
    registry = load_source_registry(REGISTRY_PATH)
    dataset = load_public_investigation_dataset(SEED_PATH)

    assert len(registry.sources) == 18
    assert len(dataset.cases) == 4
    assert {case.source_id for case in dataset.cases} <= {
        source.source_id for source in registry.sources
    }
    assert all(case.verifier_references for case in dataset.cases)


def test_public_projection_excludes_verifier_references() -> None:
    dataset = load_public_investigation_dataset(SEED_PATH)
    projection = dataset.public_projection()
    serialized = json.dumps(projection, sort_keys=True)

    assert "verifier_references" not in serialized
    assert "RIR2405" not in serialized
    assert "CSBFinalReportBP" not in serialized


def test_public_projection_sanitizes_truth_metadata() -> None:
    dataset = load_public_investigation_dataset(SEED_PATH)
    case = dataset.cases[0].model_copy(
        update={
            "metadata": {
                **dataset.cases[0].metadata,
                "probable_cause": "must remain sealed",
                "nested": {"official_findings": ["sealed"], "safe": "visible"},
            }
        }
    )

    projection = case.public_projection()

    assert "probable_cause" not in projection["metadata"]
    assert "official_findings" not in projection["metadata"]["nested"]
    assert projection["metadata"]["nested"]["safe"] == "visible"


def test_public_projection_sanitizes_artifact_metadata_and_omits_dataset_notes() -> None:
    dataset = load_public_investigation_dataset(SEED_PATH)
    payload = dataset.model_dump(mode="json")
    payload["notes"] = ["probable cause: must not reach the public projection"]
    payload["cases"][0]["public_evidence"][0]["metadata"] = {
        "probable_cause": "must remain sealed",
        "safe": "visible",
    }
    modified = PublicInvestigationDataset.model_validate(payload)

    projection = modified.public_projection()
    artifact_metadata = projection["cases"][0]["public_evidence"][0]["metadata"]

    assert "notes" not in projection
    assert "probable_cause" not in artifact_metadata
    assert artifact_metadata["safe"] == "visible"


def test_projection_hash_is_deterministic() -> None:
    dataset = load_public_investigation_dataset(SEED_PATH)

    public_hash = dataset.public_projection()["content_hash"]
    verifier_hash = dataset.verifier_projection()["content_hash"]

    assert public_hash == dataset.public_projection()["content_hash"]
    assert verifier_hash == dataset.verifier_projection()["content_hash"]


def test_invalid_public_verifier_overlap_rejected() -> None:
    dataset = load_public_investigation_dataset(SEED_PATH)
    payload = dataset.model_dump(mode="json")
    payload["cases"][0]["verifier_references"][0] = {
        **payload["cases"][0]["public_evidence"][0],
        "role": "verifier_reference",
    }

    with pytest.raises(ValidationError, match="public/verifier artifact overlap"):
        PublicInvestigationDataset.model_validate(payload)


def test_writer_does_not_emit_verifier_file_by_default(tmp_path: Path) -> None:
    dataset = load_public_investigation_dataset(SEED_PATH)
    public_output = tmp_path / "public.json"
    verifier_output = tmp_path / "verifier.json"

    result = write_dataset_projections(dataset, public_output=public_output)

    assert public_output.exists()
    assert not verifier_output.exists()
    assert result["verifier_output"] is None
    assert result["verifier_hash"] is None
