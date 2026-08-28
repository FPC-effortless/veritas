# Branch naming and exact-base policy for parallel roadmap agents

**Policy ID:** `veritas.agent-branch-policy.v1`  
**Applies to:** roadmap work coordinated through issue Work Contracts  
**Authority:** subordinate to `AGENTS.md`, active Work Contracts, repository protection/rulesets, and explicit higher-authority instructions

## Purpose

Parallel agents must not accidentally stack work on unrelated feature branches, reuse another agent's implementation lane, or treat CI from a stale base as final merge evidence.

This policy defines:

- how a roadmap ticket chooses its branch;
- which exact commit the branch starts from;
- when unmerged provider work may be used as a parent;
- how target-branch movement invalidates or refreshes evidence;
- how branch identity relates to Work ID ownership.

A branch is an implementation container. It is not the authority for ownership, review, merge, qualification, release, or access.

## Core invariants

1. **Work ID owns the lane; branch name records the lane.** Ownership comes from the active Work Contract and accepted claim, not from possession of a Git ref.
2. **Use the declared branch by default.** A claimed branch must equal the Work Contract's `Branch` value unless the Work Contract explicitly authorizes a branch pattern or stack relationship.
3. **Default base is exact current `main`.** Create independent work from the current `main` commit observed at branch creation, not from an arbitrary local/remote feature head.
4. **Hard-merge dependencies land first.** If a dependency is classified `hard_merge`, dependent implementation must wait for the provider to merge before taking its final independent base.
5. **Stacking is exceptional and explicit.** An unmerged provider branch may be a parent only when the consumer Work Contract names the parent issue/PR and the stack semantics.
6. **One active Work ID, one implementation branch.** Never reuse another active Work ID's branch unless an explicit stacked-work contract says the branch is intentionally shared; ordinary roadmap work must not share branches.
7. **Current target state matters at merge time.** Green checks against an earlier merge candidate are not automatically final evidence after `main` moves.
8. **Every base-changing sync creates new evidence obligations.** Rebase, merge-from-main, provider-head update, conflict resolution, or generated-output refresh that changes the candidate invalidates stale exact-head evidence as applicable.
9. **Do not force a stale branch through controls.** Branch protection/rulesets/checks/reviews are never weakened to compensate for an outdated base.
10. **Do not smuggle unrelated work through a branch.** A branch must remain within its Work Contract positive ownership and negative ownership boundaries.

## Canonical branch source

For an enrolled roadmap issue, the Work Contract's `Branch` field is the canonical default branch name.

Example:

```text
Work ID: DX-003
Branch: feat/environment-templates
```

The corresponding claim should use that exact branch:

```text
/claim dx-templates-a1 feat/environment-templates
```

Do not substitute a convenient pre-existing feature branch merely because it already contains useful code.

If a Work Contract intentionally permits a generated branch pattern, it must state the pattern and uniqueness rule explicitly. Otherwise the literal `Branch` value is authoritative.

## Current workflow branch grammar

The current coordination command parser accepts claim branch strings matching:

```regex
[A-Za-z0-9][A-Za-z0-9._/-]{0,127}
```

This means coordination input is structurally bounded to 1–128 characters, starts alphanumeric, and then uses only alphanumerics, `.`, `_`, `/`, and `-`.

This parser constraint is not the complete Git ref validity specification. A branch must also be a valid Git/GitHub branch reference. Prefer simple names such as:

```text
feat/environment-templates
docs/agent-branch-policy
fix/fidelity-revalidation
review/trace-integrity-a1
```

Avoid ambiguous or pathological ref forms even if a partial parser might accept them.

## Important current automation boundary

The coordination workflow currently:

- records the branch supplied by the accepted `/claim` command;
- stores it in the agent-work status;
- can validate a supplied heartbeat branch against the recorded branch;
- validates at `/handoff` that the linked PR's head branch matches the recorded claim branch.

