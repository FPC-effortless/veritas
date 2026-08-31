from pathlib import Path


WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
COORDINATOR = Path(".github/scripts/agent-work-claims.js")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _recovery_job() -> str:
    workflow = _workflow()
    assert "  recover-merged:\n" in workflow
    return workflow.split("  recover-merged:\n", 1)[1]


def _assert_contains(text: str, *needles: str) -> None:
    for needle in needles:
        assert needle in text


def test_recovery_is_separate_and_serialized() -> None:
    workflow = _workflow()
    coordinate = workflow.split("  coordinate:\n", 1)[1].split(
        "  recover-merged:\n", 1
    )[0]
    recovery = _recovery_job()

    _assert_contains(
        recovery,
        "startsWith(github.event.comment.body, '/recover-merged ')",
        "group: agent-work-coordination",
        "cancel-in-progress: false",
        "actions: read",
        "contents: read",
        "issues: write",
        "pull-requests: read",
    )
    assert "/recover-merged" not in coordinate


def test_recovery_requires_owner_and_review_holder() -> None:
    recovery = _recovery_job()

    _assert_contains(
        recovery,
        "association !== 'OWNER'",
        "status.state !== 'REVIEW'",
        "status.github_actor !== actor",
        "status.agent_id !== command.agent",
        "status.linked_pr !== command.pr",
        "pr.head?.ref !== status.branch",
        "previousHead === finalHead",
        "ordinary /done owns exact-head completion",
        "Array.isArray(status.ownership_paths)",
    )


def test_recovery_requires_exact_head_review() -> None:
    recovery = _recovery_job()

    _assert_contains(
        recovery,
        "RECOGNIZED_REVIEW_STATES",
        "DECISIVE_REVIEW_STATES",
        "review.commit_id",
        "decisive review has malformed commit identity",
        "decisive review has no concrete reviewer login",
        "decisive review has no positive integer review id",
        (
            "decisive review timestamp is not "
            "timezone-aware ISO-8601"
        ),
        "review.login !== prAuthor",
        "exact-head changes requested by",
        (
            "no exact-head approval from a GitHub identity "
            "distinct from the PR author"
        ),
        "github.rest.pulls.listReviews",
    )


def test_recovery_requires_exact_head_gates() -> None:
    recovery = _recovery_job()

    _assert_contains(
        recovery,
        (
            "REQUIRED_WORKFLOWS = "
            "['Security', 'Python Quality Ratchet', 'CI']"
        ),
        "github.rest.actions.listWorkflowRunsForRepo",
        "run.head_sha === headSha",
        "run.event === 'pull_request'",
        "run.status !== 'completed' || run.conclusion !== 'success'",
        "missing exact-head ${name} workflow run",
    )


def test_recovery_requires_merge_on_default_branch() -> None:
    recovery = _recovery_job()

    _assert_contains(
        recovery,
        "pr.state !== 'closed' || pr.merged !== true || !pr.merged_at",
        "pr.merge_commit_sha",
        "github.rest.repos.compareCommitsWithBasehead",
        "basehead: `${mergeCommit}...${defaultBranch}`",
        "comparison.behind_by !== 0",
        "['ahead', 'identical'].includes(comparison.status)",
    )


def test_recovery_preserves_done_head_invariant() -> None:
    recovery = _recovery_job()
    coordinator = COORDINATOR.read_text(encoding="utf-8")
    done_guard = (
        "PR #${command.pr} head moved after handoff; "
        "re-handoff/review exact final head before DONE"
    )

    assert done_guard in coordinator
    _assert_contains(
        recovery,
        "schema_version: 'veritas.owner-post-merge-head-recovery.v1'",
        "previous_handoff_head: previousHead",
        "pr_head: finalHead",
        "merge_commit: mergeCommit",
        "review_id: approval.reviewId",
        "required_workflows: gates",
        "state: 'DONE'",
        "linked_pr_head: finalHead",
    )


def test_local_done_precedes_registry_cleanup() -> None:
    recovery = _recovery_job()

    local_write = recovery.index("comment_id: trusted.commentId")
    done_label = recovery.index("labels: ['agent-work', 'work:done']")
    registry_lookup = recovery.index("issue_number: 150")
    registry_write = recovery.index("comment_id: registry.commentId")

    assert local_write < done_label < registry_lookup < registry_write
    _assert_contains(
        recovery,
        "If later cleanup fails, a stale",
        "global reservation remains fail-closed",
    )


def test_rejections_are_audited_and_fail_closed() -> None:
    recovery = _recovery_job()
    rejection = (
        "Rejected \\`recover-merged\\` from "
        "@${actor}: ${message}"
    )

    assert rejection in recovery
    assert "throw error;" in recovery
