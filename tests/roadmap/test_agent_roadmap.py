from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
MODULE_PATH = ROOT / "tools" / "roadmap" / "agent_roadmap.py"
SPEC = importlib.util.spec_from_file_location("agent_roadmap", MODULE_PATH)
assert SPEC and SPEC.loader
roadmap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(roadmap)


def row(
    work_id: str,
    issue: int,
    *,
    state: str = "READY",
    deps: list[str] | None = None,
    hard: list[str] | None = None,
    path: str | None = None,
    aliases: list[str] | None = None,
) -> dict:
    return {
        "work_id": work_id,
        "aliases": aliases or [],
        "issue": issue,
        "title": work_id,
        "state": state,
        "dependencies": deps or [],
        "hard_dependencies": hard or [],
        "external_issue_dependencies": [],
        "dependency_summary": "test",
        "branch": f"test/{work_id.lower()}",
        "linked_pr": None,
        "claimant": None,
        "ownership": {
            "positive_summary": path or "tests/**",
            "negative_summary": "unrelated",
            "exclusive_paths": [path] if path else [],
        },
        "program": "test",
        "wave": "UNASSIGNED",
        "strategic_rank": None,
        "critical_path": False,
    }


def manifest(*rows: dict) -> dict:
    return {
        "schema_version": roadmap.SCHEMA,
        "repository": "FPC-effortless/veritas",
        "source_commit": "0" * 40,
        "state_authority": {
            "execution": "test",
            "qualification": "not_authoritative",
        },
        "work": list(rows),
    }


def issue(
    number: int,
    work_id: str,
    state: str,
    dependencies: str,
    *,
    comments: int = 0,
    path: str | None = None,
) -> dict:
    ownership_path = path or f"src/{work_id.lower()}/**"
    return {
        "number": number,
        "title": work_id,
        "comments": comments,
        "labels": [{"name": "agent-work"}, {"name": f"work:{state.lower()}"}],
        "body": f"""<!-- veritas-agent-work -->
- **Work ID:** {work_id}
- **State:** BLOCKED
- **Dependencies:** {dependencies}
- **Branch:** `feat/{work_id.lower()}`
- **Positive ownership:** `{ownership_path}`
- **Negative ownership:** other
- **Claim holder:** none
- **Linked PR:** none
""",
    }


def status(
    number: int,
    work_id: str,
    state: str,
    *,
    agent: str | None = None,
    branch: str | None = None,
    linked_pr: int | None = None,
) -> dict:
    return {
        "issue_number": number,
        "work_id": work_id,
        "state": state,
        "agent_id": agent,
        "branch": branch,
        "linked_pr": linked_pr,
        "transition_seq": 1,
    }


def test_checked_in_manifest_validates() -> None:
    current = roadmap.load(ROOT / ".github" / "agent-roadmap.yml")
    assert roadmap.validate(current) == []


def test_duplicate_work_id_and_alias_fail_closed() -> None:
    errors = roadmap.validate(
        manifest(row("A", 1, aliases=["B"]), row("B", 2))
    )
    assert any("duplicate Work ID/alias" in error for error in errors)


def test_cycle_and_missing_dependency_fail_closed() -> None:
    cyclic = manifest(
        row("A", 1, deps=["B"]),
        row("B", 2, deps=["A"]),
    )
    assert any("dependency cycle:" in error for error in roadmap.validate(cyclic))

    missing = manifest(row("A", 1, deps=["MISSING"]))
    assert "A: missing roadmap dependency MISSING" in roadmap.validate(missing)


def test_direct_active_path_collision_fails_closed() -> None:
    errors = roadmap.validate(
        manifest(
            row("A", 1, path="src/x/**"),
            row("B", 2, state="CLAIMED", path="src/x/**"),
        )
    )
    assert "direct ownership collision on src/x/**: A and B" in errors


def test_owned_blocked_path_collision_fails_closed() -> None:
    blocked = row("A", 1, state="BLOCKED", path="src/x/**")
    blocked["claimant"] = "agent-a"
    errors = roadmap.validate(manifest(blocked, row("B", 2, path="src/x/**")))
    assert "direct ownership collision on src/x/**: A and B" in errors


def test_done_path_may_be_reused() -> None:
    data = manifest(
        row("OLD", 1, state="DONE", path="src/x/**"),
        row("NEW", 2, path="src/x/**"),
    )
    assert roadmap.validate(data) == []


def test_unfinished_hard_dependency_blocks_active_item() -> None:
    data = manifest(
        row("P", 1, state="BLOCKED"),
        row("C", 2, deps=["P"], hard=["P"]),
    )
    assert "C: active while hard dependency P is BLOCKED" in roadmap.validate(data)


def test_done_history_does_not_reopen() -> None:
    data = manifest(
        row("P", 1, state="BLOCKED"),
        row("H", 2, state="DONE", deps=["P"], hard=["P"]),
    )
    assert roadmap.validate(data) == []


