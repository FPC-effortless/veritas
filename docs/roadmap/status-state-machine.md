# Agent-work coordination state machine

Status: coordination policy only. This document governs repository work ownership and handoff. It does not define environment maturity, scientific qualification, Frontier qualification, training qualification, commercial readiness, release state, or sealed/private evidence state.

## Authority and canonical state

For an enrolled `<!-- veritas-agent-work -->` issue, the canonical coordination state is the single `work:*` state maintained by `.github/workflows/agent-work-claims.yml`, together with the latest trusted `<!-- veritas-agent-work-status:v1 -->` record authored by `github-actions[bot]` when such a record exists.

The issue body's `State`, `Claim holder`, and `Linked PR` fields are bootstrap metadata, not mutable execution authority after trusted status exists. A chat transcript, branch name, open PR, green CI run, or untrusted issue comment cannot independently change coordination state.

Exactly one of these coordination states is valid at a time:

- `BLOCKED`
- `READY`
- `CLAIMED`
- `REVIEW`
- `DONE`
- `SUPERSEDED`

The workflow removes prior `work:*` labels before applying the next state label, so multiple simultaneous coordination-state labels are invalid drift rather than a supported composite state.

## State meanings

### BLOCKED

Work cannot be claimed through the normal `/claim` path. BLOCKED may mean either:

1. **unowned/dependency-blocked** — no active holder exists and a prerequisite or external condition prevents execution; or
2. **owner-held blocked** — a current holder moved active work to BLOCKED using `/blocked <agent> <reason>` and retains the lane until explicit release or authorized recovery.

A blocker reason is required for an owner-held transition from CLAIMED or REVIEW. BLOCKED is coordination state only; it must not be interpreted as failure of a scientific or product qualification gate unless that separate system says so.

### READY

The work contract is available for a permitted agent claim. READY carries no owner and no implementation authority beyond eligibility to claim.

### CLAIMED

One agent ID, under one authenticated GitHub actor, owns the issue's coordination lane. The trusted status records the agent ID, branch, claim time, heartbeat, and actor. A claim grants work ownership only; it does not grant merge, release, payment, external-account, sealed-data, or qualification authority.

### REVIEW

The current holder has handed off an open PR whose head branch matches the recorded claim branch. REVIEW reserves the work lane while implementation is independently reviewed, corrected, merged, or otherwise dispositioned according to the work contract.

REVIEW is not DONE and does not imply that required CI, security, exact-head review, merge authority, scientific evidence, or external/manual conditions have passed.

### DONE

The work-class-specific completion condition has been satisfied and the coordination issue is complete. `/done` is not a generic synonym for "PR exists" or "CI is green". Completion rules must remain separate from scientific, Frontier, training, commercial, release, and external/manual evidence states.

### SUPERSEDED

The work item has been explicitly replaced by another canonical item or invalidated by an authorized administrative decision. SUPERSEDED is terminal for ordinary agent commands. Replacement identity and reason must be auditable.

The current claim workflow has no ordinary agent command that creates or reopens SUPERSEDED; such transitions therefore require a separately authorized administrative mechanism rather than being inferred from labels or inactivity.

## Normal transition graph

```text
BLOCKED --authorized prerequisite/admin resolution--> READY
READY   --/claim-->                            CLAIMED
CLAIMED --/handoff-->                          REVIEW
REVIEW  --work-class completion + /done-->     DONE

CLAIMED --/release-->                          READY
CLAIMED --/blocked <reason>-->                 BLOCKED
REVIEW  --/blocked <reason>-->                 BLOCKED

CLAIMED --authorized supersession-->           SUPERSEDED
REVIEW  --authorized supersession-->           SUPERSEDED
READY   --authorized supersession-->           SUPERSEDED
BLOCKED --authorized supersession-->           SUPERSEDED
```

A work contract whose bootstrap state is BLOCKED may return to BLOCKED rather than READY when an active holder uses `/release`; the initial contract state remains relevant to release targeting. Ordinary `/claim` is still prohibited until an authorized transition has made the issue READY.

## Command preconditions enforced by the current workflow

The repository workflow parses only exact single-line commands and checks the authenticated GitHub actor's repository association. For ordinary agent transitions it enforces these state preconditions:

