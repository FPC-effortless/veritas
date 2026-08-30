import json
import subprocess
from pathlib import Path

WORKFLOW = Path(".github/workflows/roadmap-dependency-notifications.yml")
SCRIPT = Path(".github/scripts/roadmap-dependency-notifications.js")


def _run_node(source: str) -> None:
    result = subprocess.run(
        ["node", "-e", source],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"node harness failed with exit {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def test_workflow_is_serialized_and_least_privilege() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "push:" in text
    assert "types: [closed]" in text
    assert "contents: read" in text
    assert "issues: write" in text
    assert "pull-requests: read" in text
    assert "group: agent-work-coordination" in text
    assert "cancel-in-progress: false" in text
    assert "actions: write" not in text
    assert "contents: write" not in text
    assert "secrets:" not in text
    assert "roadmap-dependency-notifications.js" in text


def test_reconciler_is_fail_closed_collision_safe_and_idempotent() -> None:
    script_path = json.dumps(str(SCRIPT.resolve()))
    source = r"""
const fs = require('fs');
const STATUS = '<!-- veritas-agent-work-status:v1 -->';
const REGISTRY = '<!-- veritas-agent-work-reservations:v1 -->';
const ENROLL = '<!-- veritas-agent-work -->';
const MAIN = 'a'.repeat(40);
const HEAD_A = 'b'.repeat(40);
const HEAD_B = 'c'.repeat(40);
const MERGE_A = 'd'.repeat(40);
const MERGE_B = 'e'.repeat(40);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const roadmap = {
  schema_version: 'veritas.agent-roadmap.v1',
  work: [
    {
      work_id: 'ROADMAP-002',
      issue: 196,
      program: 'coordination',
      hard_dependencies: [],
    },
    {
      work_id: 'ROADMAP-AUDIT-001',
      issue: 209,
      program: 'coordination',
      hard_dependencies: [],
    },
    {
      work_id: 'ROADMAP-PROGRAM-001',
      issue: 239,
      program: 'coordination',
      hard_dependencies: ['ROADMAP-002', 'ROADMAP-AUDIT-001'],
    },
  ],
};

const originalRead = fs.readFileSync;
fs.readFileSync = (path, encoding) => {
  if (String(path).endsWith('.github/agent-roadmap.yml')) {
    return JSON.stringify(roadmap);
  }
  return originalRead(path, encoding);
};
const reconcile = require(__SCRIPT__);

function statusComment(id, status) {
  return {
    id,
    user: { login: 'github-actions[bot]' },
    body: `${STATUS}\n**Agent work status**\n\n` +
      `\`\`\`json\n${JSON.stringify(status, null, 2)}\n\`\`\``,
  };
}

function registryComment(entries) {
  const payload = {
    schema_version: 'veritas.agent-work-reservations.v1',
    updated_at: '2026-08-30T00:00:00Z',
    entries,
  };
  return {
    id: 900,
    user: { login: 'github-actions[bot]' },
    body: `${REGISTRY}\n\`\`\`json\n` +
      `${JSON.stringify(payload, null, 2)}\n\`\`\``,
  };
}

function doneStatus(issue, workId, pr, head) {
  return {
    schema_version: 'veritas.agent-work-status.v1',
    work_id: workId,
    issue_number: issue,
    state: 'DONE',
    github_actor: 'FPC-effortless',
    agent_id: 'provider-agent',
    branch: `provider-${issue}`,
    claimed_at: '2026-08-30T00:00:00Z',
    heartbeat_at: '2026-08-30T00:01:00Z',
    linked_pr: pr,
    linked_pr_head: head,
    ownership_paths: [`docs/provider-${issue}.md`],
    blocker: null,
    released_reason: null,
    return_state: 'READY',
    transition_seq: 2,
    last_command_comment_id: 10,
    updated_at: '2026-08-30T00:02:00Z',
  };
}

function blockedStatus(holder = false) {
  return {
    schema_version: 'veritas.agent-work-status.v1',
    work_id: 'ROADMAP-PROGRAM-001',
    issue_number: 239,
    state: 'BLOCKED',
    github_actor: holder ? 'FPC-effortless' : null,
    agent_id: holder ? 'holder' : null,
    branch: holder ? 'audit/full-roadmap-coverage' : null,
    claimed_at: holder ? '2026-08-30T00:00:00Z' : null,
    heartbeat_at: holder ? '2026-08-30T00:01:00Z' : null,
    linked_pr: null,
    linked_pr_head: null,
    ownership_paths: holder
      ? ['docs/roadmap/full-roadmap-coverage-audit.md']
      : [],
    blocker: holder ? 'manual blocker' : 'bootstrap/reconciliation required',
    released_reason: null,
    return_state: 'BLOCKED',
    transition_seq: 0,
    last_command_comment_id: 0,
    updated_at: '2026-08-30T00:00:00Z',
  };
}

function contract() {
  return `${ENROLL}\n## Work Contract\n` +
    '- **Work ID:** ROADMAP-PROGRAM-001\n' +
    '- **State:** BLOCKED\n' +
    '- **Branch:** `audit/full-roadmap-coverage`\n' +
    '- **Positive ownership:** ' +
    '`docs/roadmap/full-roadmap-coverage-audit.md`\n' +
    '- **Claim holder:** none\n' +
    '- **Linked PR:** none';
}

function parseStatus(comment) {
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  return match ? JSON.parse(match[1]) : null;
}

function makeWorld({
  holder = false,
  unmerged = false,
  reservationCollision = false,
  openPrCollision = false,
} = {}) {
  let nextCommentId = 1000;
  const events = [];
  const issues = {
    150: { number: 150, body: '', labels: [] },
    196: { number: 196, body: '', labels: [{ name: 'work:done' }] },
    209: { number: 209, body: '', labels: [{ name: 'work:done' }] },
    239: {
      number: 239,
      body: contract(),
      labels: [{ name: 'agent-work' }, { name: 'work:blocked' }],
    },
  };
  const registryEntries = reservationCollision
    ? [{
        issue: 999,
        state: 'CLAIMED',
        paths: ['docs/roadmap/**'],
      }]
    : [];
  const comments = {
    150: [registryComment(registryEntries)],
    196: [
      statusComment(
        1960,
        doneStatus(196, 'ROADMAP-002', 262, HEAD_A),
      ),
    ],
    209: [
      statusComment(
        2090,
        doneStatus(209, 'ROADMAP-AUDIT-001', 295, HEAD_B),
      ),
    ],
    239: [statusComment(2390, blockedStatus(holder))],
  };
  const prs = {
    262: {
      number: 262,
      merged: !unmerged,
      state: unmerged ? 'open' : 'closed',
      head: { sha: HEAD_A },
      merge_commit_sha: MERGE_A,
    },
    295: {
      number: 295,
      merged: true,
      state: 'closed',
      head: { sha: HEAD_B },
      merge_commit_sha: MERGE_B,
    },
  };
  const openPulls = openPrCollision
    ? [{ number: 700, head: { ref: 'other-branch' } }]
    : [];

  const github = {
    rest: {
      issues: {
        get: async ({ issue_number }) => ({ data: issues[issue_number] }),
        listComments: async ({ issue_number }) => comments[issue_number] || [],
        updateComment: async ({ comment_id, body }) => {
          for (const [issueNumber, issueComments] of Object.entries(comments)) {
            const target = issueComments.find((item) => item.id === comment_id);
            if (!target) continue;
            target.body = body;
            events.push(`status-${issueNumber}`);
            return { data: target };
          }
          throw new Error(`unknown comment ${comment_id}`);
        },
        createComment: async ({ issue_number, body }) => {
          const created = {
            id: nextCommentId++,
            user: { login: 'github-actions[bot]' },
            body,
          };
          comments[issue_number] = comments[issue_number] || [];
          comments[issue_number].push(created);
          events.push(`comment-${issue_number}`);
          return { data: created };
        },
        removeLabel: async ({ issue_number, name }) => {
          issues[issue_number].labels = issues[issue_number].labels.filter(
            (item) => item.name !== name,
          );
          events.push(`remove-${name}`);
          return { data: {} };
        },
        addLabels: async ({ issue_number, labels }) => {
          const names = new Set(
            issues[issue_number].labels.map((item) => item.name),
          );
          for (const name of labels) names.add(name);
          issues[issue_number].labels = [...names].map((name) => ({ name }));
          events.push(`labels-${issue_number}`);
          return { data: {} };
        },
      },
      pulls: {
        list: async () => openPulls,
        listFiles: async () => openPrCollision
          ? [{ filename: 'docs/roadmap/full-roadmap-coverage-audit.md' }]
          : [],
        get: async ({ pull_number }) => ({ data: prs[pull_number] }),
      },
      repos: {
        get: async () => ({ data: { default_branch: 'main' } }),
        getBranch: async () => ({ data: { commit: { sha: MAIN } } }),
        compareCommitsWithBasehead: async () => ({
          data: { behind_by: 0, status: 'ahead' },
        }),
      },
    },
    paginate: async (fn, args) => fn(args),
  };
  const context = { repo: { owner: 'FPC-effortless', repo: 'veritas' } };
  return { comments, context, events, github, issues };
}

(async () => {
  const world = makeWorld();
  await reconcile({ github: world.github, context: world.context });
  let status = parseStatus(world.comments[239][0]);
  assert(status.state === 'READY', 'satisfied dependencies did not unblock');
  assert(status.agent_id === null, 'unblocking created an owner');
  assert(status.branch === null, 'unblocking created a branch reservation');
  assert(
    status.dependency_ready_event.dependencies.join(',') ===
      'ROADMAP-002,ROADMAP-AUDIT-001',
    'dependency proof was not recorded',
  );
  assert(
    world.events.indexOf('status-239') < world.events.indexOf('labels-239'),
    'discovery label was published before trusted READY state',
  );
  assert(
    world.issues[239].labels.some((item) => item.name === 'work:ready'),
    'READY label missing after transition',
  );
  const readyComments = () => world.comments[239].filter(
    (item) => item.body.includes('veritas-roadmap-dependency-ready:v1'),
  );
  assert(readyComments().length === 1, 'READY audit comment missing');
  await reconcile({ github: world.github, context: world.context });
  assert(readyComments().length === 1, 'repeated run duplicated READY notice');

  const unmerged = makeWorld({ unmerged: true });
  await reconcile({ github: unmerged.github, context: unmerged.context });
  status = parseStatus(unmerged.comments[239][0]);
  assert(status.state === 'BLOCKED', 'unmerged provider satisfied dependency');

  const held = makeWorld({ holder: true });
  await reconcile({ github: held.github, context: held.context });
  status = parseStatus(held.comments[239][0]);
  assert(status.state === 'BLOCKED', 'holder-owned BLOCKED work was unblocked');
  assert(status.agent_id === 'holder', 'holder metadata was changed');

  const reserved = makeWorld({ reservationCollision: true });
  await reconcile({ github: reserved.github, context: reserved.context });
  await reconcile({ github: reserved.github, context: reserved.context });
  status = parseStatus(reserved.comments[239][0]);
  assert(status.state === 'BLOCKED', 'active path collision was ignored');
  const blockedNotices = reserved.comments[239].filter(
    (item) => item.body.includes('veritas-roadmap-dependency-blocked:v1'),
  );
  assert(blockedNotices.length === 1, 'collision notice was not idempotent');

  const prCollision = makeWorld({ openPrCollision: true });
  await reconcile({ github: prCollision.github, context: prCollision.context });
  status = parseStatus(prCollision.comments[239][0]);
  assert(status.state === 'BLOCKED', 'open PR path collision was ignored');
})();
""".replace("__SCRIPT__", script_path)
    _run_node(source)
