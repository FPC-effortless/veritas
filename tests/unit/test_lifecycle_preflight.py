"""Invented preflight controls; no model or causal-diversity evidence."""
import copy
import json
import sys

import pytest

pytest.importorskip("forge_data")
pytest.importorskip("research_lab")
from forge_data.core import canonical, release
from forge_data.dataset import Dataset
from research_lab import lifecycle_preflight as gate
from research_lab.ecosystem import _sha
from trainlab.runner import LabError, digest, read_json, write_json

CUTOFF = "2026-11-13T00:00:00Z"
DRIVER = '''import json, os
from pathlib import Path
out = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
(out / "sentinel.txt").write_text("executed")
(out / "metrics.json").write_text(json.dumps({"sentinel": 1}))
'''


def make_source(root, *, observed=True, fail=False):
    root.mkdir()
    pairs, rows = [], []
    for group in range(300):
        for stratum in ("overwrite", "delete_recreate"):
            ids = []
            for op in ("copy", "link"):
                rid = f"r-{group}-{stratum}-{op}"
                ids.append(rid)
                events = [{"op": "set", "key": "a", "value": "old"},
                          {"op": op, "key": "f", "source": "a"}]
                if stratum == "delete_recreate":
                    events.append({"op": "delete", "key": "a"})
                    if observed:
                        events.append({"op": "copy", "key": "q", "source": "f"})
                events.append({"op": "set", "key": "a", "value": "new"})
                memory = {"schema": "woyengi.lifecycle.v1", "keys": ["a", "f", "q"],
                          "composed_keys": ["f", "q"], "events": events}
                rows.append({"episode_id": rid, "subject_id": f"group-{group}",
                             "record_id": rid, "observed_at": CUTOFF, "available_at": CUTOFF,
                             "observation": {"memory": memory}, "action": None,
                             "outcome": {"status": "unknown", "verified": False}})
            pairs.append({"records": ids, "stratum": stratum})
    write_json(root / "source.json", {
        "dataset_id": "invented-gate-test", "source_id": "fixture/preflight",
        "source_version": "1", "adapter": "operations-jsonl", "license_id": "Apache-2.0",
        "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/515",
        "ai_use_allowed": True, "redistribution_allowed": True, "privacy_reviewed": True,
        "split_salt": "fixed-preflight-software-control",
    })
    (root / "source.jsonl").write_bytes(b"".join(canonical(r) for r in rows))
    release(root / "source.jsonl", root / "source.json", root / "dataset")
    pin = digest(root / "dataset/manifest.json")
    data = Dataset(root / "dataset", manifest_sha256=pin)
    selected = {r["record_id"] for split in ("train", "validation") for r in
                data.examples(split, cutoff=CUTOFF, feature_fields=["memory"])}
    write_json(root / "pairs.json", [p for p in pairs if p["records"][0] in selected])
    (root / "design.md").write_text("Invented duplicate mechanics; no causal diversity claim.")
    (root / "driver.py").write_text("raise SystemExit(7)" if fail else DRIVER)
    write_json(root / "recipe.json", {
        "schema": "trainlab.experiment.v2", "name": "sentinel", "description": "No model fit",
        "command": [sys.executable, "driver.py"], "seed": 1, "timeout_seconds": 10,
        "source_kind": "CONSTRUCTED", "split_identity": pin,
        "inputs": ["driver.py", "design.md", "pairs.json"] + ["dataset/" + n for n in
                   ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")],
        "artifacts": ["sentinel.txt"], "metrics": {"sentinel": "max"},
        "budget": {"model_fits": 0}, "workload": {"kind": "test", "training_method": None,
                                                "execution": "single_process"}, "checks": {},
    })
    write_json(root / "spec.json", {
        "schema": "veritas.lifecycle-preflight.v1", "dataset": "dataset",
        "manifest_sha256": pin, "cutoff": CUTOFF, "pairs": "pairs.json",
        "recipe": "recipe.json", "design": "design.md", "minimum_groups": 30,
    })


@pytest.fixture
def prepared(tmp_path):
    source, root = tmp_path / "source", tmp_path / "campaign"
    make_source(source)
    pin = gate.prepare(source / "spec.json", root)["protocol_sha256"]
    return source, root, pin


def review(root, pin, report):
    path = root.parent / "review.json"
    write_json(path, {"schema": "veritas.lifecycle-preflight-review.v1",
                      "protocol_sha256": pin, "report_sha256": _sha(report),
                      "verdict": "clean", "findings": [],
                      "independence": "SEPARATE_SESSION_OPERATOR_ASSERTED",
                      "reviewer": "invented-test-reviewer", "summary": "Software fixture only."})
    return path, digest(path)


def test_positive_reviewed_sentinel_and_once_only_dispatch(prepared):
    _, root, pin = prepared
    report = gate.record(root, pin)
    assert report["status"] == "READY_FOR_REVIEW"
    assert report["scientific_qualification"] == "NOT_QUALIFIED"
    assert report["counts"]["validation"]["delete_recreate"]["preserved_groups"] == 30
    path, review_pin = review(root, pin, report)
    assert gate.dispatch(root, pin, path, review_pin)["status"] == "succeeded"
    assert len(list((root / "execution/runs").glob("*/run.json"))) == 1
    assert (root / "research_lab/lab.sqlite3").exists()
    assert gate.verify(root, pin) == report
    with pytest.raises(LabError, match="attempt already reserved"):
        gate.dispatch(root, pin, path, review_pin)


def test_unobserved_deletion_is_retained_and_never_dispatched(tmp_path, monkeypatch):
    source, root = tmp_path / "source", tmp_path / "campaign"
    make_source(source, observed=False)
    pin = gate.prepare(source / "spec.json", root)["protocol_sha256"]
    report = gate.record(root, pin)
    assert report["status"] == "BLOCKED"
    assert report["counts"]["validation"]["delete_recreate"]["sensitive_pairs"] == 0
    assert any(r["code"] == "INSUFFICIENT_PRESERVED_ABSENCE_GROUPS" for r in report["reasons"])
    path, review_pin = review(root, pin, report)
    monkeypatch.setattr(gate, "run_experiment", lambda *a: pytest.fail("must not execute"))
    with pytest.raises(LabError, match="preflight blocked"):
        gate.dispatch(root, pin, path, review_pin)
    assert not (root / "execution").exists()
    assert gate.verify(root, pin) == report


@pytest.mark.parametrize("change", ["omit", "duplicate", "stratum", "split", "cross_group"])
def test_pair_inventory_failures_block(prepared, change):
    source, root, _ = prepared
    pairs = read_json(source / "pairs.json")
    if change == "omit":
        pairs.pop()
    elif change == "duplicate":
        pairs.append(copy.deepcopy(pairs[0]))
    elif change == "stratum":
        pairs[0]["stratum"] = "delete_recreate"
    else:
        data = Dataset(source / "dataset", manifest_sha256=digest(source / "dataset/manifest.json"))
        val = {r["record_id"] for r in data.examples(
            "validation", cutoff=CUTOFF, feature_fields=["memory"])}
        first = next(p for p in pairs if p["records"][0] not in val)
        second = next(p for p in pairs if p["records"][0].split("-")[1]
                      != first["records"][0].split("-")[1]
                      and (p["records"][0] in val) == (change == "split"))
        first["records"][1], second["records"][1] = second["records"][1], first["records"][1]
    write_json(source / "pairs.json", pairs)
    invalid = root.with_name("invalid")
    pin = gate.prepare(source / "spec.json", invalid)["protocol_sha256"]
    with pytest.raises((LabError, ValueError)):
        gate.record(invalid, pin)


@pytest.mark.parametrize("target", [
    "input", "protocol", "report", "review", "review_pin", "runtime"
])
def test_stale_or_forged_evidence_never_executes(prepared, target, monkeypatch):
    _, root, pin = prepared
    report = gate.record(root, pin)
    path, review_pin = review(root, pin, report)
    if target == "input":
        (root / "inputs/driver.py").write_text("changed")
    elif target == "protocol":
        p = read_json(root / "protocol.json")
        p["spec"]["minimum_groups"] = 1
        write_json(root / "protocol.json", p)
    elif target == "report":
        p = copy.deepcopy(report)
        p["counts"]["validation"]["delete_recreate"]["pairs"] = 9000
        write_json(root / "preflight.json", p)
    elif target == "review":
        p = read_json(path)
        p["report_sha256"] = "0" * 64
        write_json(path, p)
        review_pin = digest(path)
    elif target == "review_pin":
        review_pin = "0" * 64
    else:
        monkeypatch.setattr(gate, "_runtime", lambda: {"changed": True})
    monkeypatch.setattr(gate, "run_experiment", lambda *a: pytest.fail("must not execute"))
    with pytest.raises((LabError, ValueError)):
        gate.dispatch(root, pin, path, review_pin)
    assert not (root / "execution").exists()


def test_missing_review_and_interrupted_reservation(prepared):
    _, root, pin = prepared
    report = gate.record(root, pin)
    with pytest.raises((OSError, LabError)):
        gate.dispatch(root, pin, root / "missing.json", "0" * 64)
    path, review_pin = review(root, pin, report)
    (root / "execution").mkdir()
    with pytest.raises(LabError, match="attempt already reserved"):
        gate.dispatch(root, pin, path, review_pin)


def test_failure_is_retained_without_retry(tmp_path):
    source, root = tmp_path / "source", tmp_path / "campaign"
    make_source(source, fail=True)
    pin = gate.prepare(source / "spec.json", root)["protocol_sha256"]
    report = gate.record(root, pin)
    path, review_pin = review(root, pin, report)
    assert gate.dispatch(root, pin, path, review_pin)["status"] == "failed"
    with pytest.raises(LabError, match="attempt already reserved"):
        gate.dispatch(root, pin, path, review_pin)


def test_cannot_weaken_floor_or_select_test(prepared):
    source, root, _ = prepared
    spec = read_json(source / "spec.json")
    for modified in (dict(spec, minimum_groups=1), dict(spec, split="test")):
        write_json(source / "spec.json", modified)
        with pytest.raises((LabError, ValueError)):
            gate.prepare(source / "spec.json", root.with_name("invalid"))


@pytest.mark.parametrize("field,value", [
    ("verdict", "blocking"), ("findings", ["unresolved"]), ("summary", " "),
    ("independence", "SAME_SESSION"), ("protocol_sha256", "0" * 64),
])
def test_review_requires_complete_clean_bound_decision(prepared, field, value):
    _, root, pin = prepared
    report = gate.record(root, pin)
    path, _ = review(root, pin, report)
    decision = read_json(path)
    decision[field] = value
    write_json(path, decision)
    with pytest.raises(LabError):
        gate.dispatch(root, pin, path, digest(path))
    assert not (root / "execution").exists()


def test_exact_external_review_bytes_are_retained(prepared):
    _, root, pin = prepared
    path, _ = review(root, pin, gate.record(root, pin))
    compact = json.dumps(read_json(path), separators=(",", ":")).encode()
    path.write_bytes(compact)
    review_pin = digest(path)
    assert gate.dispatch(root, pin, path, review_pin)["status"] == "succeeded"
    assert (root / "execution/review.json").read_bytes() == compact
    assert digest(root / "execution/review.json") == review_pin


@pytest.mark.parametrize("status,code", [
    ("succeeded", 0), ("failed", 1), ("timed_out", 1), ("interrupted", 1), ("unknown", 1),
])
def test_cli_only_successful_dispatch_exits_zero(monkeypatch, status, code):
    monkeypatch.setattr(sys, "argv", ["gate", "dispatch", "unused", "--protocol-sha256", "x",
                                     "--review", "unused", "--review-sha256", "y"])
    monkeypatch.setattr(gate, "dispatch", lambda *args: {"status": status})
    assert gate.main() == code
