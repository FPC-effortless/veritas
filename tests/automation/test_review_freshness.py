from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

MODULE_PATH = Path(__file__).parents[2] / "tools" / "review_freshness.py"
SPEC = importlib.util.spec_from_file_location("review_freshness", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
review_freshness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = review_freshness
SPEC.loader.exec_module(review_freshness)


class FakeClient:
    def __init__(
        self,
        pulls: list[dict[str, Any]],
        comparisons: dict[str, dict[str, Any]],
        reviews: dict[int, list[dict[str, Any]]],
        merge_state: dict[int, tuple[bool | None, str]] | None = None,
    ) -> None:
        self.pulls = pulls
        self.comparisons = comparisons
        self.reviews = reviews
        self.merge_state = merge_state or {}
        self.review_calls: list[int] = []

    def get_pages(self, path: str) -> list[dict[str, Any]]:
        if path.endswith("/pulls?state=open"):
            return self.pulls
        number = int(path.split("/pulls/")[1].split("/")[0])
        self.review_calls.append(number)
        return self.reviews.get(number, [])

    def get_object(self, path: str) -> dict[str, Any]:
        if "/compare/" in path:
            comparison = path.split("/compare/")[1]
            return self.comparisons[comparison]
        number = int(path.rsplit("/pulls/", 1)[1])
        source = next(item for item in self.pulls if item["number"] == number)
        mergeable, mergeable_state = self.merge_state.get(number, (True, "clean"))
        return {**source, "mergeable": mergeable, "mergeable_state": mergeable_state}


def pull(
    number: int,
    *,
    base_sha: str,
    head_sha: str,
    draft: bool = False,
    title: str | None = None,
) -> dict[str, Any]:
    return {
        "number": number,
        "title": title or f"PR {number}",
        "html_url": f"https://github.com/FPC-effortless/veritas/pull/{number}",
        "draft": draft,
        "base": {"ref": "main", "sha": base_sha},
        "head": {"ref": f"topic-{number}", "sha": head_sha},
    }


def review(
    review_id: int,
    *,
    state: str,
    commit_id: str | None,
    login: str = "reviewer",
    submitted_at: str = "2026-08-30T08:00:00Z",
) -> dict[str, Any]:
    return {
        "id": review_id,
        "state": state,
        "commit_id": commit_id,
        "submitted_at": submitted_at,
        "user": {"login": login},
    }


def test_stale_base_wins_without_spending_review_api_call() -> None:
    base = "a" * 40
    head = "b" * 40
    client = FakeClient(
        [pull(10, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "diverged", "behind_by": 3, "ahead_by": 2}},
        {10: [review(1, state="APPROVED", commit_id=head)]},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)

    entry = report["pull_requests"][0]
    assert entry["review_freshness"] == "STALE_BASE"
    assert entry["exact_head_review_state"] == "NOT_EVALUATED"
    assert client.review_calls == []


def test_old_head_approval_is_stale_review() -> None:
    base = "a" * 40
    head = "b" * 40
    old = "c" * 40
    client = FakeClient(
        [pull(11, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {11: [review(1, state="APPROVED", commit_id=old)]},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)

    assert report["pull_requests"][0]["review_freshness"] == "STALE_REVIEW"


def test_current_head_approval_is_current_review_not_merge_authority() -> None:
    base = "a" * 40
    head = "b" * 40
    client = FakeClient(
        [pull(12, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {12: [review(1, state="APPROVED", commit_id=head)]},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)
    markdown = review_freshness.render_markdown(report)

    assert report["pull_requests"][0]["review_freshness"] == "CURRENT_REVIEW"
    assert "merge/release authority" in markdown
    assert "MERGE_READY" not in markdown


def test_current_head_changes_requested_overrides_approval() -> None:
    base = "a" * 40
    head = "b" * 40
    client = FakeClient(
        [pull(13, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {
            13: [
                review(
                    1,
                    state="APPROVED",
                    commit_id=head,
                    login="reviewer-a",
                    submitted_at="2026-08-30T08:00:00Z",
                ),
                review(
                    2,
                    state="CHANGES_REQUESTED",
                    commit_id=head,
                    login="reviewer-b",
                    submitted_at="2026-08-30T08:01:00Z",
                ),
            ]
        },
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)

    assert report["pull_requests"][0]["review_freshness"] == "CHANGES_REQUESTED"


def test_same_reviewer_latest_decisive_review_wins() -> None:
    head = "b" * 40
    summary = review_freshness.summarize_reviews(
        [
            review(
                1,
                state="CHANGES_REQUESTED",
                commit_id=head,
                submitted_at="2026-08-30T08:00:00Z",
            ),
            review(
                2,
                state="APPROVED",
                commit_id=head,
                submitted_at="2026-08-30T08:05:00Z",
            ),
        ],
        head,
    )

    assert summary.exact_head_state == "APPROVED"
    assert summary.has_approval_history is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commit_id", None),
        ("commit_id", "not-a-sha"),
        ("user", None),
        ("user", {"login": ""}),
        ("user", {"login": " reviewer "}),
        ("id", None),
        ("id", True),
        ("id", "1"),
        ("submitted_at", None),
        ("submitted_at", ""),
        ("submitted_at", "not-a-timestamp"),
        ("submitted_at", "2026-08-30T08:00:00"),
    ],
)
@pytest.mark.parametrize("state", ["APPROVED", "CHANGES_REQUESTED"])
@pytest.mark.parametrize("use_old_head", [False, True])
def test_malformed_decisive_review_fails_closed(
    field: str,
    value: Any,
    state: str,
    use_old_head: bool,
) -> None:
    base = "a" * 40
    head = "b" * 40
    candidate = review(
        1,
        state=state,
        commit_id="c" * 40 if use_old_head else head,
    )
    candidate[field] = value
    client = FakeClient(
        [pull(22, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {22: [candidate]},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)
    entry = report["pull_requests"][0]

    assert entry["review_freshness"] == "UNKNOWN"
    assert entry["exact_head_review_state"] == "UNKNOWN"
    assert entry["approval_history"] is None
    assert entry["error"]


@pytest.mark.parametrize("bad_state", [None, 1, "", "UNKNOWN_FUTURE_STATE"])
def test_malformed_review_state_fails_closed_with_valid_approval(
    bad_state: Any,
) -> None:
    base = "a" * 40
    head = "b" * 40
    malformed = review(2, state="COMMENTED", commit_id=head)
    malformed["state"] = bad_state
    client = FakeClient(
        [pull(23, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {
            23: [
                review(1, state="APPROVED", commit_id=head),
                malformed,
            ]
        },
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)
    entry = report["pull_requests"][0]

    assert entry["review_freshness"] == "UNKNOWN"
    assert entry["exact_head_review_state"] == "UNKNOWN"
    assert entry["approval_history"] is None
    assert "review state is missing or invalid" in entry["error"]


def test_draft_cannot_be_current_review() -> None:
    base = "a" * 40
    head = "b" * 40
    client = FakeClient(
        [pull(14, base_sha=base, head_sha=head, draft=True)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {14: [review(1, state="APPROVED", commit_id=head)]},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)

    assert report["pull_requests"][0]["review_freshness"] == "DRAFT"
    assert client.review_calls == []


@pytest.mark.parametrize("bad_draft", [None, "false", 0])
def test_non_boolean_draft_fails_closed(bad_draft: Any) -> None:
    base = "a" * 40
    head = "b" * 40
    candidate = pull(18, base_sha=base, head_sha=head)
    candidate["draft"] = bad_draft
    client = FakeClient(
        [candidate],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {18: [review(1, state="APPROVED", commit_id=head)]},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)
    entry = report["pull_requests"][0]

    assert entry["review_freshness"] == "UNKNOWN"
    assert entry["draft"] is None
    assert "draft state is missing or not boolean" in entry["error"]
    assert client.review_calls == []


def test_missing_draft_fails_closed() -> None:
    base = "a" * 40
    head = "b" * 40
    candidate = pull(19, base_sha=base, head_sha=head)
    candidate.pop("draft")
    client = FakeClient(
        [candidate],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {19: [review(1, state="APPROVED", commit_id=head)]},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)
    entry = report["pull_requests"][0]

    assert entry["review_freshness"] == "UNKNOWN"
    assert entry["draft"] is None
    assert "draft state is missing or not boolean" in entry["error"]
    assert client.review_calls == []


def test_merge_state_is_surface_only_not_authority() -> None:
    base = "a" * 40
    head = "b" * 40
    client = FakeClient(
        [pull(16, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {16: [review(1, state="APPROVED", commit_id=head)]},
        {16: (False, "dirty")},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)
    entry = report["pull_requests"][0]

    assert entry["review_freshness"] == "CURRENT_REVIEW"
    assert entry["mergeable"] is False
    assert entry["mergeable_state"] == "dirty"
    assert "dirty / false" in review_freshness.render_markdown(report)


def test_unknown_comparison_fails_closed() -> None:
    base = "a" * 40
    head = "b" * 40
    client = FakeClient(
        [pull(15, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "mystery", "behind_by": 0, "ahead_by": 1}},
        {},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)

    entry = report["pull_requests"][0]
    assert entry["review_freshness"] == "UNKNOWN"
    assert entry["error"]


def test_pr_movement_during_collection_fails_closed() -> None:
    base = "a" * 40
    head = "b" * 40
    moved = "c" * 40

    class MovingClient(FakeClient):
        def get_object(self, path: str) -> dict[str, Any]:
            if "/compare/" in path:
                return super().get_object(path)
            detail = super().get_object(path)
            detail["head"] = {**detail["head"], "sha": moved}
            return detail

    client = MovingClient(
        [pull(17, base_sha=base, head_sha=head)],
        {f"{base}...{head}": {"status": "ahead", "behind_by": 0, "ahead_by": 1}},
        {},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)

    assert report["pull_requests"][0]["review_freshness"] == "UNKNOWN"
    assert "moved during freshness collection" in report["pull_requests"][0]["error"]


def test_report_order_is_deterministic_by_status_then_number() -> None:
    base = "a" * 40
    head_20 = "b" * 40
    head_21 = "c" * 40
    client = FakeClient(
        [
            pull(21, base_sha=base, head_sha=head_21),
            pull(20, base_sha=base, head_sha=head_20),
        ],
        {
            f"{base}...{head_20}": {"status": "ahead", "behind_by": 0, "ahead_by": 1},
            f"{base}...{head_21}": {"status": "diverged", "behind_by": 2, "ahead_by": 1},
        },
        {20: []},
    )

    report = review_freshness.build_report("FPC-effortless/veritas", client)

    assert [item["number"] for item in report["pull_requests"]] == [21, 20]
    assert [item["review_freshness"] for item in report["pull_requests"]] == [
        "STALE_BASE",
        "NEEDS_REVIEW",
    ]


def test_repository_input_rejects_non_owner_name_form() -> None:
    with pytest.raises(ValueError):
        review_freshness._repository("https://example.com/not-a-repo")
