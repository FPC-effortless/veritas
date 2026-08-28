# Agent Work Claim Automation

The `Agent Work Claims` workflow turns GitHub issues marked with `<!-- veritas-agent-work -->` into an auditable coordination queue for parallel coding agents.

Coordination state is separate from Veritas environment maturity, scientific qualification, Frontier qualification, training qualification, and commercial release state.

## Discovery

After roadmap bootstrap, claimable work is discoverable with GitHub search:

```text
is:issue is:open label:agent-work label:work:ready
```

Other useful states are `work:claimed`, `work:blocked`, `work:review`, `work:done`, and `work:superseded`.

Exactly one `work:*` coordination-state label is maintained by the workflow. Existing unrelated labels are preserved.

## Authorization

State-changing commands are accepted only from GitHub actors whose issue-comment `author_association` is `OWNER`, `MEMBER`, or `COLLABORATOR`.

The declared agent ID is coordination metadata only. It is not authentication and must never contain a token, password, email address, or other secret.

## Commands

Commands must be one exact line. Quoted or multiline command text is rejected.

```text
/claim <agent-id> <branch>
/heartbeat <agent-id> [branch]
/release <agent-id> [reason]
/blocked <agent-id> <reason>
/handoff <agent-id> <pr-number>
/done <agent-id> <pr-number>
```

The coordination owner should run `/roadmap-bootstrap` on issue #150 after the workflow is installed or when a one-time label reconciliation is required.

## Claim behavior

`/claim` is accepted only when the canonical live status is `READY`. The workflow serializes all coordination transitions through a non-cancelling concurrency group, so simultaneous claim events cannot use last-writer-wins semantics.

An accepted claim records:

- Work ID and issue;
- authenticated GitHub actor;
- declared agent ID;
- branch;
- claim timestamp;
- latest heartbeat;
- linked PR/head when present;
- blocker/release reason;
- monotonically increasing transition sequence.

The current record is maintained in a bot-authored issue comment marked `veritas-agent-work-status:v1`. User-authored lookalike comments are not accepted as status authority. Every accepted or rejected transition also receives a human-readable audit comment.

## Heartbeats and stale work

A heartbeat refreshes the current claim timestamp but does not change ownership. This workflow does not automatically steal or expire a claim. Stale-claim monitoring/reclaim is a separate audited policy.

## Release and blocking

A holder may release active work. A ticket whose Work Contract was originally dependency-blocked returns conservatively to `BLOCKED`; otherwise it returns to `READY`.

`/blocked` preserves the current owner and branch while moving the coordination label to `work:blocked`, so the ticket is visibly non-claimable while the blocker exists.

## Handoff

`/handoff` is accepted only from a current claimant and validates that:

- the PR exists in this repository;
- it is open;
- its head branch matches the recorded claim branch;
- its body references both the roadmap issue and the primary Work ID.

A valid handoff moves the ticket to `REVIEW` and records the PR number/head SHA.

## Done

For this first coordination layer, `/done` requires a prior `REVIEW` handoff and a merged linked PR. It does not close the issue automatically and it does not imply any scientific/manual/evidence qualification state.

Work classes whose completion requires experiments, private evidence, Frontier evaluation, training evidence, external accounts, payment, legal decisions, or release authority must retain their stricter completion gate outside this implementation-level transition.

## Bootstrap

`/roadmap-bootstrap` is accepted only on #150 from an authorized actor. It:

1. creates the canonical coordination labels if absent;
2. scans open issues marked `veritas-agent-work`;
3. applies `agent-work` plus exactly one Work Contract/current-status label;
4. preserves existing CLAIMED/REVIEW reservations;
5. creates a canonical status comment for pre-existing active lanes where needed;
6. posts an aggregate initialization audit to #150.

Bootstrap changes coordination metadata only.

## Security boundaries

The workflow has only:

```text
contents: read
issues: write
pull-requests: read
```

It has no `actions: write`, no secrets permission, and no release/package authority. It cannot dispatch model-training, sealed, release, publishing, payment, or other protected workflows.

The issue-comment body is consumed through the GitHub Script API rather than interpolated into a shell command. Agent IDs and branch names are validated against narrow character sets; reasons are stored as data and never executed.

## Failure model

The canonical bot status record plus coordination label is the live state. Commands are globally serialized and event comment IDs make accepted transitions idempotent against duplicate delivery.

A partial GitHub API outage should be treated conservatively: agents must inspect the canonical status comment/label and wait for a reconciled transition rather than assuming work became free. More extensive rollback/reclaim automation is tracked separately.

## Agent startup rule

An agent must not begin editing simply because an issue looks interesting. The required sequence is:

1. read `AGENTS.md` and repository overlay;
2. find a `work:ready` issue;
3. inspect dependencies and positive/negative ownership;
4. post `/claim <agent-id> <branch>`;
5. wait for the workflow's accepted `CLAIMED` acknowledgement;
6. only then create/use the branch and edit owned paths.

A claim grants coordination ownership only. It does not grant merge, release, sealed/private-data, paid-compute, or qualification authority.
