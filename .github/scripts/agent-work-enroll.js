const ENROLLMENT_MARKER = '<!-- veritas-agent-work -->';
const STATUS_MARKER = '<!-- veritas-agent-work-status:v1 -->';
const STATES = ['READY', 'CLAIMED', 'BLOCKED', 'REVIEW', 'DONE', 'SUPERSEDED'];
const ALLOWED_ASSOCIATIONS = new Set(['OWNER', 'MEMBER', 'COLLABORATOR']);
const EXPLICIT_NO_SOURCE_OWNERSHIP = new Set([
  "this issue's comments/labels only",
  'issue labels/comments for roadmap tickets only',
  'roadmap issue comments/labels/manifest metadata only',
  'coordination issue comments/registry only',
]);
const LABEL_DEFINITIONS = {
  'agent-work': ['5319e7', 'Roadmap work managed by agent coordination automation'],
  'work:ready': ['1f883d', 'Available for an authorized agent to claim'],
  'work:claimed': ['fbca04', 'Actively owned by an agent'],
  'work:blocked': ['d93f0b', 'Blocked by a dependency or explicit blocker'],
  'work:review': ['0969da', 'Implementation handed off for review or merge'],
  'work:done': ['8250df', 'Work contract completion condition satisfied'],
  'work:superseded': ['cfd3d7', 'Replaced by another canonical work item'],
};
const STATE_LABELS = new Set(STATES.map((state) => `work:${state.toLowerCase()}`));
const now = () => new Date().toISOString();
const labelForState = (state) => `work:${state.toLowerCase()}`;

function contractValue(text, field, unwrapSingleCodeSpan = true) {
  const escaped = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = String(text || '').match(new RegExp(`^- \\*\\*${escaped}:\\*\\*\\s*(.+)$`, 'mi'));
  if (!match) return null;
  const value = match[1].trim();
  if (unwrapSingleCodeSpan && /^`[^`]+`$/.test(value)) return value.slice(1, -1);
  return value;
}

function repositoryPathToken(value) {
  const raw = String(value || '').trim();
  if (!raw || raw.startsWith('#') || /\s/.test(raw)) return null;
  const normalized = raw.replace(/^\.\//, '');
  if (!normalized || normalized.startsWith('/') || normalized.endsWith('/') || normalized.includes('//')) return null;
  if (!/^[A-Za-z0-9._/*+\-]+$/.test(normalized)) return null;
  if (normalized.includes('*') && !/^[^*]+\/\*\*$/.test(normalized)) return null;
  if (normalized.split('/').some((segment) => segment === '.' || segment === '..')) return null;
  return normalized;
}

function parsePaths(text) {
  const paths = [];
  for (const match of String(text || '').matchAll(/`([^`]+)`/g)) {
    const path = repositoryPathToken(match[1]);
    if (path) paths.push(path);
  }
  return [...new Set(paths)].sort();
}

function isExplicitNoSourceOwnership(text) {
  const normalized = String(text || '').trim().toLowerCase().replace(/\s+/g, ' ');
  return EXPLICIT_NO_SOURCE_OWNERSHIP.has(normalized);
}

function branchIsConcrete(branch) {
  return Boolean(branch && /^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$/.test(branch));
}

function parseContract(text, number) {
  const state = (contractValue(text, 'State') || 'BLOCKED').toUpperCase();
  const positiveOwnership = contractValue(text, 'Positive ownership', false) || '';
  return {
    enrolled: String(text || '').includes(ENROLLMENT_MARKER),
    workId: contractValue(text, 'Work ID') || `ISSUE-${number}`,
    initialState: STATES.includes(state) ? state : 'BLOCKED',
    declaredStateValid: STATES.includes(state),
    declaredBranch: contractValue(text, 'Branch'),
    declaredHolder: contractValue(text, 'Claim holder'),
    declaredPr: contractValue(text, 'Linked PR'),
    positiveOwnership,
    paths: parsePaths(positiveOwnership),
  };
}

function renderStatus(status) {
  return `${STATUS_MARKER}\n**Agent work status**\n\n\`\`\`json\n${JSON.stringify(status, null, 2)}\n\`\`\``;
}

function parseStatusComment(comment, expectedIssue) {
  if (comment.user?.login !== 'github-actions[bot]' || !comment.body?.includes(STATUS_MARKER)) return null;
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const status = JSON.parse(match[1]);
    if (status.schema_version !== 'veritas.agent-work-status.v1' || status.issue_number !== expectedIssue) return null;
    return { commentId: comment.id, status };
  } catch {
    return null;
  }
}

