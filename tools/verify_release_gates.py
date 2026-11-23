"""Require completed exact-source CI/security before publishing release artifacts.

Run as ``python -m tools.verify_release_gates`` from the repository root. The
checkout must include current origin/main and tags (actions/checkout fetch-depth: 0).
No release, tag, workflow, or repository setting is changed by this command.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from tools.review_provenance import GitHubClient, ProvenanceError

# These are mandatory on the release commit, including a main push. PR-only
# review-refresh/dependency-review jobs are deliberately not success substitutes.
REQUIRED_JOBS = {
    "ci.yml": ("Required",),
    "security.yml": (
        "Python dependency audit", "Python source security", "Node dependency audit",
    ),
}


class ReleaseGateError(ProvenanceError):
    """The available evidence cannot authorize publication."""


class ReleaseGatesPending(ReleaseGateError):
    """Required exact-source evidence is absent or still running."""


def verify_source(
    source_commit: str, tag: str, ref: str, directory: Path | None = None,
) -> str | None:
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ReleaseGateError("release source must be a full lowercase commit SHA")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ReleaseGateError("release tag must match the canonical version")
    if ref not in {"refs/heads/main", f"refs/tags/{tag}"}:
        raise ReleaseGateError("release ref must be main or the canonical release tag")

    def git(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments], cwd=directory, capture_output=True, text=True,
            timeout=30, check=False,
        )

    head = git("rev-parse", "--verify", "HEAD")
    if head.returncode or head.stdout.strip() != source_commit:
        raise ReleaseGateError("checkout does not match the release source commit")
    if git("merge-base", "--is-ancestor", source_commit, "refs/remotes/origin/main").returncode:
        raise ReleaseGateError("release source is not present on origin/main")
    exists = git("show-ref", "--verify", "--quiet", f"refs/tags/{tag}")
    if exists.returncode == 1:
        if ref.startswith("refs/tags/"):
            raise ReleaseGateError("release tag ref is missing from checkout")
        return None
    if exists.returncode:
        raise ReleaseGateError("could not determine the release tag identity")
    target = git("rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    if target.returncode or target.stdout.strip() != source_commit:
        raise ReleaseGateError("release tag points to a different source commit")
    return source_commit


def _items(client: GitHubClient, path: str, key: str, **query: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    # GitHub caps filtered workflow-run searches at 1,000 results. Never accept
    # a truncated history that could omit a newer failed/running execution.
    for page in range(1, 11):
        params = urlencode({**query, "per_page": 100, "page": page})
        payload, _ = client._request(f"{path}?{params}")
        if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
            raise ReleaseGateError(f"malformed GitHub {key} response")
        total = payload.get("total_count")
        if type(total) is not int or not 0 <= total <= 1000:
            raise ReleaseGateError(f"GitHub {key} history is missing or exceeds 1,000 entries")
        rows = payload[key]
        if any(not isinstance(item, dict) for item in rows):
            raise ReleaseGateError(f"malformed GitHub {key} entry")
        items.extend(rows)
        if len(rows) < 100:
            if len(items) != total:
                raise ReleaseGateError(f"incomplete GitHub {key} history")
            return items
        if len(items) == total:
            return items
    raise ReleaseGateError(f"GitHub {key} pagination exceeded safety limit")


def _matches(run: dict[str, Any], workflow: str, head: str, tag: str | None) -> bool:
    branch = run.get("head_branch")
    event = run.get("event")
    # Dispatching the same commit through a research branch can change ref-based
    # job conditions. Such a run is not evidence for a main/tag release.
    allowed_ref = (
        branch == "main" and event in ("push", "workflow_dispatch", "schedule")
    ) or (tag is not None and branch == tag and event == "workflow_dispatch")
    return (
        run.get("head_sha") == head
        and str(run.get("path", "")).split("@", 1)[0] == f".github/workflows/{workflow}"
        and allowed_ref
    )


def check_workflows(
    client: GitHubClient, repository: str, head: str, tag: str | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ReleaseGateError("repository must be owner/name")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ReleaseGateError("release source must be a full lowercase commit SHA")
    if tag is not None and not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ReleaseGateError("release tag must match the canonical version")
    evidence = {}
    for workflow, required in REQUIRED_JOBS.items():
        runs = _items(
            client, f"/repos/{repository}/actions/workflows/{workflow}/runs",
            "workflow_runs", head_sha=head,
        )
        candidates = [run for run in runs if _matches(run, workflow, head, tag)]
        if not candidates:
            raise ReleaseGatesPending(f"{workflow}: no exact-source main/tag workflow evidence")
        if any(type(run.get("id")) is not int or run["id"] <= 0 for run in candidates):
            raise ReleaseGateError(f"{workflow}: malformed workflow identity")
        latest = max(candidates, key=lambda run: run["id"])
        run_id = latest["id"]
        path = f"/repos/{repository}/actions/runs/{run_id}"
        current, _ = client._request(path)
        if not isinstance(current, dict) or current.get("id") != run_id:
            raise ReleaseGateError(f"{workflow}: malformed workflow response")
        if not _matches(current, workflow, head, tag):
            raise ReleaseGateError(f"{workflow}: workflow source identity changed")
        if current.get("status") != "completed":
            raise ReleaseGatesPending(f"{workflow}: latest exact-source execution is not complete")
        if current.get("conclusion") != "success":
            raise ReleaseGateError(f"{workflow}: latest exact-source execution did not pass")
        attempt = current.get("run_attempt")
        if type(attempt) is not int or attempt <= 0:
            raise ReleaseGateError(f"{workflow}: missing workflow attempt identity")
        jobs = _items(client, f"{path}/attempts/{attempt}/jobs", "jobs")
        for name in required:
            matching = [job for job in jobs if job.get("name") == name]
            if len(matching) != 1 or any(
                job.get("status") != "completed" or job.get("conclusion") != "success"
                for job in matching
            ):
                raise ReleaseGateError(
                    f"{workflow}: required job {name!r} did not pass exactly once"
                )
        refreshed, _ = client._request(path)
        identity = (
            "id", "head_sha", "head_branch", "path", "event", "status", "conclusion", "run_attempt",
        )
        if not isinstance(refreshed, dict) or any(
            refreshed.get(key) != current.get(key) for key in identity
        ):
            raise ReleaseGatesPending(f"{workflow}: execution changed while checking jobs")
        evidence[workflow] = {
            "run_id": run_id, "run_attempt": attempt, "jobs": list(required),
            "url": f"https://github.com/{repository}/actions/runs/{run_id}",
        }
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if not 0 <= args.wait_seconds <= 1800:
            raise ReleaseGateError("wait must be between 0 and 1,800 seconds")
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise ReleaseGateError("GITHUB_TOKEN or GH_TOKEN is required")
        tag_target = verify_source(args.source_commit, args.tag, args.ref)
        client = GitHubClient(token)
        deadline = time.monotonic() + args.wait_seconds
        while True:
            try:
                workflows = check_workflows(client, args.repository, args.source_commit, args.tag)
                break
            except ReleaseGatesPending as error:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                print(f"Waiting for release gates: {error}", file=sys.stderr, flush=True)
                time.sleep(min(15, remaining))
        payload = {
            "schema": "veritas.release-gates.v1", "status": "passed",
            "repository": args.repository, "source_commit": args.source_commit,
            "tag": args.tag, "existing_tag_target": tag_target, "ref": args.ref,
            "checked_at": datetime.now(timezone.utc).isoformat(), "workflows": workflows,
        }
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        print(encoded, end="")
        return 0
    except (ProvenanceError, OSError, subprocess.SubprocessError) as error:
        print(f"Release blocked: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
