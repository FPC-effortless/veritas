"""Constructed software controls: real ecosystem APIs, no neural-model fits."""

from __future__ import annotations

import copy
import sys

import pytest

from investigation_world.benchmark.memory_comparison import score, state

forge = pytest.importorskip("forge_data.core")
runner = pytest.importorskip("trainlab.runner")
campaign = pytest.importorskip("research_lab.memory_campaign")
canonical, release = forge.canonical, forge.release
LabError, digest, read_json, write_json = (
    runner.LabError, runner.digest, runner.read_json, runner.write_json
)
assess, prepare, run, verify = campaign.assess, campaign.prepare, campaign.run, campaign.verify

CUTOFF = "2026-01-01T00:00:00Z"
MEMORY = {
    "keys": ["a", "b", "c", "d"],
    "events": [
        {"op": "set", "key": "a", "value": "old"},
        {"op": "set", "key": "b", "value": "keep"},
        {"op": "set", "key": "c", "value": "gone"},
        {"op": "set", "key": "a", "value": "new"},
        {"op": "delete", "key": "c"},
    ],
}

# Intentionally independent of the Veritas replay implementation.
DRIVER = '''
import json
import os
import sys
from pathlib import Path
from forge_data.dataset import Dataset
from trainlab.runner import digest
if sys.argv[1] == "fail":
    raise SystemExit(7)
data = Dataset(Path("dataset"), manifest_sha256=digest(Path("dataset/manifest.json")))
rows = data.examples("validation", cutoff="2026-01-01T00:00:00Z", feature_fields=["memory"])
predictions = {}
for row in rows:
    answer = dict.fromkeys(row["features"]["memory"]["keys"])
    for event in row["features"]["memory"]["events"]:
        key = event["key"]
        if sys.argv[1] == "stale":
            if event["op"] == "set" and answer[key] is None:
                answer[key] = event["value"]
        elif event["op"] == "delete":
            answer[key] = None
        else:
            answer[key] = event["value"]
    predictions[row["record_id"]] = answer
output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
(output / "memory_predictions.json").write_text(json.dumps({"predictions": predictions}))
# This metric is deliberately wrong; the campaign must independently rescore.
(output / "metrics.json").write_text(json.dumps({"reported_accuracy": 0.123}))
'''


