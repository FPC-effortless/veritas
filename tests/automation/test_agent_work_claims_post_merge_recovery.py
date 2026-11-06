from json import dumps, loads
from pathlib import Path
from subprocess import run

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
COORDINATOR = Path(".github/scripts/agent-work-claims.js")
OLD_HEAD = "1" * 40
FINAL_HEAD = "2" * 40
MERGE_SHA = "3" * 40

NODE_HARNESS = r"""
const fs = require('fs');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const fixture = payload.fixture;
const emitted = [];
const mutations = [];
const listComments = function listComments() {};
const listReviews = function listReviews() {};
const listWorkflowRunsForRepo = function listWorkflowRunsForRepo() {};

const github = {
  rest: {
    issues: {
      get: async () => ({ data: fixture.issue }),
      listComments,
      updateComment: async (args) => {
        mutations.push({ op: 'updateComment', args });
        return { data: {} };
      },
      removeLabel: async (args) => {
        mutations.push({ op: 'removeLabel', args });
        return { data: {} };
      },
      addLabels: async (args) => {
        mutations.push({ op: 'addLabels', args });
        return { data: {} };
      },
      createComment: async (args) => {
        emitted.push(args.body);
        mutations.push({ op: 'createComment', args });
        return { data: {} };
      },
    },
    pulls: {
      get: async () => ({ data: fixture.pr }),
      listReviews,
    },
    actions: { listWorkflowRunsForRepo },
    repos: {
      get: async () => ({ data: { default_branch: 'main' } }),
      compareCommitsWithBasehead: async () => ({ data: fixture.comparison }),
    },
  },
  paginate: async (fn, args) => {
    if (fn === listComments) {
      return args.issue_number === 150 ? fixture.root_comments : fixture.comments;
    }
    if (fn === listReviews) return fixture.reviews;
    if (fn === listWorkflowRunsForRepo) return fixture.runs;
    throw new Error('unexpected paginate target');
  },
};

const context = {
  repo: { owner: 'FPC-effortless', repo: 'veritas' },
  issue: { number: 322 },
  actor: fixture.actor,
  payload: {
    comment: {
      id: 9001,
      author_association: fixture.association,
      body: fixture.command,
    },
  },
};

(async () => {
  try {
    const runner = new AsyncFunction('github', 'context', 'core', payload.script);
    await runner(github, context, {});
    process.stdout.write(JSON.stringify({ ok: true, emitted, mutations }));
  } catch (error) {
    process.stdout.write(JSON.stringify({
      ok: false,
      error: error && error.message ? error.message : String(error),
      emitted,
      mutations,
    }));
  }
})();
"""


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _recovery_job() -> str:
    workflow = _workflow()
    assert "  recover-merged:\n" in workflow
    return workflow.split("  recover-merged:\n", 1)[1]


def _recovery_script() -> str:
    lines = _workflow().splitlines()
    marker = "      - name: Recover merged exact-head completion"
    start = lines.index(marker)
    script_line = next(
        index
        for index in range(start, len(lines))
        if lines[index] == "          script: |"
    )
    body = []
    for line in lines[script_line + 1 :]:
        if line and not line.startswith("            "):
            break
        body.append(line[12:] if line.startswith("            ") else "")
    script = "\n".join(body).rstrip() + "\n"
    assert "post-merge recovery requires repository OWNER authority" in script
    return script


def _marked_comment(marker, value, comment_id):
    return {
        "id": comment_id,
        "user": {"login": "github-actions[bot]"},
        "body": f"{marker}\n```json\n{dumps(value)}\n```",
    }


def _base_fixture():
    status = {
        "schema_version": "veritas.agent-work-status.v1",
        "work_id": "ROADMAP-REVIEW-PROVENANCE-002",
        "issue_number": 322,
        "state": "REVIEW",
        "github_actor": "FPC-effortless",
        "agent_id": "review-provenance-a1",
        "branch": "fix/review-provenance-gate",
        "linked_pr": 323,
        "linked_pr_head": OLD_HEAD,
        "ownership_paths": ["tools/review_provenance.py"],
        "transition_seq": 2,
    }
    registry = {
        "schema_version": "veritas.agent-work-reservations.v1",
        "updated_at": "2026-08-31T00:00:00Z",
        "entries": [{"issue": 322, "paths": ["tools/review_provenance.py"]}],
    }
    runs = []
    for index, name in enumerate(
        ["Security", "Python Quality Ratchet", "CI"],
        start=1,
    ):
        runs.append(
            {
                "name": name,
                "head_sha": FINAL_HEAD,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "success",
                "run_number": index,
                "run_attempt": 1,
                "id": 8000 + index,
            }
        )
    return {
        "actor": "FPC-effortless",
        "association": "OWNER",
        "command": (
            "/recover-merged review-provenance-a1 323 "
            "reconcile-final-head"
        ),
        "issue": {"labels": ["agent-work", "work:review"]},
        "comments": [
            _marked_comment(
                "<!-- veritas-agent-work-status:v1 -->",
                status,
                1001,
            )
        ],
        "root_comments": [
            _marked_comment(
                "<!-- veritas-agent-work-reservations:v1 -->",
                registry,
                1501,
            )
        ],
        "pr": {
            "state": "closed",
            "merged": True,
            "merged_at": "2026-08-31T01:00:00Z",
            "head": {
                "ref": "fix/review-provenance-gate",
                "sha": FINAL_HEAD,
            },
            "merge_commit_sha": MERGE_SHA,
            "user": {"login": "FPC-effortless"},
            "body": (
                "Fixes #322\n\n"
                "Work ID: ROADMAP-REVIEW-PROVENANCE-002"
            ),
        },
        "reviews": [
            {
                "state": "APPROVED",
                "commit_id": FINAL_HEAD,
                "user": {"login": "independent-reviewer"},
                "id": 7001,
                "submitted_at": "2026-08-31T01:01:00Z",
            }
        ],
        "runs": runs,
        "comparison": {"behind_by": 0, "status": "ahead"},
    }


