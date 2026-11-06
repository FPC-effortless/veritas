import json
import subprocess
from pathlib import Path

WORKFLOW = Path(".github/workflows/roadmap-completion-sync.yml")
SCRIPT = Path(".github/scripts/roadmap-completion-sync.js")


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


def test_workflow_is_serialized_triggered_and_least_privilege() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "push:" in text
    assert "types: [opened, edited, reopened]" in text
    assert "issue_comment:" in text
    assert 'workflows: ["Agent Work Claims"]' in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "contents: read" in text
    assert "issues: write" in text
    assert "group: agent-work-coordination" in text
    assert "cancel-in-progress: false" in text
    assert "actions: write" not in text
    assert "contents: write" not in text
    assert "pull-requests: write" not in text
    assert "secrets:" not in text
    assert "roadmap-completion-sync.js" in text


def test_owner_evidence_completion_is_strict_ordered_and_idempotent() -> None:
    script_path = json.dumps(str(SCRIPT.resolve()))
    source = r"""
const syncCompletion = require(__SCRIPT__);
const STATUS = '<!-- veritas-agent-work-status:v1 -->';
const ENROLL = '<!-- veritas-agent-work -->';
const AUDIT = 'veritas-roadmap-owner-evidence-completion:v1';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function contract({
  evidenceId = 200,
  completionRule = 'OWNER_EVIDENCE',
  completionClass = 'COORDINATION_OPERATION',
  ownership = 'issue labels/comments for roadmap tickets only',
} = {}) {
  return `${ENROLL}
## Work Contract
- **Work ID:** ROADMAP-CLAIM-BOOTSTRAP
- **State:** BLOCKED
- **Branch:** no product branch; one-time coordination operation
- **Positive ownership:** ${ownership}
- **Claim holder:** none
- **Linked PR:** none
- **Completion rule:** \`${completionRule}\`
- **Completion class:** \`${completionClass}\`
- **Completion evidence comment:** \`${evidenceId}\`
- **Terminal state:** \`DONE\``;
}

function blockedStatus({
  holder = false,
  workMismatch = false,
  invalidSeq = false,
  malformedEvent = false,
} = {}) {
  return {
    schema_version: 'veritas.agent-work-status.v1',
    work_id: workMismatch ? 'OTHER-WORK' : 'ROADMAP-CLAIM-BOOTSTRAP',
    issue_number: 216,
    state: 'BLOCKED',
    github_actor: holder ? 'FPC-effortless' : null,
    agent_id: holder ? 'holder' : null,
    branch: holder ? 'held/branch' : null,
    claimed_at: holder ? '2026-08-30T00:00:00Z' : null,
    heartbeat_at: holder ? '2026-08-30T00:01:00Z' : null,
    linked_pr: null,
    linked_pr_head: null,
    ownership_paths: holder ? ['docs/held.md'] : [],
    blocker: 'bootstrap/reconciliation required',
    released_reason: null,
    return_state: 'BLOCKED',
    transition_seq: invalidSeq ? '0' : 0,
    last_command_comment_id: 0,
    updated_at: '2026-08-30T00:00:00Z',
    completion_evidence: malformedEvent ? { rule: 'OWNER_EVIDENCE' } : null,
  };
}

function statusComment(status) {
  return {
    id: 100,
    user: { login: 'github-actions[bot]' },
    body: `${STATUS}\n**Agent work status**\n\n` +
      `\`\`\`json\n${JSON.stringify(status, null, 2)}\n\`\`\``,
  };
}

function markedStatusWithoutJson() {
  return {
    id: 101,
    user: { login: 'github-actions[bot]' },
    body: `${STATUS}\n**Agent work status**`,
  };
}

function parseStatus(comment) {
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  return match ? JSON.parse(match[1]) : null;
}

function makeWorld({
  evidenceId = 200,
  association = 'OWNER',
  evidenceActor = 'FPC-effortless',
  evidenceBody = 'Completion evidence: bootstrap completed.',
  evidenceCreatedAt = '2026-08-30T01:00:00Z',
  holder = false,
  workMismatch = false,
  invalidSeq = false,
  malformedEvent = false,
  completionRule = 'OWNER_EVIDENCE',
  completionClass = 'COORDINATION_OPERATION',
  ownership = 'issue labels/comments for roadmap tickets only',
  spoofAudit = false,
  malformedNewestStatus = false,
} = {}) {
  let nextCommentId = 1000;
  const events = [];
  const issue = {
    number: 216,
    state: 'open',
    state_reason: null,
    body: contract({
      evidenceId,
      completionRule,
      completionClass,
      ownership,
    }),
    labels: [{ name: 'agent-work' }, { name: 'work:blocked' }],
  };
  const comments = [
    statusComment(blockedStatus({
      holder,
      workMismatch,
      invalidSeq,
      malformedEvent,
    })),
    {
      id: 200,
      user: { login: evidenceActor },
      author_association: association,
      created_at: evidenceCreatedAt,
      body: evidenceBody,
    },
  ];
  if (spoofAudit) {
    comments.push({
      id: 201,
      user: { login: 'outside-user' },
      author_association: 'NONE',
      created_at: '2026-08-30T01:01:00Z',
      body: `<!-- ${AUDIT}:216:200 -->`,
    });
  }
  if (malformedNewestStatus) comments.push(markedStatusWithoutJson());

  const github = {
    rest: {
      issues: {
        listForRepo: async () => issue.state === 'open' ? [issue] : [],
        listComments: async () => comments,
        get: async () => ({ data: issue }),
        updateComment: async ({ comment_id, body }) => {
          const target = comments.find((item) => item.id === comment_id);
          if (!target) throw new Error(`unknown comment ${comment_id}`);
          target.body = body;
          events.push('status');
          return { data: target };
        },
        createComment: async ({ body }) => {
          const created = {
            id: nextCommentId++,
            user: { login: 'github-actions[bot]' },
            body,
          };
          comments.push(created);
          events.push('audit');
          return { data: created };
        },
        removeLabel: async ({ name }) => {
          issue.labels = issue.labels.filter((item) => item.name !== name);
          events.push(`remove-${name}`);
          return { data: {} };
        },
        addLabels: async ({ labels }) => {
          const names = new Set(issue.labels.map((item) => item.name));
          for (const name of labels) names.add(name);
          issue.labels = [...names].map((name) => ({ name }));
          events.push('labels');
          return { data: {} };
        },
        update: async ({ state, state_reason }) => {
          issue.state = state;
          issue.state_reason = state_reason;
          events.push('close');
          return { data: issue };
        },
      },
    },
    paginate: async (fn, args) => fn(args),
  };
  const context = { repo: { owner: 'FPC-effortless', repo: 'veritas' } };
  return { comments, context, events, github, issue };
}

function audits(world) {
  return world.comments.filter(
    (item) =>
      item.user?.login === 'github-actions[bot]' &&
      item.body.includes(AUDIT),
  );
}

(async () => {
  const world = makeWorld();
  await syncCompletion({ github: world.github, context: world.context });
  let status = parseStatus(world.comments[0]);
  assert(status.state === 'DONE', 'valid OWNER evidence did not complete');
  assert(status.transition_seq === 1, 'completion sequence was not advanced');
  assert(
    status.completion_evidence.evidence_comment_id === 200,
    'exact evidence comment was not recorded',
  );
  assert(
    status.completion_evidence.evidence_actor === 'FPC-effortless',
    'evidence actor was not recorded',
  );
  assert(
    status.completion_evidence.evidence_created_at ===
      '2026-08-30T01:00:00Z',
    'evidence timestamp was not recorded',
  );
  assert(
    world.events.indexOf('status') < world.events.indexOf('labels'),
    'DONE discovery label was published before trusted status',
  );
  assert(
    world.events.indexOf('status') < world.events.indexOf('close'),
    'issue was closed before trusted DONE status',
  );
  assert(
    world.issue.labels.some((item) => item.name === 'work:done'),
    'DONE label missing',
  );
  assert(world.issue.state === 'closed', 'completed issue remained open');
  assert(audits(world).length === 1, 'completion audit comment missing');

  world.issue.state = 'open';
  world.issue.labels = [
    { name: 'agent-work' },
    { name: 'work:blocked' },
  ];
  world.events.length = 0;
  await syncCompletion({ github: world.github, context: world.context });
  status = parseStatus(world.comments[0]);
  assert(status.transition_seq === 1, 'reopen repeated DONE transition');
  assert(audits(world).length === 1, 'reopen duplicated completion audit');
  assert(world.issue.state === 'closed', 'reopened DONE issue was not repaired');
  assert(!world.events.includes('status'), 'reopen rewrote trusted status');

  const spoofedAudit = makeWorld({ spoofAudit: true });
  await syncCompletion({
    github: spoofedAudit.github,
    context: spoofedAudit.context,
  });
  status = parseStatus(spoofedAudit.comments[0]);
  assert(status.state === 'DONE', 'spoofed audit prevented DONE transition');
  assert(audits(spoofedAudit).length === 1, 'trusted audit was not retained');
  assert(
    spoofedAudit.events.includes('audit'),
    'outside marker suppressed trusted completion audit',
  );

  const malformedStatus = makeWorld({ malformedNewestStatus: true });
  let malformedRejected = false;
  try {
    await syncCompletion({
      github: malformedStatus.github,
      context: malformedStatus.context,
    });
  } catch {
    malformedRejected = true;
  }
  status = parseStatus(malformedStatus.comments[0]);
  assert(malformedRejected, 'malformed newest trusted status did not reject');
  assert(status.state === 'BLOCKED', 'malformed newest status completed work');
  assert(malformedStatus.issue.state === 'open', 'malformed status closed issue');

  const invalidWorlds = [
    makeWorld({ evidenceId: 201 }),
    makeWorld({ association: 'MEMBER' }),
    makeWorld({ evidenceActor: null }),
    makeWorld({ evidenceActor: 42 }),
    makeWorld({ evidenceActor: '   ' }),
    makeWorld({ evidenceBody: 'Completion evidence:' }),
    makeWorld({ evidenceBody: 'Looks complete.' }),
    makeWorld({ evidenceCreatedAt: null }),
    makeWorld({ holder: true }),
    makeWorld({ workMismatch: true }),
    makeWorld({ invalidSeq: true }),
    makeWorld({ malformedEvent: true }),
    makeWorld({ completionRule: 'PR_MERGE' }),
    makeWorld({ completionClass: 'SCIENTIFIC_QUALIFICATION' }),
    makeWorld({ ownership: 'coordination docs and labels only' }),
  ];
  for (const invalid of invalidWorlds) {
    await syncCompletion({
      github: invalid.github,
      context: invalid.context,
    });
    status = parseStatus(invalid.comments[0]);
    assert(status.state === 'BLOCKED', 'invalid evidence completed work');
    assert(invalid.issue.state === 'open', 'invalid evidence closed issue');
    assert(audits(invalid).length === 0, 'invalid evidence was audited DONE');
  }
})();
""".replace("__SCRIPT__", script_path)
    _run_node(source)