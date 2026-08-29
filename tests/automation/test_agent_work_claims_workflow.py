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
    assert "return_state: current.status.return_state ||" in script
    release_block = script.split("} else if (command.kind === 'release') {", 1)[1].split(
        "} else if (command.kind === 'blocked') {", 1
    )[0]
    assert "contract.initialState" not in release_block


def test_bootstrap_ignores_untrusted_state_labels_and_is_owner_only() -> None:
    script = _script()
    bootstrap_status = script.split("function bootstrapStatus(issue, contract) {", 1)[1].split(
        "async function listEnrolledIssues()", 1
    )[0]
    assert "let state = contract.initialState" in bootstrap_status
    assert "labelNames(issue)" not in bootstrap_status
    assert "labeledStates" not in bootstrap_status
    bootstrap = script.split("async function bootstrap(actor, association) {", 1)[1].split(
        "const triggerBody", 1
    )[0]
    assert "association !== 'OWNER'" in bootstrap
    assert "repository OWNER is required" in bootstrap


def test_claim_enforces_declared_branch_global_paths_and_branch_uniqueness() -> None:
    script = _script()
    assert "command.branch !== contract.declaredBranch" in script
    assert "trustedRegistry" in script
    assert "updateRegistryEntry" in script
    assert "openPrConflicts" in script
    assert "pathsOverlap(candidate, reserved)" in script
    assert "reservation.branch && reservation.branch === branch" in script
    assert "is already reserved" in script
    assert "open PR #${conflict.pr} reserves" in script
    assert "veritas.agent-work-reservations.v1" in script


def test_active_ownership_is_frozen_in_trusted_status() -> None:
    script = _script()
    claim_block = script.split("if (command.kind === 'claim') {", 1)[1].split(
        "} else if (command.kind === 'heartbeat') {", 1
    )[0]
    assert "ownership_paths: contract.paths.slice()" in claim_block
    registry_block = script.split("async function updateRegistryEntry", 1)[1].split(
        "async function openPrConflicts", 1
    )[0]
    assert "frozenOwnershipPaths(status)" in registry_block
    assert "paths: contract.paths" not in registry_block
    assert "trusted ownership snapshot is missing" in script
    assert "!Array.isArray(current.status.ownership_paths)" in script


def test_label_reconciliation_reads_fresh_issue_state() -> None:
    script = _script()
    assert "freshIssue = (await github.rest.issues.get" in script
    assert "setStateLabels(issue.number, status.state)" in script


def test_handoff_and_done_bind_exact_final_pr_head_and_allow_same_pr_rehandoff() -> None:
    script = _script()
    handoff_block = script.split("} else if (command.kind === 'handoff') {", 1)[1].split(
        "} else if (command.kind === 'done') {", 1
    )[0]
    assert "['CLAIMED', 'REVIEW'].includes(status.state)" in handoff_block
    assert "status.state === 'REVIEW' && status.linked_pr !== command.pr" in handoff_block
    assert "pr.head.ref !== status.branch" in handoff_block
    assert "prBody.includes(`#${issueNumber}`)" in handoff_block
    assert "prBody.includes(primaryWorkId)" in handoff_block
    assert "status.linked_pr_head = pr.head.sha" in handoff_block
    assert "!status.linked_pr || status.linked_pr !== command.pr" in script
    assert "status.linked_pr_head !== pr.head.sha" in script
    assert "re-handoff/review exact final head before DONE" in script


def test_bootstrap_materializes_and_migrates_frozen_status_for_all_enrolled_issues() -> None:
    script = _script()
    assert "bootstrapStatus(issue, contract)" in script
    assert "current = await writeStatus(issue, null, bootstrapStatus(issue, contract))" in script
    assert "ownership_paths: contract.paths.slice()" in script
    assert "Array.isArray(current.status.ownership_paths)" in script
    assert "paths: frozenOwnershipPaths(current.status)" in script
    assert "writeRegistry(entries)" in script
    assert "Labels are discovery metadata only after bootstrap" in script


def test_bootstrap_holder_and_stale_recovery_require_owner_audit() -> None:
    script = _script()
    assert "command.kind === 'recover'" in script
    assert "association !== 'OWNER'" in script
    assert "status.github_actor !== 'bootstrap' && !stale" in script
    assert "frozenOwnershipPaths(status)" in script
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
    assert "frozen ownership" in doc.lower()
    assert "OWNER-only" in doc
    assert "same PR" in doc
    assert "comment-ID order" in doc
    assert "/recover" in doc
    assert "does not grant merge, release" in doc
