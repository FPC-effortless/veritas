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
STATES = {"READY", "BLOCKED", "CLAIMED", "REVIEW", "DONE", "SUPERSEDED"}
ACTIVE = {"READY", "CLAIMED", "REVIEW"}
SATISFIED = {"DONE", "SUPERSEDED"}
LABEL_STATE = {f"work:{s.lower()}": s for s in STATES}
MARKER = "<!-- veritas-agent-work -->"
STATUS_MARKER = "<!-- veritas-agent-work-status:v1 -->"
FIELD_RE = re.compile(r"^- \*\*(?P<key>[^*]+):\*\* (?P<value>.*)$", re.M)
REF_RE = re.compile(r"(?<![\w/])#(\d+)\b")
TICK_RE = re.compile(r"`([^`]+)`")
STATUS_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


class RoadmapError(ValueError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RoadmapError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RoadmapError("roadmap root must be an object")
    return value


def validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA!r}")
    rows = data.get("work")
    if not isinstance(rows, list) or not rows:
        return errors + ["work must be a non-empty list"]

    by_id: dict[str, dict[str, Any]] = {}
    by_issue: dict[int, str] = {}
    names: dict[str, str] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"work[{i}] must be an object")
            continue
        wid = row.get("work_id")
        if not isinstance(wid, str) or not wid:
            errors.append(f"work[{i}].work_id must be non-empty")
            continue
        if wid in by_id or wid in names:
            errors.append(f"duplicate Work ID/alias: {wid}")
        by_id[wid] = row
        names.setdefault(wid, wid)
        issue = row.get("issue")
        if not isinstance(issue, int) or issue <= 0:
            errors.append(f"{wid}: issue must be positive")
        elif issue in by_issue:
            errors.append(f"duplicate issue #{issue}: {by_issue[issue]} and {wid}")
        else:
            by_issue[issue] = wid
        for key in ("title", "branch", "program", "wave"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                errors.append(f"{wid}: {key} must be non-empty")
        if row.get("state") not in STATES:
            errors.append(f"{wid}: invalid state {row.get('state')!r}")
        if row.get("linked_pr") is not None and (
            not isinstance(row["linked_pr"], int) or row["linked_pr"] <= 0
        ):
            errors.append(f"{wid}: linked_pr must be null or positive")
        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            errors.append(f"{wid}: aliases must be a list")
        else:
            for alias in aliases:
                if not isinstance(alias, str) or not alias:
                    errors.append(f"{wid}: alias must be non-empty")
                elif alias in names or alias in by_id:
                    errors.append(f"duplicate Work ID/alias: {alias}")
                else:
                    names[alias] = wid
        own = row.get("ownership")
        if not isinstance(own, dict):
            errors.append(f"{wid}: ownership must be an object")
        else:
            for key in ("positive_summary", "negative_summary"):
                if not isinstance(own.get(key), str) or not own[key].strip():
                    errors.append(f"{wid}: ownership.{key} must be non-empty")
            paths = own.get("exclusive_paths")
            if not isinstance(paths, list) or any(not isinstance(p, str) or not p for p in paths):
                errors.append(f"{wid}: ownership.exclusive_paths must be string list")
        deps, hard = row.get("dependencies"), row.get("hard_dependencies")
        if not isinstance(deps, list) or any(not isinstance(d, str) or not d for d in deps):
            errors.append(f"{wid}: dependencies must be Work ID list")
        if not isinstance(hard, list) or any(not isinstance(d, str) or not d for d in hard):
            errors.append(f"{wid}: hard_dependencies must be Work ID list")
        elif isinstance(deps, list):
            errors.extend(f"{wid}: hard dependency {d} missing from dependencies" for d in hard if d not in deps)

    graph: dict[str, list[str]] = {}
    for wid, row in by_id.items():
        deps = row.get("dependencies", [])
        graph[wid] = []
        if isinstance(deps, list):
            for dep in deps:
                if dep not in by_id:
                    errors.append(f"{wid}: missing roadmap dependency {dep}")
                else:
                    graph[wid].append(dep)

    visiting: set[str] = set()
    done: set[str] = set()
    stack: list[str] = []
    def visit(wid: str) -> None:
        if wid in done:
            return
        if wid in visiting:
            start = stack.index(wid)
            errors.append("dependency cycle: " + " -> ".join(stack[start:] + [wid]))
            return
        visiting.add(wid); stack.append(wid)
        for dep in graph.get(wid, []): visit(dep)
        stack.pop(); visiting.remove(wid); done.add(wid)
    for wid in sorted(graph): visit(wid)

    # ROADMAP-002 checks exact active claims only. Parent/glob and live PR overlap
    # remain ROADMAP-004 / ROADMAP-LOCK-001 responsibilities.
    owner: dict[str, str] = {}
    for wid, row in sorted(by_id.items()):
        if row.get("state") not in ACTIVE:
            continue
        own = row.get("ownership", {})
        for path in own.get("exclusive_paths", []) if isinstance(own, dict) else []:
            if path in owner and owner[path] != wid:
                errors.append(f"direct ownership collision on {path}: {owner[path]} and {wid}")
            else:
                owner[path] = wid
        for dep in row.get("hard_dependencies", []) if isinstance(row.get("hard_dependencies"), list) else []:
            if dep in by_id and by_id[dep].get("state") not in SATISFIED:
                errors.append(f"{wid}: active while hard dependency {dep} is {by_id[dep].get('state')}")
    return sorted(set(errors))


def request_json(url: str, token: str | None) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "veritas-roadmap-sync", "X-GitHub-Api-Version": "2022-11-28"}
    if token: headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            return json.load(response)
    except Exception as exc:  # network/API errors must fail closed
        raise RoadmapError(f"GitHub request failed for {url}: {exc}") from exc


