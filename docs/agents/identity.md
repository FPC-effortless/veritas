# Agent identity conventions for roadmap coordination

**Policy ID:** `veritas.agent-identity.v1`  
**Applies to:** roadmap coordination commands handled by `.github/workflows/agent-work-claims.yml`  
**Security classification:** public coordination metadata; never a credential

## Purpose

Multiple coding agents may operate through the same authenticated GitHub account. The roadmap therefore records two distinct identities:

- **GitHub actor** — the authenticated account that submitted the command and whose repository permissions/association are authoritative;
- **agent ID** — a short, non-secret coordination label that distinguishes one agent/session/role from another.

The agent ID answers **“which coding-agent lane currently owns this work?”** It does not answer **“who is authenticated or authorized?”**

## Canonical identity tuple

An active claim is identified by at least:

```text
(repository, issue/work ID, github_actor, agent_id, branch)
```

The coordination status also records timestamps and linked-PR state as applicable.

`github_actor` and `agent_id` must both remain visible in the audit trail. Two agents using the same GitHub account are distinguishable by agent ID; two different GitHub actors using the same declared agent ID remain distinguishable by authenticated actor.

## Agent ID format

The current claim workflow accepts agent IDs matching:

```regex
[A-Za-z0-9][A-Za-z0-9._-]{0,63}
```

Therefore an agent ID:

- is 1–64 characters long;
- starts with an ASCII letter or digit;
- after the first character may contain only ASCII letters, digits, `.`, `_`, or `-`;
- contains no whitespace, slash, `@`, colon, shell metacharacters, or free-form text.

Recommended style:

```text
<lane-or-role>-<instance>
```

Examples:

```text
exp-diagnostics-a1
sandbox-local-a2
chatgpt-sol-competitive
review-fidelity-b1
```

The format restriction is an input-safety and auditability boundary. It is **not** proof that the value is non-secret; agents must still follow the secret rules below.

## Stable enough to audit, narrow enough to rotate

An agent ID should be stable for the lifetime of the work it owns. It should describe the agent role/session lane rather than encode transient prose.

Good:

```text
trace-review-a1
roadmap-policy-b2
```

Poor:

```text
agent
new-agent
fix-the-thing-after-lunch
```

A globally unique identifier is not required. The issue/work ID and GitHub actor provide additional scope. However, agents running concurrently should choose IDs that make their lanes unambiguous to humans reading claim history.

## Never put secrets or personal credentials in an agent ID

Agent IDs and coordination commands are public/auditable repository metadata. Never place any of the following in an agent ID:

- API keys or access tokens;
- passwords or passphrases;
- private keys or signing material;
- session cookies;
- bearer/JWT/OAuth credentials;
- email addresses used as credentials or identity proof;
- secret-bearing URLs;
- customer/private benchmark identifiers that are not approved for public disclosure;
- any value whose disclosure would require rotation or incident response.

A value can match the allowed regex and still be a secret. The coordination workflow validates structure; it is not a secret-detection system.

If secret material is accidentally posted in an issue comment, treat that as a security incident under the repository's secret-handling process. Renaming the agent ID does not undo disclosure.

## Authentication and authorization

Agent ID is **coordination metadata only**.

Repository authorization comes from the authenticated GitHub actor plus repository controls. The current coordination workflow accepts state-changing commands only from allowed GitHub associations (`OWNER`, `MEMBER`, or `COLLABORATOR`).

An agent ID:

- does not create a GitHub identity;
- does not grant repository permissions;
- does not grant branch-write or merge permission;
- does not grant access to secrets/private artifacts;
- does not grant release, payment, legal, sealed, paid-compute, or qualification authority;
- must never be treated as an authentication token by another workflow or service.

If an agent presents the right ID through an unauthorized GitHub actor, the claim workflow must reject the command. Conversely, an authorized GitHub actor must still use the current recorded agent ID to act as that claim holder.

## Command syntax is exact and single-line

Coordination commands are parsed as complete single-line comments. Do not append explanatory text to the command comment.

Valid:

```text
/claim roadmap-policy-a1 docs/roadmap-policy-a1
```

Invalid:

```text
/claim roadmap-policy-a1 docs/roadmap-policy-a1
I am starting this now.
```

Use a separate issue/PR comment for evidence or narrative.

The current agent-ID-bearing commands are:

```text
/claim <agent-id> <branch>
/heartbeat <agent-id> [branch]
/release <agent-id> [reason]
/blocked <agent-id> <reason>
/handoff <agent-id> <pr-number>
/done <agent-id> <pr-number>
```

The same agent-ID format applies to each command. Free-form reason fields are command-specific and do not become part of the identity.

## Claim lifecycle

### Claim

A successful `/claim` records:

- authenticated `github_actor`;
- declared `agent_id`;
- branch;
- claim timestamp;
- heartbeat timestamp;
- issue/work identity.

The agent must verify that the workflow accepted the transition before editing. Posting a syntactically correct command is not enough if the work was already claimed, blocked, done, or otherwise unavailable.

### Heartbeat

Each active ticket is heartbeated independently. An agent holding several non-conflicting issues must not assume that activity on one issue refreshes another issue's claim.

A heartbeat proves only that the recorded holder renewed the coordination timestamp. It is not evidence of code progress, test success, review, merge authority, or qualification.

### Handoff

The current holder uses the same agent ID when handing an open PR to review. A different agent ID cannot hand off another holder's claim merely because both use the same GitHub account.

### Release

