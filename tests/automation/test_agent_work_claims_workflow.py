from pathlib import Path

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
SCRIPT = Path(".github/scripts/agent-work-claims.js")
DOC = Path("docs/automation/agent-work-claims.md")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


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


def test_claim_workflow_serializes_and_drains_through_script() -> None:
    workflow = _workflow()
    script = _script()
    assert "group: agent-work-coordination" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "actions/checkout@v4" in workflow
    assert "agent-work-claims.js" in workflow
    assert "sort((a, b) => a.id - b.id)" in script
    assert "last_command_comment_id" in script


def test_execution_requires_trusted_status_not_labels_or_mutable_contract_state() -> None:
    script = _script()
    assert "trusted status is missing" in script
    assert "labels and mutable Work Contract state are not execution authority" in script
    assert "const target = status.return_state === 'BLOCKED' ? 'BLOCKED' : 'READY'" in script
    assert "return_state: contract.initialState === 'BLOCKED' ? 'BLOCKED' : 'READY'" in script
    release_block = script.split("} else if (command.kind === 'release') {", 1)[1].split(
        "} else if (command.kind === 'blocked') {", 1
    )[0]
    assert "contract.initialState" not in release_block


def test_claim_enforces_declared_branch_and_global_path_reservations() -> None:
    script = _script()
    assert "command.branch !== contract.declaredBranch" in script
    assert "trustedRegistry" in script
    assert "updateRegistryEntry" in script
    assert "openPrConflicts" in script
    assert "pathsOverlap(candidate, reserved)" in script
    assert "open PR #${conflict.pr} reserves" in script
    assert "veritas.agent-work-reservations.v1" in script


def test_label_reconciliation_reads_fresh_issue_state() -> None:
    script = _script()
    assert "freshIssue = (await github.rest.issues.get" in script
    assert "setStateLabels(issue.number, status.state)" in script


def test_handoff_and_done_bind_exact_final_pr_head() -> None:
    script = _script()
    assert "pr.head.ref !== status.branch" in script
    assert "prBody.includes(`#${issueNumber}`)" in script
    assert "prBody.includes(primaryWorkId)" in script
    assert "!status.linked_pr || status.linked_pr !== command.pr" in script
    assert "status.linked_pr_head !== pr.head.sha" in script
    assert "re-handoff/review exact final head before DONE" in script


def test_bootstrap_materializes_status_for_all_enrolled_issues() -> None:
    script = _script()
    assert "bootstrapStatus(issue, contract)" in script
    assert "current = await writeStatus(issue, null, bootstrapStatus(issue, contract))" in script
    assert "writeRegistry(entries)" in script
    assert "Labels are discovery metadata only after bootstrap" in script


def test_bootstrap_holder_and_stale_recovery_require_owner_audit() -> None:
    script = _script()
    assert "command.kind === 'recover'" in script
    assert "association !== 'OWNER'" in script
    assert "status.github_actor !== 'bootstrap' && !stale" in script
    assert "STALE_MS = 2 * 60 * 60 * 1000" in script


def test_untrusted_comment_text_is_not_sent_to_a_shell() -> None:
    workflow = _workflow()
    assert "uses: actions/github-script@v7" in workflow
    assert "shell:" not in workflow
    assert "run:" not in workflow


def test_bootstrap_and_agent_startup_are_documented() -> None:
    doc = DOC.read_text(encoding="utf-8")
    assert "/roadmap-bootstrap" in doc
    assert "trusted bot-authored status" in doc
    assert "comment-ID order" in doc
    assert "/recover" in doc
    assert "does not grant merge, release" in doc