| Command | Required current state | Required holder relation | Result |
| --- | --- | --- | --- |
| `/claim <agent> <branch>` | READY | none | CLAIMED |
| `/heartbeat <agent> [branch]` | CLAIMED, BLOCKED, or REVIEW | current holder | state unchanged |
| `/release <agent> [reason]` | CLAIMED, BLOCKED, or REVIEW | current holder | READY, or contract-initial BLOCKED |
| `/blocked <agent> <reason>` | CLAIMED or REVIEW | current holder | BLOCKED |
| `/handoff <agent> <pr>` | CLAIMED | current holder | REVIEW only after PR/branch validation |
| `/done <agent> <pr>` | REVIEW | current holder | DONE only after workflow completion checks |

Commands outside their permitted source states are rejected rather than silently relabeling the issue. A malformed, multiline, unauthorized, non-holder, mismatched-branch, unresolved-PR, or otherwise invalid command must leave the canonical state unchanged.

## Illegal transitions

The following are illegal for ordinary agents unless a separate explicit administrative contract authorizes them:

- `BLOCKED -> CLAIMED` directly;
- `READY -> REVIEW` or `READY -> DONE`;
- `BLOCKED -> REVIEW` or `BLOCKED -> DONE`;
- `CLAIMED -> DONE` without REVIEW;
- `DONE -> READY|CLAIMED|REVIEW|BLOCKED`;
- `SUPERSEDED -> READY|CLAIMED|REVIEW|BLOCKED|DONE`;
- changing holder identity by heartbeat, handoff, blocked, release, or done commands;
- treating an arbitrary label edit or ordinary comment as an authorized transition.

If DONE or SUPERSEDED must be reopened, the action must be explicit, authorized, and audited with the prior terminal state, acting GitHub actor, reason, replacement/reopened Work ID when applicable, and timestamp. Reopening must never occur merely because a new comment, branch, PR, or stale timer appears.

## Staleness

Staleness is metadata, not a coordination state.

A missed heartbeat may mark a claim as stale for human/admin attention, but it does not:

- remove the current holder;
- change CLAIMED, REVIEW, or owner-held BLOCKED to READY;
- authorize a competing agent to claim the lane;
- close or supersede the issue;
- grant force-release authority.

Recovery from a stale holder requires the existing holder's valid `/release` or a separately authorized and audited administrative recovery path.

## Transition audit contract

Every accepted transition must preserve enough information to reconstruct ownership from GitHub alone. The trusted status record should retain, as applicable:

- schema version and Work ID;
- issue number;
- resulting coordination state;
- authenticated GitHub actor;
- declared agent ID;
- claimed branch;
- claim and heartbeat timestamps;
- linked PR and exact linked PR head;
- blocker or release reason;
- monotonically increasing transition sequence;
- triggering command comment ID;
- update timestamp.

For transitions that cannot be represented by the current ordinary command workflow, the administrative record must additionally identify the transition authority and why the exceptional edge was allowed.

## Separation from qualification and maturity

Coordination state answers only: **who may work on this repository item, and where is it in the work handoff lifecycle?**

It must never be overloaded with environment or evidence meaning. In particular:

- READY does not mean an environment is usable;
- CLAIMED does not mean implementation is correct;
- REVIEW does not mean exact-head gates passed;
- DONE does not mean scientific, Frontier, training, commercial, or release qualification passed;
- BLOCKED does not by itself mean a scientific test failed;
- SUPERSEDED does not erase historical evidence.

Those systems require their own content-bound evidence and authority.

## Falsifiers and regression expectations

The coordination contract is violated if any of the following is possible:

1. one issue carries more than one `work:*` state as a valid result of an accepted transition;
2. `/claim` succeeds while canonical state is BLOCKED;
3. `/done` succeeds directly from READY, BLOCKED, or CLAIMED;
4. a non-holder can heartbeat, release, block, hand off, or complete another holder's work;
5. a branch mismatch can hand off a PR into REVIEW;
6. an ordinary issue comment is interpreted as ownership authority;
7. heartbeat expiry automatically frees a lane;
8. DONE or SUPERSEDED reopens without an explicit audited authority action;
9. coordination state is cited as scientific, Frontier, training, commercial, release, sealed, paid-compute, or external-account PASS.

## Implementation boundary

This specification is grounded in the current `agent-work-claims.yml` behavior but does not modify that workflow. Where the policy requires an administrative supersede/reopen transition, current ordinary automation is intentionally insufficient; a future owner-scoped coordination change must implement that path explicitly rather than pretending an existing agent command already provides it.
