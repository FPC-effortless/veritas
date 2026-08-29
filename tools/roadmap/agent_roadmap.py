#!/usr/bin/env python3
"""Validate or refresh Veritas' checked-in agent-work roadmap."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

SCHEMA = "veritas.agent-roadmap.v1"
STATUS_SCHEMA = "veritas.agent-work-status.v1"
STATES = {"READY", "BLOCKED", "CLAIMED", "REVIEW", "DONE", "SUPERSEDED"}
ACTIVE = {"READY", "CLAIMED", "REVIEW"}
TRUSTED_STATUS_REQUIRED = {"CLAIMED", "REVIEW"}
SATISFIED = {"DONE", "SUPERSEDED"}
LABEL_STATE = {f"work:{state.lower()}": state for state in STATES}
MARKER = "<!-- veritas-agent-work -->"
STATUS_MARKER = "<!-- veritas-agent-work-status:v1 -->"
FIELD_RE = re.compile(r"^- \*\*(?P<key>[^*]+):\*\* (?P<value>.*)$", re.MULTILINE)
REF_RE = re.compile(r"(?<![\w/])#(\d+)\b")
TICK_RE = re.compile(r"`([^`]+)`")
STATUS_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class RoadmapError(ValueError):
    """Raised when roadmap metadata cannot be trusted."""


def load(path: Path) -> dict[str, Any]:
    """Load the JSON-compatible YAML roadmap."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RoadmapError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RoadmapError("roadmap root must be an object")
    return value


def reserves_exclusive_paths(row: dict[str, Any]) -> bool:
    """Return whether a row still reserves its declared exclusive paths."""
    state = row.get("state")
    if state in ACTIVE:
        return True
    claimant = row.get("claimant")
    return state == "BLOCKED" and isinstance(claimant, str) and bool(claimant.strip())


