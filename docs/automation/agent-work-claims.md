# Agent Work Claim Automation

The `Agent Work Claims` workflow turns GitHub issues marked with `<!-- veritas-agent-work -->` into an auditable coordination queue for parallel coding agents. Coordination state remains separate from environment maturity, scientific qualification, Frontier qualification, training qualification, commercial readiness, merge authority, and release authority.

## Canonical authority

The only execution authority is the latest trusted bot-authored status record marked `veritas-agent-work-status:v1`. `work:*` labels are discovery metadata only. Mutable issue-body `State`, `Claim holder`, `Linked PR`, `Positive ownership`, and manual label edits cannot directly authorize or reshape a later active transition.

The effective positive-ownership paths are frozen into trusted status as `ownership_paths` when a claim is accepted or when a legacy status is deliberately migrated. Active registry updates consume that frozen ownership snapshot rather than reparsing mutable issue-body ownership text. Changing a Work Contract after claim therefore does not silently widen, shrink, or move an active reservation.

## Automatic enrollment

A newly opened or reopened issue with `<!-- veritas-agent-work -->` is automatically enrolled when the issue author has GitHub `OWNER`, `MEMBER`, or `COLLABORATOR` association. Enrollment is serialized through the same `agent-work-coordination` concurrency group as claim/status commands.

Automatic enrollment is intentionally weaker than a claim. The enrollment path may create only an **unowned** trusted `READY` or `BLOCKED` record and its discovery label. It cannot create a holder, active reservation, linked PR, REVIEW state, DONE state, or any merge/release/qualification authority.

Initial state comes from the Work Contract, never from mutable `work:*` labels. A valid new `READY` contract must have a concrete branch and machine-checkable positive ownership, unless it uses an exact allow-listed no-source coordination form. A valid `BLOCKED` contract is enrolled as unowned `BLOCKED`.

Automatic enrollment fails closed to unowned `BLOCKED` when the issue tries to start in `CLAIMED`, `REVIEW`, `DONE`, or `SUPERSEDED`; declares a holder or linked PR; or exposes invalid READY branch/ownership metadata. The blocker records that OWNER reconciliation is required. Automatic enrollment never publishes an active owner from issue-body declarations.

Trusted status is written before discovery labels. If label reconciliation later fails, execution remains fail-closed because labels are not authority. Repeated `opened`/`reopened` delivery is idempotent: if trusted status already exists, the workflow preserves that status and only reconciles labels from it rather than creating another trusted record.

`/roadmap-bootstrap` on coordination root #150 is therefore a **repair and migration operation**, not the normal path for new Work Contracts. It remains OWNER-only and is used to initialize legacy issues, reconcile pre-enrollment metadata, or repair deliberately supported migration cases. Ordinary coordination commands still fail closed if trusted status is missing.

Adding the enrollment marker later through an arbitrary issue edit is not treated as automatic authority by this version. Such a migration requires the explicit OWNER reconciliation path.

## Discovery

Claimable work remains discoverable with:

```text
is:issue is:open label:agent-work label:work:ready
```

The workflow maintains exactly one discovery label from `work:ready`, `work:claimed`, `work:blocked`, `work:review`, `work:done`, and `work:superseded`. The label is a view of trusted state, not a substitute for it.

## Authorization and identity

Ordinary commands require GitHub `OWNER`, `MEMBER`, or `COLLABORATOR` association. The authenticated GitHub actor is authority; the declared agent ID is public coordination metadata only and must not contain secrets.

Ordinary holder commands require both the matching agent ID and the authenticated GitHub actor recorded by the claim. Bootstrap-derived holders use `github_actor: "bootstrap"` and cannot silently inherit ordinary holder authority.

Repository owners may explicitly adopt a bootstrap-derived or stale held source lane with:

```text
/recover <new-agent-id> <recorded-branch> <reason>
```

Recovery requires `OWNER`, preserves the existing branch and frozen ownership paths, is accepted immediately for bootstrap-derived ownership, and otherwise requires the last heartbeat to be at least two hours old. It is an audited ownership recovery, not automatic expiry.

A separate narrow recovery command exists only for legacy bootstrap metadata-only reservations whose recorded branch is descriptive prose rather than a repository branch:

```text
/recover-metadata <new-agent-id> <reason>
```

