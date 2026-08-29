import json
import subprocess
from pathlib import Path

WORKFLOW = Path(".github/workflows/agent-work-claims.yml")
SCRIPT = Path(".github/scripts/agent-work-claims.js")
DOC = Path("docs/automation/agent-work-claims.md")


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


def test_claim_workflow_has_least_privilege_and_no_dispatch_authority() -> None:
    text = _workflow()
    assert "contents: read" in text
    assert "issues: write" in text
    assert "pull-requests: read" in text
    assert "actions: write" not in text
    assert "packages: write" not in text
    assert "id-token: write" not in text
    assert "secrets:" not in text
    assert "workflow_dispatch:" not in text


def test_claim_workflow_serializes_and_drains_through_script() -> None:
    workflow = _workflow()
    script = _script()
    assert "group: agent-work-coordination" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "actions/checkout@v4" in workflow
    assert "agent-work-claims.js" in workflow
    assert "sort((a, b) => a.id - b.id)" in script
    assert "last_command_comment_id" in script


def test_execution_requires_trusted_status_not_labels_or_mutable_contract_state() -> None:
    script = _script()
    assert "trusted status is missing" in script
    assert "labels and mutable Work Contract state are not execution authority" in script
    assert "const target = status.return_state === 'BLOCKED' ? 'BLOCKED' : 'READY'" in script
    assert "return_state: current.status.return_state ||" in script
    release_block = script.split("} else if (command.kind === 'release') {", 1)[1].split(
        "} else if (command.kind === 'blocked') {", 1
    )[0]
    assert "contract.initialState" not in release_block


def test_bootstrap_ignores_untrusted_state_labels_and_is_owner_only() -> None:
    script = _script()
    bootstrap_status = script.split("function bootstrapStatus(issue, contract) {", 1)[1].split(
        "async function listEnrolledIssues()", 1
    )[0]
    assert "let state = contract.initialState" in bootstrap_status
    assert "labelNames(issue)" not in bootstrap_status
    assert "labeledStates" not in bootstrap_status
    bootstrap = script.split("async function bootstrap(actor, association) {", 1)[1].split(
        "const triggerBody", 1
    )[0]
    assert "association !== 'OWNER'" in bootstrap
    assert "repository OWNER is required" in bootstrap


def test_claim_enforces_declared_branch_global_paths_and_branch_uniqueness() -> None:
    script = _script()
    assert "command.branch !== contract.declaredBranch" in script
    assert "trustedRegistry" in script
    assert "updateRegistryEntry" in script
    assert "openPrConflicts" in script
    assert "pathsOverlap(candidate, reserved)" in script
    assert "reservation.branch && reservation.branch === branch" in script
    assert "is already reserved" in script
    assert "open PR #${conflict.pr} reserves" in script
    assert "veritas.agent-work-reservations.v1" in script


def test_zero_path_claim_exemption_is_explicit_and_narrow() -> None:
    script = _script()
    assert "EXPLICIT_NO_SOURCE_OWNERSHIP" in script
    assert "isExplicitNoSourceOwnership(contract.positiveOwnership)" in script
    assert "!/coordination|metadata only|no product branch/i" not in script
    assert '"this issue\'s comments/labels only"' in script
    assert "coordination docs/tests only" not in script


def test_ownership_path_wildcards_are_terminal_subtrees_only() -> None:
    script_path = json.dumps(str(SCRIPT.resolve()))
    source = r"""
const fs = require('fs');
const vm = require('vm');
const exportPathToken = '\nmodule.exports.__pathToken = repositoryPathToken;';
const source = fs.readFileSync(__SCRIPT__, 'utf8') + exportPathToken;
const moduleObject = { exports: {} };
vm.runInNewContext(source, {
  module: moduleObject,
  exports: moduleObject.exports,
  require,
  console,
  Set,
  Date,
  JSON,
  String,
  Number,
  Boolean,
  RegExp,
  Error,
});
const pathToken = moduleObject.exports.__pathToken;
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
const invalidPaths = ['src/*/private/**', 'src/**/private/**', '*.md/**'];
for (const invalid of invalidPaths) {
  assert(pathToken(invalid) === null, `unsupported wildcard accepted: ${invalid}`);
}
const validPaths = [
  'Dockerfile',
  '.github/workflows/file.yml',
  'src/private/file.py',
  'src/private/**',
];
for (const valid of validPaths) {
  assert(pathToken(valid) === valid, `valid ownership rejected: ${valid}`);
}
""".replace("__SCRIPT__", script_path)
    _run_node(source)


