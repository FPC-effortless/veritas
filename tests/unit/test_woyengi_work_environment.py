from __future__ import annotations

import json

from typer.testing import CliRunner

from investigation_world.authoring.woyengi_work import (
    EVIDENCE_ID,
    WORK_ID,
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