def test_contract_parser_keeps_alias_paths_and_refs() -> None:
    body = """<!-- veritas-agent-work -->
- **Work ID:** A / OLD-A
- **State:** BLOCKED
- **Dependencies:** #151 and #65
- **Branch:** `feat/a`
- **Positive ownership:** `src/a/**`
- **Negative ownership:** root files
- **Claim holder:** none
- **Linked PR:** #246
"""
    parsed = roadmap.parse_contract(body, 9)
    assert parsed["work_id"] == "A"
    assert parsed["aliases"] == ["OLD-A"]
    assert parsed["refs"] == [151, 65]
    assert parsed["paths"] == ["src/a/**"]
    assert parsed["linked_pr"] == 246


def test_sync_uses_live_labels_and_preserves_curated_hard_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = manifest(
        row("A", 1, state="BLOCKED"),
        row("B", 2, state="BLOCKED", deps=["A"], hard=["A"]),
    )
    current["work"][0].update(
        program="quality",
        strategic_rank=2,
        critical_path=True,
    )
    issue_a = issue(1, "A", "DONE", "none")
    issue_b = issue(2, "B", "READY", "A")
    monkeypatch.setattr(roadmap, "fetch_issues", lambda *_: [issue_a, issue_b])

    synced = roadmap.sync(current, "FPC-effortless/veritas", None)
    by_id = {entry["work_id"]: entry for entry in synced["work"]}
    assert by_id["A"]["state"] == "DONE"
    assert by_id["A"]["program"] == "quality"
    assert by_id["A"]["strategic_rank"] == 2
    assert by_id["B"]["state"] == "READY"
    assert by_id["B"]["dependencies"] == ["A"]
    assert by_id["B"]["hard_dependencies"] == ["A"]


def test_sync_removes_dependency_deleted_from_live_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = manifest(
        row("A", 1, state="BLOCKED"),
        row("B", 2, state="BLOCKED", deps=["A"], hard=["A"]),
    )
    issue_a = issue(1, "A", "BLOCKED", "none")
    issue_b = issue(2, "B", "READY", "none")
    monkeypatch.setattr(roadmap, "fetch_issues", lambda *_: [issue_a, issue_b])
    monkeypatch.setattr(roadmap, "status_record", lambda *_: None)

    synced = roadmap.sync(current, "FPC-effortless/veritas", None)
    by_id = {entry["work_id"]: entry for entry in synced["work"]}
    assert by_id["B"]["dependencies"] == []
    assert by_id["B"]["hard_dependencies"] == []
    assert roadmap.validate(synced) == []


def test_sync_resolves_dependency_alias_from_live_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = manifest(
        row("A", 1, state="DONE", aliases=["OLD-A"]),
        row("B", 2, state="BLOCKED"),
    )
    issue_a = issue(1, "A / OLD-A", "DONE", "none")
    issue_b = issue(2, "B", "BLOCKED", "OLD-A")
    monkeypatch.setattr(roadmap, "fetch_issues", lambda *_: [issue_a, issue_b])
    monkeypatch.setattr(roadmap, "status_record", lambda *_: None)

    synced = roadmap.sync(current, "FPC-effortless/veritas", None)
    by_id = {entry["work_id"]: entry for entry in synced["work"]}
    assert by_id["B"]["dependencies"] == ["A"]


def test_sync_rejects_active_issue_without_trusted_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = manifest(row("A", 1, state="CLAIMED"))
    issue_a = issue(1, "A", "CLAIMED", "none")
    monkeypatch.setattr(roadmap, "fetch_issues", lambda *_: [issue_a])
    monkeypatch.setattr(roadmap, "status_record", lambda *_: None)

    with pytest.raises(
        roadmap.RoadmapError,
        match="missing trusted coordination status",
    ):
        roadmap.sync(current, "FPC-effortless/veritas", None)


def test_sync_owned_blocked_status_preserves_holder_and_reserves_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = row("A", 1, state="CLAIMED", path="src/x/**")
    ready = row("B", 2, path="src/x/**")
    current = manifest(blocked, ready)
    issue_a = issue(1, "A", "BLOCKED", "none", comments=1, path="src/x/**")
    issue_b = issue(2, "B", "READY", "none", path="src/x/**")
    monkeypatch.setattr(roadmap, "fetch_issues", lambda *_: [issue_a, issue_b])

    def status_record(_repo: str, number: int, _token: str | None) -> dict | None:
        if number == 1:
            return status(1, "A", "BLOCKED", agent="agent-a", branch="feat/a")
        return None

    monkeypatch.setattr(roadmap, "status_record", status_record)
    with pytest.raises(roadmap.RoadmapError, match="direct ownership collision"):
        roadmap.sync(current, "FPC-effortless/veritas", None)


def test_sync_released_blocked_status_clears_stale_holder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked = row("A", 1, state="BLOCKED")
    blocked["claimant"] = "agent-a"
    blocked["branch"] = "feat/stale-a"
    blocked["linked_pr"] = 99
    current = manifest(blocked)
    issue_a = issue(1, "A", "BLOCKED", "none", comments=1)
    monkeypatch.setattr(roadmap, "fetch_issues", lambda *_: [issue_a])
    monkeypatch.setattr(
        roadmap,
        "status_record",
        lambda *_: status(1, "A", "BLOCKED"),
    )

    synced = roadmap.sync(current, "FPC-effortless/veritas", None)
    entry = synced["work"][0]
    assert entry["claimant"] is None
    assert entry["branch"] == "feat/a"
    assert entry["linked_pr"] is None
