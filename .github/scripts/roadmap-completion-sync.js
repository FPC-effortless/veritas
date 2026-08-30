const STATUS_MARKER = '<!-- veritas-agent-work-status:v1 -->';
const ENROLLMENT_MARKER = '<!-- veritas-agent-work -->';
const COMPLETION_MARKER = 'veritas-roadmap-owner-evidence-completion:v1';
const EVIDENCE_PREFIX = 'Completion evidence:';
const STATES = new Set([
  'work:ready',
  'work:claimed',
  'work:blocked',
  'work:review',
  'work:done',
  'work:superseded',
]);
const EXPLICIT_NO_SOURCE_OWNERSHIP = new Set([
  "this issue's comments/labels only",
  'issue labels/comments for roadmap tickets only',
  'roadmap issue comments/labels/manifest metadata only',
  'coordination issue comments/registry only',
]);

const now = () => new Date().toISOString();

function contractValue(text, field, unwrapSingleCodeSpan = true) {
  const escaped = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = String(text || '').match(
    new RegExp(`^- \\*\\*${escaped}:\\*\\*\\s*(.+)$`, 'mi'),
  );
  if (!match) return null;
  const value = match[1].trim();
  if (unwrapSingleCodeSpan && /^`[^`]+`$/.test(value)) {
    return value.slice(1, -1);
  }
  return value;
}

function isExplicitNoSourceOwnership(text) {
  const normalized = String(text || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
  return EXPLICIT_NO_SOURCE_OWNERSHIP.has(normalized);
}

function parseContract(text) {
  const evidenceRaw = contractValue(text, 'Completion evidence comment');
  const evidenceId = /^[1-9][0-9]*$/.test(String(evidenceRaw || ''))
    ? Number(evidenceRaw)
    : null;
  return {
    enrolled: String(text || '').includes(ENROLLMENT_MARKER),
    workId: contractValue(text, 'Work ID'),
    positiveOwnership: contractValue(text, 'Positive ownership', false) || '',
    completionRule: contractValue(text, 'Completion rule'),
    completionClass: contractValue(text, 'Completion class'),
    evidenceCommentId: evidenceId,
    terminalState: contractValue(text, 'Terminal state'),
  };
}

function parseStatusComment(comment, issueNumber) {
  if (
    comment.user?.login !== 'github-actions[bot]' ||
    !comment.body?.includes(STATUS_MARKER)
  ) {
    return null;
  }
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  if (!match) return null;
  let status;
  try {
    status = JSON.parse(match[1]);
  } catch {
    throw new Error(`issue #${issueNumber} has malformed trusted status JSON`);
  }
  if (
    status.schema_version !== 'veritas.agent-work-status.v1' ||
    status.issue_number !== issueNumber
  ) {
    throw new Error(`issue #${issueNumber} has invalid trusted status identity`);
  }
  return { commentId: comment.id, status };
}

function renderStatus(status) {
  return `${STATUS_MARKER}\n**Agent work status**\n\n\`\`\`json\n${JSON.stringify(
    status,
    null,
    2,
  )}\n\`\`\``;
}

function completionAuditMarker(issueNumber, evidenceCommentId) {
  return `<!-- ${COMPLETION_MARKER}:${issueNumber}:${evidenceCommentId} -->`;
}

function validTransitionSequence(status) {
  return Number.isInteger(status?.transition_seq) && status.transition_seq >= 0;
}

function hasUnownedTerminalEligibleStatus(status) {
  return Boolean(
    status &&
      ['BLOCKED', 'READY'].includes(status.state) &&
      status.github_actor === null &&
      status.agent_id === null &&
      status.branch === null &&
      status.linked_pr === null &&
      status.linked_pr_head === null &&
      Array.isArray(status.ownership_paths) &&
      status.ownership_paths.length === 0 &&
      status.completion_evidence == null &&
      validTransitionSequence(status),
  );
}

function isValidOwnerEvidence(comment, expectedId) {
  if (!comment || comment.id !== expectedId) return false;
  if (comment.author_association !== 'OWNER') return false;
  if (!comment.user?.login) return false;
  if (
    typeof comment.created_at !== 'string' ||
    !Number.isFinite(Date.parse(comment.created_at))
  ) {
    return false;
  }
  const body = String(comment.body || '');
  return body.startsWith(EVIDENCE_PREFIX) &&
    body.slice(EVIDENCE_PREFIX.length).trim().length > 0;
}

function hasMatchingCompletionEvent(status, contract, evidence) {
  const event = status?.completion_evidence;
  return Boolean(
    status?.state === 'DONE' &&
      status.work_id === contract.workId &&
      validTransitionSequence(status) &&
      event?.schema_version === 'veritas.owner-evidence-completion.v1' &&
      event.rule === 'OWNER_EVIDENCE' &&
      event.completion_class === 'COORDINATION_OPERATION' &&
      event.evidence_comment_id === contract.evidenceCommentId &&
      event.evidence_actor === evidence.user.login &&
      event.evidence_created_at === evidence.created_at &&
      event.transition_seq === status.transition_seq,
  );
}

