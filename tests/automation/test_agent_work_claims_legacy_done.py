# ruff: noqa: E501

import json
import subprocess
from pathlib import Path

SCRIPT = Path(".github/scripts/agent-work-claims.js")


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


def test_legacy_review_can_finish_only_through_exact_done() -> None:
    script_path = json.dumps(str(SCRIPT.resolve()))
    source = r"""
const coordinate = require(__SCRIPT__);
const ENROLL = '<!-- veritas-agent-work -->';
const STATUS = '<!-- veritas-agent-work-status:v1 -->';
const REGISTRY = '<!-- veritas-agent-work-reservations:v1 -->';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function issueBody() {
  return `${ENROLL}
## Work Contract
- **Work ID:** LEGACY
- **State:** REVIEW
- **Branch:** \`feat/legacy\`
- **Positive ownership:** \`src/legacy/**\`
- **Claim holder:** legacy-agent
- **Linked PR:** #42`;
}

function legacyReview(head = 'reviewed-head') {
  return {
    schema_version: 'veritas.agent-work-status.v1',
    work_id: 'LEGACY',
    issue_number: 1,
    state: 'REVIEW',
    github_actor: 'FPC-effortless',
    agent_id: 'legacy-agent',
    branch: 'feat/legacy',
    claimed_at: '2026-08-29T00:00:00.000Z',
    heartbeat_at: '2026-08-29T00:00:00.000Z',
    linked_pr: 42,
    linked_pr_head: head,
    blocker: null,
    released_reason: null,
    return_state: 'READY',
    transition_seq: 5,
    last_command_comment_id: 0,
    updated_at: '2026-08-29T00:00:00.000Z',
  };
}

function statusComment(status) {
  return {
    id: 1001,
    user: { login: 'github-actions[bot]' },
    author_association: 'NONE',
    body: `${STATUS}\n**Agent work status**\n\n\`\`\`json\n${JSON.stringify(status, null, 2)}\n\`\`\``,
  };
}

function registryComment() {
  return {
    id: 900,
    user: { login: 'github-actions[bot]' },
    author_association: 'NONE',
    body: `${REGISTRY}\n**Global agent-work reservations**\n\n\`\`\`json\n${JSON.stringify({
      schema_version: 'veritas.agent-work-reservations.v1',
      updated_at: '2026-08-29T00:00:00.000Z',
      entries: [{
        issue: 1,
        work_id: 'LEGACY',
        state: 'REVIEW',
        actor: 'FPC-effortless',
        agent: 'legacy-agent',
        branch: 'feat/legacy',
        linked_pr: 42,
        paths: ['src/legacy/**'],
      }],
    }, null, 2)}\n\`\`\``,
  };
}

function commandComment(id, body) {
  return {
    id,
    user: { login: 'FPC-effortless' },
    author_association: 'OWNER',
    body,
  };
}

function parseJsonComment(comment) {
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  return match ? JSON.parse(match[1]) : null;
}

function makeWorld({ command, status, prHead = 'reviewed-head', merged = true }) {
  const issues = {
    1: {
      number: 1,
      state: 'closed',
      body: issueBody(),
      labels: [{ name: 'agent-work' }, { name: 'work:review' }],
    },
  };
  const comments = {
    1: [statusComment(status), command],
    150: [registryComment()],
  };
  const audits = [];

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
    listComments: async ({ issue_number }) => comments[issue_number] || [],
    removeLabel: async ({ issue_number, name }) => {
      issues[issue_number].labels = (issues[issue_number].labels || [])
        .filter((item) => item.name !== name);
      return { data: {} };
    },
    addLabels: async ({ issue_number, labels }) => {
      const names = new Set((issues[issue_number].labels || []).map((item) => item.name));
      for (const name of labels) names.add(name);
      issues[issue_number].labels = [...names].map((name) => ({ name }));
      return { data: {} };
    },
    updateComment: async ({ comment_id, body }) => {
      for (const issueComments of Object.values(comments)) {
        const target = issueComments.find((item) => item.id === comment_id);
        if (target) {
          target.body = body;
          return { data: target };
        }
      }
      throw new Error(`unknown comment ${comment_id}`);
    },
    createComment: async ({ issue_number, body }) => {
      audits.push({ issue: issue_number, body });
      return { data: { id: 5000 + audits.length, body } };
    },
  };

  const pullApi = {
    get: async ({ pull_number }) => {
      assert(pull_number === 42, 'unexpected PR lookup');
      return {
        data: {
          number: 42,
          merged_at: merged ? '2026-08-29T01:00:00Z' : null,
          head: { sha: prHead },
        },
      };
    },
    list: async () => [],
    listFiles: async () => [],
  };

  return {
    github: {
      rest: { issues: issueApi, pulls: pullApi },
      paginate: async (fn, args) => fn(args),
    },
    issues,
    comments,
    audits,
  };
}

function context(body) {
  return {
    repo: { owner: 'FPC-effortless', repo: 'veritas' },
    issue: { number: 1 },
    actor: 'FPC-effortless',
    payload: { comment: { body, author_association: 'OWNER' } },
  };
}

async function exactMergedDoneSucceeds() {
  const command = commandComment(2001, '/done legacy-agent 42');
  const world = makeWorld({ command, status: legacyReview() });
  await coordinate({ github: world.github, context: context(command.body) });

  const finalStatus = parseJsonComment(world.comments[1][0]);
  assert(finalStatus.state === 'DONE', 'legacy REVIEW did not reach DONE');
  assert(Array.isArray(finalStatus.ownership_paths), 'legacy DONE did not materialize ownership snapshot');
  assert(finalStatus.ownership_paths.length === 0, 'legacy DONE snapshot should be inert');
  const registry = parseJsonComment(world.comments[150][0]);
  assert(registry.entries.length === 0, 'legacy DONE left active reservation after successful cleanup');
  assert(world.issues[1].labels.some((item) => item.name === 'work:done'), 'DONE label was not reconciled');
}

async function movedHeadStillRejects() {
  const command = commandComment(2001, '/done legacy-agent 42');
  const world = makeWorld({ command, status: legacyReview('reviewed-head'), prHead: 'moved-head' });
  await coordinate({ github: world.github, context: context(command.body) });

  const finalStatus = parseJsonComment(world.comments[1][0]);
  assert(finalStatus.state === 'REVIEW', 'moved PR head incorrectly reached DONE');
  assert(!Array.isArray(finalStatus.ownership_paths), 'rejected legacy REVIEW was silently migrated');
  assert(
    world.audits.some((entry) => entry.body.includes('head moved after handoff')),
    'moved-head rejection was not audited'
  );
}

async function nonDoneLegacyCommandFailsClosed() {
  const command = commandComment(2001, '/release legacy-agent should-not-release');
  const world = makeWorld({ command, status: legacyReview() });
  await coordinate({ github: world.github, context: context(command.body) });

  const finalStatus = parseJsonComment(world.comments[1][0]);
  assert(finalStatus.state === 'REVIEW', 'legacy REVIEW was released without ownership migration');
  assert(
    world.audits.some((entry) => entry.body.includes('predates frozen ownership snapshots')),
    'legacy non-DONE command did not fail closed'
  );
}

(async () => {
  await exactMergedDoneSucceeds();
  await movedHeadStillRejects();
  await nonDoneLegacyCommandFailsClosed();
  process.stdout.write('ok\n');
})().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
""".replace("__SCRIPT__", script_path)
    _run_node(source)
