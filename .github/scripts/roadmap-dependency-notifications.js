const fs = require('fs');
const crypto = require('crypto');

const ENROLLMENT_MARKER = '<!-- veritas-agent-work -->';
const STATUS_MARKER = '<!-- veritas-agent-work-status:v1 -->';
const RESERVATION_MARKER = '<!-- veritas-agent-work-reservations:v1 -->';
const READY_MARKER = 'veritas-roadmap-dependency-ready:v1';
const BLOCKED_MARKER = 'veritas-roadmap-dependency-blocked:v1';
const ACTIVE_RESERVATION_STATES = new Set(['CLAIMED', 'REVIEW', 'BLOCKED']);
const STATE_LABELS = new Set([
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

function repositoryPathToken(value) {
  const raw = String(value || '').trim();
  if (!raw || raw.startsWith('#') || /\s/.test(raw)) return null;
  const normalized = raw.replace(/^\.\//, '');
  if (
    !normalized ||
    normalized.startsWith('/') ||
    normalized.endsWith('/') ||
    normalized.includes('//')
  ) {
    return null;
  }
  if (!/^[A-Za-z0-9._/*+\-]+$/.test(normalized)) return null;
  if (normalized.includes('*') && !/^[^*]+\/\*\*$/.test(normalized)) {
    return null;
  }
  if (normalized.split('/').some((segment) => segment === '.' || segment === '..')) {
    return null;
  }
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
  const normalized = String(text || '')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
  return EXPLICIT_NO_SOURCE_OWNERSHIP.has(normalized);
}

function parseContract(text) {
  const positiveOwnership = contractValue(text, 'Positive ownership', false) || '';
  const watchers = contractValue(text, 'Watchers', false) || '';
  return {
    enrolled: String(text || '').includes(ENROLLMENT_MARKER),
    branch: contractValue(text, 'Branch'),
    positiveOwnership,
    paths: parsePaths(positiveOwnership),
    watchers: [...watchers.matchAll(/@([A-Za-z0-9-]+)/g)].map((match) => match[1]),
  };
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

function parseStatusComment(comment, issueNumber, expectedWorkId = null) {
  if (
    comment.user?.login !== 'github-actions[bot]' ||
    !comment.body?.includes(STATUS_MARKER)
  ) {
    return null;
  }
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  if (!match) {
    throw new Error(`issue #${issueNumber} trusted status JSON is missing`);
  }
  let status;
  try {
    status = JSON.parse(match[1]);
  } catch {
    throw new Error(`issue #${issueNumber} has malformed trusted status JSON`);
  }
  if (
    status.schema_version !== 'veritas.agent-work-status.v1' ||
    status.issue_number !== issueNumber ||
    (expectedWorkId !== null && status.work_id !== expectedWorkId)
  ) {
    throw new Error(`issue #${issueNumber} has invalid trusted status identity`);
  }
  return { commentId: comment.id, status };
}

function parseRegistryComment(comment) {
  if (
    comment.user?.login !== 'github-actions[bot]' ||
    !comment.body?.includes(RESERVATION_MARKER)
  ) {
    return null;
  }
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  if (!match) throw new Error('trusted reservation registry JSON is missing');
  let registry;
  try {
    registry = JSON.parse(match[1]);
  } catch {
    throw new Error('trusted reservation registry JSON is malformed');
  }
  if (
    registry.schema_version !== 'veritas.agent-work-reservations.v1' ||
    !Array.isArray(registry.entries)
  ) {
    throw new Error('trusted reservation registry identity is invalid');
  }
  const issues = new Set();
  for (const entry of registry.entries) {
    const validLinkedPr =
      entry?.linked_pr === null ||
      (Number.isInteger(entry?.linked_pr) && entry.linked_pr > 0);
    const validPaths =
      Array.isArray(entry?.paths) &&
      entry.paths.every(
        (path) =>
          typeof path === 'string' && repositoryPathToken(path) === path,
      );
    if (
      !Number.isInteger(entry?.issue) ||
      entry.issue <= 0 ||
      issues.has(entry.issue) ||
      typeof entry.work_id !== 'string' ||
      !entry.work_id.trim() ||
      !ACTIVE_RESERVATION_STATES.has(entry.state) ||
      typeof entry.actor !== 'string' ||
      !entry.actor.trim() ||
      typeof entry.agent !== 'string' ||
      !entry.agent.trim() ||
      !branchIsConcrete(entry.branch) ||
      !validLinkedPr ||
      !validPaths
    ) {
      throw new Error('trusted reservation registry entry is invalid');
    }
    issues.add(entry.issue);
  }
  return registry;
}

function validTransitionSequence(status) {
  return Number.isInteger(status?.transition_seq) && status.transition_seq >= 0;
}

function hasNoActiveOwnership(status) {
  return Boolean(
    status?.github_actor === null &&
      status.agent_id === null &&
      status.branch === null &&
      status.claimed_at === null &&
      status.heartbeat_at === null &&
      status.linked_pr === null &&
      status.linked_pr_head === null &&
      Array.isArray(status.ownership_paths) &&
      status.ownership_paths.length === 0,
  );
}

function hasValidReadyEvent(status, work) {
  const event = status?.dependency_ready_event;
  return Boolean(
    status?.state === 'READY' &&
      hasNoActiveOwnership(status) &&
      status.blocker === null &&
      status.return_state === 'READY' &&
      validTransitionSequence(status) &&
      event?.schema_version === 'veritas.dependency-ready-event.v1' &&
      event.transition_seq === status.transition_seq &&
      Array.isArray(event.dependencies) &&
      event.dependencies.length === work.hard_dependencies.length &&
      event.dependencies.every(
        (dependency, index) =>
          dependency === work.hard_dependencies[index],
      ) &&
      /^[0-9a-f]{40}$/.test(String(event.canonical_base || '')),
  );
}

function hasUnownedBlockedStatus(status) {
  return Boolean(
    status?.state === 'BLOCKED' &&
      hasNoActiveOwnership(status) &&
      status.dependency_ready_event == null &&
      validTransitionSequence(status),
  );
}

function renderStatus(status) {
  return `${STATUS_MARKER}\n**Agent work status**\n\n\`\`\`json\n${JSON.stringify(
    status,
    null,
    2,
  )}\n\`\`\``;
}

function blockerKey(issueNumber, reason) {
  const digest = crypto.createHash('sha256').update(reason).digest('hex').slice(0, 16);
  return `<!-- ${BLOCKED_MARKER}:${issueNumber}:${digest} -->`;
}

function readyKey(issueNumber, sequence) {
  return `<!-- ${READY_MARKER}:${issueNumber}:${sequence} -->`;
}

function loadRoadmap(path = '.github/agent-roadmap.yml') {
  const parsed = JSON.parse(fs.readFileSync(path, 'utf8'));
  if (
    parsed.schema_version !== 'veritas.agent-roadmap.v1' ||
    !Array.isArray(parsed.work)
  ) {
    throw new Error('roadmap manifest has unexpected schema');
  }
  return parsed;
}

module.exports = async function reconcileDependencies({ github, context }) {
  const owner = context.repo.owner;
  const repo = context.repo.repo;
  const roadmap = loadRoadmap();
  const byWorkId = new Map(roadmap.work.map((item) => [item.work_id, item]));

  async function commentsFor(issueNumber) {
    return github.paginate(github.rest.issues.listComments, {
      owner,
      repo,
      issue_number: issueNumber,
      per_page: 100,
    });
  }

  async function trustedStatus(issueNumber, expectedWorkId) {
    const comments = await commentsFor(issueNumber);
    for (const comment of comments.slice().reverse()) {
      const parsed = parseStatusComment(
        comment,
        issueNumber,
        expectedWorkId,
      );
      if (parsed) return parsed;
    }
    return null;
  }

  async function trustedRegistry() {
    const comments = await commentsFor(150);
    for (const comment of comments.slice().reverse()) {
      const registry = parseRegistryComment(comment);
      if (registry) return registry;
    }
    throw new Error('trusted reservation registry is missing');
  }

  async function setReadyLabel(issueNumber) {
    const issue = (
      await github.rest.issues.get({ owner, repo, issue_number: issueNumber })
    ).data;
    const names = new Set(
      (issue.labels || []).map((item) =>
        typeof item === 'string' ? item : item.name,
      ),
    );
    for (const label of STATE_LABELS) {
      if (!names.has(label)) continue;
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
      labels: ['agent-work', 'work:ready'],
    });
  }

  async function ensureComment(issueNumber, marker, body) {
    const comments = await commentsFor(issueNumber);
    if (
      comments.some(
        (comment) =>
          comment.user?.login === 'github-actions[bot]' &&
          typeof comment.body === 'string' &&
          comment.body.startsWith(`${marker}\n`),
      )
    ) {
      return;
    }
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: issueNumber,
      body: `${marker}\n${body}`,
    });
  }

  async function reportBlocked(issueNumber, reason) {
    const marker = blockerKey(issueNumber, reason);
    await ensureComment(
      issueNumber,
      marker,
      `Dependency readiness remains **BLOCKED**: ${reason}. ` +
        'No claim or reservation was created.',
    );
  }

  const repository = (await github.rest.repos.get({ owner, repo })).data;
  const defaultBranch = repository.default_branch;
  if (!defaultBranch) throw new Error('repository default branch is missing');
  const branch = (
    await github.rest.repos.getBranch({ owner, repo, branch: defaultBranch })
  ).data;
  const mainSha = branch.commit?.sha;
  if (!/^[0-9a-f]{40}$/.test(String(mainSha || ''))) {
    throw new Error('default branch SHA is missing or malformed');
  }

  const registry = await trustedRegistry();
  const openPulls = await github.paginate(github.rest.pulls.list, {
    owner,
    repo,
    state: 'open',
    per_page: 100,
  });
  const openPrFiles = [];
  for (const pr of openPulls) {
    const files = await github.paginate(github.rest.pulls.listFiles, {
      owner,
      repo,
      pull_number: pr.number,
      per_page: 100,
    });
    for (const file of files) {
      if (typeof file.filename === 'string') {
        openPrFiles.push({ pr: pr.number, branch: pr.head?.ref || null, path: file.filename });
      }
    }
  }

  async function providerProof(workId) {
    const provider = byWorkId.get(workId);
    if (!provider) {
      return { ok: false, reason: `hard dependency ${workId} is missing from roadmap` };
    }
    if (provider.program !== 'coordination') {
      return {
        ok: false,
        reason: `hard dependency ${workId} requires non-coordination authority`,
      };
    }
    const current = await trustedStatus(provider.issue, workId);
    if (
      !current ||
      current.status.state !== 'DONE' ||
      !validTransitionSequence(current.status)
    ) {
      return { ok: false, reason: `hard dependency ${workId} is not trusted DONE` };
    }
    const linkedPr = current.status.linked_pr;
    const linkedHead = current.status.linked_pr_head;
    if (!Number.isInteger(linkedPr) || !/^[0-9a-f]{40}$/.test(String(linkedHead || ''))) {
      return {
        ok: false,
        reason: `hard dependency ${workId} lacks exact merged-PR identity`,
      };
    }
    const pr = (
      await github.rest.pulls.get({ owner, repo, pull_number: linkedPr })
    ).data;
    if (
      pr.merged !== true ||
      pr.state !== 'closed' ||
      pr.head?.sha !== linkedHead ||
      !/^[0-9a-f]{40}$/.test(String(pr.merge_commit_sha || ''))
    ) {
      return {
        ok: false,
        reason: `hard dependency ${workId} is not exact-head merged`,
      };
    }
    const comparison = (
      await github.rest.repos.compareCommitsWithBasehead({
        owner,
        repo,
        basehead: `${pr.merge_commit_sha}...${mainSha}`,
      })
    ).data;
    if (
      comparison.behind_by !== 0 ||
      !['ahead', 'identical'].includes(comparison.status)
    ) {
      return {
        ok: false,
        reason: `hard dependency ${workId} merge is not on current ${defaultBranch}`,
      };
    }
    return {
      ok: true,
      work_id: workId,
      issue: provider.issue,
      pr: linkedPr,
      pr_head: linkedHead,
      merge_commit: pr.merge_commit_sha,
    };
  }

  for (const work of roadmap.work) {
    if (work.program !== 'coordination') continue;
    if (!Array.isArray(work.hard_dependencies) || work.hard_dependencies.length === 0) {
      continue;
    }

    const issue = (
      await github.rest.issues.get({ owner, repo, issue_number: work.issue })
    ).data;
    if (issue.state !== 'open') continue;

    const current = await trustedStatus(work.issue, work.work_id);
    if (!current) continue;

    if (hasValidReadyEvent(current.status, work)) {
      await setReadyLabel(work.issue);
      const event = current.status.dependency_ready_event;
      const marker = readyKey(work.issue, event.transition_seq);
      const contract = parseContract(issue.body || '');
      const mention = contract.watchers.length
        ? `${contract.watchers.map((watcher) => `@${watcher}`).join(' ')} `
        : '';
      await ensureComment(
        work.issue,
        marker,
        `${mention}**${work.work_id}** is dependency-ready. ` +
          `Verified hard dependencies: ${event.dependencies.join(', ')}. ` +
          'No claim or ownership reservation was created.',
      );
      continue;
    }

    const status = current.status;
    if (!hasUnownedBlockedStatus(status)) continue;

    const proofs = [];
    let dependencyFailure = null;
    for (const dependency of work.hard_dependencies) {
      const proof = await providerProof(dependency);
      if (!proof.ok) {
        dependencyFailure = proof.reason;
        break;
      }
      proofs.push(proof);
    }
    if (dependencyFailure) continue;

    const contract = parseContract(issue.body || '');
    if (!contract.enrolled || !branchIsConcrete(contract.branch)) {
      await reportBlocked(work.issue, 'candidate Work Contract lacks a concrete branch');
      continue;
    }
    if (
      contract.paths.length === 0 &&
      !isExplicitNoSourceOwnership(contract.positiveOwnership)
    ) {
      await reportBlocked(
        work.issue,
        'candidate Work Contract lacks machine-checkable positive ownership',
      );
      continue;
    }

    let collision = null;
    for (const reservation of registry.entries) {
      if (reservation.issue === work.issue) continue;
      for (const candidate of contract.paths) {
        const reserved = reservation.paths.find((path) => pathsOverlap(candidate, path));
        if (reserved) {
          collision = `path ${candidate} overlaps active #${reservation.issue} path ${reserved}`;
          break;
        }
      }
      if (collision) break;
    }
    if (!collision) {
      for (const candidate of contract.paths) {
        const conflict = openPrFiles.find(
          (file) =>
            file.branch !== contract.branch && pathsOverlap(candidate, file.path),
        );
        if (conflict) {
          collision = `path ${candidate} overlaps open PR #${conflict.pr} file ${conflict.path}`;
          break;
        }
      }
    }
    if (collision) {
      await reportBlocked(work.issue, collision);
      continue;
    }

    const transitionSeq = status.transition_seq + 1;
    const dependencyIds = proofs.map((proof) => proof.work_id);
    const nextStatus = {
      ...status,
      state: 'READY',
      blocker: null,
      return_state: 'READY',
      transition_seq: transitionSeq,
      updated_at: now(),
      dependency_ready_event: {
        schema_version: 'veritas.dependency-ready-event.v1',
        transition_seq: transitionSeq,
        dependencies: dependencyIds,
        canonical_base: mainSha,
      },
    };

    await github.rest.issues.updateComment({
      owner,
      repo,
      comment_id: current.commentId,
      body: renderStatus(nextStatus),
    });
    await setReadyLabel(work.issue);

    const marker = readyKey(work.issue, transitionSeq);
    const mention = contract.watchers.length
      ? `${contract.watchers.map((watcher) => `@${watcher}`).join(' ')} `
      : '';
    await ensureComment(
      work.issue,
      marker,
      `${mention}**${work.work_id}** transitioned **BLOCKED → READY** after ` +
        `verifying hard dependencies ${dependencyIds.join(', ')} on canonical ` +
        `${defaultBranch} ${mainSha.slice(0, 12)}. No claim or ownership reservation ` +
        'was created.',
    );
  }
};

module.exports.__test = {
  branchIsConcrete,
  hasUnownedBlockedStatus,
  hasValidReadyEvent,
  isExplicitNoSourceOwnership,
  parseContract,
  parseStatusComment,
  pathsOverlap,
  repositoryPathToken,
  validTransitionSequence,
};