module.exports = async function syncCompletion({ github, context }) {
  const owner = context.repo.owner;
  const repo = context.repo.repo;

  async function commentsFor(issueNumber) {
    return github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: issueNumber,
      per_page: 100,
    });
  }

  async function trustedStatus(issueNumber, comments = null) {
    const issueComments = comments || (await commentsFor(issueNumber));
    for (const comment of issueComments.slice().reverse()) {
      const parsed = parseStatusComment(comment, issueNumber);
      if (parsed) return parsed;
    }
    return null;
  }

  async function setDoneLabel(issueNumber) {
    const issue = (
      await github.rest.issues.get({ owner, repo, issue_number: issueNumber })
    ).data;
    const current = new Set(
      (issue.labels || []).map((item) =>
        typeof item === 'string' ? item : item.name,
      ),
    );
    for (const label of STATES) {
      if (!current.has(label)) continue;
      try {
        await github.rest.issues.removeLabel({
          owner,
          repo,
          issue_number: issueNumber,
          name: label,
        });
      } catch (error) {
        if (error.status !== 404) throw error;
      }
    }
    await github.rest.issues.addLabels({
      owner,
      repo,
      issue_number: issueNumber,
      labels: ['agent-work', 'work:done'],
    });
  }

  async function ensureCompletionAudit(issue, contract, event, comments = null) {
    const marker = completionAuditMarker(issue.number, event.evidence_comment_id);
    const issueComments = comments || (await commentsFor(issue.number));
    if (issueComments.some((comment) => comment.body?.includes(marker))) return;
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: issue.number,
      body:
        `${marker}\n**${contract.workId}** completion synchronized to **DONE** ` +
        `from OWNER evidence comment ${event.evidence_comment_id} ` +
        `by @${event.evidence_actor}. ` +
        'No PR, claim, merge/release authority, or qualification PASS was ' +
        'fabricated.',
    });
  }

  const issues = await github.paginate(github.rest.issues.listForRepo, {
    owner,
    repo,
    state: 'open',
    per_page: 100,
  });

  for (const issue of issues) {
    if (issue.pull_request || !issue.body?.includes(ENROLLMENT_MARKER)) continue;
    const contract = parseContract(issue.body);
    if (contract.completionRule !== 'OWNER_EVIDENCE') continue;
    if (
      contract.completionClass !== 'COORDINATION_OPERATION' ||
      contract.terminalState !== 'DONE' ||
      !contract.workId ||
      !contract.evidenceCommentId ||
      !isExplicitNoSourceOwnership(contract.positiveOwnership)
    ) {
      continue;
    }

    const comments = await commentsFor(issue.number);
    const current = await trustedStatus(issue.number, comments);
    if (!current || current.status.work_id !== contract.workId) continue;

    const evidence = comments.find(
      (comment) => comment.id === contract.evidenceCommentId,
    );
    if (!isValidOwnerEvidence(evidence, contract.evidenceCommentId)) continue;

    if (hasMatchingCompletionEvent(current.status, contract, evidence)) {
      const event = current.status.completion_evidence;
      await setDoneLabel(issue.number);
      await ensureCompletionAudit(issue, contract, event, comments);
      await github.rest.issues.update({
        owner,
        repo,
        issue_number: issue.number,
        state: 'closed',
        state_reason: 'completed',
      });
      continue;
    }

    if (!hasUnownedTerminalEligibleStatus(current.status)) continue;

    const transitionSeq = current.status.transition_seq + 1;
    const event = {
      schema_version: 'veritas.owner-evidence-completion.v1',
      rule: 'OWNER_EVIDENCE',
      completion_class: 'COORDINATION_OPERATION',
      evidence_comment_id: evidence.id,
      evidence_actor: evidence.user.login,
      evidence_created_at: evidence.created_at,
      transition_seq: transitionSeq,
    };
    const nextStatus = {
      ...current.status,
      state: 'DONE',
      blocker: null,
      released_reason: null,
      transition_seq: transitionSeq,
      updated_at: now(),
      completion_evidence: event,
    };

    await github.rest.issues.updateComment({
      owner,
      repo,
      comment_id: current.commentId,
      body: renderStatus(nextStatus),
    });
    await setDoneLabel(issue.number);
    await ensureCompletionAudit(issue, contract, event, comments);
    await github.rest.issues.update({
      owner,
      repo,
      issue_number: issue.number,
      state: 'closed',
      state_reason: 'completed',
    });
  }
};

module.exports.__test = {
  completionAuditMarker,
  contractValue,
  hasMatchingCompletionEvent,
  hasUnownedTerminalEligibleStatus,
  isExplicitNoSourceOwnership,
  isValidOwnerEvidence,
  parseContract,
  parseStatusComment,
};
