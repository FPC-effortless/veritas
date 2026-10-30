"""Offline, constructed-only Forge developer quickstart. No model or source qualification."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from forge_data.core import normalize, point_in_time, release, verify_release
from forge_data.evidence_receipt import validate_evidence


def run_demo() -> dict:
    # Synthetic integration fixture ONLY. These declarations do not establish real rights.
    spec = {
        "dataset_id": "constructed-quickstart-not-real",
        "source_id": "fixture/operations",
        "source_version": "constructed-v1",
        "adapter": "operations-jsonl",
        "license_id": "fixture-only-not-a-publisher-license",
        "provenance_uri": "https://example.invalid/constructed",
        "ai_use_allowed": True,
        "redistribution_allowed": True,
        "privacy_reviewed": True,
        "split_salt": "constructed-quickstart-frozen-v1",
    }
    rows = [
        {
            "episode_id": f"episode-{i}",
            "subject_id": f"machine-{i}",
            "record_id": f"record-{i}",
            "observed_at": "2026-01-01T10:00:00Z",
            "available_at": "2026-01-01T10:00:01Z",
            "observation": {"temperature_c": 30 + i},
            "action": {
                "performed_at": "2026-01-01T10:02:00Z",
                "available_at": "2026-01-01T10:02:30Z",
                "payload": {"type": "inspect"},
            },
            "outcome": {"status": "unknown", "verified": False},
        }
        for i in range(12)
    ]
    with tempfile.TemporaryDirectory(prefix="forge-constructed-") as temp:
        root = Path(temp)
        input_path, spec_path, output = root / "input.jsonl", root / "spec.json", root / "release"
        input_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
        release(input_path, spec_path, output)
        verification = verify_release(output)
        assert verification["valid"] is True and verification["records"] == 12
        # Link this ephemeral constructed release to a nonqualifying TrainLab
        # developer receipt; this digest is byte identity, NOT publisher proof.
        template = Path(__file__).with_name("CONSTRUCTED_trainlab_evidence.json")
        receipt = json.loads(template.read_text(encoding="utf-8"))
        receipt["source"]["release_manifest_sha256"] = hashlib.sha256(
            (output / "manifest.json").read_bytes()
        ).hexdigest()
        receipt_result = validate_evidence(receipt)
        assert receipt_result["scientific_qualification"] == "NOT_QUALIFIED"

        seen_subjects: set[str] = set()
        for split in ("train", "validation", "test"):
            subjects = {
                row["subject_id"]
                for line in (output / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
                if (row := json.loads(line))
            }
            assert not (seen_subjects & subjects), "subject leaked across splits"
            seen_subjects.update(subjects)
        assert len(seen_subjects) == 12

        sample = normalize(rows[0], adapter="operations-jsonl", source_id=spec["source_id"])
        assert point_in_time(sample, "2026-01-01T10:00:00Z") is None
        early = point_in_time(sample, "2026-01-01T10:00:01Z")
        assert early is not None and early["action"] is None and early["outcome"] is None
        later = point_in_time(sample, "2026-01-01T10:02:30Z")
        assert later is not None and later["action"] is not None and later["outcome"] is None

    return {
        "demo": "CONSTRUCTED_ONLY",
        "records": 12,
        "subject_split_isolation": "PASS_CONSTRUCTED",
        "point_in_time_masking": "PASS_CONSTRUCTED",
        "rights": "FIXTURE_DECLARATIONS_NOT_VERIFIED",
        "authentic_dataset": "NOT_USED",
        "scientific_qualification": "NOT_PERFORMED",
        "model_training": "NOT_PERFORMED",
        "physical_offline_inference": "NOT_RUN",
        "trainlab_receipt_structural": receipt_result["structural_validation"],
        "trainlab_receipt_science": receipt_result["scientific_qualification"],
        "trainlab_receipt_device": receipt_result["hardware_qualification"],
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), sort_keys=True))