def _run_recovery(fixture):
    completed = run(
        ["node", "-e", NODE_HARNESS],
        input=dumps(
            {"script": _recovery_script(), "fixture": fixture}
        ),
        capture_output=True,
        check=True,
        text=True,
    )
    result = loads(completed.stdout)
    assert isinstance(result, dict)
    return result


def _assert_rejected(fixture, expected):
    result = _run_recovery(fixture)
    assert result["ok"] is False
    assert expected in str(result["error"])
    assert any(
        "Rejected `recover-merged`" in body
        for body in result["emitted"]
    )


def test_recovery_is_separate_and_serialized():
    workflow = _workflow()
    coordinate = workflow.split("  coordinate:\n", 1)[1].split(
        "  recover-merged:\n", 1
    )[0]
    recovery = _recovery_job()
    needles = (
        "startsWith(github.event.comment.body, '/recover-merged ')",
        "group: agent-work-coordination",
        "cancel-in-progress: false",
        "actions: read",
        "contents: read",
        "issues: write",
        "pull-requests: read",
    )
    for needle in needles:
        assert needle in recovery
    assert "/recover-merged" not in coordinate


def test_recovery_accepts_only_fully_verified_case():
    result = _run_recovery(_base_fixture())
    assert result["ok"] is True
    operations = [item["op"] for item in result["mutations"]]
    assert operations.index("updateComment") < operations.index("addLabels")
    assert operations.count("updateComment") == 2
    assert any("→ **DONE**" in body for body in result["emitted"])


def test_recovery_rejects_wrong_actor_agent_pr_and_branch():
    cases = []

    fixture = _base_fixture()
    fixture["actor"] = "different-owner"
    cases.append((fixture, "current authenticated REVIEW holder"))

    fixture = _base_fixture()
    fixture["command"] = "/recover-merged other-agent 323 reason"
    cases.append((fixture, "current authenticated REVIEW holder"))

    fixture = _base_fixture()
    fixture["command"] = (
        "/recover-merged review-provenance-a1 324 reason"
    )
    cases.append((fixture, "PR mismatch"))

    fixture = _base_fixture()
    fixture["pr"]["head"]["ref"] = "wrong-branch"
    cases.append((fixture, "does not match trusted branch"))

    for fixture, expected in cases:
        _assert_rejected(fixture, expected)


def test_recovery_rejects_non_owner_and_unmerged_pr():
    fixture = _base_fixture()
    fixture["association"] = "MEMBER"
    _assert_rejected(
        fixture,
        "requires repository OWNER authority",
    )

    fixture = _base_fixture()
    fixture["pr"]["merged"] = False
    _assert_rejected(fixture, "PR #323 is not merged")


def test_recovery_rejects_same_author_or_stale_review():
    fixture = _base_fixture()
    fixture["reviews"][0]["user"]["login"] = "FPC-effortless"
    _assert_rejected(
        fixture,
        "no exact-head approval from a GitHub identity distinct",
    )

    fixture = _base_fixture()
    fixture["reviews"][0]["commit_id"] = OLD_HEAD
    _assert_rejected(
        fixture,
        "no exact-head approval from a GitHub identity distinct",
    )


def test_recovery_rejects_changes_requested_on_final_head():
    fixture = _base_fixture()
    fixture["reviews"].append(
        {
            "state": "CHANGES_REQUESTED",
            "commit_id": FINAL_HEAD,
            "user": {"login": "blocking-reviewer"},
            "id": 7002,
            "submitted_at": "2026-08-31T01:02:00Z",
        }
    )
    _assert_rejected(
        fixture,
        "exact-head changes requested by blocking-reviewer",
    )


def test_recovery_rejects_missing_or_failed_required_gate():
    fixture = _base_fixture()
    fixture["runs"] = [
        run for run in fixture["runs"] if run["name"] != "Security"
    ]
    _assert_rejected(
        fixture,
        "missing exact-head Security workflow run",
    )

    fixture = _base_fixture()
    ci_run = next(
        run for run in fixture["runs"] if run["name"] == "CI"
    )
    ci_run["conclusion"] = "failure"
    _assert_rejected(
        fixture,
        "exact-head CI is completed/failure",
    )


def test_recovery_rejects_merge_not_on_current_main():
    fixture = _base_fixture()
    fixture["comparison"] = {
        "behind_by": 1,
        "status": "diverged",
    }
    _assert_rejected(
        fixture,
        "merge is not on current main",
    )


def test_recovery_preserves_done_head_invariant():
    coordinator = COORDINATOR.read_text(encoding="utf-8")
    done_guard = (
        "PR #${command.pr} head moved after handoff; "
        "re-handoff/review exact final head before DONE"
    )
    assert done_guard in coordinator

    fixture = _base_fixture()
    body = fixture["comments"][0]["body"]
    fixture["comments"][0]["body"] = body.replace(
        OLD_HEAD,
        FINAL_HEAD,
    )
    _assert_rejected(
        fixture,
        "ordinary /done owns exact-head completion",
    )