def fetch_issues(repo: str, token: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = request_json(f"https://api.github.com/repos/{repo}/issues?state=all&labels=agent-work&per_page=100&page={page}", token)
        if not isinstance(batch, list): raise RoadmapError("GitHub issues response must be a list")
        out.extend(x for x in batch if isinstance(x, dict) and "pull_request" not in x)
        if len(batch) < 100: return out
        page += 1


def parse_contract(body: str, issue: int) -> dict[str, Any]:
    if MARKER not in body: raise RoadmapError(f"issue #{issue}: missing agent-work marker")
    fields = {m.group("key").strip().lower().replace(" ", "_"): m.group("value").strip() for m in FIELD_RE.finditer(body)}
    required = {"work_id", "dependencies", "branch", "positive_ownership", "negative_ownership", "linked_pr"}
    missing = sorted(required - fields.keys())
    if missing: raise RoadmapError(f"issue #{issue}: missing Work Contract fields: {', '.join(missing)}")
    ids = [x.strip() for x in fields["work_id"].split("/") if x.strip()]
    linked = REF_RE.search(fields["linked_pr"])
    paths = sorted(set(x.strip() for x in TICK_RE.findall(fields["positive_ownership"]) if "/" in x or x in {"README.md", "BUILD_STATUS.md", "pyproject.toml"}))
    return {"work_id": ids[0], "aliases": ids[1:], "branch": fields["branch"].strip("`"), "dependency_summary": fields["dependencies"], "refs": [int(x) for x in REF_RE.findall(fields["dependencies"])], "positive": fields["positive_ownership"], "negative": fields["negative_ownership"], "paths": paths, "linked_pr": int(linked.group(1)) if linked else None}


def state_from_labels(issue: dict[str, Any], number: int) -> str:
    found = sorted(LABEL_STATE[x.get("name")] for x in issue.get("labels", []) if isinstance(x, dict) and x.get("name") in LABEL_STATE)
    if len(found) != 1: raise RoadmapError(f"issue #{number}: expected one work:* state label, got {found}")
    return found[0]


def status_record(repo: str, number: int, token: str | None) -> dict[str, Any] | None:
    comments = request_json(f"https://api.github.com/repos/{repo}/issues/{number}/comments?per_page=100", token)
    trusted: list[dict[str, Any]] = []
    for comment in comments if isinstance(comments, list) else []:
        user = comment.get("user", {}) if isinstance(comment, dict) else {}
        body = comment.get("body", "") if isinstance(comment, dict) else ""
        if user.get("login") != "github-actions[bot]" or STATUS_MARKER not in body: continue
        match = STATUS_RE.search(body)
        if match:
            try: record = json.loads(match.group(1))
            except json.JSONDecodeError: continue
            if isinstance(record, dict): trusted.append(record)
    return max(trusted, key=lambda x: int(x.get("transition_seq", -1)), default=None)


def sync(current: dict[str, Any], repo: str, token: str | None) -> dict[str, Any]:
    issues = fetch_issues(repo, token)
    previous = {x.get("issue"): x for x in current.get("work", []) if isinstance(x, dict)}
    parsed: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    issue_id: dict[int, str] = {}
    for issue in issues:
        number, body = issue.get("number"), issue.get("body")
        if not isinstance(number, int) or not isinstance(body, str): raise RoadmapError("agent-work issue missing number/body")
        contract = parse_contract(body, number); state = state_from_labels(issue, number)
        if number in issue_id or contract["work_id"] in issue_id.values(): raise RoadmapError("duplicate live issue/Work ID")
        issue_id[number] = contract["work_id"]; parsed.append((issue, contract, state))
    known = set(issue_id.values()); rows: list[dict[str, Any]] = []
    for issue, contract, state in parsed:
        number = issue["number"]; old = previous.get(number, {}) if isinstance(previous.get(number, {}), dict) else {}
        deps = [issue_id[r] for r in contract["refs"] if r in issue_id]
        deps += [d for d in old.get("dependencies", []) if isinstance(d, str) and d in known]
        deps = sorted(set(deps)); hard = [d for d in old.get("hard_dependencies", []) if d in deps]
        pr, branch, claimant = contract["linked_pr"], contract["branch"], old.get("claimant")
        status = status_record(repo, number, token) if state in {"CLAIMED", "REVIEW"} else None
        if status:
            if status.get("issue_number") != number or status.get("work_id") != contract["work_id"] or status.get("state") != state:
                raise RoadmapError(f"issue #{number}: trusted status disagrees with live issue")
            if isinstance(status.get("linked_pr"), int): pr = status["linked_pr"]
            if isinstance(status.get("branch"), str) and status["branch"]: branch = status["branch"]
            if isinstance(status.get("agent_id"), str) and status["agent_id"]: claimant = status["agent_id"]
        rows.append({"work_id": contract["work_id"], "aliases": contract["aliases"], "issue": number, "title": issue.get("title", contract["work_id"]), "state": state, "dependencies": deps, "hard_dependencies": hard, "external_issue_dependencies": sorted(r for r in contract["refs"] if r not in issue_id), "dependency_summary": contract["dependency_summary"], "branch": branch, "linked_pr": pr, "claimant": claimant, "ownership": {"positive_summary": contract["positive"], "negative_summary": contract["negative"], "exclusive_paths": contract["paths"]}, "program": old.get("program", "UNASSIGNED"), "wave": old.get("wave", "UNASSIGNED"), "strategic_rank": old.get("strategic_rank"), "critical_path": bool(old.get("critical_path", False))})
    result = {"schema_version": SCHEMA, "repository": repo, "source_commit": current.get("source_commit"), "state_authority": current.get("state_authority", {"execution": "GitHub work:* labels + trusted bot status", "qualification": "not_authoritative"}), "work": sorted(rows, key=lambda x: x["issue"])}
    errors = validate(result)
    if errors: raise RoadmapError("synchronized manifest invalid:\n- " + "\n- ".join(errors))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, default=Path(".github/agent-roadmap.yml"))
    sub = parser.add_subparsers(dest="command", required=True); sub.add_parser("validate"); s = sub.add_parser("sync"); s.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", "FPC-effortless/veritas")); s.add_argument("--token-env", default="GITHUB_TOKEN")
    args = parser.parse_args(argv)
    try:
        data = load(args.manifest)
        if args.command == "validate":
            errors = validate(data)
            if errors:
                print("\n".join(errors), file=sys.stderr); return 1
            print(f"roadmap valid: {len(data['work'])} work items"); return 0
        data = sync(data, args.repository, os.environ.get(args.token_env)); args.manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8"); print(f"roadmap synchronized: {len(data['work'])} work items"); return 0
    except RoadmapError as exc:
        print(exc, file=sys.stderr); return 1


if __name__ == "__main__": raise SystemExit(main())