The current workflow does **not** by itself guarantee that the claimed branch equals the issue body's declared Work Contract `Branch` value.

Therefore agents and roadmap validators must treat the following as a required invariant:

```text
claimed branch == declared Work Contract branch
```

unless the Work Contract explicitly declares an allowed branch pattern or stack exception.

A future validator may enforce this mechanically. Until then, absence of automation is not permission to diverge.

## Exact base selection

### Independent work

Unless the Work Contract states otherwise:

1. resolve the current `main` commit immediately before branch creation;
2. record that SHA in the implementation/PR evidence;
3. create the work branch from that exact SHA;
4. verify the new branch points to that SHA before the first implementation commit.

Example evidence:

```text
Base branch: main
Base SHA: fbdb74db7080a078c945506a6c759305f4cd1f78
```

Do not say only "latest main". The commit SHA is the auditable base identity.

### Why exact SHA matters

`main` is moving shared state. Two agents can both say they started "from main" while actually starting from different commits. Exact base identity lets reviewers determine:

- which provider changes were present;
- whether a dependency had actually merged;
- whether CI was run before or after a relevant shared change;
- whether a stale-base result can still be used.

## Dependency-aware base rules

Branch policy consumes dependency semantics; it does not redefine the dependency taxonomy.

### `hard_merge` dependency

When an active dependency is marked `hard_merge`:

- do not take the provider's feature branch as the consumer's ordinary base;
- wait until the provider is merged into the required target branch;
- resolve the new exact `main` SHA containing that provider;
- create or synchronize the consumer branch onto that SHA;
- run consumer gates against the resulting candidate.

The provider's green PR is not equivalent to a merged dependency.

### Read-only dependency

A consumer may inspect an allowed provider/interface source without editing or stacking on it when the Work Contract permits read-only dependency use.

Reading another branch is not a reason to base on it. The consumer remains based on its own authorized base.

### Generated/shared dependency

If generated/shared output is owned by a designated generator or convergence lane, consumers must not create a branch from another consumer's modified generated output. Use the canonical merged generator output or the explicit convergence branch required by the Work Contract.

## Stacked branches

Stacked work is exceptional because it couples two unmerged candidates and makes review evidence easier to invalidate.

A stack is permitted only when the consumer Work Contract or explicit higher-authority instruction identifies at least:

- parent issue/Work ID;
- parent PR or branch;
- exact parent head SHA used as the child base;
- intended merge order;
- ownership boundaries between parent and child;
- what happens when the parent head changes.

Example stack declaration:

```text
Base policy: STACKED
Parent Work ID: PROVIDER-001
Parent PR: #321
Parent head: <40-char-sha>
Merge order: parent before child
```

Without this declaration, do not branch from an unmerged feature head.

### Stacked evidence invalidation

If the parent head changes:

- the child is no longer proven against the current parent;
- update/rebase the child to the approved parent head if the stack remains authorized;
- rerun affected child checks;
- obtain fresh review where the child exact head or effective diff changed.

When the parent merges, prefer collapsing the child back onto current `main` before final merge evidence unless the repository's active merge policy explicitly accepts the remaining stack state.

## Never use an unrelated active feature branch as a convenience base

Invalid pattern:

```text
main
  └─ feat/data-policy        # unrelated active work
      └─ feat/my-runtime     # accidentally inherits data-policy
```

unless `feat/data-policy` is an explicitly declared stack parent.

The dependent branch otherwise carries unrelated commits, can expose another lane's unreviewed semantics, and makes changed-file ownership misleading.

Correct default:

```text
main
  ├─ feat/data-policy
  └─ feat/my-runtime
```

with each branch created from the exact permitted main SHA for its ticket.

## Active branch uniqueness

Before creating or claiming a branch, inspect active coordination status.

An ordinary branch must not already be recorded by another active Work ID in `CLAIMED`, `BLOCKED`, or `REVIEW` state.

If the name is already active:

