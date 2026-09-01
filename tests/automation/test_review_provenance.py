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
    body: str | None = None,
) -> dict[str, object]:
    return {
        "id": review_id,
        "user": {"login": login},
        "state": state,
        "commit_id": commit_id,
        "submitted_at": submitted_at,
        "body": body,
    }


def _agent_review(
    *,
    review_id: int,
    login: str = "implementer",
    verdict: str = "clean",
    commit_id: str = HEAD,
    marker_head: str | None = None,
    submitted_at: str = "2026-08-31T06:00:00Z",
    extra_body: str = "Semantic review completed against the exact candidate.",
) -> dict[str, object]:
    marker_head = marker_head or commit_id
    return _review(
        review_id=review_id,
        login=login,
        state="COMMENTED",
        commit_id=commit_id,
        submitted_at=submitted_at,
        body=(
            f"<!-- veritas-agent-review:v1 head={marker_head} verdict={verdict} -->\n"
            f"{extra_body}"
        ),
    )


def test_distinct_github_identity_exact_head_approval_passes() -> None:
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[_review(review_id=1, login="reviewer")],
    )
    assert decision.ok is True
    assert decision.reviewer == "reviewer"
    assert decision.review_id == 1


def test_same_account_free_form_review_does_not_claim_authority() -> None:
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
    assert "canonical clean agent review" in decision.reason


def test_quoted_marker_handoff_is_ignored_as_non_authoritative() -> None:
    handoff = _review(
        review_id=1,
        login="implementer",
        state="COMMENTED",
        body=(
            "Review handoff only — this is NOT merge-authoritative review evidence.\n\n"
            f"`<!-- veritas-agent-review:v1 head={HEAD} verdict=clean -->`\n\n"
            "If blocked, use `BLOCKING:` findings."
        ),
    )
    clean = _agent_review(
        review_id=2,
        submitted_at="2026-08-31T06:01:00Z",
    )
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[handoff, clean],
    )
    assert decision.ok is True
    assert decision.review_id == 2


def test_fenced_marker_example_is_ignored_as_non_authoritative() -> None:
    handoff = _review(
        review_id=1,
        login="implementer",
        state="COMMENTED",
        body=(
            "Example only:\n```text\n"
            f"<!-- veritas-agent-review:v1 head={HEAD} verdict=clean -->\n"
            "```\nBLOCKING: appears here only as instructional prose."
        ),
    )
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[handoff],
    )
    assert decision.ok is False
    assert "no exact-head" in decision.reason


def test_indented_code_marker_example_is_ignored_as_non_authoritative() -> None:
    handoff = _review(
        review_id=1,
        login="implementer",
        state="COMMENTED",
        body=(
            "Example only:\n\n"
            f"    <!-- veritas-agent-review:v1 head={HEAD} verdict=clean -->\n"
            "    BLOCKING: example finding"
        ),
    )
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[handoff],
    )
    assert decision.ok is False
    assert "no exact-head" in decision.reason


def test_long_fence_does_not_close_on_shorter_inner_fence() -> None:
    handoff = _review(
        review_id=1,
        login="implementer",
        state="COMMENTED",
        body=(
            "Example only:\n````markdown\n```\n"
            f"<!-- veritas-agent-review:v1 head={HEAD} verdict=clean -->\n"
            "```\n````"
        ),
    )
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[handoff],
    )
    assert decision.ok is False
    assert "no exact-head" in decision.reason


def test_canonical_same_account_agent_review_passes() -> None:
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[_agent_review(review_id=2)],
    )
    assert decision.ok is True
    assert decision.reviewer == "implementer"
    assert decision.review_id == 2
    assert "agent-session" in decision.reason


def test_stale_head_reviews_do_not_carry_forward() -> None:
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[
            _review(review_id=1, login="reviewer", commit_id=OLD_HEAD),
            _agent_review(review_id=2, commit_id=OLD_HEAD),
        ],
    )
    assert decision.ok is False
    assert "no exact-head" in decision.reason


def test_agent_marker_must_bind_to_review_commit() -> None:
    with pytest.raises(ProvenanceError, match="marker head"):
        evaluate_reviews(
            pr_author="implementer",
            head_sha=HEAD,
            reviews=[
                _agent_review(
                    review_id=1,
                    commit_id=HEAD,
                    marker_head=OLD_HEAD,
                )
            ],
        )


def test_malformed_agent_marker_fails_closed() -> None:
    malformed = _review(
        review_id=1,
        login="implementer",
        state="COMMENTED",
        body="<!-- veritas-agent-review:v1 clean -->",
    )
    with pytest.raises(ProvenanceError, match="marker is malformed"):
        evaluate_reviews(
            pr_author="implementer",
            head_sha=HEAD,
            reviews=[malformed],
        )


def test_duplicate_agent_markers_fail_closed() -> None:
    marker = f"<!-- veritas-agent-review:v1 head={HEAD} verdict=clean -->"
    duplicate = _review(
        review_id=1,
        login="implementer",
        state="COMMENTED",
        body=f"{marker}\n{marker}",
    )
    with pytest.raises(ProvenanceError, match="exactly one canonical marker"):
        evaluate_reviews(
            pr_author="implementer",
            head_sha=HEAD,
            reviews=[duplicate],
        )


def test_blocking_agent_review_vetoes_clean_review() -> None:
    reviews = [
        _agent_review(review_id=1, verdict="clean"),
        _agent_review(
            review_id=2,
            verdict="blocking",
            submitted_at="2026-08-31T06:01:00Z",
            extra_body="BLOCKING: correctness defect remains.",
        ),
    ]
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=reviews,
    )
    assert decision.ok is False
    assert "blocking" in decision.reason


def test_clean_agent_review_with_inline_finding_is_blocked() -> None:
    review = _agent_review(review_id=7)
    comments = [
        {
            "pull_request_review_id": 7,
            "commit_id": HEAD,
            "body": "This invariant is not enforced.",
        }
    ]
    decision = evaluate_reviews(
        pr_author="implementer",
        head_sha=HEAD,
        reviews=[review],
        review_comments=comments,
    )
    assert decision.ok is False
    assert "inline finding" in decision.reason


def test_clean_agent_review_cannot_contain_blocking_summary() -> None:
    with pytest.raises(ProvenanceError, match="clean agent review contains"):
        evaluate_reviews(
            pr_author="implementer",
            head_sha=HEAD,
            reviews=[
                _agent_review(
                    review_id=1,
                    verdict="clean",
                    extra_body="BLOCKING: contradictory clean verdict.",
                )
            ],
        )


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


def test_any_current_changes_requested_blocks_agent_review() -> None:
    reviews = [
        _agent_review(review_id=1),
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
