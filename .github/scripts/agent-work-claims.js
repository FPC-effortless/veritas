const ENROLLMENT_MARKER = '<!-- veritas-agent-work -->';
const STATUS_MARKER = '<!-- veritas-agent-work-status:v1 -->';
const RESERVATION_MARKER = '<!-- veritas-agent-work-reservations:v1 -->';
const STATES = ['READY', 'CLAIMED', 'BLOCKED', 'REVIEW', 'DONE', 'SUPERSEDED'];
const ACTIVE_STATES = new Set(['CLAIMED', 'REVIEW', 'BLOCKED']);
const ALLOWED_ASSOCIATIONS = new Set(['OWNER', 'MEMBER', 'COLLABORATOR']);
const STALE_MS = 2 * 60 * 60 * 1000;
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
const labelNames = (issue) => new Set((issue.labels || []).map((item) => typeof item === 'string' ? item : item.name));

function contractValue(text, field, unwrapSingleCodeSpan = true) {
  const escaped = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = text.match(new RegExp(`^- \\*\\*${escaped}:\\*\\*\\s*(.+)$`, 'mi'));
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
  if (normalized.includes('*') && !normalized.endsWith('/**')) return null;
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

function parseContract(text, number) {
  const state = (contractValue(text, 'State') || 'BLOCKED').toUpperCase();
  const positiveOwnership = contractValue(text, 'Positive ownership', false) || '';
  return {
    enrolled: text.includes(ENROLLMENT_MARKER),
    workId: contractValue(text, 'Work ID') || `ISSUE-${number}`,
    initialState: STATES.includes(state) ? state : 'BLOCKED',
    declaredBranch: contractValue(text, 'Branch'),
    declaredHolder: contractValue(text, 'Claim holder'),
    declaredPr: contractValue(text, 'Linked PR'),
    positiveOwnership,
    paths: parsePaths(positiveOwnership),
  };
}

function parseCommand(text) {
  if (text.includes('\n') || text.includes('\r')) return null;
  let match;
  if ((match = text.match(/^\/claim ([A-Za-z0-9][A-Za-z0-9._-]{0,63}) ([A-Za-z0-9][A-Za-z0-9._/-]{0,127})$/))) return { kind: 'claim', agent: match[1], branch: match[2] };
  if ((match = text.match(/^\/heartbeat ([A-Za-z0-9][A-Za-z0-9._-]{0,63})(?: ([A-Za-z0-9][A-Za-z0-9._/-]{0,127}))?$/))) return { kind: 'heartbeat', agent: match[1], branch: match[2] || null };
  if ((match = text.match(/^\/release ([A-Za-z0-9][A-Za-z0-9._-]{0,63})(?: (.{1,500}))?$/))) return { kind: 'release', agent: match[1], reason: match[2] || null };
  if ((match = text.match(/^\/blocked ([A-Za-z0-9][A-Za-z0-9._-]{0,63}) (.{1,500})$/))) return { kind: 'blocked', agent: match[1], reason: match[2] };
  if ((match = text.match(/^\/handoff ([A-Za-z0-9][A-Za-z0-9._-]{0,63}) ([1-9][0-9]*)$/))) return { kind: 'handoff', agent: match[1], pr: Number(match[2]) };
  if ((match = text.match(/^\/done ([A-Za-z0-9][A-Za-z0-9._-]{0,63}) ([1-9][0-9]*)$/))) return { kind: 'done', agent: match[1], pr: Number(match[2]) };
  if ((match = text.match(/^\/recover ([A-Za-z0-9][A-Za-z0-9._-]{0,63}) ([A-Za-z0-9][A-Za-z0-9._/-]{0,127}) (.{1,500})$/))) return { kind: 'recover', agent: match[1], branch: match[2], reason: match[3] };
  return text === '/roadmap-bootstrap' ? { kind: 'bootstrap' } : null;
}

function looksLikeCommand(text) {
  return /^\/(claim|heartbeat|release|blocked|handoff|done|recover)(?:\s|$)/.test(text) || text === '/roadmap-bootstrap';
}

function branchIsConcrete(branch) {
  return Boolean(branch && /^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$/.test(branch));
}

function normalizePath(path) {
  return String(path).replace(/^\.\//, '').replace(/\/\*\*$/, '').replace(/\/$/, '');
}

function pathsOverlap(left, right) {
  const a = normalizePath(left);
  const b = normalizePath(right);
  return a === b || a.startsWith(`${b}/`) || b.startsWith(`${a}/`);
}

function frozenOwnershipPaths(status) {
  if (!Array.isArray(status.ownership_paths)) {
    throw new Error('trusted ownership snapshot is missing; run /roadmap-bootstrap on #150');
  }
  if (status.ownership_paths.some((path) => typeof path !== 'string' || !path)) {
    throw new Error('trusted ownership snapshot is malformed');
  }
  return [...new Set(status.ownership_paths)].sort();
}

function hasActiveReservation(status) {
  return Boolean(status && ACTIVE_STATES.has(status.state) && status.agent_id);
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

function parseRegistryComment(comment) {
  if (comment.user?.login !== 'github-actions[bot]' || !comment.body?.includes(RESERVATION_MARKER)) return null;
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const registry = JSON.parse(match[1]);
    if (registry.schema_version !== 'veritas.agent-work-reservations.v1' || !Array.isArray(registry.entries)) return null;
    return { commentId: comment.id, registry };
  } catch {
    return null;
  }
}

module.exports = async function coordinate({ github, context }) {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const issueNumber = context.issue.number;

  async function audit(number, message) {
    await github.rest.issues.createComment({ owner, repo, issue_number: number, body: message });
  }

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

  async function setStateLabels(issueNumberToUpdate, state) {
    const freshIssue = (await github.rest.issues.get({ owner, repo, issue_number: issueNumberToUpdate })).data;
    const existing = labelNames(freshIssue);
    for (const label of STATE_LABELS) {
      if (!existing.has(label)) continue;
      try {
        await github.rest.issues.removeLabel({ owner, repo, issue_number: issueNumberToUpdate, name: label });
      } catch (error) {
        if (error.status !== 404) throw error;
      }
    }
    await github.rest.issues.addLabels({ owner, repo, issue_number: issueNumberToUpdate, labels: ['agent-work', labelForState(state)] });
  }

  async function commentsFor(number) {
    return github.paginate(github.rest.issues.listComments, { owner, repo, issue_number: number, per_page: 100 });
  }

  async function trustedStatus(issue) {
    const comments = await commentsFor(issue.number);
    for (const comment of comments.slice().reverse()) {
      const parsed = parseStatusComment(comment, issue.number);
      if (parsed) return parsed;
    }
    return null;
  }

  async function writeStatus(issue, current, status) {
    const body = renderStatus(status);
    if (current?.commentId) {
      await github.rest.issues.updateComment({ owner, repo, comment_id: current.commentId, body });
      return { commentId: current.commentId, status };
    }
    const created = await github.rest.issues.createComment({ owner, repo, issue_number: issue.number, body });
    return { commentId: created.data.id, status };
  }

  function bootstrapStatus(issue, contract) {
    let state = contract.initialState;
    const holder = contract.declaredHolder && !/^none$/i.test(contract.declaredHolder) ? contract.declaredHolder : null;
    if (state === 'READY' && holder) state = 'CLAIMED';
    if (ACTIVE_STATES.has(state) && !holder) state = 'BLOCKED';
    const declaredPr = contract.declaredPr && !/^none$/i.test(contract.declaredPr) ? Number(String(contract.declaredPr).replace(/^#/, '')) || null : null;
    const timestamp = now();
    return {
      schema_version: 'veritas.agent-work-status.v1', work_id: contract.workId, issue_number: issue.number, state,
      github_actor: holder ? 'bootstrap' : null, agent_id: holder,
      branch: holder && branchIsConcrete(contract.declaredBranch) ? contract.declaredBranch : null,
      claimed_at: holder ? timestamp : null, heartbeat_at: holder ? timestamp : null,
      linked_pr: declaredPr, linked_pr_head: null,
      ownership_paths: contract.paths.slice(),
      blocker: state === 'BLOCKED' ? 'bootstrap/reconciliation required' : null,
      released_reason: null, return_state: state === 'BLOCKED' ? 'BLOCKED' : 'READY',
      transition_seq: 0, last_command_comment_id: 0, updated_at: timestamp,
    };
  }

  async function listEnrolledIssues() {
    const issues = await github.paginate(github.rest.issues.listForRepo, { owner, repo, state: 'open', per_page: 100 });
    return issues.filter((issue) => !issue.pull_request && issue.body?.includes(ENROLLMENT_MARKER));
  }

  async function trustedRegistry() {
    const comments = await commentsFor(150);
    for (const comment of comments.slice().reverse()) {
      const parsed = parseRegistryComment(comment);
      if (parsed) return parsed;
    }
    return null;
  }

  async function writeRegistry(entries) {
    const sorted = entries.slice().sort((a, b) => a.issue - b.issue);
    const body = `${RESERVATION_MARKER}\n**Global agent-work reservations**\n\n\`\`\`json\n${JSON.stringify({ schema_version: 'veritas.agent-work-reservations.v1', updated_at: now(), entries: sorted }, null, 2)}\n\`\`\``;
    const current = await trustedRegistry();
    if (current) {
      await github.rest.issues.updateComment({ owner, repo, comment_id: current.commentId, body });
    } else {
      await github.rest.issues.createComment({ owner, repo, issue_number: 150, body });
    }
  }

  async function updateRegistryEntry(issue, contract, status) {
    const current = await trustedRegistry();
    if (!current) throw new Error('global reservation registry is missing; run /roadmap-bootstrap on #150');
    const entries = current.registry.entries.filter((entry) => entry.issue !== issue.number);
    if (hasActiveReservation(status)) {
      entries.push({ issue: issue.number, work_id: contract.workId, state: status.state, actor: status.github_actor, agent: status.agent_id, branch: status.branch, linked_pr: status.linked_pr, paths: frozenOwnershipPaths(status) });
    }
    await writeRegistry(entries);
  }

  async function openPrConflicts(candidatePaths, candidateBranch) {
    const pulls = await github.paginate(github.rest.pulls.list, { owner, repo, state: 'open', per_page: 100 });
    for (const pr of pulls) {
      if (pr.head?.ref === candidateBranch) continue;
      const files = await github.paginate(github.rest.pulls.listFiles, { owner, repo, pull_number: pr.number, per_page: 100 });
      for (const file of files) {
        for (const candidate of candidatePaths) {
          if (pathsOverlap(candidate, file.filename)) return { pr: pr.number, path: file.filename, candidate };
        }
      }
    }
    return null;
  }

  async function assertClaimHasNoConflict(issue, contract, branch) {
    if (contract.paths.length === 0 && !isExplicitNoSourceOwnership(contract.positiveOwnership)) {
      throw new Error('claim exposes no machine-checkable positive-ownership path');
    }
    const registry = await trustedRegistry();
    if (!registry) throw new Error('global reservation registry is missing; run /roadmap-bootstrap on #150');
    for (const reservation of registry.registry.entries) {
      if (reservation.issue === issue.number) continue;
      if (reservation.branch && reservation.branch === branch) {
        throw new Error(`branch conflict with ${reservation.work_id}/#${reservation.issue}: ${branch} is already reserved`);
      }
      for (const candidate of contract.paths) {
        for (const reserved of reservation.paths || []) {
          if (pathsOverlap(candidate, reserved)) throw new Error(`ownership conflict with ${reservation.work_id}/#${reservation.issue}: ${candidate} overlaps ${reserved}`);
        }
      }
    }
    const conflict = await openPrConflicts(contract.paths, branch);
    if (conflict) throw new Error(`open PR #${conflict.pr} reserves ${conflict.path}, overlapping ${conflict.candidate}`);
  }

  async function bootstrap(actor, association) {
    if (issueNumber !== 150) return audit(issueNumber, 'Rejected `/roadmap-bootstrap`: bootstrap is accepted only on coordination root #150.');
    if (association !== 'OWNER') return audit(issueNumber, `Rejected roadmap bootstrap from unauthorized actor @${actor} (${association || 'NONE'}); repository OWNER is required.`);
    await ensureLabels();
    const counts = {};
    const entries = [];
    const plans = [];
    let initialized = 0;
    for (const issue of await listEnrolledIssues()) {
      const contract = parseContract(issue.body || '', issue.number);
      const current = await trustedStatus(issue);
      let status;
      let writeRequired = false;
      if (!current) {
        status = bootstrapStatus(issue, contract);
        writeRequired = true;
      } else if (!current.status.return_state || !Array.isArray(current.status.ownership_paths)) {
        status = {
          ...current.status,
          return_state: current.status.return_state || (contract.initialState === 'BLOCKED' ? 'BLOCKED' : 'READY'),
          ownership_paths: Array.isArray(current.status.ownership_paths) ? current.status.ownership_paths : contract.paths.slice(),
          updated_at: now(),
        };
        writeRequired = true;
      } else {
        status = current.status;
      }
      counts[status.state] = (counts[status.state] || 0) + 1;
      if (hasActiveReservation(status)) {
        entries.push({ issue: issue.number, work_id: contract.workId, state: status.state, actor: status.github_actor, agent: status.agent_id, branch: status.branch, linked_pr: status.linked_pr, paths: frozenOwnershipPaths(status) });
      }
      plans.push({ issue, current, status, writeRequired });
      initialized += 1;
    }

    // Publish all active reservations before materializing/migrating trusted local active state.
    // If a later local write fails, the stale reservation remains fail-closed and blocks overlap.
    await writeRegistry(entries);
    for (const plan of plans) {
      if (plan.writeRequired) {
        await writeStatus(plan.issue, plan.current, plan.status);
      }
      await setStateLabels(plan.issue.number, plan.status.state);
    }
    await audit(issueNumber, `Roadmap bootstrap complete: trusted status materialized/reconciled for ${initialized} agent-work issues. State counts: ${Object.entries(counts).sort().map(([key, value]) => `${key}=${value}`).join(', ')}. Labels are discovery metadata only after bootstrap.`);
  }

  const triggerBody = context.payload.comment?.body || '';
  const triggerCommand = parseCommand(triggerBody);
  if (triggerCommand?.kind === 'bootstrap') {
    await bootstrap(context.actor, context.payload.comment?.author_association || '');
    return;
  }

  const issue = (await github.rest.issues.get({ owner, repo, issue_number: issueNumber })).data;
  const contract = parseContract(issue.body || '', issueNumber);
  if (!contract.enrolled) return audit(issueNumber, 'Rejected agent-work command: this issue is not enrolled with the `veritas-agent-work` marker.');
  await ensureLabels();
  let current = await trustedStatus(issue);
  if (!current) {
    await audit(issueNumber, 'Rejected agent-work command: trusted status is missing. Run `/roadmap-bootstrap` on #150; labels and mutable Work Contract state are not execution authority.');
    return;
  }
  if (ACTIVE_STATES.has(current.status.state) && current.status.agent_id && !Array.isArray(current.status.ownership_paths)) {
    await audit(issueNumber, 'Rejected agent-work command: trusted active status predates frozen ownership snapshots. Run `/roadmap-bootstrap` on #150 before further transitions.');
    return;
  }

  const allComments = await commentsFor(issueNumber);
  const lastProcessed = Number(current.status.last_command_comment_id || 0);
  const pending = allComments.filter((comment) => comment.id > lastProcessed && looksLikeCommand(comment.body || '') && comment.body !== '/roadmap-bootstrap').sort((a, b) => a.id - b.id);

  for (const comment of pending) {
    const actor = comment.user?.login || 'unknown';
    const association = comment.author_association || '';
    const command = parseCommand(comment.body || '');
    const previousStatus = current.status;
    const status = { ...previousStatus };
    const timestamp = now();

    async function persistProcessed() {
      status.last_command_comment_id = comment.id;
      status.updated_at = timestamp;
      current = await writeStatus(issue, current, status);
    }
    async function reject(message) {
      await persistProcessed();
      await audit(issueNumber, `Rejected \`${command?.kind || 'malformed'}\` from @${actor}: ${message}`);
    }
    function isHolder(agent) {
      return Boolean(status.agent_id && status.agent_id === agent && status.github_actor === actor);
    }

    if (!command) { await reject('malformed command. Commands must be one exact single line.'); continue; }
    if (!ALLOWED_ASSOCIATIONS.has(association)) { await reject(`unauthorized actor association ${association || 'NONE'}.`); continue; }

    try {
      if (command.kind === 'claim') {
        if (status.state !== 'READY') throw new Error(`work is ${status.state}; current holder is ${status.agent_id || 'none'}`);
        if (branchIsConcrete(contract.declaredBranch) && command.branch !== contract.declaredBranch) throw new Error(`branch ${command.branch} does not match Work Contract branch ${contract.declaredBranch}`);
        await assertClaimHasNoConflict(issue, contract, command.branch);
        Object.assign(status, { state: 'CLAIMED', github_actor: actor, agent_id: command.agent, branch: command.branch, claimed_at: timestamp, heartbeat_at: timestamp, linked_pr: null, linked_pr_head: null, ownership_paths: contract.paths.slice(), blocker: null, released_reason: null, return_state: 'READY' });
      } else if (command.kind === 'heartbeat') {
        if (!ACTIVE_STATES.has(status.state) || !isHolder(command.agent)) throw new Error('heartbeat requires the current authenticated holder');
        if (command.branch && status.branch && command.branch !== status.branch) throw new Error(`branch mismatch; recorded branch is ${status.branch}`);
        status.heartbeat_at = timestamp;
      } else if (command.kind === 'release') {
        if (!ACTIVE_STATES.has(status.state) || !isHolder(command.agent)) throw new Error('release requires the current authenticated holder');
        const target = status.return_state === 'BLOCKED' ? 'BLOCKED' : 'READY';
        Object.assign(status, { state: target, github_actor: null, agent_id: null, branch: null, claimed_at: null, heartbeat_at: null, linked_pr: null, linked_pr_head: null, ownership_paths: [], blocker: target === 'BLOCKED' ? status.blocker : null, released_reason: command.reason });
      } else if (command.kind === 'blocked') {
        if (!['CLAIMED', 'REVIEW'].includes(status.state) || !isHolder(command.agent)) throw new Error('blocked transition requires the current authenticated holder');
        status.state = 'BLOCKED'; status.blocker = command.reason; status.heartbeat_at = timestamp;
      } else if (command.kind === 'handoff') {
        if (!['CLAIMED', 'REVIEW'].includes(status.state) || !isHolder(command.agent)) throw new Error('handoff requires the current CLAIMED/REVIEW authenticated holder');
        if (status.state === 'REVIEW' && status.linked_pr !== command.pr) throw new Error(`re-handoff must preserve linked PR #${status.linked_pr || 'none'}`);
        const pr = (await github.rest.pulls.get({ owner, repo, pull_number: command.pr })).data;
        if (pr.state !== 'open') throw new Error(`PR #${command.pr} is not open`);
        if (status.branch && pr.head.ref !== status.branch) throw new Error(`PR #${command.pr} head ${pr.head.ref} does not match claimed branch ${status.branch}`);
        const primaryWorkId = String(contract.workId).split('/')[0].trim();
        const prBody = pr.body || '';
        if (!prBody.includes(`#${issueNumber}`) || !prBody.includes(primaryWorkId)) throw new Error(`PR #${command.pr} must reference both #${issueNumber} and work ID ${primaryWorkId}`);
        status.state = 'REVIEW'; status.linked_pr = command.pr; status.linked_pr_head = pr.head.sha; status.heartbeat_at = timestamp;
      } else if (command.kind === 'done') {
        if (status.state !== 'REVIEW' || !isHolder(command.agent)) throw new Error('done requires the current REVIEW authenticated holder');
        if (!status.linked_pr || status.linked_pr !== command.pr) throw new Error(`PR mismatch; handoff recorded PR #${status.linked_pr || 'none'}`);
        const pr = (await github.rest.pulls.get({ owner, repo, pull_number: command.pr })).data;
        if (!pr.merged_at) throw new Error(`PR #${command.pr} is not merged; implementation work remains in REVIEW`);
        if (status.linked_pr_head && status.linked_pr_head !== pr.head.sha) throw new Error(`PR #${command.pr} head moved after handoff; re-handoff/review exact final head before DONE`);
        status.state = 'DONE'; status.linked_pr_head = pr.head.sha; status.heartbeat_at = timestamp;
      } else if (command.kind === 'recover') {
        if (association !== 'OWNER') throw new Error('stale/bootstrap recovery requires repository OWNER authority');
        if (!ACTIVE_STATES.has(status.state) || !status.agent_id) throw new Error('recovery requires an active held lane');
        const heartbeat = Date.parse(status.heartbeat_at || status.updated_at || 0);
        const stale = Number.isFinite(heartbeat) && Date.now() - heartbeat >= STALE_MS;
        if (status.github_actor !== 'bootstrap' && !stale) throw new Error('holder is not bootstrap-derived or stale for at least two hours');
        if (status.branch && command.branch !== status.branch) throw new Error(`recovery branch must preserve recorded branch ${status.branch}`);
        if (branchIsConcrete(contract.declaredBranch) && command.branch !== contract.declaredBranch) throw new Error(`recovery branch must match Work Contract branch ${contract.declaredBranch}`);
        frozenOwnershipPaths(status);
        status.github_actor = actor; status.agent_id = command.agent; status.branch = command.branch; status.heartbeat_at = timestamp; status.released_reason = `owner recovery: ${command.reason}`;
      }
    } catch (error) {
      await reject(error.message || String(error));
      continue;
    }

    status.transition_seq = Number(status.transition_seq || 0) + 1;
    status.last_command_comment_id = comment.id;
    status.updated_at = timestamp;

    const reservationMustPrecedeLocal = !hasActiveReservation(previousStatus) && hasActiveReservation(status);
    if (reservationMustPrecedeLocal) {
      // Claim publication is two-phase: reserve globally, then publish trusted local state.
      // A local publication failure leaves a stale global reservation, which is fail-closed.
      await updateRegistryEntry(issue, contract, status);
    }
    current = await writeStatus(issue, current, status);
    await setStateLabels(issue.number, status.state);
    if (!reservationMustPrecedeLocal) {
      // Releases/removals publish locally first. If registry cleanup then fails, the stale
      // reservation remains conservative rather than making active ownership look free.
      await updateRegistryEntry(issue, contract, status);
    }
    const holder = status.agent_id ? ` owner=${status.agent_id} (@${status.github_actor})` : '';
    const prText = status.linked_pr ? ` PR=#${status.linked_pr}` : '';
    await audit(issueNumber, `Agent-work transition accepted in comment order: **${contract.workId}** → **${status.state}**.${holder}${prText} Transition #${status.transition_seq}. Coordination state only; no merge, release, sealed, paid-compute, or qualification authority is granted.`);
  }
};