- do not reuse it;
- do not force-update it;
- resolve whether the issue is a duplicate, stale claim, intended stack, or naming collision;
- use the explicit release/reassignment process where appropriate.

A branch name collision does not transfer ownership.

After a ticket is completed, prefer deleting obsolete feature branches rather than recycling their names for unrelated Work IDs. New work should get a new auditable branch/Work ID pair.

## Branch creation protocol

For ordinary independent roadmap work:

1. verify the issue is dependency-ready and unclaimed;
2. verify its positive/negative paths do not conflict with active work;
3. resolve exact current `main` SHA;
4. post the exact single-line `/claim <agent-id> <declared-branch>` command;
5. verify the claim transition was accepted and recorded the expected branch;
6. verify no other active Work ID records that branch;
7. create the declared branch from the resolved exact base SHA;
8. verify the branch base;
9. implement only inside the Work Contract lane.

If the branch was created before claim acceptance, do not edit it until claim acceptance is confirmed. A branch's existence does not reserve the work.

## PR and handoff identity

The implementation PR should record:

- Work ID / issue;
- claimed branch;
- target branch;
- initial base SHA;
- final head SHA;
- any synchronization commits or stack parent identity relevant to the candidate.

The current coordination workflow verifies during `/handoff` that the PR head branch matches the recorded claim branch and records the linked PR/head in status.

This is a useful integrity check but not complete merge evidence. Reviewers must still assess base freshness, target movement, changed files, dependencies, gates, and authority.

## Target-branch movement

`main` may advance while a PR is open. A previous head being green does not prove that the candidate is valid against the new target state.

When the target moves, classify the change before treating old evidence as final.

### No relevant semantic interaction

For an ordinary additive lane, repository policy may allow the unchanged feature head to remain while GitHub recomputes the merge candidate against current `main`.

Before merge, verify:

- the PR remains mergeable;
- the current synthetic merge candidate or required checks actually incorporate the new target state where the repository requires that;
- no dependency/interface changed in a way that invalidates the implementation or review;
- no shared/convergence rule requires an explicit sync.

Do not infer freshness merely from the age of the green check mark.

### Relevant target change or explicit current-main requirement

If `main` changed an interface, dependency, shared generated output, root integration surface, or other semantic input relevant to the ticket, synchronize before final verification.

After synchronization:

- record the new exact head/base relationship;
- rerun targeted and required broader gates;
- recheck ownership/diff;
- obtain fresh independent review when the reviewed exact head changed or the effective semantics changed.

### Shared convergence/root integration

Shared convergence work must use the stricter current-main rule defined by its Work Contract/merge policy: synchronize to current target state, run the full applicable suite, and review the synchronized exact head.

Pre-sync green evidence is not final evidence for convergence work.

## Synchronization methods

A Work Contract may choose rebase or merge-from-target according to repository conventions. Both can change the candidate and therefore its evidence identity.

### Rebase

Rebase rewrites feature commit IDs.

Use it only when allowed by collaboration/review policy. After rebase:

- the new head is a different exact candidate;
- rerun affected gates;
- do not cite pre-rebase exact-head approval as approval of the new head unless an independent reviewer explicitly establishes unchanged equivalence under repository policy.

Never force-push a shared/protected branch merely to make history look cleaner.

### Merge current target into the feature branch

A synchronization merge preserves existing feature commits but creates a new branch head.

The merge commit is still a new exact candidate. Run required gates and review it according to the task class.

Do not use merge-from-target to pull in arbitrary feature branches; only the authorized target/current dependency state belongs in the sync.

## Conflict resolution

A conflict means target/provider state intersects the implementation. Conflict resolution is a semantic change, not mechanical evidence preservation.

After resolving conflicts:

- inspect the final diff carefully;
- ensure no other agent's owned changes were accidentally rewritten;
- rerun relevant tests/gates;
- obtain independent review of the resulting exact head.

