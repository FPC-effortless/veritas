#!/usr/bin/env python3
"""Build a read-only exact-head review freshness report for open pull requests."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence

SCHEMA_VERSION = "veritas.review-freshness.v1"
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
COMPARE_STATES = {"ahead", "behind", "diverged", "identical"}
DECISIVE_REVIEW_STATES = {"APPROVED", "CHANGES_REQUESTED"}
REVIEW_STATES = DECISIVE_REVIEW_STATES | {"COMMENTED", "DISMISSED", "PENDING"}
STATUS_ORDER = {
    "UNKNOWN": 0,
    "STALE_BASE": 1,
    "DRAFT": 2,
    "CHANGES_REQUESTED": 3,
    "STALE_REVIEW": 4,
    "NEEDS_REVIEW": 5,
    "CURRENT_REVIEW": 6,
}


class GitHubApiError(RuntimeError):
    """GitHub API request failed or returned an unexpected shape."""


@dataclass(frozen=True)
class ReviewSummary:
    exact_head_state: str
    has_approval_history: bool


class GitHubReader(Protocol):
    def get_pages(self, path: str) -> list[dict[str, Any]]:
        ...

    def get_object(self, path: str) -> dict[str, Any]:
        ...


class GitHubClient:
    """Minimal fixed-host GitHub REST client with explicit pagination."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("GitHub token is required")
        self._token = token

    def _get_json(self, path: str) -> Any:
        if not path.startswith("/"):
            raise ValueError("GitHub API path must be absolute")
        connection = http.client.HTTPSConnection("api.github.com", timeout=30)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "veritas-review-freshness",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            payload = response.read()
        finally:
            connection.close()
        if response.status < 200 or response.status >= 300:
            raise GitHubApiError(f"GitHub API returned HTTP {response.status}")
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubApiError("GitHub API returned invalid JSON") from exc

    def get_pages(self, path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            separator = "&" if "?" in path else "?"
            payload = self._get_json(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
                raise GitHubApiError("GitHub paginated endpoint returned an unexpected shape")
            items.extend(payload)
            if len(payload) < 100:
                return items
            page += 1
            if page > 100:
                raise GitHubApiError("GitHub pagination exceeded safety limit")

    def get_object(self, path: str) -> dict[str, Any]:
        payload = self._get_json(path)
        if not isinstance(payload, dict):
            raise GitHubApiError("GitHub object endpoint returned an unexpected shape")
        return payload


def _repository(value: str) -> str:
    if not REPOSITORY_RE.fullmatch(value):
        raise ValueError("repository must be in owner/name form")
    return value


def _sha(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise GitHubApiError(f"{field} is missing or not a full commit SHA")
    return value


def _pr_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    number = item.get("number")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise GitHubApiError("pull request number is missing or invalid")
    title = item.get("title")
    html_url = item.get("html_url")
    base = item.get("base")
    head = item.get("head")
    draft = item.get("draft")
    if not isinstance(title, str) or not isinstance(html_url, str):
        raise GitHubApiError(f"PR #{number} is missing title or URL")
    if not isinstance(base, Mapping) or not isinstance(head, Mapping):
        raise GitHubApiError(f"PR #{number} is missing base/head metadata")
    if type(draft) is not bool:
        raise GitHubApiError(f"PR #{number} draft state is missing or not boolean")
    base_ref = base.get("ref")
    head_ref = head.get("ref")
    if not isinstance(base_ref, str) or not isinstance(head_ref, str):
        raise GitHubApiError(f"PR #{number} is missing base/head refs")
    return {
        "number": number,
        "title": title,
        "url": html_url,
        "draft": draft,
        "base_ref": base_ref,
        "base_sha": _sha(base.get("sha"), field=f"PR #{number} base SHA"),
        "head_ref": head_ref,
        "head_sha": _sha(head.get("sha"), field=f"PR #{number} head SHA"),
    }


def _merge_state(
    detail: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> tuple[bool | None, str]:
    """Read mergeability without allowing it to become integration authority."""

    detailed = _pr_snapshot(detail)
    if detailed["number"] != snapshot["number"]:
        raise GitHubApiError("pull request detail number changed during collection")
    if detailed["base_sha"] != snapshot["base_sha"] or detailed["head_sha"] != snapshot["head_sha"]:
        raise GitHubApiError(f"PR #{snapshot['number']} moved during freshness collection")

    mergeable = detail.get("mergeable")
    if mergeable is not None and type(mergeable) is not bool:
        mergeable = None
    mergeable_state = detail.get("mergeable_state")
    if not isinstance(mergeable_state, str) or not mergeable_state:
        mergeable_state = "UNKNOWN"
    return mergeable, mergeable_state


def _review_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise GitHubApiError("decisive review timestamp is missing or invalid")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GitHubApiError("decisive review timestamp is missing or invalid") from exc
    if timestamp.utcoffset() is None:
        raise GitHubApiError("decisive review timestamp is missing or invalid")
    return timestamp


def _decisive_review(review: Mapping[str, Any]) -> tuple[str, str, int, datetime, str]:
    state = review.get("state")
    if state not in DECISIVE_REVIEW_STATES:
        raise GitHubApiError("decisive review state is invalid")
    commit_id = _sha(review.get("commit_id"), field="decisive review commit ID")
    user = review.get("user")
    login = user.get("login") if isinstance(user, Mapping) else None
    if not isinstance(login, str) or not login or login != login.strip():
        raise GitHubApiError("decisive review identity is missing or invalid")
    review_id = review.get("id")
    if (
        not isinstance(review_id, int)
        or isinstance(review_id, bool)
        or review_id <= 0
    ):
        raise GitHubApiError("decisive review ID is missing or invalid")
    submitted_at = _review_timestamp(review.get("submitted_at"))
    return state, commit_id, review_id, submitted_at, login


def summarize_reviews(reviews: Iterable[Mapping[str, Any]], head_sha: str) -> ReviewSummary:
    """Reduce visible review objects to exact-head state without inferring independence."""

    latest_by_reviewer: dict[str, tuple[tuple[datetime, int], str]] = {}
    has_approval_history = False
    for review in reviews:
        state = review.get("state")
        if not isinstance(state, str) or state not in REVIEW_STATES:
            raise GitHubApiError("review state is missing or invalid")
        if state not in DECISIVE_REVIEW_STATES:
            continue
        state, commit_id, review_id, submitted_at, login = _decisive_review(review)
        if state == "APPROVED":
            has_approval_history = True
        if commit_id != head_sha:
            continue
        order_key = (submitted_at, review_id)
        current = latest_by_reviewer.get(login)
        if current is None or order_key >= current[0]:
            latest_by_reviewer[login] = (order_key, state)

    current_states = {state for _, state in latest_by_reviewer.values()}
    if "CHANGES_REQUESTED" in current_states:
        exact_head_state = "CHANGES_REQUESTED"
    elif "APPROVED" in current_states:
        exact_head_state = "APPROVED"
    else:
        exact_head_state = "NONE"
    return ReviewSummary(
        exact_head_state=exact_head_state,
        has_approval_history=has_approval_history,
    )


def classify(
    *,
    behind_by: int | None,
    compare_status: str | None,
    draft: bool,
    review_summary: ReviewSummary | None,
) -> str:
    """Classify freshness conservatively; UNKNOWN outranks missing evidence."""

    if behind_by is None or compare_status not in COMPARE_STATES:
        return "UNKNOWN"
    if behind_by > 0:
        return "STALE_BASE"
    if draft:
        return "DRAFT"
    if review_summary is None:
        return "UNKNOWN"
    if review_summary.exact_head_state == "CHANGES_REQUESTED":
        return "CHANGES_REQUESTED"
    if review_summary.exact_head_state == "APPROVED":
        return "CURRENT_REVIEW"
    if review_summary.has_approval_history:
        return "STALE_REVIEW"
    return "NEEDS_REVIEW"


def build_report(repository: str, client: GitHubReader) -> dict[str, Any]:
    repository = _repository(repository)
    pulls = client.get_pages(f"/repos/{repository}/pulls?state=open")
    entries: list[dict[str, Any]] = []

    for raw_pull in pulls:
        try:
            snapshot = _pr_snapshot(raw_pull)
            detail = client.get_object(f"/repos/{repository}/pulls/{snapshot['number']}")
            mergeable, mergeable_state = _merge_state(detail, snapshot)
            comparison = client.get_object(
                f"/repos/{repository}/compare/{snapshot['base_sha']}...{snapshot['head_sha']}"
            )
            behind_by = comparison.get("behind_by")
            ahead_by = comparison.get("ahead_by")
            compare_status = comparison.get("status")
            if (
                not isinstance(behind_by, int)
                or isinstance(behind_by, bool)
                or behind_by < 0
            ):
                raise GitHubApiError(f"PR #{snapshot['number']} comparison lacks behind_by")
            if (
                not isinstance(ahead_by, int)
                or isinstance(ahead_by, bool)
                or ahead_by < 0
            ):
                raise GitHubApiError(f"PR #{snapshot['number']} comparison lacks ahead_by")
            if not isinstance(compare_status, str) or compare_status not in COMPARE_STATES:
                raise GitHubApiError(f"PR #{snapshot['number']} comparison status is unknown")

            review_summary: ReviewSummary | None = None
            if behind_by == 0 and not snapshot["draft"]:
                reviews = client.get_pages(
                    f"/repos/{repository}/pulls/{snapshot['number']}/reviews"
                )
                review_summary = summarize_reviews(reviews, snapshot["head_sha"])

            status = classify(
                behind_by=behind_by,
                compare_status=compare_status,
                draft=snapshot["draft"],
                review_summary=review_summary,
            )
            entries.append(
                {
                    **snapshot,
                    "compare_status": compare_status,
                    "behind_by": behind_by,
                    "ahead_by": ahead_by,
                    "mergeable": mergeable,
                    "mergeable_state": mergeable_state,
                    "review_freshness": status,
                    "exact_head_review_state": (
                        review_summary.exact_head_state
                        if review_summary is not None
                        else "NOT_EVALUATED"
                    ),
                    "approval_history": (
                        review_summary.has_approval_history
                        if review_summary is not None
                        else None
                    ),
                    "error": None,
                }
            )
        except (GitHubApiError, KeyError, TypeError, ValueError) as exc:
            number = raw_pull.get("number")
            title = raw_pull.get("title")
            url = raw_pull.get("html_url")
            raw_draft = raw_pull.get("draft")
            entries.append(
                {
                    "number": (
                        number
                        if isinstance(number, int) and not isinstance(number, bool)
                        else 0
                    ),
                    "title": title if isinstance(title, str) else "UNKNOWN",
                    "url": url if isinstance(url, str) else "",
                    "draft": raw_draft if type(raw_draft) is bool else None,
                    "base_ref": None,
                    "base_sha": None,
                    "head_ref": None,
                    "head_sha": None,
                    "compare_status": None,
                    "behind_by": None,
                    "ahead_by": None,
                    "mergeable": None,
                    "mergeable_state": "UNKNOWN",
                    "review_freshness": "UNKNOWN",
                    "exact_head_review_state": "UNKNOWN",
                    "approval_history": None,
                    "error": str(exc),
                }
            )

    entries.sort(key=lambda item: (STATUS_ORDER[item["review_freshness"]], item["number"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": repository,
        "authority_boundary": (
            "Coordination observability only; freshness does not imply independent-review, "
            "CI/security, merge, release, scientific, Frontier, training, or commercial authority."
        ),
        "pull_requests": entries,
    }


def _escape_markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _merge_text(item: Mapping[str, Any]) -> str:
    mergeable = item.get("mergeable")
    if mergeable is True:
        mergeable_text = "true"
    elif mergeable is False:
        mergeable_text = "false"
    else:
        mergeable_text = "unknown"
    return f"{item.get('mergeable_state', 'UNKNOWN')} / {mergeable_text}"


def render_markdown(report: Mapping[str, Any]) -> str:
    pulls = report.get("pull_requests")
    if not isinstance(pulls, Sequence) or isinstance(pulls, (str, bytes)):
        raise ValueError("report pull_requests must be a sequence")
    lines = [
        "# Exact-head review freshness queue",
        "",
        "> Coordination observability only. `CURRENT_REVIEW` means an APPROVED review object is "
        "anchored to the current head; it does not prove reviewer independence, passing gates, or "
        "merge/release authority.",
        "",
        "| State | PR | Behind | Merge state | Exact-head review | Head | Title |",
        "| --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for item in pulls:
        if not isinstance(item, Mapping):
            raise ValueError("report entry must be an object")
        number = item.get("number", 0)
        url = item.get("url", "")
        pr_link = f"[#{number}]({url})" if url else f"#{number}"
        behind = item.get("behind_by")
        behind_text = "UNKNOWN" if behind is None else str(behind)
        head_sha = item.get("head_sha")
        head_text = str(head_sha)[:12] if head_sha else "UNKNOWN"
        lines.append(
            "| {state} | {pr} | {behind} | {merge} | {review} | `{head}` | {title} |".format(
                state=_escape_markdown(item.get("review_freshness", "UNKNOWN")),
                pr=pr_link,
                behind=behind_text,
                merge=_escape_markdown(_merge_text(item)),
                review=_escape_markdown(item.get("exact_head_review_state", "UNKNOWN")),
                head=head_text,
                title=_escape_markdown(item.get("title", "UNKNOWN")),
            )
        )
    if not pulls:
        lines.append("| — | — | — | — | — | — | No open pull requests |")
    lines.extend(
        [
            "",
            "Merge state is reported only as GitHub metadata and never upgrades freshness into "
            "integration or merge authority.",
            "",
            "States are conservative: `STALE_BASE`, `DRAFT`, `CHANGES_REQUESTED`, "
            "`STALE_REVIEW`, `NEEDS_REVIEW`, `CURRENT_REVIEW`, or `UNKNOWN`.",
            "",
        ]
    )
    return "\n".join(lines)


def _write(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="GitHub repository in owner/name form (defaults to GITHUB_REPOSITORY)",
    )
    parser.add_argument("--json-out", default="review-freshness.json")
    parser.add_argument("--markdown-out", default="review-freshness.md")
    args = parser.parse_args(argv)

    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN or GH_TOKEN is required")

    report = build_report(args.repository, GitHubClient(token))
    _write(args.json_out, json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write(args.markdown_out, render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