A holder that stops work without completing the ticket releases the claim explicitly. Release preserves an auditable transition instead of allowing another agent to silently ignore the previous holder.

### Done

`/done` is a completion transition, not an identity change. The command still requires the recorded holder identity and does not convert coordination identity into release/qualification authority.

## One agent ID holding multiple tickets

One agent ID may hold multiple tickets when normal concurrency rules permit it. This is a convenience, not a reservation over a project area.

For every ticket independently, the agent must:

- claim the issue;
- respect that issue's positive/negative ownership;
- maintain its heartbeat;
- link/handoff the correct PR;
- release or complete the ticket explicitly.

A claim on issue A grants no ownership over issue B, even when the same agent ID and GitHub actor are used.

Agents should avoid accumulating more concurrent claims than they can actively maintain. Stale ownership is a coordination defect even when path ownership does not conflict.

## Two agents sharing one GitHub account

Example:

```text
GitHub actor: FPC-effortless
Agent ID: fidelity-review-a1
Issue: ENV-001
```

and concurrently:

```text
GitHub actor: FPC-effortless
Agent ID: sandbox-local-b1
Issue: SANDBOX-001
```

The authenticated authority is the same account, but the roadmap audit has two distinguishable holders. Each holder may act only on its own claim and owned paths.

The shared GitHub actor does not make the two coding agents mutually authorized to release, hand off, or complete one another's tickets.

## Switching agent IDs

Do not silently change agent ID mid-claim.

If work must move from `agent-old` to `agent-new`:

1. `agent-old` releases the current claim (or an authorized coordination recovery process explicitly reassigns it);
2. verify the issue returns to its appropriate claimable state;
3. `agent-new` posts a fresh claim on the intended branch;
4. verify the new claim transition was accepted;
5. record any handoff context separately without putting it inside the command line.

This produces an audit trail of the ownership transfer.

A new agent must not merely start using the old agent ID to impersonate continuity. If continuity is intentional because the same agent process/session has resumed, retain the existing ID and heartbeat the existing claim instead of manufacturing a transfer.

## GitHub actor changes

If the authenticated GitHub actor changes, treat that as an authority change even if the agent ID string remains identical.

The coordination workflow binds holder operations to both:

- the recorded agent ID; and
- the recorded authenticated actor (except explicit bootstrap semantics implemented by the workflow).

Do not design consumers that key solely on `agent_id` and discard `github_actor`.

## Branch identity is related but distinct

The branch is recorded with the claim because path ownership must map to an isolated implementation lane. It is not part of authentication and should not be overloaded as the agent identity.

One agent ID may use different branches for different tickets. The claim command records the exact branch for that issue, and subsequent heartbeat/handoff validation may reject branch mismatches.

Branch naming conventions are governed separately; an agent ID does not need to equal the branch name.

## Input-safety properties of the current workflow

The current coordination workflow treats the agent ID as untrusted public input and constrains it before storing it:

- the complete comment must match a recognized command grammar;
- multiline commands are rejected;
- agent IDs use the fixed allow-list regex above;
- branch values use a separate constrained grammar;
- state transitions are performed through the GitHub API rather than interpolating the agent ID into a shell command;
- state-changing commands require an allowed authenticated GitHub association;
- holder operations check both recorded agent ID and authenticated actor.

These properties reduce command-injection and ambiguous-parsing risk. They do not make the agent ID confidential, authenticated, globally unique, or safe for use as an authorization credential outside the coordination workflow.

## Audit requirements

A coordination status/audit record should preserve at least:

- work/issue identity;
- state;
- GitHub actor;
- agent ID;
- claimed branch;
- claim timestamp;
- latest heartbeat timestamp;
- linked PR and reviewed/linked head when available;
- transition sequence or equivalent ordering;
- blocker/release reason when applicable.

Audit consumers should display GitHub actor and agent ID together where ownership attribution matters.

Do not collapse the pair into a single display string and later treat that string as authoritative identity.

## Failure cases

### Agent ID mistaken for authentication

**Invalid:** a workflow accepts `release-a1` because the string is present on an allow-list, without checking the authenticated GitHub actor.

**Required behavior:** authorization remains actor/repository-policy based; agent ID only selects/validates the coordination holder.

### Secret-like identifier

**Invalid:** `/claim ghp_<token> feature-x`.

Even if a token-like string happened to fit structural constraints, secrets are forbidden because issue comments and status records are auditable/public metadata.

### Two agents under one GitHub account

**Invalid:** both claim unrelated issues as generic `agent`, making ownership operationally ambiguous.

**Preferred:** use role/instance IDs such as `trace-a1` and `sandbox-b1`.

### Silent identity switch

**Invalid:** `agent-b1` begins posting holder commands for a ticket claimed by `agent-a1` without a release/reclaim transition.

**Required behavior:** release/reclaim or an explicitly authorized recovery/reassignment path.

### Cross-ticket inference

**Invalid:** an agent holds one `docs/agents/**` ticket and infers ownership of every file in that directory.

**Required behavior:** ownership comes from each Work Contract, not from identity reuse or path proximity.

## Relationship to merge/release authority

Identity establishes who owns a coordination lane; it does not decide what that holder is authorized to merge or execute.

Use `docs/agents/merge-authority.md` when present for implementation merge boundaries. Higher-authority repository, security, scientific, release, and explicit user/owner rules continue to take precedence.

No identity convention may weaken branch protection, independent review, privacy, sealed-data, qualification, release, payment, or legal controls.