`/recover-metadata` is OWNER-only and does not accept a branch argument. It applies only when the trusted lane is bootstrap-derived with zero frozen source paths, zero transition history, no linked PR, an exact allow-listed no-source `Positive ownership` form, and matching non-concrete descriptive branch metadata. Source-owning, concrete-branch, transitioned, or non-OWNER cases fail closed.

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
/recover-metadata <new-agent-id> <reason>
```

The repository OWNER may run `/roadmap-bootstrap` only on #150.

## Deterministic command ordering

GitHub Actions concurrency is non-cancelling but is not FIFO. Every command invocation reads pending coordination comments for that issue and processes them in ascending comment-ID order after the last recorded command. Rapid dependent commands are therefore evaluated in authoring order rather than runner start order. Rejected commands are recorded as processed so they cannot replay indefinitely.

Issue enrollment and command processing share the same workflow-level concurrency group. A newly created issue cannot race a later `/claim` into two independent authority paths: enrollment publishes the initial trusted record, while the existing transition engine remains the only path that can create an active holder.

## Claim locking and parallelism

Before accepting `/claim`, the transition engine:

1. requires trusted canonical state `READY`;
2. requires the claimed branch to match a concrete Work Contract branch when one is declared;
3. extracts machine-checkable backticked positive-ownership paths;
4. rejects reuse of a branch already held by another active reservation;
5. rejects ancestor/descendant or exact path overlap with active `CLAIMED`, `REVIEW`, or owner-held `BLOCKED` roadmap reservations;
6. scans changed files of open PRs and rejects overlap, excluding only an existing PR on the candidate branch itself;
7. freezes accepted ownership paths into trusted status;
8. commits the active global reservation before publishing trusted local `CLAIMED` state or its discovery label.

Backticked ownership tokens may be root-level repository files such as `Dockerfile`, `Makefile`, `LICENSE`, or `CODEOWNERS`, or nested exact paths. Wildcards are restricted to one terminal subtree suffix such as `src/private/**`. Whitespace-bearing prose, absolute paths, traversal, empty path segments, and unsupported wildcard forms fail closed.

Zero-path claims are exceptional and use an exact allow-list of GitHub-coordination-only ownership forms. One valid example is `this issue's comments/labels only`. Repository-editing prose does not qualify merely because it contains words such as “coordination” or “metadata”; for example, `coordination docs/tests only` must expose concrete repository paths and does not bypass locking.

The current active roadmap reservations are mirrored in one trusted bot-authored `veritas-agent-work-reservations:v1` record on #150. Active entries use frozen ownership snapshots. Open-PR changed files remain a live claim-time reservation source, including legacy or automated PRs that are not `agent-work`.

Claim publication is fail-closed across partial API failure. If the reservation write fails, local `CLAIMED` state is not published. If the reservation succeeds but later status/label publication fails, the reservation is intentionally left stale so overlapping work stays blocked until reconciliation.

## Release and blocking

A successful claim stores its release target in trusted status as `return_state`. `/release` uses that frozen value rather than mutable Work Contract `State` and clears active ownership metadata.

If registry cleanup fails after an active-to-inactive transition, the old reservation remains stale and conservative: work may be temporarily non-claimable, but still-owned work cannot appear free.

`/blocked` preserves the authenticated holder, branch, and frozen ownership reservation. Staleness alone never frees a lane; explicit `/release` or authorized recovery is required.

## Handoff and exact-head completion

`/handoff` requires the authenticated holder and validates that the PR exists in this repository, is open, uses the recorded branch, and references both the roadmap issue and primary Work ID. Handoff records the exact PR head SHA.

A corrected PR may be handed off again while already in REVIEW only for the same PR, refreshing exact-head evidence. It cannot silently switch REVIEW ownership to another PR.

`/done` requires the authenticated REVIEW holder, the exact linked merged PR, and the same PR head SHA most recently handed off. If the head moves, final handoff/review must be repeated.

A narrow migration exception permits legacy REVIEW records created before `ownership_paths` existed to complete only when normal authenticated-holder, exact PR, merged-PR, and handed-off-head checks still pass. Other commands on active legacy records without frozen ownership remain fail-closed.

Implementation-level DONE does not imply scientific, Frontier, training, commercial, external/manual, convergence, release, or private-evidence completion.

## Bootstrap and reconciliation

OWNER-only bootstrap remains available for migration and repair. It:

1. creates missing coordination labels;
2. scans enrolled open issues;
3. preserves existing trusted status records;
4. computes missing legacy trusted status from Work Contract migration data, never mutable state labels;
5. computes frozen ownership snapshots for supported legacy statuses;
6. publishes the complete active reservation registry on #150 before materializing newly migrated active local state;
7. materializes/migrates trusted records;
8. reconciles discovery labels from trusted state.

If bootstrap cannot publish the reservation registry, it does not materialize new active trusted state. If registry publication succeeds and later status/label publication fails, the reservation remains fail-closed until another OWNER reconciliation.

Bootstrap is not required for ordinary new authorized READY/BLOCKED Work Contracts after automatic enrollment is installed.

## Security boundary

The workflow retains only:

```text
contents: read
issues: write
pull-requests: read
```

It has no Actions write, package, release, secret, payment, deployment, or model-training authority. Inputs are handled inside `actions/github-script`; no untrusted command text is interpolated into a shell.

Automatic enrollment is additionally constrained by issue author association and cannot publish active ownership. Unsupported authors or active-state declarations remain outside autonomous coordination authority and require explicit OWNER reconciliation.

## Agent startup rule

An agent must:

1. read `AGENTS.md` and repository overlays;
2. find a `work:ready` issue;
3. inspect the latest trusted status plus dependencies and positive/negative ownership;
4. post `/claim <agent-id> <branch>`;
5. wait for the accepted `CLAIMED` acknowledgement;
6. only then edit the frozen owned lane.

A claim grants coordination ownership only. It does not grant merge, release, sealed/private-data, paid-compute, external-account, deployment, or qualification authority.
