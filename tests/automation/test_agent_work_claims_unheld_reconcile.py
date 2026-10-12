# ruff: noqa: E501, I001

import json
import subprocess
import unittest


SCRIPT = ".github/scripts/agent-work-claims.js"

NODE_HARNESS = r"""
const coordinate = require('./.github/scripts/agent-work-claims.js');
const input = JSON.parse(process.argv[1]);

const STATUS_MARKER = '<!-- veritas-agent-work-status:v1 -->';
const REGISTRY_MARKER = '<!-- veritas-agent-work-reservations:v1 -->';
const target = {
  number: 286,
  state: 'open',
  pull_request: null,
  body: `<!-- veritas-agent-work -->\n## Work Contract\n\n- **Work ID:** ROADMAP-LOCK-004\n- **State:** READY\n- **Branch:** \`fix/roadmap-metadata-only-recovery\`\n- **Positive ownership:** \`.github/scripts/agent-work-claims.js\`, \`docs/automation/agent-work-claims.md\`, \`tests/automation/test_agent_work_claims_workflow.py\`\n- **Claim holder:** none\n- **Linked PR:** none`,
  labels: [{ name: 'agent-work' }, { name: 'work:blocked' }],
};
const root = {
  number: 150,
  state: 'open',
  pull_request: null,
  body: '<!-- veritas-agent-work -->',
  labels: [{ name: 'agent-work' }],
};
const status = {
  schema_version: 'veritas.agent-work-status.v1',
  work_id: 'ROADMAP-LOCK-004',
  issue_number: 286,
  state: 'BLOCKED',
  github_actor: null,
  agent_id: null,
  branch: null,
  claimed_at: null,
  heartbeat_at: null,
  linked_pr: null,
  linked_pr_head: null,
  ownership_paths: [
    '.github/scripts/agent-work-claims.js',
    'docs/automation/agent-work-claims.md',
    'tests/automation/test_agent_work_claims_workflow.py',
  ],
  blocker: 'bootstrap/reconciliation required',
  released_reason: null,
  return_state: 'BLOCKED',
  transition_seq: 0,
  last_command_comment_id: 0,
  updated_at: '2026-08-29T13:37:58.142Z',
  ...input.status,
};

let nextCommentId = 9000;
const comments = {
  150: [{
    id: 8000,
    user: { login: 'github-actions[bot]' },
    body: `${REGISTRY_MARKER}\n\n\`\`\`json\n${JSON.stringify({ schema_version: 'veritas.agent-work-reservations.v1', updated_at: 'old', entries: [] })}\n\`\`\``,
  }],
  286: [{
    id: 8100,
    user: { login: 'github-actions[bot]' },
    body: `${STATUS_MARKER}\n\n\`\`\`json\n${JSON.stringify(status)}\n\`\`\``,
  }],
};
const issues = { 150: root, 286: target };

function findComment(id) {
  for (const list of Object.values(comments)) {
    const found = list.find((item) => item.id === id);
    if (found) return found;
  }
  return null;
}

const issueApi = {
  listLabelsForRepo: async () => Object.values({
    a: { name: 'agent-work' },
    b: { name: 'work:ready' },
    c: { name: 'work:claimed' },
    d: { name: 'work:blocked' },
    e: { name: 'work:review' },
    f: { name: 'work:done' },
    g: { name: 'work:superseded' },
  }),
  listForRepo: async () => [target],
  listComments: async ({ issue_number }) => comments[issue_number] || [],
  get: async ({ issue_number }) => ({ data: issues[issue_number] }),
  createLabel: async () => ({ data: {} }),
  removeLabel: async ({ issue_number, name }) => {
    issues[issue_number].labels = (issues[issue_number].labels || []).filter((item) => item.name !== name);
    return { data: {} };
  },
  addLabels: async ({ issue_number, labels }) => {
    const current = new Set((issues[issue_number].labels || []).map((item) => item.name));
    for (const name of labels) current.add(name);
    issues[issue_number].labels = [...current].map((name) => ({ name }));
    return { data: {} };
  },
  updateComment: async ({ comment_id, body }) => {
    const comment = findComment(comment_id);
    if (!comment) throw new Error(`missing comment ${comment_id}`);
    comment.body = body;
    return { data: comment };
  },
  createComment: async ({ issue_number, body }) => {
    const comment = { id: nextCommentId++, user: { login: 'github-actions[bot]' }, body };
    (comments[issue_number] ||= []).push(comment);
    return { data: comment };
  },
};
const github = {
  rest: { issues: issueApi },
  paginate: async (fn, args) => fn(args),
};
const context = {
  repo: { owner: 'FPC-effortless', repo: 'veritas' },
  issue: { number: 150 },
  actor: 'FPC-effortless',
  payload: {
    comment: { body: '/roadmap-bootstrap', author_association: 'OWNER' },
  },
};

(async () => {
  await coordinate({ github, context });
  const statusComment = comments[286].find((item) => item.body.includes(STATUS_MARKER));
  const match = statusComment.body.match(/```json\s*([\s\S]*?)```/);
  const finalStatus = JSON.parse(match[1]);
  const registryComment = comments[150].find((item) => item.body.includes(REGISTRY_MARKER));
  const registryMatch = registryComment.body.match(/```json\s*([\s\S]*?)```/);
  const registry = JSON.parse(registryMatch[1]);
  console.log(JSON.stringify({
    status: finalStatus,
    labels: issues[286].labels.map((item) => item.name).sort(),
    registry,
  }));
})().catch((error) => {
  console.error(error.stack || String(error));
  process.exit(1);
});
"""