Do not resolve a conflict by deleting a safety/qualification check, changing an unrelated shared API, or taking ownership of another lane.

## Stale-base CI evidence

A workflow result is auditable evidence only for the candidate it actually tested.

Record enough identity to answer:

- feature head SHA;
- target/base SHA or synthetic merge SHA when relevant;
- workflow/run identity;
- whether the run occurred before or after the latest required synchronization.

The following are not sufficient final statements:

```text
CI passed earlier.
The branch was green yesterday.
The provider PR was green.
```

Instead report the exact candidate and current target relationship.

If repository CI uses a GitHub synthetic PR merge commit, verify which feature head and base it combined. If the base changes after that run and the workflow does not rerun, the old synthetic merge result is stale for a policy requiring current-target validation.

## Ownership is not branch ancestry

A child commit can contain files from its base, but an agent's edit authority remains defined by the Work Contract.

Being based on a provider branch does not authorize editing provider-owned files. Being based on `main` does not authorize editing every file in `main`.

Likewise, branch creator/author identity does not supersede positive/negative path ownership.

## Branch and agent identity are distinct

Agent ID identifies the coordination holder. Branch identifies the implementation lane. Work ID identifies the scoped task.

Do not derive one from another as an authorization rule.

The same agent ID may hold multiple non-conflicting Work IDs on different branches. A branch must not be shared by independent active Work IDs merely because the same agent owns both.

## Evidence fields for roadmap metadata

Roadmap tooling may represent branch/base information with fields equivalent to:

```yaml
branch:
  name: feat/example
  base_policy: current_main   # current_main | hard_merge | stacked
  base_ref: main
  base_sha: <40-char-sha>
  parent_work_id: null
  parent_pr: null
  parent_head_sha: null
```

These fields are coordination/evidence metadata, not GitHub permissions.

For `hard_merge`, `base_sha` should identify the current target commit that already contains the required provider. For `stacked`, the parent identity fields are mandatory and the Work Contract must state merge order.

A roadmap validator may compare:

- declared branch vs claimed branch;
- active branch uniqueness;
- base policy vs dependency type;
- recorded base SHA vs required merged dependency ancestry;
- PR head branch vs claim branch;
- current-target synchronization requirements.

## Failure cases

### Arbitrary active feature base

**Invalid:** a new independent ticket branches from another agent's unmerged PR because that branch is convenient.

**Required:** branch from exact current `main`, or declare an authorized stack.

### Hard-merge dependency bypass

**Invalid:** consumer branches from a green but unmerged provider PR and treats provider CI as dependency satisfaction.

**Required:** wait for provider merge, then base/sync from target containing it.

### Branch mismatch

**Invalid:** Work Contract declares `feat/a`, claim records `feat/b`, and the difference is ignored because both are owned by the same GitHub actor.

**Required:** reject/correct the claim unless the Work Contract explicitly permits the alternate branch.

### Duplicate active branch

**Invalid:** two unrelated Work IDs both claim `feat/shared-work`.

**Required:** one active branch per independent Work ID; resolve/release/reassign before proceeding.

### Stale pre-sync checks

**Invalid:** shared convergence PR is approved, then merges current `main`, but cites only tests/review from the pre-sync head.

**Required:** rerun applicable gates and review the synchronized exact candidate.

### Hidden stack after provider update

**Invalid:** child remains based on provider head A after provider moves to head B, while child reports itself current.

**Required:** update the child to the authorized parent/current main as required and regenerate evidence.

## Relationship to review and merge authority

Branch policy determines candidate ancestry and identity. It does not itself authorize merge.

The final merge decision must separately establish:

- correct Work Contract ownership;
- exact candidate identity;
- dependency satisfaction;
- applicable gates;
- independent review;
- target freshness/current-main rules;
- repository controls;
- merge/evidence/release authority.

When these policies differ, apply the stricter active requirement. A green branch is never sufficient by itself.