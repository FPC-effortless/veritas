#!/usr/bin/env python3
"""Fail-closed independent-review provenance for Veritas pull requests."""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RECOGNIZED_STATES = {
    "APPROVED",
    "CHANGES_REQUESTED",
    "COMMENTED",
    "DISMISSED",
    "PENDING",
}
DECISIVE_STATES = {"APPROVED", "CHANGES_REQUESTED"}


class ProvenanceError(RuntimeError):
    """Review metadata is insufficient or malformed for a safe decision."""


@dataclass(frozen=True)
class ReviewDecision:
    ok: bool
    reason: str
    reviewer: str | None = None
    review_id: int | None = None


def _valid_login(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceError("decisive review has no concrete reviewer login")
    return value.strip()


def _valid_review_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProvenanceError("decisive review has no positive integer review id")
    return value


def _valid_timestamp(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ProvenanceError("decisive review has no submission timestamp")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ProvenanceError("decisive review timestamp is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProvenanceError("decisive review timestamp is not timezone-aware")
    return parsed


def _validate_review_state(review: dict[str, Any]) -> str:
    state = review.get("state")
    if not isinstance(state, str) or state not in RECOGNIZED_STATES:
        raise ProvenanceError("review has missing, non-string, or unknown state")
    return state


def _decisive_review(review: dict[str, Any]) -> tuple[str, str, int, dt.datetime] | None:
    state = _validate_review_state(review)
    if state not in DECISIVE_STATES:
        return None
    commit_id = review.get("commit_id")
    if not isinstance(commit_id, str) or not SHA_RE.fullmatch(commit_id):
        raise ProvenanceError("decisive review has malformed commit identity")
    user = review.get("user")
    if not isinstance(user, dict):
        raise ProvenanceError("decisive review has malformed reviewer identity")
    login = _valid_login(user.get("login"))
    review_id = _valid_review_id(review.get("id"))
    submitted_at = _valid_timestamp(review.get("submitted_at"))
    return state, login, review_id, submitted_at


def evaluate_reviews(
    *,
    pr_author: str,
    head_sha: str,
    reviews: list[dict[str, Any]],
) -> ReviewDecision:
    """Return whether exact-head independent review provenance is satisfied."""
    if not isinstance(pr_author, str) or not pr_author.strip():
        raise ProvenanceError("pull request author identity is missing")
    if not SHA_RE.fullmatch(str(head_sha)):
        raise ProvenanceError("pull request head is not a full commit SHA")

    latest: dict[str, tuple[dt.datetime, int, str]] = {}
    for review in reviews:
        if not isinstance(review, dict):
            raise ProvenanceError("review payload contains a non-object entry")
        decisive = _decisive_review(review)
        if decisive is None:
            continue
        state, login, review_id, submitted_at = decisive
        if review["commit_id"] != head_sha:
            continue
        ordering = (submitted_at, review_id)
        previous = latest.get(login)
        if previous is None or ordering > (previous[0], previous[1]):
            latest[login] = (submitted_at, review_id, state)

    blockers = sorted(
        login for login, (_, _, state) in latest.items() if state == "CHANGES_REQUESTED"
    )
    if blockers:
        return ReviewDecision(
            ok=False,
            reason="exact-head changes requested by " + ", ".join(blockers),
        )

    author = pr_author.strip()
    approvals = sorted(
        (
            (submitted_at, review_id, login)
            for login, (submitted_at, review_id, state) in latest.items()
            if state == "APPROVED" and login != author
        ),
        reverse=True,
    )
    if approvals:
        _, review_id, login = approvals[0]
        return ReviewDecision(
            ok=True,
            reason="exact-head approval from distinct GitHub identity",
            reviewer=login,
            review_id=review_id,
        )

    same_author_approval = any(
        state == "APPROVED" and login == author
        for login, (_, _, state) in latest.items()
    )
    if same_author_approval:
        return ReviewDecision(
            ok=False,
            reason="same-account approval is not independent review authority",
        )
    return ReviewDecision(
        ok=False,
        reason="no exact-head approval from a GitHub identity distinct from the PR author",
    )


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def _request(self, path: str) -> tuple[Any, dict[str, str]]:
        connection = http.client.HTTPSConnection("api.github.com", timeout=30)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "veritas-review-provenance",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        if response.status < 200 or response.status >= 300:
            raise ProvenanceError(
                f"GitHub API GET {path} failed with HTTP {response.status}: {body[:300]}"
            )
        try:
            return json.loads(body), response_headers
        except json.JSONDecodeError as exc:
            raise ProvenanceError(f"GitHub API GET {path} returned invalid JSON") from exc
        finally:
            connection.close()

    def get_pr(self, repository: str, pr_number: int) -> dict[str, Any]:
        payload, _ = self._request(f"/repos/{repository}/pulls/{pr_number}")
        if not isinstance(payload, dict):
            raise ProvenanceError("GitHub pull request response is not an object")
        return payload

    def get_reviews(self, repository: str, pr_number: int) -> list[dict[str, Any]]:
        reviews: list[dict[str, Any]] = []
        page = 1
        while True:
            query = urlencode({"per_page": 100, "page": page})
            payload, _ = self._request(
                f"/repos/{repository}/pulls/{pr_number}/reviews?{query}"
            )
            if not isinstance(payload, list):
                raise ProvenanceError("GitHub review response is not a list")
            reviews.extend(payload)
            if len(payload) < 100:
                return reviews
            page += 1
            if page > 100:
                raise ProvenanceError("review pagination exceeded safety limit")


def check(repository: str, pr_number: int, expected_head: str, token: str) -> ReviewDecision:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ProvenanceError("repository must be owner/name")
    if pr_number <= 0:
        raise ProvenanceError("pull request number must be positive")
    if not SHA_RE.fullmatch(expected_head):
        raise ProvenanceError("expected head must be a full lowercase SHA")

    client = GitHubClient(token)
    pr = client.get_pr(repository, pr_number)
    head = pr.get("head")
    user = pr.get("user")
    if not isinstance(head, dict) or head.get("sha") != expected_head:
        raise ProvenanceError("pull request moved or head identity is malformed")
    if not isinstance(user, dict):
        raise ProvenanceError("pull request author identity is malformed")
    author = _valid_login(user.get("login"))
    reviews = client.get_reviews(repository, pr_number)
    return evaluate_reviews(pr_author=author, head_sha=expected_head, reviews=reviews)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    command = subparsers.add_parser("check", help="check one exact PR head")
    command.add_argument("--repository", required=True)
    command.add_argument("--pr", required=True, type=int)
    command.add_argument("--head", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("REVIEW_PROVENANCE_FAIL: GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    try:
        decision = check(args.repository, args.pr, args.head, token)
    except ProvenanceError as exc:
        print(f"REVIEW_PROVENANCE_FAIL: {exc}", file=sys.stderr)
        return 2
    if not decision.ok:
        print(f"REVIEW_PROVENANCE_FAIL: {decision.reason}", file=sys.stderr)
        return 2
    print(
        "REVIEW_PROVENANCE_PASS: "
        f"reviewer={decision.reviewer} review_id={decision.review_id} "
        f"head={args.head}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