def test_active_ownership_is_frozen_in_trusted_status() -> None:
    script = _script()
    claim_block = script.split("if (command.kind === 'claim') {", 1)[1].split(
        "} else if (command.kind === 'heartbeat') {", 1
    )[0]
    assert "ownership_paths: contract.paths.slice()" in claim_block
    registry_block = script.split("async function updateRegistryEntry", 1)[1].split(
        "async function openPrConflicts", 1
    )[0]
    assert "frozenOwnershipPaths(status)" in registry_block
    assert "paths: contract.paths" not in registry_block
    assert "trusted ownership snapshot is missing" in script
    assert "!Array.isArray(current.status.ownership_paths)" in script


def test_label_reconciliation_reads_fresh_issue_state() -> None:
    script = _script()
    assert "freshIssue = (await github.rest.issues.get" in script
    assert "setStateLabels(plan.issue.number, plan.status.state)" in script
    assert "setStateLabels(issue.number, status.state)" in script


def test_handoff_and_done_bind_exact_final_pr_head_and_allow_same_pr_rehandoff() -> None:
    script = _script()
    handoff_block = script.split("} else if (command.kind === 'handoff') {", 1)[1].split(
        "} else if (command.kind === 'done') {", 1
    )[0]
    assert "['CLAIMED', 'REVIEW'].includes(status.state)" in handoff_block
    assert "status.state === 'REVIEW' && status.linked_pr !== command.pr" in handoff_block
    assert "pr.head.ref !== status.branch" in handoff_block
    assert "prBody.includes(`#${issueNumber}`)" in handoff_block
    assert "prBody.includes(primaryWorkId)" in handoff_block
    assert "status.linked_pr_head = pr.head.sha" in handoff_block
    assert "!status.linked_pr || status.linked_pr !== command.pr" in script
    assert "status.linked_pr_head !== pr.head.sha" in script
    assert "re-handoff/review exact final head before DONE" in script


def test_bootstrap_reserves_before_materializing_active_status() -> None:
    script = _script()
    bootstrap = script.split("async function bootstrap(actor, association) {", 1)[1].split(
        "const triggerBody", 1
    )[0]
    assert "status = bootstrapStatus(issue, contract)" in bootstrap
    assert "plans.push({ issue, current, status, writeRequired })" in bootstrap
    assert "await writeRegistry(entries)" in bootstrap
    assert "await writeStatus(plan.issue, plan.current, plan.status)" in bootstrap
    assert bootstrap.index("await writeRegistry(entries)") < bootstrap.index(
        "await writeStatus(plan.issue, plan.current, plan.status)"
    )
    assert "paths: frozenOwnershipPaths(status)" in bootstrap
    assert "Labels are discovery metadata only after bootstrap" in bootstrap


def test_claim_publication_is_reservation_first_and_release_is_fail_closed() -> None:
    script = _script()
    tail = script.split(
        "const reservationMustPrecedeLocal = !hasActiveReservation(previousStatus)", 1
    )[1]
    assert "await updateRegistryEntry(issue, contract, status)" in tail
    assert "current = await writeStatus(issue, current, status)" in tail
    first_registry = tail.index("await updateRegistryEntry(issue, contract, status)")
    local_status = tail.index("current = await writeStatus(issue, current, status)")
    assert first_registry < local_status
    assert "stale global reservation" in tail
    assert "reservation remains conservative" in tail


def test_bootstrap_holder_and_stale_recovery_require_owner_audit() -> None:
    script = _script()
    assert "command.kind === 'recover'" in script
    assert "association !== 'OWNER'" in script
    assert "status.github_actor !== 'bootstrap' && !stale" in script
    assert "frozenOwnershipPaths(status)" in script
    assert "STALE_MS = 2 * 60 * 60 * 1000" in script


