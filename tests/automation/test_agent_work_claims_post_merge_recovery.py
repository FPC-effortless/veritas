from pathlib import Path


WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
COORDINATOR = Path(".github/scripts/agent-work-claims.js")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _recovery_job() -> str:
    workflow = _workflow()
    assert "  recover-merged:\n" in workflow
    return workflow.split("  recover-merged:\n", 1)[1]


def test_recover_merged_is_separate_and_serialized_with_coordination() -> None:
    workflow = _workflow()
    coordinate = workflow.split("  coordinate:\n", 1)[1].split(
        "  recover-merged:\n", 1
    )[0]
    recovery = _recovery_job()

    assert "startsWith(github.event.comment.body, '/recover-merged ')" in recovery
    assert "/recover-merged" not in coordinate
    assert "group: agent-work-coordination" in recovery
    assert "cancel-in-progress: false" in recovery
    assert "actions: read" in recovery
    assert "contents: read" in recovery
    assert "issues: write" in recovery
    assert "pull-requests: read" in recovery


def test_recover_merged_requires_owner_and_exact_trusted_review_holder() -> None:
    recovery = _recovery_job()

    assert "association !== 'OWNER'" in recovery
    assert "status.state !== 'REVIEW'" in recovery
    assert "status.github_actor !== actor" in recovery
    assert "status.agent_id !== command.agent" in recovery
    assert "status.linked_pr !== command.pr" in recovery
    assert "pr.head?.ref !== status.branch" in recovery
    assert "previousHead === finalHead" in recovery
    assert "ordinary /done owns exact-head completion" in recovery
    assert "Array.isArray(status.ownership_paths)" in recovery


def test_recover_merged_requires_exact_final_head_review_provenance() -> None:
    recovery = _recovery_job()

    assert "RECOGNIZED_REVIEW_STATES" in recovery
    assert "DECISIVE_REVIEW_STATES" in recovery
    assert "review.commit_id" in recovery
    assert "decisive review has malformed commit identity" in recovery
    assert "decisive review has no concrete reviewer login" in recovery
    assert "decisive review has no positive integer review id" in recovery
    assert "decisive review timestamp is not timezone-aware ISO-8601" in recovery
    assert "review.login !== prAuthor" in recovery
    assert "exact-head changes requested by" in recovery
    assert (
        "no exact-head approval from a GitHub identity distinct from the PR author"
        in recovery
    )
    assert "github.rest.pulls.listReviews" in recovery


def test_recover_merged_requires_exact_head_security_quality_and_ci() -> None:
    recovery = _recovery_job()

    assert (
        "REQUIRED_WORKFLOWS = ['Security', 'Python Quality Ratchet', 'CI']"
        in recovery
    )
    assert "github.rest.actions.listWorkflowRunsForRepo" in recovery
    assert "run.head_sha === headSha" in recovery
    assert "run.event === 'pull_request'" in recovery
    assert "run.status !== 'completed' || run.conclusion !== 'success'" in recovery
    assert "missing exact-head ${name} workflow run" in recovery


def test_recover_merged_requires_merge_on_current_default_branch() -> None:
    recovery = _recovery_job()

    assert "pr.state !== 'closed' || pr.merged !== true || !pr.merged_at" in recovery
    assert "pr.merge_commit_sha" in recovery
    assert "github.rest.repos.compareCommitsWithBasehead" in recovery
    assert "basehead: `${mergeCommit}...${defaultBranch}`" in recovery
    assert "comparison.behind_by !== 0" in recovery
    assert "['ahead', 'identical'].includes(comparison.status)" in recovery


def test_recovery_preserves_done_exact_head_invariant_and_audits_head_rewrite() -> None:
    recovery = _recovery_job()
    coordinator = COORDINATOR.read_text(encoding="utf-8")

    # Ordinary completion remains strict and cannot silently rewrite a handoff head.
    assert (
        "PR #${command.pr} head moved after handoff; re-handoff/review exact final head before DONE"
        in coordinator
    )

    assert "schema_version: 'veritas.owner-post-merge-head-recovery.v1'" in recovery
    assert "previous_handoff_head: previousHead" in recovery
    assert "pr_head: finalHead" in recovery
    assert "merge_commit: mergeCommit" in recovery
    assert "review_id: approval.reviewId" in recovery
    assert "required_workflows: gates" in recovery
    assert "state: 'DONE'" in recovery
    assert "linked_pr_head: finalHead" in recovery


def test_terminal_local_state_is_published_before_registry_cleanup() -> None:
    recovery = _recovery_job()

    local_write = recovery.index("comment_id: trusted.commentId")
    done_label = recovery.index("labels: ['agent-work', 'work:done']")
    registry_lookup = recovery.index("issue_number: 150")
    registry_write = recovery.index("comment_id: registry.commentId")

    assert local_write < done_label < registry_lookup < registry_write
    assert "If later cleanup fails, a stale" in recovery
    assert "global reservation remains fail-closed" in recovery


def test_recovery_rejections_are_audited_and_fail_closed() -> None:
    recovery = _recovery_job()

    assert "Rejected \\`recover-merged\\` from @${actor}: ${message}" in recovery
    assert "throw error;" in recovery