@pytest.fixture
def prepared(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    spec = {
        "dataset_id": "memory-software-control", "source_id": "fixture/memory",
        "source_version": "v1", "adapter": "operations-jsonl",
        "license_id": "Apache-2.0", "provenance_uri": "https://github.com/FPC-effortless/veritas",
        "ai_use_allowed": True, "redistribution_allowed": True, "privacy_reviewed": True,
        "split_salt": "memory-software-control-v1",
    }
    write_json(source / "source.json", spec)
    rows = [
        {
            "episode_id": f"episode-{i}", "subject_id": f"subject-{i}", "record_id": f"row-{i}",
            "observed_at": CUTOFF, "available_at": CUTOFF,
            "observation": {"memory": MEMORY}, "action": None,
            "outcome": {"status": "unknown", "verified": False},
        }
        for i in range(30)
    ]
    (source / "source.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
    release(source / "source.jsonl", source / "source.json", source / "dataset")
    (source / "driver.py").write_text(DRIVER)
    (source / "design.md").write_text("Public scripted controls. No matched model comparison.")
    slots = []
    for arm in ("perfect", "stale", "fail"):
        for seed in (7, 17):
            slot = {"id": f"{arm}-{seed}", "arm": arm, "seed": seed,
                    "recipe": f"{arm}-{seed}.json"}
            slots.append(slot)
            recipe = {
                "schema": "trainlab.experiment.v2", "name": slot["id"],
                "description": "Constructed software control, no training",
                "command": [sys.executable, "driver.py", arm],
                "seed": seed, "timeout_seconds": 20, "source_kind": "CONSTRUCTED",
                "split_identity": digest(source / "dataset/manifest.json"),
                "inputs": ["driver.py", "design.md"] + [
                    "dataset/" + name
                    for name in ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")
                ],
                "artifacts": ["memory_predictions.json"],
                "metrics": {"reported_accuracy": "max"}, "budget": {"model_fits": 0},
                "workload": {"kind": "test", "training_method": None,
                             "execution": "single_process"}, "checks": {},
            }
            write_json(source / slot["recipe"], recipe)
    campaign = {
        "schema": "veritas.memory-campaign.v1", "dataset": "dataset",
        "split": "validation", "cutoff": CUTOFF, "design": "design.md", "slots": slots,
    }
    write_json(source / "campaign.json", campaign)
    root = tmp_path / "campaign"
    pin = prepare(source / "campaign.json", root)["protocol_sha256"]
    return source, root, pin


def test_all_attempts_rescored_and_failed_seeds_retained(prepared, monkeypatch):
    _, root, pin = prepared
    assert all(v["status"] == "MISSING" for v in assess(root, pin)["slots"].values())
    report = run(root, pin)
    assert report["execution"] == "INCOMPLETE"
    for seed in (7, 17):
        positive = report["slots"][f"perfect-{seed}"]["metrics"]
        negative = report["slots"][f"stale-{seed}"]["metrics"]
        assert positive["complete_state_accuracy"]["value"] == 1
        assert positive["current_answer_accuracy"]["value"] == 1
        assert negative["complete_state_accuracy"]["value"] == 0
        assert negative["current_answer_accuracy"]["value"] == 0.5
        assert negative["stale_answer_rate"]["value"] == 1
        assert negative["deletion_accuracy"]["value"] == 0
        assert negative["untouched_fact_accuracy"]["value"] == 0.5
        assert report["slots"][f"fail-{seed}"]["status"] == "FAILED"
    assert report["inference_cost"] == "NOT_MEASURED"
    assert report["scientific_qualification"] == "NOT_QUALIFIED"
    assert (root / "research_lab/lab.sqlite3").is_file()
    assert read_json(root / "evidence.json")["record"]["outcome"] == "OBSERVED"
    monkeypatch.setattr(
        "research_lab.memory_campaign.run_experiment",
        lambda *a, **k: pytest.fail("verification/resume must not execute an existing slot"),
    )
    assert verify(root, pin) == report
    assert run(root, pin) == report


def test_complete_campaign_requires_all_declared_cells(prepared):
    source, root, _ = prepared
    spec = read_json(source / "campaign.json")
    spec["slots"] = [slot for slot in spec["slots"] if slot["arm"] != "fail"]
    write_json(source / "campaign.json", spec)
    root = root.with_name("complete")
    pin = prepare(source / "campaign.json", root)["protocol_sha256"]
    report = run(root, pin)
    assert report["execution"] == "COMPLETE"
    assert report["frontier_qualification"] == "NOT_YET_FRONTIER_QUALIFIED"


@pytest.mark.parametrize("target", ["input", "protocol", "report", "prediction", "metadata"])
def test_tampering_never_retains_a_verified_report(prepared, target):
    _, root, pin = prepared
    run(root, pin)
    if target == "input":
        (root / "inputs/driver.py").write_text("changed")
    elif target == "protocol":
        protocol = read_json(root / "protocol.json")
        protocol["spec"]["slots"].pop()
        write_json(root / "protocol.json", protocol)
    elif target == "report":
        report = read_json(root / "report.json")
        report["execution"] = "COMPLETE"
        write_json(root / "report.json", report)
    else:
        attempt = next((root / "runs/perfect-7").iterdir())
        if target == "prediction":
            write_json(attempt / "output/memory_predictions.json", {"predictions": {}})
        else:
            record = read_json(attempt / "run.json")
            record["budget"]["model_fits"] = 999
            write_json(attempt / "run.json", record)
    with pytest.raises((LabError, ValueError)):
        verify(root, pin)


def test_source_archive_and_seed_grid(prepared):
    source, root, pin = prepared
    (source / "driver.py").write_text("original checkout can change after archival")
    assert assess(root, pin)["execution"] == "INCOMPLETE"
    spec = read_json(source / "campaign.json")
    original = copy.deepcopy(spec)
    spec["slots"].pop()
    write_json(source / "campaign.json", spec)
    with pytest.raises(ValueError, match="seed grid"):
        prepare(source / "campaign.json", root.with_name("uneven"))
    write_json(source / "campaign.json", original)
    with pytest.raises(ValueError, match="must be new"):
        prepare(source / "campaign.json", root)


def test_missing_duplicate_and_unfinished_receipts_are_not_completed(prepared):
    _, root, pin = prepared
    run(root, pin)
    attempt = next((root / "runs/perfect-7").iterdir())
    record = read_json(attempt / "run.json")
    record["status"] = "running"
    write_json(attempt / "run.json", record)
    assert assess(root, pin)["slots"]["perfect-7"]["status"] == "UNFINISHED"
    (root / "runs/stale-7/second-attempt").mkdir()
    assert assess(root, pin)["slots"]["stale-7"]["status"] == "INVALID"
    (root / "runs/undeclared").mkdir()
    assert assess(root, pin)["unexpected_run_directories"] is True


def test_metric_denominators_and_strict_predictions():
    example = {"record_id": "row", "features": {"memory": {"keys": ["a"], "events": []}},
               "target": None}
    metrics = score([example], {"row": {"a": None}})
    assert metrics["stale_answer_rate"] == {"numerator": 0, "denominator": 0, "value": None}
    for predictions in ({}, {"row": {}}, {"row": {"a": False}},
                        {"row": {"a": None}, "extra": {"a": None}}):
        with pytest.raises(ValueError):
            score([example], predictions)
    with pytest.raises(ValueError):
        score([example, example], {"row": {"a": None}})
    future = copy.deepcopy(example)
    future["features"]["memory"]["events"] = [{"op": "set", "key": "a", "value": "later"}]
    assert score([example], {"row": {"a": "later"}})["current_answer_accuracy"]["value"] == 0
    assert score([future], {"row": {"a": "later"}})["current_answer_accuracy"]["value"] == 1


@pytest.mark.parametrize("event", [
    {"op": "set", "key": "a", "value": True},
    {"op": "set", "key": "a", "value": None},
    {"op": "delete", "key": "missing"},
    {"op": "delete", "key": "a", "value": "unexpected"},
])
def test_malformed_events_rejected(event):
    with pytest.raises(ValueError):
        state({"keys": ["a"], "events": [event]})
