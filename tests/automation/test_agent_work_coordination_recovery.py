# ruff: noqa: E501

import json
import subprocess
from pathlib import Path

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
SCRIPT = Path(".github/scripts/agent-work-claims.js")


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


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


def test_only_actual_coordinate_job_owns_global_mutation_concurrency() -> None:
    workflow = _workflow()
    header, jobs = workflow.split("jobs:", 1)
    assert "concurrency:" not in header
    coordinate = jobs.split("  coordinate:", 1)[1]
    enroll = jobs.split("  enroll:", 1)[1].split("  coordinate:", 1)[0]
    assert "concurrency:" not in enroll
    assert "group: agent-work-coordination" in coordinate
    assert "cancel-in-progress: false" in coordinate
    assert "startsWith(github.event.comment.body, '/recover-linked ')" in coordinate


def test_linked_recovery_is_owner_pr_bound_and_reservation_first() -> None:
    script = _script()
    assert "command.kind === 'recover-linked'" in script
    assert "linked-PR recovery requires repository OWNER authority" in script
    assert "linked-PR recovery is restricted to bootstrap-derived legacy holders" in script
    assert "linked-PR recovery requires a non-concrete legacy recorded branch" in script
    assert "status.linked_pr !== command.pr" in script
    assert "pr.head.ref !== command.branch" in script
    assert "status.linked_pr_head && status.linked_pr_head !== pr.head.sha" in script
    assert "status.linked_pr_head = status.linked_pr_head || pr.head.sha" in script
    assert "activeReservationMetadataChanged" in script
    assert "command.kind === 'recover-linked'" in script.split(
        "const activeReservationMetadataChanged", 1
    )[1].split(";", 1)[0]


