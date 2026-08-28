from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location("agent_roadmap", ROOT / "tools/roadmap/agent_roadmap.py")
assert SPEC and SPEC.loader
roadmap = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(roadmap)


def row(wid: str, issue: int, *, state: str = "READY", deps=None, hard=None, path=None, aliases=None):
    return {"work_id": wid, "aliases": aliases or [], "issue": issue, "title": wid, "state": state, "dependencies": deps or [], "hard_dependencies": hard or [], "external_issue_dependencies": [], "dependency_summary": "test", "branch": f"test/{wid.lower()}", "linked_pr": None, "claimant": None, "ownership": {"positive_summary": path or "tests/**", "negative_summary": "unrelated", "exclusive_paths": [path] if path else []}, "program": "test", "wave": "UNASSIGNED", "strategic_rank": None, "critical_path": False}


def manifest(*rows):
    return {"schema_version": roadmap.SCHEMA, "repository": "FPC-effortless/veritas", "source_commit": "0" * 40, "state_authority": {"execution": "test", "qualification": "not_authoritative"}, "work": list(rows)}


def test_checked_in_manifest_validates():
    assert roadmap.validate(roadmap.load(ROOT / ".github/agent-roadmap.yml")) == []


def test_duplicate_work_id_and_alias_fail_closed():
    errors = roadmap.validate(manifest(row("A", 1, aliases=["B"]), row("B", 2)))
    assert any("duplicate Work ID/alias" in error for error in errors)


def test_cycle_and_missing_dependency_fail_closed():
    assert any("dependency cycle:" in e for e in roadmap.validate(manifest(row("A", 1, deps=["B"]), row("B", 2, deps=["A"]))))
    assert "A: missing roadmap dependency MISSING" in roadmap.validate(manifest(row("A", 1, deps=["MISSING"])))


def test_direct_active_path_collision_fails_closed():
    errors = roadmap.validate(manifest(row("A", 1, path="src/x/**"), row("B", 2, state="CLAIMED", path="src/x/**")))
    assert "direct ownership collision on src/x/**: A and B" in errors


def test_done_path_may_be_reused():
    assert roadmap.validate(manifest(row("OLD", 1, state="DONE", path="src/x/**"), row("NEW", 2, path="src/x/**"))) == []


def test_unfinished_hard_dependency_blocks_active_item():
    errors = roadmap.validate(manifest(row("P", 1, state="BLOCKED"), row("C", 2, deps=["P"], hard=["P"])))
    assert any("C: active while hard dependency P is BLOCKED" == e for e in errors)


def test_done_history_does_not_reopen():
    assert roadmap.validate(manifest(row("P", 1, state="BLOCKED"), row("H", 2, state="DONE", deps=["P"], hard=["P"]))) == []


def test_contract_parser_keeps_alias_paths_and_refs():
    body = """<!-- veritas-agent-work -->\n- **Work ID:** A / OLD-A\n- **State:** BLOCKED\n- **Dependencies:** #151 and #65\n- **Branch:** `feat/a`\n- **Positive ownership:** `src/a/**`\n- **Negative ownership:** root files\n- **Claim holder:** none\n- **Linked PR:** #246\n"""
    parsed = roadmap.parse_contract(body, 9)
    assert parsed["work_id"] == "A" and parsed["aliases"] == ["OLD-A"]
    assert parsed["refs"] == [151, 65] and parsed["paths"] == ["src/a/**"] and parsed["linked_pr"] == 246


def test_sync_uses_live_labels_and_preserves_curated_edges(monkeypatch: pytest.MonkeyPatch):
    current = manifest(row("A", 1, state="BLOCKED"), row("B", 2, state="BLOCKED", deps=["A"], hard=["A"]))
    current["work"][0].update(program="quality", strategic_rank=2, critical_path=True)
    issues = [
        {"number": 1, "title": "A", "labels": [{"name": "agent-work"}, {"name": "work:done"}], "body": "<!-- veritas-agent-work -->\n- **Work ID:** A\n- **State:** READY\n- **Dependencies:** none\n- **Branch:** `feat/a`\n- **Positive ownership:** `src/a/**`\n- **Negative ownership:** other\n- **Claim holder:** none\n- **Linked PR:** none\n"},
        {"number": 2, "title": "B", "labels": [{"name": "agent-work"}, {"name": "work:ready"}], "body": "<!-- veritas-agent-work -->\n- **Work ID:** B\n- **State:** BLOCKED\n- **Dependencies:** #1\n- **Branch:** `feat/b`\n- **Positive ownership:** `src/b/**`\n- **Negative ownership:** other\n- **Claim holder:** none\n- **Linked PR:** none\n"},
    ]
    monkeypatch.setattr(roadmap, "fetch_issues", lambda *_: issues)
    synced = roadmap.sync(current, "FPC-effortless/veritas", None); by_id = {x["work_id"]: x for x in synced["work"]}
    assert by_id["A"]["state"] == "DONE" and by_id["A"]["program"] == "quality" and by_id["A"]["strategic_rank"] == 2
    assert by_id["B"]["state"] == "READY" and by_id["B"]["hard_dependencies"] == ["A"]