module.exports = async function enroll({ github, context }) {
  if (context.eventName !== 'issues' || !['opened', 'reopened'].includes(context.payload.action)) return;

  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const issueNumber = context.payload.issue?.number || context.issue.number;
  const association = context.payload.issue?.author_association || '';

  async function audit(message) {
    await github.rest.issues.createComment({ owner, repo, issue_number: issueNumber, body: message });
  }

  if (!ALLOWED_ASSOCIATIONS.has(association)) {
    await audit('Agent-work automatic enrollment skipped: issue author is not OWNER, MEMBER, or COLLABORATOR. Repository OWNER reconciliation is required.');
    return;
  }

  const issue = (await github.rest.issues.get({ owner, repo, issue_number: issueNumber })).data;
  const contract = parseContract(issue.body || '', issueNumber);
  if (!contract.enrolled) return;

  async function ensureLabels() {
    const existing = await github.paginate(github.rest.issues.listLabelsForRepo, { owner, repo, per_page: 100 });
    const names = new Set(existing.map((item) => item.name));
    for (const [name, [color, description]] of Object.entries(LABEL_DEFINITIONS)) {
      if (names.has(name)) continue;
      try {
        await github.rest.issues.createLabel({ owner, repo, name, color, description });
      } catch (error) {
        if (error.status !== 422) throw error;
      }
    }
  }

  async function setStateLabels(state) {
    const freshIssue = (await github.rest.issues.get({ owner, repo, issue_number: issueNumber })).data;
    const existing = new Set((freshIssue.labels || []).map((item) => typeof item === 'string' ? item : item.name));
    for (const label of STATE_LABELS) {
      if (!existing.has(label)) continue;
      try {
        await github.rest.issues.removeLabel({ owner, repo, issue_number: issueNumber, name: label });
      } catch (error) {
        if (error.status !== 404) throw error;
      }
    }
    await github.rest.issues.addLabels({ owner, repo, issue_number: issueNumber, labels: ['agent-work', labelForState(state)] });
  }

  async function trustedStatus() {
    const comments = await github.paginate(github.rest.issues.listComments, { owner, repo, issue_number: issueNumber, per_page: 100 });
    for (const comment of comments.slice().reverse()) {
      const parsed = parseStatusComment(comment, issueNumber);
      if (parsed) return parsed;
    }
    return null;
  }

  await ensureLabels();
  const current = await trustedStatus();
  if (current) {
    await setStateLabels(current.status.state);
    return;
  }

  const declaredHolder = contract.declaredHolder && !/^none$/i.test(contract.declaredHolder) ? contract.declaredHolder : null;
  const declaredPr = contract.declaredPr && !/^none$/i.test(contract.declaredPr) ? contract.declaredPr : null;
  const invalidReasons = [];

  if (!contract.declaredStateValid || !['READY', 'BLOCKED'].includes(contract.initialState)) {
    invalidReasons.push('automatic enrollment accepts only READY or BLOCKED initial state');
  }
  if (declaredHolder) invalidReasons.push('automatic enrollment cannot materialize a declared holder');
  if (declaredPr) invalidReasons.push('automatic enrollment cannot materialize a linked PR');
  if (contract.initialState === 'READY' && !branchIsConcrete(contract.declaredBranch)) {
    invalidReasons.push('READY work requires a concrete declared branch');
  }
  if (contract.initialState === 'READY' && contract.paths.length === 0 && !isExplicitNoSourceOwnership(contract.positiveOwnership)) {
    invalidReasons.push('READY work requires machine-checkable positive ownership or an allow-listed no-source ownership form');
  }

  const state = invalidReasons.length ? 'BLOCKED' : contract.initialState;
  const timestamp = now();
  const status = {
    schema_version: 'veritas.agent-work-status.v1',
    work_id: contract.workId,
    issue_number: issueNumber,
    state,
    github_actor: null,
    agent_id: null,
    branch: null,
    claimed_at: null,
    heartbeat_at: null,
    linked_pr: null,
    linked_pr_head: null,
    ownership_paths: contract.paths.slice(),
    blocker: invalidReasons.length
      ? `automatic enrollment failed closed: ${invalidReasons.join('; ')}`
      : state === 'BLOCKED' ? 'work-contract-blocked' : null,
    released_reason: null,
    return_state: state === 'BLOCKED' ? 'BLOCKED' : 'READY',
    transition_seq: 0,
    last_command_comment_id: 0,
    updated_at: timestamp,
  };

  // Publish trusted state before discovery labels. If label reconciliation fails,
  // execution still fails safe because labels are never authoritative.
  await github.rest.issues.createComment({ owner, repo, issue_number: issueNumber, body: renderStatus(status) });
  await setStateLabels(status.state);
  await audit(
    invalidReasons.length
      ? `Agent-work automatic enrollment failed closed: **${contract.workId}** -> **BLOCKED**. ${invalidReasons.join('; ')}. OWNER reconciliation is required before claim.`
      : `Agent-work automatic enrollment accepted: **${contract.workId}** -> **${status.state}**. Trusted state was derived from the Work Contract; discovery labels are not execution authority.`
  );
};
