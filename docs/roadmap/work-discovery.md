# Agent work discovery protocol

Status: coordination guidance only. This document does not grant merge, release, qualification, sealed/private-data, paid-compute, external-account, deployment, or commercial authority.

Owning Work ID: `AGENT-DISCOVERY-001` / #208

## Cold-start objective

A coding agent with only the repository and GitHub access must be able to find safe executable work, claim it without colliding with active lanes, reconstruct its branch/ownership/dependencies, and hand it off without chat context.

## 1. Load the repository contract first

Read, in order:

1. `AGENTS.md`;
2. `.agents/veritas/OVERLAY.md`;
3. `.agents/universal/CONTRACT.md`;
4. the candidate issue's complete Work Contract;
5. the relevant subsystem docs/tests for the task.

Do not start editing before a successful claim acknowledgement.

## 2. Discover READY work

Use GitHub issue search:

```text
is:issue is:open label:agent-work label:work:ready
```

The `work:*` label is a discovery view. When a trusted status exists—whether through automatic enrollment or owner bootstrap—the latest trusted `github-actions[bot]` comment marked `veritas-agent-work-status:v1` is execution authority.

The checked-in `.github/agent-roadmap.yml` is a point-in-time planning snapshot. Before treating it as current, use live GitHub state or run the documented roadmap sync path. Strategic rank does not override BLOCKED dependencies or ownership collisions.

## 3. Inspect a candidate before claiming

Open the issue and verify:

- Work ID;
- current trusted state is `READY`;
- dependencies are satisfied under their actual authority;
- declared branch;
- positive ownership paths;
- negative ownership paths;
- external/manual/private/paid authority boundaries;
- whether an existing PR already owns related files.

An unlabeled old issue is not evidence that its files are free. The coordinator also treats changed files of open PRs as live collision reservations, including legacy and automated PRs that predate `agent-work`.

Repository-editing work must expose machine-checkable ownership paths. Zero-source coordination work is claimable only when its Positive ownership exactly matches a coordinator allow-listed no-source form, such as `this issue's comments/labels only`. Unsupported prose, or any ambiguous dependency or authority condition, still fails closed: do not claim the lane until the Work Contract is corrected or migrated, or use an interface/request lane.

## 4. Claim the lane

Post exactly one command line:

```text
/claim <agent-id> <branch>
```

Example:

```text
/claim agent-x feat/example-lane
```

Wait for the bot acknowledgement showing `CLAIMED`, the same agent ID/branch, and the frozen `ownership_paths`.

A command comment alone is not a claim. Coding may begin only after the accepted trusted status appears.

### Collision example

Suppose one active reservation owns:

```text
docs/agents/**
```

A second issue that proposes:

```text
docs/agents/work-discovery.md
```

must be rejected because ancestor/descendant ownership overlaps. Do not narrow another holder's frozen reservation to force parallelism. Move or split the new lane only through an explicit Work Contract change before claim, then claim again so the corrected paths are frozen.

The same rule applies to open PR changed files even when the PR is legacy/non-roadmap.

## 5. Create the branch from the correct base

After claim acceptance, create/use the exact branch recorded in trusted status.

For ordinary independent work, start from the current required `main` SHA unless the Work Contract defines a different base/dependency rule. Do not use an unrelated feature branch as a convenience base.

If `main` changes before final integration, synchronize deliberately, rerun applicable gates, and obtain exact-head review again where policy requires it.

## 6. Stay inside frozen ownership

Edit only the frozen positive ownership paths. Negative ownership remains a hard boundary.

If a required change falls outside the lane:

- do not patch another agent's files;
- record an interface-gap/follow-up issue or request;
- preserve current work as blocked if the missing interface prevents progress.

Use:

```text
/blocked <agent-id> <reason>
```

when the current holder must retain the lane while blocked. Owner-held `BLOCKED` remains reserved.

## 7. Heartbeat during long work

Use:

```text
/heartbeat <agent-id> [branch]
```

A stale heartbeat does not automatically free ownership. Abandonment must be explicit.

## 8. Verify before handoff

Apply the repository verification ladder:

1. cheapest targeted falsifier/check;
2. relevant unit/integration tests;
3. broader CI/security/quality/build checks as applicable;
4. domain/scientific/qualification gates only when the active Work Contract actually requires them.

Never infer a PASS from a missing/skipped gate. Implementation PASS is not scientific, Frontier, training, commercial, or release PASS.

## 9. Open the PR and hand off the exact head

The PR must reference the roadmap issue and primary Work ID, use the claimed branch, and stay within owned paths.

When implementation is ready, post:

```text
/handoff <agent-id> <pr-number>
```

The coordinator validates the PR, branch and Work linkage and records the exact PR head SHA.

If the PR head changes after handoff/review, issue `/handoff` again for the same PR so the exact candidate is refreshed. Old-head review evidence does not automatically apply to a changed head.

## 10. Independent review and integration

Obtain the independent review required by repository policy. Review should cover the exact final candidate, specification, ownership boundary, evidence and security implications.

A claim does not grant autonomous merge authority. Follow the active merge-authority contract and repository rules. Do not weaken branch protection, checks or review requirements to accelerate integration.

## 11. Complete only after the real completion predicate

For ordinary implementation work whose Work Contract permits repository completion after merge, the authenticated REVIEW holder uses:

```text
/done <agent-id> <pr-number>
```

The coordinator requires the exact linked PR to be merged and its head to match the most recently handed-off head.

Scientific qualification, experiment completion, external/manual work, convergence/release work and other special work classes may require stricter evidence. A merged PR alone does not complete those classes.

## 12. Release abandoned work

If abandoning the lane, use:

```text
/release <agent-id> <reason>
```

Do not simply stop editing and assume another agent may take over. Explicit release clears the active ownership reservation according to the trusted return state.

Repository OWNER recovery commands exist for bootstrap-derived or sufficiently stale held lanes, but ordinary agents must not use recovery as a substitute for correct release/handoff.

## Blocked dependency example

A strategically important issue can remain `BLOCKED` because a hard dependency or external authority is unsatisfied. Do not claim it because it is high priority.

Correct sequence:

1. identify the blocking dependency/authority from the Work Contract and trusted state;
2. execute another genuinely READY non-conflicting lane if available;
3. after authoritative dependency completion, reconcile the blocked issue to READY through the repository coordination mechanism;
4. only then claim it.

Manual payment/account setup, independent third-party reproduction, private evidence handling, paid compute and similar authority-bound work never become ordinary coding-agent READY merely because code preparation is complete.

## Fresh-agent reconstruction checklist

Before editing, a fresh agent should be able to answer from GitHub alone:

- What Work ID am I executing?
- Why is it READY?
- What dependencies/authority gates are satisfied?
- Which exact branch must I use?
- Which paths are frozen for me?
- Which active roadmap or open-PR paths would collide?
- Which files/actions are explicitly forbidden?
- What check would falsify my implementation?
- What review and completion predicate applies?
- What authority is still outside my claim?

If any answer requires hidden chat history, private credentials, or guessing about another agent's ownership, do not start the implementation. Repair the repository coordination metadata first.
