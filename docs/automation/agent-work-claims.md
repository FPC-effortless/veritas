# Agent Work Claim Automation

The `Agent Work Claims` workflow turns GitHub issues marked with `<!-- veritas-agent-work -->` into an auditable coordination queue for parallel coding agents. Coordination state remains separate from environment maturity, scientific qualification, Frontier qualification, training qualification, commercial readiness, merge authority, and release authority.

## Canonical authority

After bootstrap, the only execution authority is the latest trusted bot-authored status record marked `veritas-agent-work-status:v1`. `work:*` labels are discovery metadata only. Mutable issue-body `State`, `Claim holder`, `Linked PR`, and manual label edits cannot directly authorize a later transition.

`/roadmap-bootstrap` on coordination root #150 materializes a trusted status record for every enrolled open roadmap issue and reconciles labels to that record. Bootstrap may use existing Work Contract/label metadata only as migration input when no trusted record exists. Ordinary commands fail closed when trusted status is missing.

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

Recovery requires `OWNER`, preserves the existing branch, is accepted immediately for bootstrap-derived ownership, and otherwise requires the last heartbeat to be at least two hours old. It is an audited ownership recovery, not automatic expiry.

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

The coordination owner may run `/roadmap-bootstrap` only on #150.

## Deterministic command ordering

GitHub Actions concurrency is non-cancelling but is not FIFO. The workflow therefore does not trust runner start order. Every invocation reads pending coordination comments for that issue and processes them in ascending comment-ID order after the last recorded command. A later event can drain an earlier pending command first, so rapid dependent commands such as `/claim` then `/release` are evaluated in authoring order rather than scheduler order.

Rejected commands are also recorded as processed so they cannot be replayed indefinitely.

## Claim locking and parallelism

Before accepting `/claim`, the workflow:

1. requires canonical state `READY`;
2. requires the claimed branch to match a concrete Work Contract branch when one is declared;
3. extracts machine-checkable backticked positive-ownership paths;
4. rejects ancestor/descendant or exact path overlap with active `CLAIMED`, `REVIEW`, or owner-held `BLOCKED` roadmap reservations;
5. scans changed files of open PRs and rejects overlap, excluding only an existing PR on the candidate branch itself.

Coordination-only or metadata-only tickets may explicitly have no source path. Ordinary code tickets without machine-checkable ownership fail closed.

The current active roadmap reservations are mirrored in one trusted bot-authored `veritas-agent-work-reservations:v1` record on #150. Open-PR changed files remain a live claim-time reservation source rather than relying on a potentially stale registry snapshot.

This locking serializes only short coordination transitions. Coding work on disjoint reservations remains parallel.

## Release and blocking

A successful claim stores its release target in trusted status as `return_state`. `/release` uses that frozen trusted value rather than reparsing mutable issue-body `State` at release time.

`/blocked` preserves the current authenticated holder and branch while making the lane non-claimable. Staleness alone never frees a lane; explicit `/release` or owner `/recover` is required.

## Handoff and exact-head completion

`/handoff` requires the authenticated CLAIMED holder and validates that the PR:

- exists in this repository;
- is open;
- uses the recorded claimed branch;
- references both the roadmap issue and primary Work ID.

The handoff records the exact PR head SHA.

`/done` requires the authenticated REVIEW holder, the exact linked PR, a merged PR, and the same PR head SHA that was handed off. If the PR head moves after handoff, `/done` rejects and the final head must be handed off/reviewed again.

This is still implementation-level completion only. Work-class-specific scientific, experiment, external/manual, convergence, and release completion rules remain stricter and must not be inferred from a merged PR.

## Bootstrap and reconciliation

Bootstrap:

1. creates missing coordination labels;
2. scans all enrolled open issues;
3. preserves existing trusted status records;
4. materializes trusted status for every issue missing one;
5. reconciles discovery labels;
6. refreshes the global active reservation record on #150.

Once bootstrap is complete, labels and Work Contract state are not execution authority.

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