def test_linked_recovery_repairs_mig_and_data_style_bootstrap_records() -> None:
    script_path = json.dumps(str(SCRIPT.resolve()))
    source = r"""
const coordinate = require(__SCRIPT__);
const ENROLL = '<!-- veritas-agent-work -->';
const STATUS = '<!-- veritas-agent-work-status:v1 -->';
const REGISTRY = '<!-- veritas-agent-work-reservations:v1 -->';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function contract(workId, branch, ownership, pr) {
  return `${ENROLL}
## Work Contract
- **Work ID:** ${workId}
- **State:** REVIEW
- **Branch:** ${branch}
- **Positive ownership:** ${ownership}
- **Claim holder:** legacy bootstrap holder
- **Linked PR:** #${pr}`;
}

function statusComment(id, status) {
  return {
    id,
    user: { login: 'github-actions[bot]' },
    author_association: 'NONE',
    body: `${STATUS}
**Agent work status**

\`\`\`json
${JSON.stringify(status, null, 2)}
\`\`\``,
  };
}

function registryComment(entries) {
  return {
    id: 900,
    user: { login: 'github-actions[bot]' },
    author_association: 'NONE',
    body: `${REGISTRY}
**Global agent-work reservations**

\`\`\`json
${JSON.stringify({
  schema_version: 'veritas.agent-work-reservations.v1',
  updated_at: '2026-08-31T00:00:00.000Z',
  entries,
}, null, 2)}
\`\`\``,
  };
}

function commandComment(id, body, association = 'OWNER') {
  return {
    id,
    user: { login: 'FPC-effortless' },
    author_association: association,
    body,
  };
}

function parseJson(comment) {
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  return match ? JSON.parse(match[1]) : null;
}

function legacyStatus({ issue, workId, branch, pr, paths }) {
  return {
    schema_version: 'veritas.agent-work-status.v1',
    work_id: workId,
    issue_number: issue,
    state: 'REVIEW',
    github_actor: 'bootstrap',
    agent_id: `existing PR #${pr} lane`,
    branch,
    claimed_at: '2026-08-28T09:29:48.647Z',
    heartbeat_at: '2026-08-28T09:29:48.647Z',
    linked_pr: pr,
    linked_pr_head: null,
    ownership_paths: paths,
    blocker: null,
    released_reason: null,
    return_state: 'READY',
    transition_seq: 0,
    last_command_comment_id: 0,
    updated_at: '2026-08-29T07:56:26.829Z',
  };
}

function makeWorld({ issue, status, command, prHead, prSha, prState = 'open' }) {
  const issues = {
    [issue.number]: issue,
  };
  const comments = {
    [issue.number]: [statusComment(1000 + issue.number, status), command],
    150: [registryComment([
      {
        issue: issue.number,
        work_id: status.work_id,
        state: status.state,
        actor: status.github_actor,
        agent: status.agent_id,
        branch: status.branch,
        linked_pr: status.linked_pr,
        paths: status.ownership_paths,
      },
    ])],
  };
  const audits = [];
  const events = [];

  const issueApi = {
    listLabelsForRepo: async () => [
      'agent-work',
      'work:ready',
      'work:claimed',
      'work:blocked',
      'work:review',
      'work:done',
      'work:superseded',
    ].map((name) => ({ name })),
    createLabel: async () => ({ data: {} }),
    get: async ({ issue_number }) => ({ data: issues[issue_number] }),
    removeLabel: async ({ issue_number, name }) => {
      issues[issue_number].labels = (issues[issue_number].labels || []).filter(
        (item) => item.name !== name
      );
      return { data: {} };
    },
    addLabels: async ({ issue_number, labels }) => {
      const names = new Set((issues[issue_number].labels || []).map((item) => item.name));
      for (const name of labels) names.add(name);
      issues[issue_number].labels = [...names].map((name) => ({ name }));
      return { data: {} };
    },
    listComments: async ({ issue_number }) => comments[issue_number] || [],
    updateComment: async ({ comment_id, body }) => {
      if (comment_id === 900) events.push('registry-write');
      for (const [number, entries] of Object.entries(comments)) {
        const target = entries.find((entry) => entry.id === comment_id);
        if (!target) continue;
        target.body = body;
        if (body.includes(STATUS)) events.push(`status-write-${number}`);
        return { data: target };
      }
      throw new Error(`unknown comment ${comment_id}`);
    },
    createComment: async ({ issue_number, body }) => {
      const created = {
        id: 5000 + audits.length,
        user: { login: 'github-actions[bot]' },
        author_association: 'NONE',
        body,
      };
      comments[issue_number] = comments[issue_number] || [];
      comments[issue_number].push(created);
      audits.push({ issue: issue_number, body });
      return { data: created };
    },
  };

  const pullApi = {
    get: async ({ pull_number }) => {
      assert(pull_number === status.linked_pr, 'unexpected PR lookup');
      return {
        data: {
          number: pull_number,
          state: prState,
          head: { ref: prHead, sha: prSha },
        },
      };
    },
  };

  const github = {
    rest: { issues: issueApi, pulls: pullApi },
    paginate: async (fn, args) => fn(args),
  };
  const context = {
    repo: { owner: 'FPC-effortless', repo: 'veritas' },
    issue: { number: issue.number },
    actor: 'FPC-effortless',
    payload: {
      comment: {
        body: command.body,
        author_association: command.author_association,
      },
    },
  };
  return { github, context, issues, comments, audits, events };
}

async function runSuccess({
  issueNumber,
  workId,
  legacyBranch,
  branch,
  pr,
  ownership,
  paths,
}) {
  const issue = {
    number: issueNumber,
    state: 'open',
    body: contract(workId, legacyBranch, ownership, pr),
    labels: [{ name: 'agent-work' }, { name: 'work:review' }],
  };
  const status = legacyStatus({
    issue: issueNumber,
    workId,
    branch: legacyBranch,
    pr,
    paths,
  });
  const command = commandComment(
    2000 + issueNumber,
    `/recover-linked coord-repair ${branch} ${pr} repair-bootstrap-metadata`
  );
  const world = makeWorld({
    issue,
    status,
    command,
    prHead: branch,
    prSha: `sha-${pr}`,
  });
  await coordinate({ github: world.github, context: world.context });
  const repaired = parseJson(world.comments[issueNumber][0]);
  assert(repaired.state === 'REVIEW', `${workId}: recovery changed state`);
  assert(repaired.github_actor === 'FPC-effortless', `${workId}: actor not repaired`);
  assert(repaired.agent_id === 'coord-repair', `${workId}: agent not repaired`);
  assert(repaired.branch === branch, `${workId}: branch not repaired`);
  assert(repaired.linked_pr === pr, `${workId}: linked PR changed`);
  assert(repaired.linked_pr_head === `sha-${pr}`, `${workId}: exact head not bound`);
  assert(
    JSON.stringify(repaired.ownership_paths) === JSON.stringify(paths),
    `${workId}: ownership changed`
  );
  const registry = parseJson(world.comments[150][0]);
  assert(registry.entries.length === 1, `${workId}: registry entry missing`);
  assert(registry.entries[0].branch === branch, `${workId}: registry branch stale`);
  assert(registry.entries[0].agent === 'coord-repair', `${workId}: registry agent stale`);
  assert(
    world.events.indexOf('registry-write') < world.events.indexOf(`status-write-${issueNumber}`),
    `${workId}: local status published before repaired global reservation`
  );
}

async function runRejectWrongBranch() {
  const issueNumber = 184;
  const pr = 134;
  const legacyBranch = 'existing `feat/investigation-structured-corpus';
  const issue = {
    number: issueNumber,
    state: 'open',
    body: contract(
      'MIG-001',
      legacyBranch,
      '`src/investigation_world/investigation_data/structured_corpus.py`',
      pr
    ),
    labels: [{ name: 'agent-work' }, { name: 'work:review' }],
  };
  const status = legacyStatus({
    issue: issueNumber,
    workId: 'MIG-001',
    branch: legacyBranch,
    pr,
    paths: ['src/investigation_world/investigation_data/structured_corpus.py'],
  });
  const command = commandComment(
    3001,
    '/recover-linked coord-repair feat/wrong 134 wrong-branch'
  );
  const world = makeWorld({
    issue,
    status,
    command,
    prHead: 'feat/investigation-structured-corpus',
    prSha: 'sha-134',
  });
  await coordinate({ github: world.github, context: world.context });
  const unchanged = parseJson(world.comments[issueNumber][0]);
  assert(unchanged.github_actor === 'bootstrap', 'wrong branch changed actor');
  assert(unchanged.branch === legacyBranch, 'wrong branch changed recorded branch');
  assert(
    world.audits.some((entry) => entry.body.includes('does not prove recovery branch')),
    'wrong branch was not rejected explicitly'
  );
}

async function runRejectHealthyHolder() {
  const issueNumber = 184;
  const pr = 134;
  const legacyBranch = 'existing `feat/investigation-structured-corpus';
  const issue = {
    number: issueNumber,
    state: 'open',
    body: contract(
      'MIG-001',
      legacyBranch,
      '`src/investigation_world/investigation_data/structured_corpus.py`',
      pr
    ),
    labels: [{ name: 'agent-work' }, { name: 'work:review' }],
  };
  const status = legacyStatus({
    issue: issueNumber,
    workId: 'MIG-001',
    branch: legacyBranch,
    pr,
    paths: ['src/investigation_world/investigation_data/structured_corpus.py'],
  });
  status.github_actor = 'FPC-effortless';
  status.agent_id = 'healthy-holder';
  const command = commandComment(
    3002,
    '/recover-linked coord-repair feat/investigation-structured-corpus 134 takeover'
  );
  const world = makeWorld({
    issue,
    status,
    command,
    prHead: 'feat/investigation-structured-corpus',
    prSha: 'sha-134',
  });
  await coordinate({ github: world.github, context: world.context });
  const unchanged = parseJson(world.comments[issueNumber][0]);
  assert(unchanged.agent_id === 'healthy-holder', 'healthy holder was replaced');
  assert(
    world.audits.some((entry) => entry.body.includes('bootstrap-derived legacy holders')),
    'healthy holder takeover was not rejected explicitly'
  );
}

async function runRejectNonOwner() {
  const issueNumber = 185;
  const pr = 147;
  const legacyBranch = 'existing PR #147 branch';
  const issue = {
    number: issueNumber,
    state: 'open',
    body: contract('DATA-001', legacyBranch, 'exactly PR #147 queue-overlay/workflow/tests/docs scope', pr),
    labels: [{ name: 'agent-work' }, { name: 'work:review' }],
  };
  const status = legacyStatus({
    issue: issueNumber,
    workId: 'DATA-001',
    branch: legacyBranch,
    pr,
    paths: [],
  });
  const command = commandComment(
    3003,
    '/recover-linked coord-repair data/gold-report-acquisition 147 non-owner',
    'MEMBER'
  );
  const world = makeWorld({
    issue,
    status,
    command,
    prHead: 'data/gold-report-acquisition',
    prSha: 'sha-147',
  });
  await coordinate({ github: world.github, context: world.context });
  const unchanged = parseJson(world.comments[issueNumber][0]);
  assert(unchanged.github_actor === 'bootstrap', 'non-owner changed actor');
  assert(
    world.audits.some((entry) => entry.body.includes('repository OWNER authority')),
    'non-owner recovery was not rejected explicitly'
  );
}

(async () => {
  await runSuccess({
    issueNumber: 184,
    workId: 'MIG-001',
    legacyBranch: 'existing `feat/investigation-structured-corpus',
    branch: 'feat/investigation-structured-corpus',
    pr: 134,
    ownership: '`src/investigation_world/investigation_data/structured_corpus.py`',
    paths: ['src/investigation_world/investigation_data/structured_corpus.py'],
  });
  await runSuccess({
    issueNumber: 185,
    workId: 'DATA-001',
    legacyBranch: 'existing PR #147 branch',
    branch: 'data/gold-report-acquisition',
    pr: 147,
    ownership: 'exactly PR #147 queue-overlay/workflow/tests/docs scope',
    paths: [],
  });
  await runRejectWrongBranch();
  await runRejectHealthyHolder();
  await runRejectNonOwner();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
""".replace("__SCRIPT__", script_path)
    _run_node(source)
