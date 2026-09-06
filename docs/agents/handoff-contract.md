# Agent handoff and completion contract

This document defines the repository-native handoff record for roadmap work. Its purpose is to make a work item reconstructible from GitHub without relying on a chat transcript, local shell history, or another agent's memory.

The issue Work Contract remains the authority for work ID, dependency state, branch, and path ownership. A handoff records evidence about one implementation head; it does not change the Work Contract or grant integration authority.

## Branch and worktree discipline

Each claimed implementation lane must use its Work Contract branch and an isolated worktree or clone. Agents running in parallel must not switch branches in a checkout that another active lane can mutate.

Before editing, record and verify:

- the exact base SHA;
- the claimed branch/worktree name;
- positive ownership paths;
- negative ownership paths;
- dependency state;
- the live claim holder.

If live GitHub state no longer matches the assignment, stop, release/reroute the lane, or obtain explicit convergence authority. Do not repair overlap by force-pushing or silently absorbing another lane's changes.

## Required handoff record

A handoff comment or PR description must contain all of the following fields. Use `UNKNOWN`, `NOT RUN`, or `N/A` rather than omitting evidence.

| Field | Required content |
| --- | --- |
| Work ID / issue | Canonical Work ID and linked roadmap issue |
| Exact base SHA | Full commit SHA used as the implementation base |
| Branch / worktree | Branch plus isolated worktree/clone identifier when applicable |
| Claim holder | Agent ID recorded by the issue coordination state |
| Positive ownership | Paths the work item is allowed to modify |
| Negative ownership | Paths explicitly outside the lane |
| Dependency state | Dependencies and their live READY/BLOCKED/etc. state |
| Files changed | Complete list of files changed by this implementation head |
| Unowned files changed | Must be `none` or include explicit authorization and rationale |
| Targeted tests | Commands/checks and results tied to the changed surface |
| Broader checks | Exact-head CI, Security, quality, build/package status as applicable |
| Semantic/privacy/qualification falsifiers | Relevant negative tests and whether each passed, failed, or was not run |
| Unresolved interface requests | Cross-lane changes needed but not owned here |
| Linked PR / head SHA | PR number and full exact head SHA |
| Evidence boundary | What the evidence establishes and what it explicitly does not establish |
| Next authority action | Review, convergence, merge, release, sealed/manual gate, or other required next step |

A green aggregate badge is not enough when an exact-head job result is required. Report the exact reviewed head and the relevant jobs/checks.

## Handoff transition

Once an implementation is pushed and its PR exists, the implementation owner announces:

`/handoff <agent-id> <pr-number>`

The handoff must be visible on the canonical work issue. The next agent must reconstruct the issue, PR, exact head, ownership, and evidence from GitHub before acting.

A handoff is not completion and is not authorization to merge. The implementation owner must not self-merge merely because its tests are green.

If the implementation changes after review starts, the previous review evidence is stale. The new head requires exact-head verification and independent review again.

## Independent review contract

An independent reviewer must verify at least:

1. the PR head is the exact SHA being reviewed;
2. changed paths comply with positive and negative ownership;
3. dependencies and interfaces are still valid against live repository state;
4. task acceptance criteria and falsifiers are addressed;
5. security/privacy and repository-specific invariants are checked where relevant;
6. claimed tests/checks actually ran on the reviewed head;
7. unresolved blockers are recorded on the PR and issue.

Review approval applies only to that exact head. It does not imply release, sealed/manual workflow, paid compute, scientific qualification, Frontier qualification, training readiness, buyer readiness, or commercial readiness.

## Completion language

Use completion statements narrowly:

- **Implementation PASS**: the owned implementation satisfies its acceptance criteria and implementation verification for the exact head.
- **Independent review PASS**: an independent reviewer found no blocking issue on that exact head.
- **Integrated**: the reviewed head was merged through authorized repository integration.
- **Scientific / Frontier / training / buyer / commercial qualification**: only use these terms when their separate qualification gates actually ran and passed.

Never collapse these states into a generic "done" statement.

The `/done <agent-id> <pr-number>` coordination transition may be used only when the work item's integration/evidence boundary is satisfied according to the issue protocol. It does not retroactively authorize actions that required separate authority.

## Reconstructing stale context

A new agent should be able to recover the lane using GitHub alone:

1. open the roadmap issue and read the Work Contract plus latest trusted coordination status;
2. verify the branch and linked PR;
3. resolve the exact PR head SHA;
4. inspect changed files and compare them with ownership;
5. read review findings and unresolved interface requests;
6. inspect exact-head CI/Security/quality evidence;
7. determine the next authority action before making a mutation.

If any required fact is absent or contradictory, treat it as unresolved rather than inferring it from an old chat transcript.

## Minimal handoff example

```text
Work ID / issue: EXAMPLE-001 / #123
Exact base SHA: <full-sha>
Branch / worktree: feat/example / worktree-example
Claim holder: agent-example
Positive ownership: src/example/**, tests/example/**
Negative ownership: release/**, shared/root metadata
Dependency state: #100 DONE
Files changed: src/example/a.py; tests/example/test_a.py
Unowned files changed: none
Targeted tests: pytest tests/example/test_a.py -> PASS
Broader checks: CI/Security/quality -> PASS on <head-sha>
Semantic/privacy/qualification falsifiers: privacy regression -> PASS; scientific qualification -> NOT RUN
Unresolved interface requests: none
Linked PR / head SHA: #456 / <full-head-sha>
Evidence boundary: implementation correctness only; no release or scientific qualification
Next authority action: independent exact-head review
```
