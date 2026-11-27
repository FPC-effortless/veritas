from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from investigation_world.authoring.woyengi_work import (
    EVIDENCE_ID,
    WORK_ID,
    WoyengiWorkTask,
    build_woyengi_work_environment,
)
from investigation_world.operational import EpisodeSubmission, OperationalRuntime
from investigation_world.operational.cli import app

CALLS = [
    ("resume_work", {"work_id": WORK_ID, "checkpoint": "checkpoint-001"}),
    ("verify_artifact", {"work_id": WORK_ID}),
    ("close_work", {"work_id": WORK_ID}),
]
SUBMISSION = {
    "conclusion": "Resumed from the handoff, verified the artifact, and closed work.",
    "claimed_state": {f"{WORK_ID}.phase": "closed"},
    "evidence_ids": [EVIDENCE_ID],
    "confidence": 1.0,
}


def test_work_requires_checkpoint_and_verification():
    runtime = OperationalRuntime(build_woyengi_work_environment())
    for name, args in (
        ("close_work", {"work_id": WORK_ID}),
        ("verify_artifact", {"work_id": WORK_ID}),
        ("resume_work", {"work_id": WORK_ID, "checkpoint": "old"}),
    ):
        assert runtime.act(name, **args)["accepted"] is False
        assert runtime.state_snapshot()[f"{WORK_ID}.phase"] == "paused"
    assert runtime.act(CALLS[0][0], **CALLS[0][1])["accepted"] is True
    assert runtime.act("close_work", work_id=WORK_ID)["accepted"] is False
    assert runtime.state_snapshot()[f"{WORK_ID}.phase"] == "resumed"


def test_work_completion_without_evidence_is_not_perfect():
    runtime = OperationalRuntime(build_woyengi_work_environment())
    for name, args in CALLS:
        assert runtime.act(name, **args)["accepted"] is True
    assert runtime.submit(EpisodeSubmission(**(SUBMISSION | {"evidence_ids": []}))).overall_reward < 1


def test_veritas_cli_can_build_validate_and_run_woyengi_work(tmp_path):
    runner = CliRunner()
    private = tmp_path / "work-contract.json"
    public = tmp_path / "work-public.json"
    vector = tmp_path / "work-vector.json"
    vector.write_text(json.dumps({"actions": [
        *({"kind": "action", "name": name, "arguments": args} for name, args in CALLS),
        {"kind": "operation", "name": "submit", "arguments": SUBMISSION},
    ]}))
    build_args = [
        "env", "woyengi-work", "--output", str(private), "--public-output", str(public),
    ]
    result = runner.invoke(app, build_args)
    assert result.exit_code == 0, result.output
    assert b"woyengi-work" in public.read_bytes()
    assert b'"target_assertions"' not in public.read_bytes()
    assert b'"target_assertions"' in private.read_bytes()
    assert runner.invoke(app, build_args).exit_code != 0  # Never overwrite outputs.
    check = runner.invoke(app, ["env", "validate", "--contract", str(private)])
    assert check.exit_code == 0, check.output
    run = runner.invoke(app, ["env", "run", "--contract", str(private), "--vector", str(vector)])
    assert run.exit_code == 0, run.output
    steps = json.loads(run.output)["steps"]
    assert steps[-1]["reward"] == 1.0
    assert steps[-1]["terminated"]




@pytest.mark.parametrize(
    "slug,first,final,wrong,phase,field,value,evidence",
    [
        (
            "approval", ("verify_approval", {"decision_id": "decision-R7"}),
            ("release_report", {"report_id": "R7", "audience": "internal"}),
            ("release_report", {"report_id": "R7", "audience": "external"}),
            "released", "released_to", "internal", ["request-R7", "decision-R7"],
        ),
        (
            "reconciliation",
            ("compare_records", {"summary_id": "summary-12", "source_id": "ledger-14"}),
            ("correct_summary", {"summary_id": "summary-12", "count": "14"}),
            ("correct_summary", {"summary_id": "summary-12", "count": "12"}),
            "reconciled", "summary_count", 14, ["summary-12", "ledger-14"],
        ),
        (
            "revision",
            ("mark_superseded", {"previous_id": "brief-r1", "replacement_id": "brief-r2"}),
            ("refresh_index", {"index_id": "brief-index", "revision_id": "brief-r2"}),
            ("refresh_index", {"index_id": "brief-index", "revision_id": "brief-r1"}),
            "updated", "indexed_revision", "r2", ["brief-r1", "brief-r2"],
        ),
        (
            "escalation", ("check_review_status", {"record_id": "review-status"}),
            ("escalate_work", {"reason": "approval_pending", "recipient": "supervisor"}),
            ("close_work", {"work_id": WORK_ID}),
            "escalated", "assigned_reviewer", "supervisor", ["work-request", "review-status"],
        ),
    ],
)
def test_selectable_work_tasks(tmp_path, slug, first, final, wrong, phase, field, value, evidence):
    episode = build_woyengi_work_environment(slug)
    runtime = OperationalRuntime(episode)
    prior = runtime.state_snapshot()
    assert runtime.act(final[0], **final[1])["accepted"] is False
    assert runtime.state_snapshot() == prior
    assert runtime.act(first[0], **first[1])["accepted"] is True
    prior = runtime.state_snapshot()
    assert runtime.act(wrong[0], **wrong[1])["accepted"] is False
    assert runtime.state_snapshot() == prior
    assert runtime.act(final[0], **final[1])["accepted"] is True
    assert runtime.act(final[0], **final[1])["accepted"] is False
    assert runtime.state_snapshot()[f"{WORK_ID}.{field}"] == value

    runner = CliRunner()
    private = tmp_path / "contract.json"
    public = tmp_path / "public.json"
    vector = tmp_path / "vector.json"
    result = runner.invoke(app, [
        "env", "woyengi-work", "--task", slug, "--output", str(private),
        "--public-output", str(public),
    ])
    assert result.exit_code == 0, result.output
    assert f'"work_task":"{slug}"'.encode() in public.read_bytes()
    assert b'"target_assertions"' not in public.read_bytes()
    check = runner.invoke(app, ["env", "validate", "--contract", str(private)])
    assert check.exit_code == 0, check.output
    vector.write_text(json.dumps({"actions": [
        *({"kind": "action", "name": name, "arguments": args} for name, args in (first, final)),
        {"kind": "operation", "name": "submit", "arguments": {
            "conclusion": f"The evidence supports marking the work {phase}.",
            "claimed_state": {f"{WORK_ID}.phase": phase, f"{WORK_ID}.{field}": value},
            "evidence_ids": evidence,
            "confidence": 1,
        }},
    ]}))
    run = runner.invoke(app, ["env", "run", "--contract", str(private), "--vector", str(vector)])
    assert run.exit_code == 0, run.output
    assert json.loads(run.output)["steps"][-1]["reward"] == 1.0


def test_work_task_identities_are_distinct_and_unknown_task_is_rejected(tmp_path):
    assert len({build_woyengi_work_environment(task).episode_id for task in WoyengiWorkTask}) == 5
    path = tmp_path / "must-not-exist.json"
    result = CliRunner().invoke(app, ["env", "woyengi-work", "--task", "not-a-task",
                                      "--output", str(path)])
    assert result.exit_code != 0
    assert not path.exists()
