from copy import deepcopy
from json import dumps, loads
from pathlib import Path
from subprocess import run

from tools.review_provenance import evaluate_reviews

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
COORDINATOR = Path(".github/scripts/agent-work-claims.js")
OLD_HEAD = "1" * 40
FINAL_HEAD = "2" * 40
MERGE_SHA = "3" * 40

NODE_HARNESS = r"""
const fs = require('fs');
const childProcess = require('node:child_process');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
const fixture = payload.fixture;
const emitted = [];
const mutations = [];
const execFileCalls = [];
const listComments = function listComments() {};
const listReviews = function listReviews() {};
const listWorkflowRunsForRepo = function listWorkflowRunsForRepo() {};

childProcess.execFileSync = (file, args, options) => {
  execFileCalls.push({ file, args, options: { ...options, env: undefined } });
  if (fixture.canonical_review.error) {
    const error = new Error('canonical checker failed');
    error.stderr = fixture.canonical_review.error;
    throw error;
  }
  return (
    `REVIEW_PROVENANCE_PASS: reviewer=${fixture.canonical_review.reviewer} ` +
    `review_id=${fixture.canonical_review.review_id} ` +
    `head=${fixture.canonical_review.head} ` +
    `reason=${fixture.canonical_review.reason}\n`
  );
};

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
  issue: { number: fixture.issue_number },
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
    process.stdout.write(JSON.stringify({ ok: true, emitted, mutations, execFileCalls }));
  } catch (error) {
    process.stdout.write(JSON.stringify({
      ok: false,
      error: error && error.message ? error.message : String(error),
      emitted,
      mutations,
      execFileCalls,
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


def _clean_agent_review(*, head=FINAL_HEAD, review_id=7001):
    return {
        "state": "COMMENTED",
        "commit_id": head,
        "user": {"login": "FPC-effortless"},
        "id": review_id,
        "submitted_at": "2026-09-04T21:16:15Z",
        "body": (
            f"<!-- veritas-agent-review:v1 head={head} verdict=clean -->\n\n"
            "Fresh exact-head review found no merge-precluding defect."
        ),
    }


def _base_fixture():
    status = {
        "schema_version": "veritas.agent-work-status.v1",
        "work_id": "ROADMAP-001 / GOLD-001-PILOT",
        "issue_number": 152,
        "state": "REVIEW",
        "github_actor": "FPC-effortless",
        "agent_id": "chatgpt-sol-gold10-pilot",
        "branch": "feat/gold10-pilot",
        "linked_pr": 354,
        "linked_pr_head": OLD_HEAD,
        "ownership_paths": [
            "data/gold10/pilot/**",
            "docs/investigation_data/gold10-pilot/**",
            "src/investigation_world/gold10/**",
            "tests/gold10/**",
        ],
        "transition_seq": 9,
    }
    registry = {
        "schema_version": "veritas.agent-work-reservations.v1",
        "updated_at": "2026-09-04T21:00:00Z",
        "entries": [{"issue": 152, "paths": status["ownership_paths"]}],
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
    review = _clean_agent_review()
    return {
        "issue_number": 152,
        "actor": "FPC-effortless",
        "association": "OWNER",
        "command": (
            "/recover-merged chatgpt-sol-gold10-pilot 354 "
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
            "merged_at": "2026-09-04T21:19:25Z",
            "head": {"ref": "feat/gold10-pilot", "sha": FINAL_HEAD},
            "merge_commit_sha": MERGE_SHA,
            "user": {"login": "FPC-effortless"},
            "body": "Implements ROADMAP-001 / #152 on the claimed lane.",
        },
        "reviews": [review],
        "canonical_review": {
            "head": FINAL_HEAD,
            "reviewer": "FPC-effortless",
            "review_id": 7001,
            "reason": "exact-head clean agent-session semantic review",
            "error": None,
        },
        "runs": runs,
        "comparison": {"behind_by": 0, "status": "ahead"},
    }


def _run_recovery(fixture):
    completed = run(
        ["node", "-e", NODE_HARNESS],
        input=dumps({"script": _recovery_script(), "fixture": fixture}),
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


def test_recovery_is_separate_serialized_and_delegates_review_authority():
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
        "- uses: actions/checkout@v4",
        "Resolve canonical exact-head review provenance",
        "tools/review_provenance.py",
        "REVIEW_PROVENANCE_PASS:",
        "node:child_process",
        "execFileSync",
    )
    for needle in needles:
        assert needle in recovery
    assert "/recover-merged" not in coordinate
    assert "exactHeadApproval" not in recovery
    assert "DECISIVE_REVIEW_STATES" not in recovery


def test_recovery_never_routes_untrusted_comment_through_a_shell():
    workflow = _workflow()
    assert "uses: actions/github-script@v7" in workflow
    assert "shell:" not in workflow
    assert "run:" not in workflow

    result = _run_recovery(_base_fixture())
    assert len(result["execFileCalls"]) == 1
    call = result["execFileCalls"][0]
    assert call["file"] == "python3"
    assert call["args"] == [
        "tools/review_provenance.py",
        "check",
        "--repository",
        "FPC-effortless/veritas",
        "--pr",
        "354",
        "--head",
        FINAL_HEAD,
    ]
    assert "shell" not in call["options"]


def test_recovery_accepts_production_shape_with_canonical_clean_agent_review():
    result = _run_recovery(_base_fixture())
    assert result["ok"] is True
    operations = [item["op"] for item in result["mutations"]]
    assert operations.index("updateComment") < operations.index("addLabels")
    assert operations.count("updateComment") == 2
    assert any("→ **DONE**" in body for body in result["emitted"])
    status_update = next(
        item
        for item in result["mutations"]
        if item["op"] == "updateComment" and item["args"]["comment_id"] == 1001
    )
    assert FINAL_HEAD in status_update["args"]["body"]
    assert '"review_id": 7001' in status_update["args"]["body"]
    assert "veritas.owner-post-merge-head-recovery.v2" in status_update["args"]["body"]


def test_recovery_uses_primary_work_id_like_ordinary_handoff():
    fixture = _base_fixture()
    fixture["pr"]["body"] = "Implements ROADMAP-001 / #152."
    assert _run_recovery(fixture)["ok"] is True

    fixture = _base_fixture()
    fixture["pr"]["body"] = "Implements #152 but omits the work ID."
    _assert_rejected(fixture, "must reference both #152 and work ID ROADMAP-001")


def test_recovery_rejects_wrong_actor_agent_pr_and_branch():
    cases = []

    fixture = _base_fixture()
    fixture["actor"] = "different-owner"
    cases.append((fixture, "current authenticated REVIEW holder"))

    fixture = _base_fixture()
    fixture["command"] = "/recover-merged other-agent 354 reason"
    cases.append((fixture, "current authenticated REVIEW holder"))

    fixture = _base_fixture()
    fixture["command"] = (
        "/recover-merged chatgpt-sol-gold10-pilot 355 reason"
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
    _assert_rejected(fixture, "requires repository OWNER authority")

    fixture = _base_fixture()
    fixture["pr"]["merged"] = False
    _assert_rejected(fixture, "PR #354 is not merged")


def test_recovery_rejects_canonical_output_identity_mismatch():
    fixture = _base_fixture()
    fixture["canonical_review"]["head"] = OLD_HEAD
    _assert_rejected(fixture, "canonical review checker returned a stale head")

    fixture = _base_fixture()
    fixture["canonical_review"]["review_id"] = 7999
    _assert_rejected(fixture, "canonical review #7999 is missing")

    fixture = _base_fixture()
    fixture["canonical_review"]["reviewer"] = "different-reviewer"
    _assert_rejected(fixture, "reviewer identity changed")

    fixture = _base_fixture()
    fixture["canonical_review"]["error"] = "REVIEW_PROVENANCE_FAIL: blocking review"
    _assert_rejected(fixture, "canonical exact-head review provenance failed")


def test_canonical_checker_accepts_clean_agent_review_and_rejects_blockers():
    clean = _clean_agent_review()
    decision = evaluate_reviews(
        pr_author="FPC-effortless",
        head_sha=FINAL_HEAD,
        reviews=[clean],
    )
    assert decision.ok is True
    assert decision.review_id == 7001

    blocking = deepcopy(clean)
    blocking["id"] = 7002
    blocking["body"] = (
        f"<!-- veritas-agent-review:v1 head={FINAL_HEAD} verdict=blocking -->\n\n"
        "BLOCKING: deterministic finding"
    )
    decision = evaluate_reviews(
        pr_author="FPC-effortless",
        head_sha=FINAL_HEAD,
        reviews=[blocking],
    )
    assert decision.ok is False

    stale = _clean_agent_review(head=OLD_HEAD)
    decision = evaluate_reviews(
        pr_author="FPC-effortless",
        head_sha=FINAL_HEAD,
        reviews=[stale],
    )
    assert decision.ok is False

    changes_requested = {
        "state": "CHANGES_REQUESTED",
        "commit_id": FINAL_HEAD,
        "user": {"login": "independent-reviewer"},
        "id": 7003,
        "submitted_at": "2026-09-04T21:17:00Z",
        "body": "Request changes",
    }
    decision = evaluate_reviews(
        pr_author="FPC-effortless",
        head_sha=FINAL_HEAD,
        reviews=[clean, changes_requested],
    )
    assert decision.ok is False

    inline_finding = {
        "pull_request_review_id": 7001,
        "commit_id": FINAL_HEAD,
        "user": {"login": "FPC-effortless"},
    }
    decision = evaluate_reviews(
        pr_author="FPC-effortless",
        head_sha=FINAL_HEAD,
        reviews=[clean],
        review_comments=[inline_finding],
    )
    assert decision.ok is False


def test_recovery_rejects_missing_or_failed_required_gate():
    fixture = _base_fixture()
    fixture["runs"] = [
        item for item in fixture["runs"] if item["name"] != "Security"
    ]
    _assert_rejected(fixture, "missing exact-head Security workflow run")

    fixture = _base_fixture()
    ci_run = next(item for item in fixture["runs"] if item["name"] == "CI")
    ci_run["conclusion"] = "failure"
    _assert_rejected(fixture, "exact-head CI is completed/failure")


def test_recovery_rejects_merge_not_on_current_main():
    fixture = _base_fixture()
    fixture["comparison"] = {"behind_by": 1, "status": "diverged"}
    _assert_rejected(fixture, "merge is not on current main")


def test_recovery_preserves_done_head_invariant():
    coordinator = COORDINATOR.read_text(encoding="utf-8")
    done_guard = (
        "PR #${command.pr} head moved after handoff; "
        "re-handoff/review exact final head before DONE"
    )
    assert done_guard in coordinator

    fixture = _base_fixture()
    body = fixture["comments"][0]["body"]
    fixture["comments"][0]["body"] = body.replace(OLD_HEAD, FINAL_HEAD)
    _assert_rejected(
        fixture,
        "ordinary /done owns exact-head completion",
    )
