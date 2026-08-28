from pathlib import Path

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
DOC = Path("docs/automation/agent-work-claims.md")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_claim_workflow_has_least_privilege_and_no_dispatch_authority() -> None:
    text = _workflow()

    assert "contents: read" in text
    assert "issues: write" in text
    assert "pull-requests: read" in text
    assert "actions: write" not in text
    assert "packages: write" not in text
    assert "id-token: write" not in text
    assert "secrets:" not in text
    assert "workflow_dispatch:" not in text


def test_claim_workflow_serializes_transitions_without_cancellation() -> None:
    text = _workflow()

    assert "group: agent-work-coordination" in text
    assert "cancel-in-progress: false" in text
    assert "last_command_comment_id" in text


def test_claim_workflow_restricts_scope_and_authority() -> None:
    text = _workflow()

    assert "OWNER', 'MEMBER', 'COLLABORATOR" in text
    assert "veritas-agent-work" in text
    assert "github-actions[bot]" in text
    assert "issueNumber !== 150" in text
    assert "Rejected malformed agent-work command" in text


def test_claim_workflow_covers_required_state_commands() -> None:
    text = _workflow()

    for command in ("claim", "heartbeat", "release", "blocked", "handoff", "done"):
        assert f"command.kind === '{command}'" in text or f"kind: '{command}'" in text

    for state in ("READY", "CLAIMED", "BLOCKED", "REVIEW", "DONE", "SUPERSEDED"):
        assert state in text


def test_handoff_and_done_validate_pull_request_evidence() -> None:
    text = _workflow()

    assert "pr.head.ref !== status.branch" in text
    assert "prBody.includes(`#${issueNumber}`)" in text
    assert "prBody.includes(primaryWorkId)" in text
    assert "!pr.merged_at" in text
    assert "done requires the current REVIEW holder" in text


def test_partial_transition_failures_stay_non_claimable() -> None:
    text = _workflow()

    assert "parseStatusComment(comment, issue.number)" in text
    assert "labeledStates.length === 1 ? labeledStates[0] : contract.initialState" in text
    assert text.index("await writeStatus(issue, current, status);") < text.index(
        "await setStateLabels(issue, status.state);"
    )


def test_untrusted_comment_text_is_not_sent_to_a_shell() -> None:
    text = _workflow()

    assert "uses: actions/github-script@v7" in text
    assert "shell:" not in text
    assert "run:" not in text


def test_bootstrap_and_agent_startup_are_documented() -> None:
    doc = DOC.read_text(encoding="utf-8")

    assert "/roadmap-bootstrap" in doc
    assert "work:ready" in doc
    assert "wait for the workflow's accepted `CLAIMED` acknowledgement" in doc
    assert "does not grant merge, release" in doc
