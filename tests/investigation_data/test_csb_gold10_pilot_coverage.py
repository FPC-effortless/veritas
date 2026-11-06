from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "docs" / "investigation_data" / "corpora" / "csb_gold_10"
INDEX_PATH = CORPUS_ROOT / "index.json"
COVERAGE_PATH = CORPUS_ROOT / "pilot_coverage.json"
PILOTS_ROOT = ROOT / "docs" / "investigation_data" / "pilots"
BLOCKED_LINK_ONLY_SUFFIXES = {
    ".avi",
    ".flac",
    ".gz",
    ".jpeg",
    ".jpg",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".tar",
    ".tiff",
    ".wav",
    ".webm",
    ".zip",
}


def load_coverage() -> dict[str, object]:
    return json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))


def load_manifest(pilot_dir: str) -> FusionManifest:
    path = PILOTS_ROOT / pilot_dir / "manifest.json"
    return FusionManifest.model_validate_json(path.read_text(encoding="utf-8"))


def test_gold10_registry_exactly_covers_canonical_index() -> None:
    index = load_fusion_corpus(INDEX_PATH)
    coverage = load_coverage()
    entries = coverage["pilots"]
    assert isinstance(entries, list)

    registered_case_ids = {entry["case_id"] for entry in entries}
    registered_pilot_dirs = [entry["pilot_dir"] for entry in entries]
    canonical_case_ids = {case.case_id for case in index.cases}

    assert coverage["schema_version"] == "1.0"
    assert coverage["corpus_id"] == index.corpus_id
    assert coverage["coverage_target"] == index.target_cases == 10
    assert len(entries) == index.target_cases
    assert registered_case_ids == canonical_case_ids
    assert len(registered_pilot_dirs) == len(set(registered_pilot_dirs))


def test_gold10_registered_pilots_are_valid_reviewed_and_non_oracular() -> None:
    index = load_fusion_corpus(INDEX_PATH)
    coverage = load_coverage()
    entries = coverage["pilots"]
    assert isinstance(entries, list)

    episode_ids: set[str] = set()
    for entry in entries:
        case_id = entry["case_id"]
        pilot_dir = entry["pilot_dir"]
        assert isinstance(case_id, str)
        assert isinstance(pilot_dir, str)

        pilot_root = PILOTS_ROOT / pilot_dir
        manifest_path = pilot_root / "manifest.json"
        review_path = pilot_root / "review_record.json"
        assert manifest_path.is_file()
        assert review_path.is_file()

        manifest = load_manifest(pilot_dir)
        review = json.loads(review_path.read_text(encoding="utf-8"))
        canonical_source_case_id = f"CSB-{case_id}"

        assert canonical_source_case_id in manifest.source_case_ids
        assert review["case_id"] == canonical_source_case_id
        assert review["source_id"] == index.source_id == "uscsb"
        assert review["status"] == "approved_for_link_only_pilot"
        assert manifest.ground_truth_claims == ()
        assert manifest.episode_id not in episode_ids
        episode_ids.add(manifest.episode_id)

        review_id = review["review_id"]
        for fragment in manifest.fragments:
            assert fragment.source_id == index.source_id
            assert fragment.epistemic_role.value != "private_truth"
            assert fragment.rights_review_id == review_id
            assert not urlparse(fragment.locator).path.lower().endswith(".pdf")


def test_gold10_link_only_pilots_do_not_check_in_source_artifact_bytes() -> None:
    coverage = load_coverage()
    entries = coverage["pilots"]
    assert isinstance(entries, list)

    for entry in entries:
        pilot_dir = entry["pilot_dir"]
        assert isinstance(pilot_dir, str)
        pilot_root = PILOTS_ROOT / pilot_dir
        blocked = {
            path.relative_to(pilot_root).as_posix()
            for path in pilot_root.rglob("*")
            if path.is_file() and path.suffix.lower() in BLOCKED_LINK_ONLY_SUFFIXES
        }
        assert not blocked, f"link-only pilot contains source artifact bytes: {blocked}"