def validate(data: dict[str, Any]) -> list[str]:
    """Return deterministic validation errors."""
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA!r}")
    source_commit = data.get("source_commit")
    if not isinstance(source_commit, str) or COMMIT_RE.fullmatch(source_commit) is None:
        errors.append("source_commit must be a 40-character lowercase Git commit SHA")
    rows = data.get("work")
    if not isinstance(rows, list) or not rows:
        return errors + ["work must be a non-empty list"]

    by_id: dict[str, dict[str, Any]] = {}
    by_issue: dict[int, str] = {}
    names: dict[str, str] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"work[{index}] must be an object")
            continue
        work_id = row.get("work_id")
        if not isinstance(work_id, str) or not work_id:
            errors.append(f"work[{index}].work_id must be non-empty")
            continue
        if work_id in by_id or work_id in names:
            errors.append(f"duplicate Work ID/alias: {work_id}")
        by_id[work_id] = row
        names.setdefault(work_id, work_id)

        issue = row.get("issue")
        if not isinstance(issue, int) or issue <= 0:
            errors.append(f"{work_id}: issue must be positive")
        elif issue in by_issue:
            errors.append(f"duplicate issue #{issue}: {by_issue[issue]} and {work_id}")
        else:
            by_issue[issue] = work_id

        for key in ("title", "branch", "program", "wave"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                errors.append(f"{work_id}: {key} must be non-empty")
        if row.get("state") not in STATES:
            errors.append(f"{work_id}: invalid state {row.get('state')!r}")
        linked_pr = row.get("linked_pr")
        if linked_pr is not None and (
            not isinstance(linked_pr, int) or isinstance(linked_pr, bool) or linked_pr <= 0
        ):
            errors.append(f"{work_id}: linked_pr must be null or positive")

        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            errors.append(f"{work_id}: aliases must be a list")
        else:
            for alias in aliases:
                if not isinstance(alias, str) or not alias:
                    errors.append(f"{work_id}: alias must be non-empty")
                elif alias in names or alias in by_id:
                    errors.append(f"duplicate Work ID/alias: {alias}")
                else:
                    names[alias] = work_id

        ownership = row.get("ownership")
        if not isinstance(ownership, dict):
            errors.append(f"{work_id}: ownership must be an object")
        else:
            for key in ("positive_summary", "negative_summary"):
                value = ownership.get(key)
                if not isinstance(value, str) or not value.strip():
                    errors.append(f"{work_id}: ownership.{key} must be non-empty")
            paths = ownership.get("exclusive_paths")
            if not isinstance(paths, list) or any(
                not isinstance(path, str) or not path for path in paths
            ):
                errors.append(f"{work_id}: ownership.exclusive_paths must be string list")

        dependencies = row.get("dependencies")
        hard_dependencies = row.get("hard_dependencies")
        if not isinstance(dependencies, list) or any(
            not isinstance(dep, str) or not dep for dep in dependencies
        ):
            errors.append(f"{work_id}: dependencies must be Work ID list")
        if not isinstance(hard_dependencies, list) or any(
            not isinstance(dep, str) or not dep for dep in hard_dependencies
        ):
            errors.append(f"{work_id}: hard_dependencies must be Work ID list")
        elif isinstance(dependencies, list):
            for dep in hard_dependencies:
                if dep not in dependencies:
                    errors.append(f"{work_id}: hard dependency {dep} missing from dependencies")

    graph: dict[str, list[str]] = {}
    for work_id, row in by_id.items():
        graph[work_id] = []
        dependencies = row.get("dependencies", [])
        if isinstance(dependencies, list):
            for dep in dependencies:
                if dep not in by_id:
                    errors.append(f"{work_id}: missing roadmap dependency {dep}")
                else:
                    graph[work_id].append(dep)

    visiting: set[str] = set()
    done: set[str] = set()
    stack: list[str] = []

    def visit(work_id: str) -> None:
        if work_id in done:
            return
        if work_id in visiting:
            start = stack.index(work_id)
            errors.append(f"dependency cycle: {' -> '.join(stack[start:] + [work_id])}")
            return
        visiting.add(work_id)
        stack.append(work_id)
        for dep in graph.get(work_id, []):
            visit(dep)
        stack.pop()
        visiting.remove(work_id)
        done.add(work_id)

    for work_id in sorted(graph):
        visit(work_id)

    path_owner: dict[str, str] = {}
    for work_id, row in sorted(by_id.items()):
        if reserves_exclusive_paths(row):
            ownership = row.get("ownership", {})
            paths = ownership.get("exclusive_paths", []) if isinstance(ownership, dict) else []
            for path in paths:
                if path in path_owner and path_owner[path] != work_id:
                    errors.append(
                        f"direct ownership collision on {path}: {path_owner[path]} and {work_id}"
                    )
                else:
                    path_owner[path] = work_id

        if row.get("state") not in ACTIVE:
            continue
        hard_dependencies = row.get("hard_dependencies", [])
        if not isinstance(hard_dependencies, list):
            continue
        for dep in hard_dependencies:
            dep_row = by_id.get(dep)
            if dep_row is not None and dep_row.get("state") not in SATISFIED:
                errors.append(
                    f"{work_id}: active while hard dependency {dep} is {dep_row.get('state')}"
                )
    return sorted(set(errors))


def request_json(url: str, token: str | None) -> Any:
    """Fetch one GitHub REST JSON response and fail closed."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "veritas-roadmap-sync",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except Exception as exc:
        raise RoadmapError(f"GitHub request failed for {url}: {exc}") from exc


def fetch_issues(repo: str, token: str | None) -> list[dict[str, Any]]:
    """Fetch all non-PR GitHub issues carrying the agent-work label."""
    issues: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"https://api.github.com/repos/{repo}/issues"
            f"?state=all&labels=agent-work&per_page=100&page={page}"
        )
        batch = request_json(url, token)
        if not isinstance(batch, list):
            raise RoadmapError("GitHub issues response must be a list")
        issues.extend(
            item for item in batch if isinstance(item, dict) and "pull_request" not in item
        )
        if len(batch) < 100:
            return issues
        page += 1


def parse_contract(body: str, issue: int) -> dict[str, Any]:
    """Parse stable fields from an agent-work Work Contract."""
    if MARKER not in body:
        raise RoadmapError(f"issue #{issue}: missing agent-work marker")
    fields = {
        match.group("key").strip().lower().replace(" ", "_"): match.group("value").strip()
        for match in FIELD_RE.finditer(body)
    }
    required = {
        "work_id",
        "dependencies",
        "branch",
        "positive_ownership",
        "negative_ownership",
        "linked_pr",
    }
    missing = sorted(required - fields.keys())
    if missing:
        raise RoadmapError(
            f"issue #{issue}: missing Work Contract fields: {', '.join(missing)}"
        )
    ids = [part.strip() for part in fields["work_id"].split("/") if part.strip()]
    if not ids:
        raise RoadmapError(f"issue #{issue}: empty Work ID")
    linked = REF_RE.search(fields["linked_pr"])
    paths = sorted(
        {
            token.strip()
            for token in TICK_RE.findall(fields["positive_ownership"])
            if "/" in token
            or token in {"README.md", "BUILD_STATUS.md", "pyproject.toml"}
        }
    )
    return {
        "work_id": ids[0],
        "aliases": ids[1:],
        "branch": fields["branch"].strip("`"),
        "dependency_summary": fields["dependencies"],
        "refs": [int(value) for value in REF_RE.findall(fields["dependencies"])],
        "positive": fields["positive_ownership"],
        "negative": fields["negative_ownership"],
        "paths": paths,
        "linked_pr": int(linked.group(1)) if linked else None,
    }


def state_from_labels(issue: dict[str, Any], number: int) -> str:
    """Resolve live execution state from exactly one work:* label."""
    found = sorted(
        LABEL_STATE[label.get("name")]
        for label in issue.get("labels", [])
        if isinstance(label, dict) and label.get("name") in LABEL_STATE
    )
    if len(found) != 1:
        raise RoadmapError(f"issue #{number}: expected one work:* state label, got {found}")
    return found[0]


def status_record(repo: str, number: int, token: str | None) -> dict[str, Any] | None:
    """Return the latest trusted coordination status comment across all pages."""
    trusted: list[dict[str, Any]] = []
    page = 1
    while True:
        url = (
            f"https://api.github.com/repos/{repo}/issues/{number}/comments"
            f"?per_page=100&page={page}"
        )
        comments = request_json(url, token)
        if not isinstance(comments, list):
            raise RoadmapError(f"issue #{number}: comments response must be a list")
        for comment in comments:
            user = comment.get("user", {}) if isinstance(comment, dict) else {}
            body = comment.get("body", "") if isinstance(comment, dict) else ""
            if user.get("login") != "github-actions[bot]" or STATUS_MARKER not in body:
                continue
            match = STATUS_RE.search(body)
            if match is None:
                raise RoadmapError(f"issue #{number}: malformed trusted coordination status")
            try:
                record = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise RoadmapError(
                    f"issue #{number}: malformed trusted coordination status"
                ) from exc
            if not isinstance(record, dict) or record.get("schema_version") != STATUS_SCHEMA:
                raise RoadmapError(f"issue #{number}: invalid trusted coordination status schema")
            sequence = record.get("transition_seq")
            if not isinstance(sequence, int) or sequence < 0:
                raise RoadmapError(f"issue #{number}: invalid trusted transition sequence")
            trusted.append(record)
        if len(comments) < 100:
            break
        page += 1
    return max(trusted, key=lambda record: record["transition_seq"], default=None)


def dependency_name_map(
    parsed: list[tuple[dict[str, Any], dict[str, Any], str]],
) -> dict[str, str]:
    """Map live primary Work IDs and aliases to their canonical Work ID."""
    names: dict[str, str] = {}
    for _issue, contract, _state in parsed:
        primary = contract["work_id"]
        for name in [primary, *contract["aliases"]]:
            owner = names.get(name)
            if owner is not None and owner != primary:
                raise RoadmapError(f"duplicate live Work ID/alias: {name}")
            names[name] = primary
    return names


def derive_dependencies(
    contract: dict[str, Any],
    issue_to_id: dict[int, str],
    name_to_id: dict[str, str],
) -> list[str]:
    """Derive current dependency edges only from the live Work Contract."""
    dependencies = {issue_to_id[ref] for ref in contract["refs"] if ref in issue_to_id}
    summary = contract["dependency_summary"]
    for name, primary in name_to_id.items():
        pattern = rf"(?<![A-Za-z0-9_-]){re.escape(name)}(?![A-Za-z0-9_-])"
        if re.search(pattern, summary):
            dependencies.add(primary)
    return sorted(dependencies)


def status_state(status: dict[str, Any], *, issue_number: int, work_id: str) -> str:
    """Resolve execution state from a trusted status record."""
    if status.get("issue_number") != issue_number or status.get("work_id") != work_id:
        raise RoadmapError(f"issue #{issue_number}: trusted status identity mismatch")
    state = status.get("state")
    if state not in STATES:
        raise RoadmapError(f"issue #{issue_number}: trusted status has invalid state {state!r}")
    return str(state)


def validate_live_status(
    status: dict[str, Any],
    *,
    issue_number: int,
    work_id: str,
    state: str,
) -> tuple[str | None, str | None, int | None]:
    """Validate status fields that are authoritative for the live coordination state."""
    if (
        status.get("issue_number") != issue_number
        or status.get("work_id") != work_id
        or status.get("state") != state
    ):
        raise RoadmapError(f"issue #{issue_number}: trusted status disagrees with live issue")

    agent_id = status.get("agent_id")
    branch = status.get("branch")
    linked_pr = status.get("linked_pr")
    if agent_id is not None and (not isinstance(agent_id, str) or not agent_id.strip()):
        raise RoadmapError(f"issue #{issue_number}: trusted status has invalid agent_id")
    if branch is not None and (not isinstance(branch, str) or not branch.strip()):
        raise RoadmapError(f"issue #{issue_number}: trusted status has invalid branch")
    if linked_pr is not None and (
        not isinstance(linked_pr, int) or isinstance(linked_pr, bool) or linked_pr <= 0
    ):
        raise RoadmapError(f"issue #{issue_number}: trusted status has invalid linked_pr")

    if state in TRUSTED_STATUS_REQUIRED:
        if agent_id is None or branch is None:
            raise RoadmapError(f"issue #{issue_number}: {state} trusted status missing holder")
        if state == "CLAIMED" and linked_pr is not None:
            raise RoadmapError(f"issue #{issue_number}: CLAIMED trusted status has linked PR")
        if state == "REVIEW" and linked_pr is None:
            raise RoadmapError(f"issue #{issue_number}: REVIEW trusted status missing linked PR")

    if state == "BLOCKED":
        if agent_id is None:
            if branch is not None or linked_pr is not None:
                raise RoadmapError(
                    f"issue #{issue_number}: unowned BLOCKED status retains active metadata"
                )
        elif branch is None:
            raise RoadmapError(f"issue #{issue_number}: owner-held BLOCKED status missing branch")

    return agent_id, branch, linked_pr


def resolve_source_commit(explicit: str | None) -> str:
    """Require an exact authority commit instead of recycling stale manifest provenance."""
    source_commit = explicit or os.environ.get("GITHUB_SHA")
    if not isinstance(source_commit, str) or COMMIT_RE.fullmatch(source_commit) is None:
        raise RoadmapError(
            "source commit is required as --source-commit or GITHUB_SHA and must be "
            "a 40-character lowercase Git SHA"
        )
    return source_commit


def sync(
    current: dict[str, Any],
    repo: str,
    token: str | None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """Refresh issue-derived coordination fields while preserving curated policy."""
    authority_commit = resolve_source_commit(source_commit)
    issues = fetch_issues(repo, token)
    previous = {
        row.get("issue"): row
        for row in current.get("work", [])
        if isinstance(row, dict)
    }
    parsed: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    trusted_by_issue: dict[int, dict[str, Any]] = {}
    issue_to_id: dict[int, str] = {}
    for issue in issues:
        number = issue.get("number")
        body = issue.get("body")
        if not isinstance(number, int) or not isinstance(body, str):
            raise RoadmapError("agent-work issue missing number/body")
        contract = parse_contract(body, number)
        if number in issue_to_id or contract["work_id"] in issue_to_id.values():
            raise RoadmapError("duplicate live issue/Work ID")

        trusted = status_record(repo, number, token)
        if trusted is not None:
            state = status_state(trusted, issue_number=number, work_id=contract["work_id"])
            trusted_by_issue[number] = trusted
        else:
            state = state_from_labels(issue, number)

        issue_to_id[number] = contract["work_id"]
        parsed.append((issue, contract, state))

    name_to_id = dependency_name_map(parsed)
    rows: list[dict[str, Any]] = []
    for issue, contract, state in parsed:
        number = issue["number"]
        candidate = previous.get(number, {})
        old = candidate if isinstance(candidate, dict) else {}
        dependencies = derive_dependencies(contract, issue_to_id, name_to_id)
        old_hard = old.get("hard_dependencies", [])
        hard_dependencies = (
            [dep for dep in old_hard if dep in dependencies]
            if isinstance(old_hard, list)
            else []
        )

        linked_pr = contract["linked_pr"]
        branch = contract["branch"]
        claimant: str | None = None
        trusted = trusted_by_issue.get(number)
        if trusted is not None:
            claimant, status_branch, status_linked_pr = validate_live_status(
                trusted,
                issue_number=number,
                work_id=contract["work_id"],
                state=state,
            )
            linked_pr = status_linked_pr
            if status_branch is not None:
                branch = status_branch
        else:
            if state in TRUSTED_STATUS_REQUIRED:
                raise RoadmapError(f"issue #{number}: {state} missing trusted coordination status")
            if state == "BLOCKED":
                linked_pr = None

        rows.append(
            {
                "work_id": contract["work_id"],
                "aliases": contract["aliases"],
                "issue": number,
                "title": issue.get("title", contract["work_id"]),
                "state": state,
                "dependencies": dependencies,
                "hard_dependencies": hard_dependencies,
                "external_issue_dependencies": sorted(
                    ref for ref in contract["refs"] if ref not in issue_to_id
                ),
                "dependency_summary": contract["dependency_summary"],
                "branch": branch,
                "linked_pr": linked_pr,
                "claimant": claimant,
                "ownership": {
                    "positive_summary": contract["positive"],
                    "negative_summary": contract["negative"],
                    "exclusive_paths": contract["paths"],
                },
                "program": old.get("program", "UNASSIGNED"),
                "wave": old.get("wave", "UNASSIGNED"),
                "strategic_rank": old.get("strategic_rank"),
                "critical_path": bool(old.get("critical_path", False)),
            }
        )

    result = {
        "schema_version": SCHEMA,
        "repository": repo,
        "source_commit": authority_commit,
        "state_authority": current.get(
            "state_authority",
            {
                "execution": "trusted bot status when present; work:* label fallback otherwise",
                "qualification": "not_authoritative",
            },
        ),
        "work": sorted(rows, key=lambda row: row["issue"]),
    }
    errors = validate(result)
    if errors:
        raise RoadmapError("synchronized manifest invalid:\n- " + "\n- ".join(errors))
    return result


def build_parser() -> argparse.ArgumentParser:
    """Construct the command-line parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path(".github/agent-roadmap.yml"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument(
        "--repository",
        default=os.environ.get("GITHUB_REPOSITORY", "FPC-effortless/veritas"),
    )
    sync_parser.add_argument("--token-env", default="GITHUB_TOKEN")
    sync_parser.add_argument("--source-commit", default=os.environ.get("GITHUB_SHA"))
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run roadmap validation or synchronization."""
    args = build_parser().parse_args(argv)
    try:
        data = load(args.manifest)
        if args.command == "validate":
            errors = validate(data)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print(f"roadmap valid: {len(data['work'])} work items")
            return 0
        data = sync(
            data,
            args.repository,
            os.environ.get(args.token_env),
            args.source_commit,
        )
        args.manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"roadmap synchronized: {len(data['work'])} work items")
        return 0
    except RoadmapError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