def test_failure_injection_preserves_global_exclusion_and_root_file_locks() -> None:
    script_path = json.dumps(str(SCRIPT.resolve()))
    source = r"""
const coordinate = require(__SCRIPT__);
const ENROLL = '<!-- veritas-agent-work -->';
const STATUS = '<!-- veritas-agent-work-status:v1 -->';
const REGISTRY = '<!-- veritas-agent-work-reservations:v1 -->';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function contract(workId, branch, ownership, state = 'READY', holder = 'none') {
  return `${ENROLL}
## Work Contract
- **Work ID:** ${workId}
- **State:** ${state}
- **Branch:** \`${branch}\`
- **Positive ownership:** ${ownership}
- **Claim holder:** ${holder}
- **Linked PR:** none`;
}

function readyStatus(issue, workId) {
  return {
    schema_version: 'veritas.agent-work-status.v1',
    work_id: workId,
    issue_number: issue,
    state: 'READY',
    github_actor: null,
    agent_id: null,
    branch: null,
    claimed_at: null,
    heartbeat_at: null,
    linked_pr: null,
    linked_pr_head: null,
    ownership_paths: [],
    blocker: null,
    released_reason: null,
    return_state: 'READY',
    transition_seq: 0,
    last_command_comment_id: 0,
    updated_at: '2026-08-29T00:00:00.000Z',
  };
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
  updated_at: '2026-08-29T00:00:00.000Z',
  entries,
}, null, 2)}
\`\`\``,
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

function parseStatus(comment) {
  const match = comment.body.match(/```json\s*([\s\S]*?)```/);
  return match ? JSON.parse(match[1]) : null;
}

function makeWorld({
  issues,
  comments,
  failRegistry = false,
  failStatusIssue = null,
  failCreatedStatusIssue = null,
}) {
  let nextCommentId = 5000;
  const audits = [];
  const events = [];
  const state = {
    failRegistry,
    failStatusIssue,
    failCreatedStatusIssue,
  };

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
      const labels = issues[issue_number].labels || [];
      issues[issue_number].labels = labels.filter((item) => item.name !== name);
      return { data: {} };
    },
    addLabels: async ({ issue_number, labels }) => {
      const existing = new Set((issues[issue_number].labels || []).map((item) => item.name));
      for (const name of labels) existing.add(name);
      issues[issue_number].labels = [...existing].map((name) => ({ name }));
      return { data: {} };
    },
    listComments: async ({ issue_number }) => comments[issue_number] || [],
    listForRepo: async () => Object.values(issues),
    updateComment: async ({ comment_id, body }) => {
      if (comment_id === 900) {
        events.push('registry-write');
        if (state.failRegistry) throw new Error('injected registry failure');
      }
      for (const [issueNumber, issueComments] of Object.entries(comments)) {
        const target = issueComments.find((comment) => comment.id === comment_id);
        if (!target) continue;
        if (
          body.includes(STATUS) &&
          state.failStatusIssue !== null &&
          Number(issueNumber) === state.failStatusIssue
        ) {
          events.push(`status-write-${issueNumber}`);
          throw new Error(`injected status failure ${issueNumber}`);
        }
        target.body = body;
        if (body.includes(STATUS)) events.push(`status-write-${issueNumber}`);
        return { data: target };
      }
      throw new Error(`unknown comment ${comment_id}`);
    },
    createComment: async ({ issue_number, body }) => {
      if (
        body.includes(STATUS) &&
        state.failCreatedStatusIssue !== null &&
        issue_number === state.failCreatedStatusIssue
      ) {
        events.push(`status-create-${issue_number}`);
        throw new Error(`injected status create failure ${issue_number}`);
      }
      const created = {
        id: nextCommentId++,
        user: { login: 'github-actions[bot]' },
        author_association: 'NONE',
        body,
      };
      comments[issue_number] = comments[issue_number] || [];
      comments[issue_number].push(created);
      if (body.includes(STATUS)) events.push(`status-create-${issue_number}`);
      else audits.push({ issue: issue_number, body });
      return { data: created };
    },
  };

  const pullApi = {
    list: async () => [],
    listFiles: async () => [],
    get: async () => {
      throw new Error('unexpected pulls.get');
    },
  };

  const github = {
    rest: { issues: issueApi, pulls: pullApi },
    paginate: async (fn, args) => fn(args),
  };

  return { github, issues, comments, audits, events, state };
}

function context(issueNumber, body) {
  return {
    repo: { owner: 'FPC-effortless', repo: 'veritas' },
    issue: { number: issueNumber },
    actor: 'FPC-effortless',
    payload: {
      comment: {
        body,
        author_association: 'OWNER',
      },
    },
  };
}

async function runClaimRegistryFailure() {
  const issues = {
    1: {
      number: 1,
      body: contract('A', 'feat/a', '`src/shared/**`'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claim = commandComment(2001, '/claim agent-a feat/a');
  const comments = {
    1: [statusComment(1001, readyStatus(1, 'A')), claim],
    150: [registryComment([])],
  };
  const world = makeWorld({ issues, comments, failRegistry: true });
  try {
    await coordinate({ github: world.github, context: context(1, claim.body) });
  } catch (error) {
    assert(error.message.includes('injected registry failure'), 'wrong injected failure');
  }
  assert(parseStatus(comments[1][0]).state === 'READY', 'registry failure published CLAIMED');
  assert(
    !world.events.some((event) => event.startsWith('status-write-1')),
    'local status write ran after failed reservation'
  );
}

async function runClaimLocalFailureThenOverlap() {
  const issues = {
    1: {
      number: 1,
      body: contract('A', 'feat/a', '`src/shared/**`'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
    2: {
      number: 2,
      body: contract('B', 'feat/b', '`src/shared/file.py`'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claimA = commandComment(2001, '/claim agent-a feat/a');
  const claimB = commandComment(3001, '/claim agent-b feat/b');
  const comments = {
    1: [statusComment(1001, readyStatus(1, 'A')), claimA],
    2: [statusComment(1002, readyStatus(2, 'B')), claimB],
    150: [registryComment([])],
  };
  const world = makeWorld({ issues, comments, failStatusIssue: 1 });
  try {
    await coordinate({ github: world.github, context: context(1, claimA.body) });
  } catch (error) {
    assert(error.message.includes('injected status failure 1'), 'wrong local failure');
  }
  const registryAfterFailure = parseStatus(comments[150][0]);
  assert(registryAfterFailure.entries.length === 1, 'reservation was not retained');
  assert(registryAfterFailure.entries[0].issue === 1, 'wrong stale reservation');
  assert(
    world.events.indexOf('registry-write') < world.events.indexOf('status-write-1'),
    'CLAIMED status was attempted before global reservation'
  );

  world.state.failStatusIssue = null;
  await coordinate({ github: world.github, context: context(2, claimB.body) });
  assert(parseStatus(comments[2][0]).state === 'READY', 'overlapping second claim was accepted');
  assert(
    world.audits.some((entry) => entry.body.includes('ownership conflict with A/#1')),
    'overlap was not rejected from stale reservation'
  );
}

async function runBootstrapFailureOrdering() {
  const issues = {
    1: {
      number: 1,
      body: contract('A', 'feat/a', '`src/shared/**`', 'CLAIMED', 'bootstrap-a'),
      labels: [{ name: 'agent-work' }, { name: 'work:claimed' }],
    },
    2: {
      number: 2,
      body: contract('B', 'feat/b', '`src/shared/file.py`'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claimB = commandComment(3001, '/claim agent-b feat/b');
  const bootstrap = commandComment(4001, '/roadmap-bootstrap');
  const comments = {
    1: [],
    2: [statusComment(1002, readyStatus(2, 'B')), claimB],
    150: [registryComment([]), bootstrap],
  };

  const registryFailureWorld = makeWorld({
    issues: JSON.parse(JSON.stringify(issues)),
    comments: {
      1: [],
      2: [statusComment(1002, readyStatus(2, 'B')), claimB],
      150: [registryComment([]), bootstrap],
    },
    failRegistry: true,
  });
  try {
    await coordinate({
      github: registryFailureWorld.github,
      context: context(150, bootstrap.body),
    });
  } catch (error) {
    assert(error.message.includes('injected registry failure'), 'wrong bootstrap registry failure');
  }
  assert(
    registryFailureWorld.comments[1].length === 0,
    'bootstrap materialized active status before registry commit'
  );

  const world = makeWorld({ issues, comments, failCreatedStatusIssue: 1 });
  try {
    await coordinate({ github: world.github, context: context(150, bootstrap.body) });
  } catch (error) {
    assert(
      error.message.includes('injected status create failure 1'),
      'wrong bootstrap local failure'
    );
  }
  const registryAfterFailure = parseStatus(comments[150][0]);
  assert(registryAfterFailure.entries.length === 1, 'bootstrap reservation was not retained');
  assert(registryAfterFailure.entries[0].issue === 1, 'bootstrap reserved wrong issue');
  assert(
    world.events.indexOf('registry-write') < world.events.indexOf('status-create-1'),
    'bootstrap local active state was attempted before registry'
  );

  world.state.failCreatedStatusIssue = null;
  await coordinate({ github: world.github, context: context(2, claimB.body) });
  assert(
    parseStatus(comments[2][0]).state === 'READY',
    'overlap escaped bootstrap stale reservation'
  );
  assert(
    world.audits.some((entry) => entry.body.includes('ownership conflict with A/#1')),
    'bootstrap stale reservation did not reject overlap'
  );
}

async function runMalformedOwnershipToken() {
  const issues = {
    1: {
      number: 1,
      body: contract('BAD', 'feat/bad', '`not a repository path`'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claim = commandComment(2001, '/claim agent-bad feat/bad');
  const comments = {
    1: [statusComment(1001, readyStatus(1, 'BAD')), claim],
    150: [registryComment([])],
  };
  const world = makeWorld({ issues, comments });
  await coordinate({ github: world.github, context: context(1, claim.body) });
  assert(parseStatus(comments[1][0]).state === 'READY', 'non-path metadata token was accepted');
  assert(
    world.audits.some(
      (entry) => entry.body.includes('no machine-checkable positive-ownership path')
    ),
    'non-path metadata token did not fail closed'
  );
}

async function runUnsupportedWildcardOwnership() {
  const ownershipCases = [
    '`src/*/private/**`',
    '`src/**/private/**`',
    '`*.md/**`',
  ];
  for (const [index, ownership] of ownershipCases.entries()) {
    const issueNumber = index + 1;
    const branch = `feat/wildcard-${index}`;
    const issues = {
      [issueNumber]: {
        number: issueNumber,
        body: contract(`WILDCARD-${index}`, branch, ownership),
        labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
      },
    };
    const claim = commandComment(2100 + index, `/claim wildcard-${index} ${branch}`);
    const status = readyStatus(issueNumber, `WILDCARD-${index}`);
    const comments = {
      [issueNumber]: [statusComment(1100 + index, status), claim],
      150: [registryComment([])],
    };
    const world = makeWorld({ issues, comments });
    await coordinate({
      github: world.github,
      context: context(issueNumber, claim.body),
    });
    assert(
      parseStatus(comments[issueNumber][0]).state === 'READY',
      `${ownership} published CLAIMED`
    );
    assert(
      parseStatus(comments[150][0]).entries.length === 0,
      `${ownership} created a reservation`
    );
    assert(
      world.audits.some(
        (entry) => entry.body.includes('no machine-checkable positive-ownership path')
      ),
      `${ownership} did not fail closed`
    );
  }
}

async function runTerminalSubtreeOpenPrCollision() {
  const issues = {
    1: {
      number: 1,
      body: contract('TREE', 'feat/tree', '`src/private/**`'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claim = commandComment(2201, '/claim agent-tree feat/tree');
  const comments = {
    1: [statusComment(1201, readyStatus(1, 'TREE')), claim],
    150: [registryComment([])],
  };
  const world = makeWorld({ issues, comments });
  world.github.rest.pulls.list = async () => [
    { number: 77, head: { ref: 'feat/other' } },
  ];
  world.github.rest.pulls.listFiles = async () => [
    { filename: 'src/private/file.py' },
  ];
  await coordinate({
    github: world.github,
    context: context(1, claim.body),
  });
  assert(
    parseStatus(comments[1][0]).state === 'READY',
    'open-PR subtree collision was accepted'
  );
  assert(
    world.audits.some(
      (entry) => entry.body.includes('open PR #77 reserves src/private/file.py')
    ),
    'terminal subtree did not collide with open PR descendant'
  );
}

async function runCoordinationRepositoryEditingProse() {
  const issues = {
    1: {
      number: 1,
      body: contract('AUTH', 'docs/auth', 'coordination docs/tests only'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claim = commandComment(2001, '/claim agent-auth docs/auth');
  const comments = {
    1: [statusComment(1001, readyStatus(1, 'AUTH')), claim],
    150: [registryComment([])],
  };
  const world = makeWorld({ issues, comments });
  await coordinate({ github: world.github, context: context(1, claim.body) });
  assert(
    parseStatus(comments[1][0]).state === 'READY',
    'repository-editing coordination prose bypassed path locking'
  );
  assert(
    world.audits.some(
      (entry) => entry.body.includes('no machine-checkable positive-ownership path')
    ),
    'repository-editing coordination prose did not fail closed'
  );
  assert(
    parseStatus(comments[150][0]).entries.length === 0,
    'rejected prose claim reserved globally'
  );
}

async function runExplicitIssueOnlyOwnership() {
  const issues = {
    1: {
      number: 1,
      body: contract('REHEARSAL', 'test/rehearsal', "this issue's comments/labels only"),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claim = commandComment(2001, '/claim agent-rehearsal test/rehearsal');
  const comments = {
    1: [statusComment(1001, readyStatus(1, 'REHEARSAL')), claim],
    150: [registryComment([])],
  };
  const world = makeWorld({ issues, comments });
  await coordinate({ github: world.github, context: context(1, claim.body) });
  assert(parseStatus(comments[1][0]).state === 'CLAIMED', 'explicit issue-only lane was rejected');
  const registry = parseStatus(comments[150][0]);
  assert(registry.entries.length === 1, 'issue-only lane was not represented in registry');
  assert(registry.entries[0].issue === 1, 'wrong issue-only reservation');
  assert(
    registry.entries[0].paths.length === 0,
    'issue-only lane unexpectedly reserved source paths'
  );
}

async function runRootFileCollision() {
  const issues = {
    1: {
      number: 1,
      body: contract('ROOT', 'feat/root', '`Dockerfile`'),
      labels: [{ name: 'agent-work' }, { name: 'work:ready' }],
    },
  };
  const claim = commandComment(2001, '/claim agent-root feat/root');
  const comments = {
    1: [statusComment(1001, readyStatus(1, 'ROOT')), claim],
    150: [registryComment([{
      issue: 99,
      work_id: 'OTHER',
      state: 'CLAIMED',
      actor: 'FPC-effortless',
      agent: 'other',
      branch: 'feat/other',
      linked_pr: null,
      paths: ['Dockerfile'],
    }])],
  };
  const world = makeWorld({ issues, comments });
  await coordinate({ github: world.github, context: context(1, claim.body) });
  assert(parseStatus(comments[1][0]).state === 'READY', 'root-file collision was accepted');
  assert(
    world.audits.some((entry) => entry.body.includes('Dockerfile overlaps Dockerfile')),
    'root-level Dockerfile was not parsed as an exact reservation'
  );
}

(async () => {
  await runClaimRegistryFailure();
  await runClaimLocalFailureThenOverlap();
  await runBootstrapFailureOrdering();
  await runMalformedOwnershipToken();
  await runUnsupportedWildcardOwnership();
  await runTerminalSubtreeOpenPrCollision();
  await runCoordinationRepositoryEditingProse();
  await runExplicitIssueOnlyOwnership();
  await runRootFileCollision();
  process.stdout.write('ok\n');
})().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
""".replace("__SCRIPT__", script_path)
    _run_node(source)


