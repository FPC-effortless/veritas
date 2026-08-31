from pathlib import Path

COMPLETION = Path(".github/workflows/roadmap-completion-sync.yml")
NOTIFICATIONS = Path(".github/workflows/roadmap-dependency-notifications.yml")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_shared_concurrency_is_reconcile_job_scoped(path: Path) -> None:
    text = _text(path)
    header, jobs = text.split("jobs:", 1)
    assert "concurrency:" not in header

    reconcile = jobs.split("  reconcile:", 1)[1]
    assert "    if: >-" in reconcile
    assert "    concurrency:" in reconcile
    assert "      group: agent-work-coordination" in reconcile
    assert "      cancel-in-progress: false" in reconcile
    assert reconcile.index("    if: >-") < reconcile.index("    concurrency:")


def test_completion_sync_skipped_comments_do_not_enter_shared_queue() -> None:
    _assert_shared_concurrency_is_reconcile_job_scoped(COMPLETION)
    text = _text(COMPLETION)
    assert "  issue_comment:" in text
    assert "startsWith(github.event.comment.body, 'Completion evidence:')" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text


def test_dependency_notifier_skipped_events_do_not_enter_shared_queue() -> None:
    _assert_shared_concurrency_is_reconcile_job_scoped(NOTIFICATIONS)
    text = _text(NOTIFICATIONS)
    assert 'workflows: ["Agent Work Claims"]' in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "contains(github.event.issue.body, '<!-- veritas-agent-work -->')" in text
