from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from investigation_world.foundry.public_investigation_corpus import (
    compile_structured_investigation_corpus,
    load_structured_source_profile,
    write_structured_investigation_corpus,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "datasets/public_investigations/profiles/cdc_nors_v1.json"
FIXTURE_PATH = REPO_ROOT / "tests/unit/fixtures/nors_sample.csv"


def test_nors_profile_separates_public_evidence_from_verifier(tmp_path: Path) -> None:
    profile = load_structured_source_profile(PROFILE_PATH)
    corpus = compile_structured_investigation_corpus(
        profile,
        FIXTURE_PATH,
        dataset_id="nors-test-v1",
        version="1.0.0",
        as_of=date(2026, 8, 28),
    )

    assert len(corpus.cases) == 2
    public = corpus.cases[0].public_projection()
    verifier = corpus.cases[0].verifier_projection()
    assert public["evidence"]["state"] == "Wisconsin"
    assert "etiology" not in public["evidence"]
    assert verifier["verifier"]["etiology"] == "Norovirus"
    assert verifier["verifier"]["food_contaminated_ingredient"] == "Lettuce"

    result = write_structured_investigation_corpus(
        corpus,
        profile,
        public_output=tmp_path / "public.jsonl",
        verifier_output=tmp_path / "sealed/verifier.jsonl",
        manifest_output=tmp_path / "manifest.json",
    )
    public_text = (tmp_path / "public.jsonl").read_text(encoding="utf-8")
    verifier_text = (tmp_path / "sealed/verifier.jsonl").read_text(encoding="utf-8")
    assert "Norovirus" not in public_text
    assert "Lettuce" not in public_text
    assert "Norovirus" in verifier_text
    assert result.public_hash == corpus.public_hash()
    assert result.verifier_hash == corpus.verifier_hash()


def test_structured_compiler_rejects_unclassified_columns(tmp_path: Path) -> None:
    profile = load_structured_source_profile(PROFILE_PATH)
    rows = list(csv.DictReader(FIXTURE_PATH.read_text(encoding="utf-8").splitlines()))
    rows[0]["Unreviewed Outcome"] = "must not leak"
    path = tmp_path / "extra-column.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="unclassified fields"):
        compile_structured_investigation_corpus(
            profile,
            path,
            dataset_id="nors-invalid-v1",
            version="1.0.0",
            as_of=date(2026, 8, 28),
        )


def test_structured_case_identity_does_not_depend_on_hidden_label(tmp_path: Path) -> None:
    profile = load_structured_source_profile(PROFILE_PATH)
    original = compile_structured_investigation_corpus(
        profile,
        FIXTURE_PATH,
        dataset_id="nors-test-v1",
        version="1.0.0",
        as_of=date(2026, 8, 28),
    )
    rows = list(csv.DictReader(FIXTURE_PATH.read_text(encoding="utf-8").splitlines()))
    rows[0]["Etiology"] = "Different hidden label"
    path = tmp_path / "changed-label.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    changed = compile_structured_investigation_corpus(
        profile,
        path,
        dataset_id="nors-test-v1",
        version="1.0.0",
        as_of=date(2026, 8, 28),
    )

    assert original.cases[0].case_id == changed.cases[0].case_id
    assert original.public_hash() == changed.public_hash()
    assert original.verifier_hash() != changed.verifier_hash()


def test_written_public_manifest_contains_no_verifier_values(tmp_path: Path) -> None:
    profile = load_structured_source_profile(PROFILE_PATH)
    corpus = compile_structured_investigation_corpus(
        profile,
        FIXTURE_PATH,
        dataset_id="nors-test-v1",
        version="1.0.0",
        as_of=date(2026, 8, 28),
    )
    write_structured_investigation_corpus(
        corpus,
        profile,
        public_output=tmp_path / "public.jsonl",
        verifier_output=tmp_path / "private/verifier.jsonl",
        manifest_output=tmp_path / "manifest.json",
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["audit"]["passed"] is True
    assert manifest["audit"]["duplicate_case_ids"] == 0
    assert "Norovirus" not in json.dumps(manifest, sort_keys=True)
