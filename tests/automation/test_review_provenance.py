from __future__ import annotations

from pathlib import Path

import pytest

from tools.review_provenance import ProvenanceError, evaluate_reviews

HEAD = "a" * 40
OLD_HEAD = "b" * 40
SECURITY = Path(".github/workflows/security.yml")


def _review(
    *,
    review_id: int,
    login: str,
    state: str = "APPROVED",
    commit_id: str = HEAD,
    submitted_at: str = "2026-08-31T06:00:00Z",
) -> dict[str, object]:
    return {
        "id": review_id,
        "user": {"login": login},
        "state": state,
        "commit_id": commit_id,
        "submitted_at": submitted_at,
    }


def test_distinct_github_identity_exact_head_approval_passes() -> None:
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[_review(review_id=1, login="reviewer")],
    )
    assert decision.ok is True
    assert decision.reviewer == "reviewer"
    assert decision.review_id == 1


def test_same_account_review_cannot_claim_independence_by_wording() -> None:
    free_form = {
        "id": 1,
        "user": {"login": "implementer"},
        "state": "COMMENTED",
        "commit_id": HEAD,
        "submitted_at": "2026-08-31T06:00:00Z",
        "body": "Independent acceptance-session review — CLEAN.",
    }
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[free_form],
    )
    assert decision.ok is False
    assert "distinct" in decision.reason

    self_approval = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[_review(review_id=2, login="implementer")],
    )
    assert self_approval.ok is False
    assert "same-account" in self_approval.reason


def test_stale_head_approval_does_not_carry_forward() -> None:
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[_review(review_id=1, login="reviewer", commit_id=OLD_HEAD)],
    )
    assert decision.ok is False
    assert "no exact-head approval" in decision.reason


def test_later_exact_head_changes_requested_supersedes_approval() -> None:
    reviews = [
        _review(
            review_id=1,
            login="reviewer",
            submitted_at="2026-08-31T06:00:00Z",
        ),
        _review(
            review_id=2,
            login="reviewer",
            state="CHANGES_REQUESTED",
            submitted_at="2026-08-31T06:01:00Z",
        ),
    ]
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=reviews,
    )
    assert decision.ok is False
    assert "changes requested" in decision.reason


def test_any_current_changes_requested_blocks_other_reviewer_approval() -> None:
    reviews = [
        _review(review_id=1, login="clean-reviewer"),
        _review(
            review_id=2,
            login="blocking-reviewer",
            state="CHANGES_REQUESTED",
            submitted_at="2026-08-31T06:01:00Z",
        ),
    ]
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=reviews,
    )
    assert decision.ok is False
    assert "blocking-reviewer" in decision.reason


def test_malformed_decisive_metadata_fails_closed() -> None:
    malformed = _review(review_id=1, login="reviewer")
    malformed["id"] = True
    with pytest.raises(ProvenanceError, match="positive integer"):
        evaluate_reviews(
            pr_author="implementer",
            head_sha=HEAD,
            reviews=[malformed],
        )

    unknown_state = _review(review_id=2, login="reviewer")
    unknown_state["state"] = "MAYBE_APPROVED"
    with pytest.raises(ProvenanceError, match="unknown state"):
        evaluate_reviews(
            pr_author="implementer",
            head_sha=HEAD,
            reviews=[unknown_state],
        )


def test_security_workflow_enforces_provenance_after_scans() -> None:
    workflow = SECURITY.read_text(encoding="utf-8")
    assert "pull_request_review:" in workflow
    assert "types: [submitted, dismissed]" in workflow
    assert "pull-requests: read" in workflow
    assert "actions: write" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert "rerun" in workflow

    source_block = workflow.split("python-source-security:", 1)[1].split(
        "node-dependency-audit:", 1
    )[0]
    assert source_block.index("bandit -r src") < source_block.index(
        "Require independent exact-head review"
    )
    assert "tools/review_provenance.py check" in source_block

    node_block = workflow.split("node-dependency-audit:", 1)[1].split(
        "dependency-review:", 1
    )[0]
    assert node_block.index("pnpm audit") < node_block.index(
        "Require independent exact-head review"
    )
    assert "tools/review_provenance.py check" in node_block
    assert "github.event_name != 'pull_request_review'" in source_block
    assert "github.event_name != 'pull_request_review'" in node_block
