# Agent Work Claim Automation

The `Agent Work Claims` workflow turns GitHub issues marked with `<!-- veritas-agent-work -->` into an auditable coordination queue for parallel coding agents. Coordination state remains separate from environment maturity, scientific qualification, Frontier qualification, training qualification, commercial readiness, merge authority, and release authority.

## Canonical authority

After bootstrap, the only execution authority is the latest trusted bot-authored status record marked `veritas-agent-work-status:v1`. `work:*` labels are discovery metadata only. Mutable issue-body `State`, `Claim holder`, `Linked PR`, `Positive ownership`, and manual label edits cannot directly authorize or reshape a later active transition.

`/roadmap-bootstrap` on coordination root #150 is OWNER-only. It materializes a trusted status record for every enrolled open roadmap issue and reconciles labels to that record. When no trusted record exists, bootstrap derives initial execution state from the Work Contract rather than mutable `work:*` labels. Ordinary commands fail closed when trusted status is missing.

The effective positive-ownership paths are frozen into trusted status as `ownership_paths` when a claim is accepted or when a legacy status is deliberately migrated during OWNER-only bootstrap. Active registry updates consume that frozen ownership snapshot rather than reparsing mutable issue-body ownership text. Changing a Work Contract after claim therefore does not silently widen, shrink, or move an active reservation.

## Discovery

Claimable work remains discoverable with:

```text
is:issue is:open label:agent-work label:work:ready
```

The workflow maintains exactly one discovery label from `work:ready`, `work:claimed`, `work:blocked`, `work:review`, `work:done`, and `work:superseded`.

## Authorization and identity

Ordinary commands require GitHub `OWNER`, `MEMBER`, or `COLLABORATOR` association. The authenticated GitHub actor is authority; the declared agent ID is public coordination metadata only and must not contain secrets.

Ordinary holder commands require both the matching agent ID and the authenticated GitHub actor recorded by the claim. Bootstrap-derived holders use `github_actor: "bootstrap"` and cannot silently inherit ordinary holder authority.

Repository owners may explicitly adopt a bootstrap-derived or stale held lane with:

```text
/recover <new-agent-id> <recorded-branch> <reason>
```

Recovery requires `OWNER`, preserves the existing branch and frozen ownership paths, is accepted immediately for bootstrap-derived ownership, and otherwise requires the last heartbeat to be at least two hours old. It is an audited ownership recovery, not automatic expiry.

## Commands

Commands are exact single lines:

```text
/claim <agent-id> <branch>
/heartbeat <agent-id> [branch]
/release <agent-id> [reason]
/blocked <agent-id> <reason>
/handoff <agent-id> <pr-number>
/done <agent-id> <pr-number>
/recover <new-agent-id> <branch> <reason>
```

The repository OWNER may run `/roadmap-bootstrap` only on #150.

## Deterministic command ordering

GitHub Actions concurrency is non-cancelling but is not FIFO. The workflow therefore does not trust runner start order. Every invocation reads pending coordination comments for that issue and processes them in ascending comment-ID order after the last recorded command. A later event can drain an earlier pending command first, so rapid dependent commands such as `/claim` then `/release` are evaluated in authoring order rather than scheduler order.

Rejected commands are also recorded as processed so they cannot be replayed indefinitely.

## Claim locking and parallelism

Before accepting `/claim`, the workflow:

1. requires canonical state `READY`;
2. requires the claimed branch to match a concrete Work Contract branch when one is declared;
3. extracts machine-checkable backticked positive-ownership paths;
4. rejects reuse of a branch already held by another active reservation;
5. rejects ancestor/descendant or exact path overlap with active `CLAIMED`, `REVIEW`, or owner-held `BLOCKED` roadmap reservations;
6. scans changed files of open PRs and rejects overlap, excluding only an existing PR on the candidate branch itself;
7. freezes the accepted ownership paths into trusted status before later registry updates.

Coordination-only or metadata-only tickets may explicitly have no source path. Ordinary code tickets without machine-checkable ownership fail closed.

The current active roadmap reservations are mirrored in one trusted bot-authored `veritas-agent-work-reservations:v1` record on #150. Active entries are rebuilt from trusted frozen ownership snapshots, not mutable Work Contract text. Open-PR changed files remain a live claim-time reservation source rather than relying on a potentially stale registry snapshot.

This locking serializes only short coordination transitions. Coding work on disjoint reservations remains parallel.

## Release and blocking

A successful claim stores its release target in trusted status as `return_state`. `/release` uses that frozen trusted value rather than reparsing mutable issue-body `State` at release time, and clears the released ownership snapshot from active status.

`/blocked` preserves the current authenticated holder, branch, and frozen ownership reservation while making the lane non-claimable. Staleness alone never frees a lane; explicit `/release` or owner `/recover` is required.

## Handoff and exact-head completion

`/handoff` requires the authenticated CLAIMED holder and validates that the PR:

- exists in this repository;
- is open;
- uses the recorded claimed branch;
- references both the roadmap issue and primary Work ID.

The handoff records the exact PR head SHA.

When a corrected PR head is pushed after independent review, the authenticated holder may issue `/handoff` again while already in REVIEW, but only for the same PR. This same PR re-handoff revalidates the PR/branch/work linkage and refreshes the exact `linked_pr_head`; it cannot switch REVIEW ownership to another PR.

`/done` requires the authenticated REVIEW holder, the exact linked PR, a merged PR, and the same PR head SHA that was most recently handed off. If the PR head moves after handoff, `/done` rejects and the final head must be handed off/reviewed again.

This is still implementation-level completion only. Work-class-specific scientific, experiment, external/manual, convergence, and release completion rules remain stricter and must not be inferred from a merged PR.

## Bootstrap and reconciliation

OWNER-only bootstrap:

1. creates missing coordination labels;
2. scans all enrolled open issues;
3. preserves existing trusted status records;
4. materializes missing trusted status from Work Contract migration data, never from mutable state labels;
5. adds a frozen ownership snapshot to legacy trusted statuses that predate that field;
6. reconciles discovery labels from trusted state;
7. refreshes the global active reservation record on #150 from frozen ownership snapshots.

Once bootstrap is complete, labels and Work Contract state/ownership are not execution authority for an already-active reservation.

## Security boundary

The workflow retains only:

```text
contents: read
issues: write
pull-requests: read
```

It has no Actions write, package, release, secret, payment, deployment, or model-training authority. Inputs are handled inside `actions/github-script`; no untrusted command text is interpolated into a shell.

## Agent startup rule

An agent must:

1. read `AGENTS.md` and repository overlays;
2. find a `work:ready` issue;
3. inspect dependencies and positive/negative ownership;
4. post `/claim <agent-id> <branch>`;
5. wait for the accepted `CLAIMED` acknowledgement;
6. only then edit the owned lane.

A claim grants coordination ownership only. It does not grant merge, release, sealed/private-data, paid-compute, external-account, or qualification authority.
