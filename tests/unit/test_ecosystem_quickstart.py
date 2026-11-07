"""Public constructed ecosystem comparison and evidence falsifiers."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("forge_data")
pytest.importorskip("trainlab")
pytest.importorskip("research_lab")

from research_lab.ecosystem import run, verify
from trainlab.runner import LabError, digest, read_json, write_json


@pytest.fixture
def comparison(tmp_path):
    root = tmp_path / "comparison"
    report = run(root)
    return root, report


def test_full_ecosystem_comparison_is_reverified_and_never_promoted(comparison):
    root, report = comparison
    assert report["source_kind"] == "CONSTRUCTED"
    assert report["promotion"]["decision"] == "NOT_PROMOTED"
    assert report["training"]["status"] == "NOT_PERFORMED"
    assert report["results"]["public_evidence_reference"]["mean_reward"] == 1
    assert report["results"]["projection_trust"]["mean_reward"] == 0
    assert verify(root) == report
    evidence = read_json(root / "evidence.json")
    assert evidence["outcome"] == "OBSERVED"
    assert evidence["artifacts"][0]["content_sha256"] == digest(root / "comparison.json")
    assert "expected_value" not in json.dumps(evidence)
    assert "oracle" not in json.dumps(evidence)
    assert (root / "research_lab/lab.sqlite3").is_file()
    public = (root / "agents/dataset/validation.jsonl").read_text()
    assert '"oracle"' not in public and '"expected_value"' not in public


@pytest.mark.parametrize(
    "target", ["dataset", "oracle", "metrics", "report", "report_bytes", "run_metadata", "runtime"]
)
def test_changed_evidence_is_rejected(comparison, target):
    root, _ = comparison
    if target == "runtime":
        path = root / "agents/protocol.json"
        protocol = read_json(path)
        protocol["runtime"]["source_trees"]["investigation_world"] = "0" * 64
        write_json(path, protocol)
    elif target == "dataset":
        path = root / "agents/dataset/validation.jsonl"
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "oracle":
        path = root / "operator/episodes.json"
        values = read_json(path)
        values[0]["oracle"]["facts"][0]["expected_value"] = "ALTERED"
        write_json(path, values)
    elif target == "report":
        path = root / "comparison.json"
        report = read_json(path)
        report["results"]["projection_trust"]["mean_reward"] = 1
        write_json(path, report)
    elif target == "report_bytes":
        path = root / "comparison.json"
        path.write_text(json.dumps(read_json(path), separators=(",", ":")))
    else:
        directory = next((root / "runs").iterdir())
        path = directory / ("output/metrics.json" if target == "metrics" else "run.json")
        record = read_json(path)
        if target == "metrics":
            record["submission_count"] = 999
        else:
            record["budget"]["agent_invocations"] += 1
        write_json(path, record)
    with pytest.raises((LabError, ValueError)):
        verify(root)


def test_demo_refuses_overwrite(comparison):
    root, _ = comparison
    with pytest.raises((LabError, ValueError)):
        run(root)


def test_broken_verifier_controls_are_rejected(comparison, monkeypatch):
    from investigation_world.companyworld import verifier

    root, _ = comparison
    original = verifier.verify_companyworld

    def broken(*args, **kwargs):
        return original(*args, **kwargs).model_copy(update={"overall_reward": 1.0})

    monkeypatch.setattr(verifier, "verify_companyworld", broken)
    with pytest.raises((LabError, ValueError), match="control"):
        verify(root)


def test_raw_oracle_in_agent_payload_is_rejected(comparison, monkeypatch):
    from forge_data.dataset import Dataset

    root, _ = comparison
    original = Dataset.examples

    def leaked(self, *args, **kwargs):
        rows = original(self, *args, **kwargs)
        rows[0]["features"]["episode"]["oracle"] = {"fixture_marker": "MUST_NOT_REACH_AGENT"}
        return rows

    monkeypatch.setattr(Dataset, "examples", leaked)
    with pytest.raises((LabError, ValueError), match="public episode"):
        verify(root)
