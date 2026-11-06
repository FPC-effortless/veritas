import json
import subprocess
from pathlib import Path

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
ENROLL_SCRIPT = Path(".github/scripts/agent-work-enroll.js")


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


def test_workflow_routes_authorized_issue_events_to_enrollment() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "issues:" in text
    assert "types: [opened, reopened]" in text
    assert "github.event_name == 'issues'" in text
    assert "<!-- veritas-agent-work -->" in text
    assert "author_association == 'OWNER'" in text
    assert "author_association == 'MEMBER'" in text
    assert "author_association == 'COLLABORATOR'" in text
    assert "agent-work-enroll.js" in text
    assert "github.event_name == 'issue_comment'" in text
    assert "agent-work-claims.js" in text
    assert "group: agent-work-coordination" in text
    assert "cancel-in-progress: false" in text


def test_automatic_enrollment_is_trusted_fail_closed_and_idempotent() -> None:
    script_path = json.dumps(str(ENROLL_SCRIPT.resolve()))
    source = r"""
const enroll = require(__SCRIPT__);
const ENROLL = '<!-- veritas-agent-work -->';
const STATUS = '<!-- veritas-agent-work-status:v1 -->';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function contract(
  workId,
  state,
  branch,
  ownership,
  holder = 'none',
  linkedPr = 'none',
) {
  return `${ENROLL}
## Work Contract
- **Work ID:** ${workId}
- **State:** ${state}
- **Branch:** \`${branch}\`
- **Positive ownership:** ${ownership}
- **Claim holder:** ${holder}
- **Linked PR:** ${linkedPr}`;
}

function parseStatus(comment) {
  if (!comment || !comment.body.includes(STATUS)) return null;
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  return match ? JSON.parse(match[1]) : null;
}

function makeWorld(issue) {
  let nextCommentId = 1000;
  const comments = [];
  const createdLabels = new Set([
    'agent-work',
    'work:ready',
    'work:claimed',
    'work:blocked',
    'work:review',
    'work:done',
    'work:superseded',
  ]);

  const github = {
    rest: {
      issues: {
        get: async () => ({ data: issue }),
        listLabelsForRepo: async () => (
          [...createdLabels].map((name) => ({ name }))
        ),
        createLabel: async ({ name }) => {
          createdLabels.add(name);
          return { data: { name } };
        },
        listComments: async () => comments,
        createComment: async ({ body }) => {
          const comment = {
            id: nextCommentId++,
            user: { login: 'github-actions[bot]' },
            body,
          };
          comments.push(comment);
          return { data: comment };
        },
        removeLabel: async ({ name }) => {
          issue.labels = (issue.labels || []).filter(
            (item) => item.name !== name,
          );
          return { data: {} };
        },
        addLabels: async ({ labels }) => {
          const names = new Set(
            (issue.labels || []).map((item) => item.name),
          );
          for (const name of labels) names.add(name);
          issue.labels = [...names].map((name) => ({ name }));
          return { data: {} };
        },
      },
    },
    paginate: async (fn, args) => fn(args),
  };

  async function trigger(association = 'OWNER', action = 'opened') {
    const context = {
      eventName: 'issues',
      repo: { owner: 'FPC-effortless', repo: 'veritas' },
      issue: { number: issue.number },
      payload: {
        action,
        issue: {
          number: issue.number,
          author_association: association,
        },
      },
    };
    await enroll({ github, context, core: {} });
  }

  return { issue, comments, trigger };
}

function trustedStatuses(world) {
  return world.comments.map(parseStatus).filter(Boolean);
}

(async () => {
  const ready = makeWorld({
    number: 10,
    body: contract(
      'AUTO-READY',
      'READY',
      'feat/auto-ready',
      '`src/auto/**`',
    ),
    labels: [{ name: 'agent-work' }, { name: 'work:blocked' }],
  });
  await ready.trigger();
  let statuses = trustedStatuses(ready);
  assert(
    statuses.length === 1,
    'READY enrollment did not create exactly one trusted status',
  );
  assert(
    statuses[0].state === 'READY',
    'valid READY contract did not enroll READY',
  );
  assert(
    statuses[0].agent_id === null && statuses[0].github_actor === null,
    'automatic READY enrollment created an owner',
  );
  assert(
    JSON.stringify(statuses[0].ownership_paths)
      === JSON.stringify(['src/auto/**']),
    'READY ownership was not frozen',
  );
  assert(
    ready.issue.labels.some((item) => item.name === 'work:ready'),
    'READY discovery label missing',
  );
  assert(
    !ready.issue.labels.some((item) => item.name === 'work:blocked'),
    'stale BLOCKED label survived READY enrollment',
  );

  await ready.trigger('OWNER', 'reopened');
  statuses = trustedStatuses(ready);
  assert(
    statuses.length === 1,
    'duplicate enrollment created a second trusted status',
  );

  const blocked = makeWorld({
    number: 11,
    body: contract(
      'AUTO-BLOCKED',
      'BLOCKED',
      'feat/blocked',
      '`src/blocked/**`',
    ),
    labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
  });
  await blocked.trigger();
  statuses = trustedStatuses(blocked);
  assert(
    statuses.length === 1 && statuses[0].state === 'BLOCKED',
    'BLOCKED contract did not remain BLOCKED',
  );
  assert(
    statuses[0].blocker === 'work-contract-blocked',
    'BLOCKED enrollment missing explicit blocker',
  );
  assert(
    blocked.issue.labels.some((item) => item.name === 'work:blocked'),
    'forged READY label was not corrected',
  );
  assert(
    !blocked.issue.labels.some((item) => item.name === 'work:ready'),
    'forged READY label remained authoritative',
  );

  const invalidActive = makeWorld({
    number: 12,
    body: contract(
      'AUTO-ACTIVE',
      'CLAIMED',
      'feat/active',
      '`src/active/**`',
      'some-agent',
      '#99',
    ),
    labels: [{ name: 'agent-work' }, { name: 'work:claimed' }],
  });
  await invalidActive.trigger();
  statuses = trustedStatuses(invalidActive);
  assert(
    statuses.length === 1 && statuses[0].state === 'BLOCKED',
    'active declaration did not fail closed',
  );
  assert(
    statuses[0].agent_id === null && statuses[0].linked_pr === null,
    'automatic enrollment materialized active authority',
  );
  assert(
    statuses[0].blocker.includes('automatic enrollment failed closed'),
    'fail-closed reason missing',
  );

  const invalidOwnership = makeWorld({
    number: 13,
    body: contract(
      'AUTO-NOPATH',
      'READY',
      'feat/no-path',
      'coordination docs/tests only',
    ),
    labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
  });
  await invalidOwnership.trigger();
  statuses = trustedStatuses(invalidOwnership);
  assert(
    statuses.length === 1 && statuses[0].state === 'BLOCKED',
    'READY prose ownership did not fail closed',
  );
  assert(
    statuses[0].blocker.includes('machine-checkable positive ownership'),
    'invalid ownership reason missing',
  );

  const outsider = makeWorld({
    number: 14,
    body: contract(
      'AUTO-OUTSIDER',
      'READY',
      'feat/outsider',
      '`src/outsider/**`',
    ),
    labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
  });
  await outsider.trigger('NONE');
  statuses = trustedStatuses(outsider);
  assert(
    statuses.length === 0,
    'unauthorized author received trusted status',
  );
  assert(
    outsider.comments.some(
      (comment) => comment.body.includes('automatic enrollment skipped'),
    ),
    'unauthorized enrollment was not audited',
  );
})();
""".replace("__SCRIPT__", script_path)
    _run_node(source)