def test_untrusted_comment_text_is_not_sent_to_a_shell() -> None:
    workflow = _workflow()
    assert "uses: actions/github-script@v7" in workflow
    assert "shell:" not in workflow
    assert "run:" not in workflow


def test_bootstrap_and_agent_startup_are_documented() -> None:
    doc = DOC.read_text(encoding="utf-8")
    assert "/roadmap-bootstrap" in doc
    assert "trusted bot-authored status" in doc
    assert "frozen ownership" in doc.lower()
    assert "OWNER-only" in doc
    assert "same PR" in doc
    assert "comment-ID order" in doc
    assert "/recover" in doc
    assert "/recover-metadata" in doc
    assert "reservation" in doc.lower()
    assert "Dockerfile" in doc
    assert "issue's comments/labels only" in doc
    assert "coordination docs/tests only" in doc
    assert "does not grant merge, release" in doc


def test_metadata_only_bootstrap_recovery_is_owner_only_and_zero_source() -> None:
    script = _script()
    script_path = json.dumps(str(SCRIPT.resolve()))
    source = r"""
const fs = require('fs');
const vm = require('vm');
const exportHelpers =
  '\nmodule.exports.__metadataRecovery = {' +
  ' parseCommand, canRecoverMetadataOnly, branchIsConcrete };';
const source = fs.readFileSync(__SCRIPT__, 'utf8') + exportHelpers;
const moduleObject = { exports: {} };
vm.runInNewContext(source, {
  module: moduleObject,
  exports: moduleObject.exports,
  require,
  console,
  Set,
  Date,
  JSON,
  String,
  Number,
  Boolean,
  RegExp,
  Error,
});
const helpers = moduleObject.exports.__metadataRecovery;
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
const descriptiveBranch = 'no product branch; coordination metadata only';
const status = {
  state: 'CLAIMED',
  github_actor: 'bootstrap',
  agent_id: 'coordination-bootstrap',
  branch: descriptiveBranch,
  linked_pr: null,
  linked_pr_head: null,
  ownership_paths: [],
  transition_seq: 0,
};
const contract = {
  paths: [],
  positiveOwnership: 'roadmap issue comments/labels/manifest metadata only',
  declaredBranch: descriptiveBranch,
};
const metadataCommand = helpers.parseCommand(
  '/recover-metadata agent-b adopt bootstrap metadata'
);
assert(
  metadataCommand && metadataCommand.kind === 'recover-metadata',
  'metadata command not parsed'
);
assert(metadataCommand.agent === 'agent-b', 'metadata agent not parsed');
assert(
  metadataCommand.reason === 'adopt bootstrap metadata',
  'metadata reason not parsed'
);
const ordinary = helpers.parseCommand(
  '/recover agent-b no product branch; coordination metadata only'
);
assert(
  ordinary && ordinary.branch === 'no',
  'ordinary recover grammar was loosened for prose branch'
);
assert(
  ordinary.branch !== descriptiveBranch,
  'ordinary recover accepted descriptive branch as repository branch'
);
assert(
  helpers.canRecoverMetadataOnly(status, contract, 'OWNER'),
  'valid metadata-only recovery rejected'
);
assert(
  !helpers.canRecoverMetadataOnly(status, contract, 'MEMBER'),
  'non-OWNER metadata recovery accepted'
);
const sourceStatus = { ...status, ownership_paths: ['src/owned.py'] };
const sourceContract = {
  ...contract,
  paths: ['src/owned.py'],
  positiveOwnership: '`src/owned.py`',
};
assert(
  !helpers.canRecoverMetadataOnly(sourceStatus, sourceContract, 'OWNER'),
  'source-owning metadata recovery accepted'
);
const concreteStatus = { ...status, branch: 'feat/concrete' };
const concreteContract = { ...contract, declaredBranch: 'feat/concrete' };
assert(
  !helpers.canRecoverMetadataOnly(concreteStatus, concreteContract, 'OWNER'),
  'concrete branch used metadata-only exception'
);
""".replace("__SCRIPT__", script_path)
    _run_node(source)


def test_recover_metadata_command_is_routed_by_workflow() -> None:
    workflow = _workflow()
    assert "startsWith(github.event.comment.body, '/recover-metadata ')" in workflow