class BootstrapUnheldReconciliationTests(unittest.TestCase):
    def run_case(self, status=None):
        completed = subprocess.run(
            ["node", "-e", NODE_HARNESS, json.dumps({"status": status or {}})],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(completed.stdout)

    def test_pristine_bootstrap_blocker_reconciles_to_ready(self):
        result = self.run_case()
        status = result["status"]
        self.assertEqual(status["state"], "READY")
        self.assertEqual(status["return_state"], "READY")
        self.assertIsNone(status["blocker"])
        self.assertEqual(
            status["ownership_paths"],
            [
                ".github/scripts/agent-work-claims.js",
                "docs/automation/agent-work-claims.md",
                "tests/automation/test_agent_work_claims_workflow.py",
            ],
        )
        self.assertIn("work:ready", result["labels"])
        self.assertNotIn("work:blocked", result["labels"])
        self.assertEqual(result["registry"]["entries"], [])

    def test_rejected_command_cursor_still_reconciles_to_ready(self):
        result = self.run_case({"last_command_comment_id": 5490536946})
        self.assertEqual(result["status"]["state"], "READY")
        self.assertEqual(result["status"]["last_command_comment_id"], 5490536946)
        self.assertIsNone(result["status"]["blocker"])

    def test_malformed_or_negative_command_cursor_is_not_reconciled(self):
        for cursor in (-1, 1.5, "5490536946", None):
            with self.subTest(cursor=cursor):
                result = self.run_case({"last_command_comment_id": cursor})
                self.assertEqual(result["status"]["state"], "BLOCKED")
                self.assertEqual(
                    result["status"]["blocker"],
                    "bootstrap/reconciliation required",
                )

    def test_transitioned_blocker_is_not_reconciled(self):
        result = self.run_case({"transition_seq": 1})
        self.assertEqual(result["status"]["state"], "BLOCKED")
        self.assertEqual(result["status"]["blocker"], "bootstrap/reconciliation required")

    def test_explicit_blocker_is_not_reconciled(self):
        result = self.run_case({"blocker": "waiting for external authority"})
        self.assertEqual(result["status"]["state"], "BLOCKED")
        self.assertEqual(result["status"]["blocker"], "waiting for external authority")

    def test_held_blocker_is_not_reconciled(self):
        result = self.run_case(
            {
                "github_actor": "bootstrap",
                "agent_id": "existing-holder",
                "branch": "existing/branch",
                "claimed_at": "2026-08-29T12:00:00Z",
                "heartbeat_at": "2026-08-29T12:00:00Z",
            }
        )
        self.assertEqual(result["status"]["state"], "BLOCKED")
        self.assertEqual(result["status"]["agent_id"], "existing-holder")


if __name__ == "__main__":
    unittest.main()
