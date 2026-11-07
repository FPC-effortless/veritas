# Agent-work coordination state machine

Status: coordination policy only. This document governs repository work ownership and handoff. It does not define environment maturity, scientific qualification, Frontier qualification, training qualification, commercial readiness, release state, or sealed/private evidence state.

## Authority and canonical state

For an enrolled `<!-- veritas-agent-work -->` issue, execution authority is the latest trusted `<!-- veritas-agent-work-status:v1 -->` record authored by `github-actions[bot]`. The `work:*` label is discovery metadata and must match the trusted status; it is not a fallback authority.

If trusted status is absent, ordinary commands are rejected. An authorized repository OWNER must run `/roadmap-bootstrap` on #150 to materialize or reconcile trusted status for enrolled issues. Bootstrap uses the Work Contract as initial metadata, but after that the trusted record carries live state, authenticated holder, branch, frozen `ownership_paths`, linked PR/head, and `return_state`. Later edits to the Work Contract state or labels cannot change those recorded values. The contract still supplies descriptive/validation inputs where documented below, such as the declared branch for a new `/claim` and the Work ID required in a PR body.

A chat transcript, branch name, open PR, green CI run, or untrusted ordinary issue comment cannot independently change coordination state.

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

The current workflow has no ordinary command that resolves an unowned dependency-blocked item to READY. `/claim` requires READY, and `/release` requires an active holder. The OWNER-only `/roadmap-bootstrap` reconciliation has one narrow exception: a pristine bootstrap BLOCKED record can become READY when the Work Contract's declared initial state is READY. It does not resolve a Work Contract initially declared BLOCKED; that still needs an audited prerequisite/admin path.

### READY

The work contract is available for a permitted agent claim. READY carries no owner and no implementation authority beyond eligibility to claim.

READY is claimable only when present in trusted bot status. A `work:ready` label without trusted status is not sufficient; ordinary commands fail closed until bootstrap creates or reconciles the trusted record.

### CLAIMED

For an ordinary `/claim`, one agent ID under one authenticated GitHub actor owns the issue's coordination lane. The trusted status records the agent ID, branch, claim time, heartbeat, and authenticated actor. A claim grants work ownership only; it does not grant merge, release, payment, external-account, sealed-data, or qualification authority.

Bootstrap can preserve a pre-existing declared holder with `github_actor: "bootstrap"`; this does not prove which actor originally created the historical lane. Ordinary holder commands require an actor match, so an OWNER must use the audited `/recover` path to bind a bootstrap-derived or sufficiently stale holder to the recovering actor before ordinary holder transitions can proceed. Do not describe a bootstrap sentinel as an authenticated actor binding.

### REVIEW

On the ordinary command path, the current holder has handed off an open PR whose head branch matches the recorded claim branch and whose body references the issue and Work ID. REVIEW reserves the work lane while implementation is independently reviewed, corrected, merged, or otherwise dispositioned according to the work contract.

Bootstrap can also reconstruct a pre-existing REVIEW lane directly from issue metadata. Such a bootstrapped REVIEW status may have a declared holder and may have `linked_pr: null`; it therefore does not prove that ordinary `/handoff` validations ran. Current `/done` rejects a missing linked PR, and a recorded linked PR must match the supplied PR.

REVIEW is not DONE and does not imply that required CI, security, exact-head review, merge authority, scientific evidence, or external/manual conditions have passed.

### DONE

DONE means the coordination workflow accepted completion for the work item. Policy requires that the work-class-specific completion condition also be satisfied before DONE is legitimate.

The current `/done` requires REVIEW, the authenticated current holder, a non-null matching linked PR, and a merged PR. When the status records a handoff head, the current PR head must match it. A bootstrap-derived record with missing linkage must first go through the applicable OWNER recovery path and cannot reach DONE by supplying an unrelated merged PR.

The current workflow also does **not** evaluate the richer work-class completion policy defined in [`docs/roadmap/completion-rules.md`](completion-rules.md), merged by PR #282; ROADMAP-DONE-001 (#233) tracks the corresponding automation. Until those owner-scoped extensions exist, a merged implementation PR can satisfy the current coordination command while still lacking scientific, Frontier, training, commercial, release, external/manual, or other class-specific evidence. Consumers must not infer those states from `work:done`.

### SUPERSEDED

The work item has been explicitly replaced by another canonical item or invalidated by an authorized administrative decision. SUPERSEDED is terminal for ordinary agent commands. Replacement identity and reason must be auditable.

The current claim workflow has no ordinary agent command that creates or reopens SUPERSEDED; such transitions therefore require a separately authorized administrative mechanism rather than being inferred from labels or inactivity.

## Transition graph: policy target and current enforcement

There is no ordinary prerequisite-resolution command for unowned BLOCKED work. Bootstrap's narrowly-scoped reconciliation is separate from the ordinary transition graph:

```text
UNOWNED BLOCKED --OWNER /roadmap-bootstrap reconciliation--> READY
                 [only when pristine bootstrap state + declared initial State is READY]

READY   --/claim-->                            CLAIMED
CLAIMED --/handoff-->                          REVIEW
REVIEW  --/done with matching merged PR/head--> DONE

CLAIMED --/release-->                          READY or BLOCKED according to trusted return_state
REVIEW  --/release-->                          READY or BLOCKED according to trusted return_state
CLAIMED --/blocked <reason>-->                 BLOCKED (owner-held)
REVIEW  --/blocked <reason>-->                 BLOCKED (owner-held)
BLOCKED (owner-held) --/release-->              READY or BLOCKED according to trusted return_state

CLAIMED --authorized supersession-->           SUPERSEDED [policy only today]
REVIEW  --authorized supersession-->           SUPERSEDED [policy only today]
READY   --authorized supersession-->           SUPERSEDED [policy only today]
BLOCKED --authorized supersession-->           SUPERSEDED [policy only today]
```

This distinction is material: an unowned initially-BLOCKED item cannot use `/release`, and `/claim` cannot make it READY. The owner-only bootstrap reconciliation can only restore READY when the immutable bootstrap snapshot conditions and declared READY initial state match; other prerequisite changes need a separately authorized mechanism.

## Command preconditions enforced by the current workflow

The repository workflow parses only exact single-line commands and checks the authenticated GitHub actor's repository association. For ordinary agent transitions it enforces these state preconditions:

| Command | Required current state | Required holder relation | Result |
| --- | --- | --- | --- |
| `/claim <agent> <branch>` | READY | none | CLAIMED with `github_actor` bound to the command actor |
| `/heartbeat <agent> [branch]` | CLAIMED, BLOCKED, or REVIEW | authenticated current holder | state unchanged |
| `/release <agent> [reason]` | CLAIMED, BLOCKED, or REVIEW | authenticated current holder | READY or BLOCKED according to trusted `return_state` |
| `/blocked <agent> <reason>` | CLAIMED or REVIEW | authenticated current holder | BLOCKED |
| `/handoff <agent> <pr>` | CLAIMED, or REVIEW for re-handoff of same PR | authenticated current holder | REVIEW only after open-PR, branch, issue, and Work-ID validation; exact head is recorded |
| `/done <agent> <pr>` | REVIEW | authenticated current holder | DONE only when the linked PR matches and is merged; if a handoff head is recorded, current PR head must match |

Commands outside their permitted source states are rejected rather than silently relabeling the issue. A malformed, multiline, unauthorized, non-holder, mismatched-branch, unresolved-PR, unmerged-PR, or otherwise invalid command must leave the canonical state unchanged.

The table describes **current automation**, not the full completion policy. Ordinary `/handoff` validates the open PR, branch, issue, and Work ID and records the exact head. Bootstrap may reconstruct a legacy linked PR without that head evidence; OWNER recovery paths have separate validation rules. `/done` requires a linked PR and checks the recorded head when present, but it does not itself rerun every ordinary handoff check. The merged policy in [`docs/roadmap/completion-rules.md`](completion-rules.md) requires work-class-specific completion; ROADMAP-DONE-001 (#233) tracks that automation.

If trusted bot status is absent, ordinary commands are rejected and the audit comment directs an OWNER to run `/roadmap-bootstrap` on #150. Labels and mutable Work Contract state are not execution authority in that case.

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

The workflow treats `work:*` labels as discovery metadata and requires trusted status before ordinary commands. If a trusted status is absent, a manually changed label cannot make `/claim` succeed; the workflow rejects the command and requires OWNER bootstrap.

An owner-held BLOCKED lane transitions through `/release` according to its trusted `return_state`. This is distinct from the prerequisite-resolution transition for an **unowned** initially-BLOCKED item, which has no ordinary command path.

If DONE or SUPERSEDED must be reopened, the action must be explicit, authorized, and audited with the prior terminal state, acting GitHub actor, reason, replacement/reopened Work ID when applicable, and timestamp. Reopening must never occur merely because a new comment, branch, PR, or stale timer appears.

## Staleness

Staleness is metadata, not a coordination state.

A missed heartbeat may mark a claim as stale for human/admin attention, but it does not:

- remove the current holder;
- change CLAIMED, REVIEW, or owner-held BLOCKED to READY;
- authorize a competing agent to claim the lane;
- close or supersede the issue;
- grant force-release authority.

The OWNER-only `/recover` command can rebind a bootstrap-derived holder or a holder stale for at least two hours, preserving the recorded branch and frozen ownership. Otherwise recovery requires the existing holder's valid `/release` or another explicitly authorized administrative path.

## Transition audit contract

Every accepted transition must preserve enough information to reconstruct ownership from GitHub alone. The trusted status record should retain, as applicable:

- schema version and Work ID;
- issue number;
- resulting coordination state;
- authenticated GitHub actor for ordinary claims, or the explicit `bootstrap` sentinel for reconstructed holders;
- declared agent ID;
- claimed branch;
- claim and heartbeat timestamps;
- linked PR and exact linked PR head when one has been validated/recorded;
- blocker or release reason;
- monotonically increasing transition sequence;
- triggering command comment ID;
- update timestamp.

The trusted status comment is the mutable current snapshot, not an immutable transition history. Accepted and rejected commands receive separate audit comments; use those comments to reconstruct prior transitions. The snapshot's `return_state` governs release targets and remains frozen across later Work Contract edits.

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

The coordination contract is violated if any of the following is possible or documented inaccurately:

1. one issue carries more than one `work:*` state as a valid result of an accepted transition;
2. `/claim` succeeds while trusted canonical state is BLOCKED;
3. `/done` succeeds directly from READY, BLOCKED, or CLAIMED;
4. an ordinary non-holder can heartbeat, release, block, hand off, or complete another ordinary holder's work;
5. a branch mismatch can pass the ordinary `/handoff` path into REVIEW;
6. an ordinary issue comment is interpreted as ownership authority;
7. heartbeat expiry automatically frees a lane;
8. DONE or SUPERSEDED reopens without an explicit audited authority action;
9. coordination state is cited as scientific, Frontier, training, commercial, release, sealed, paid-compute, or external-account PASS;
10. current `/done` merge-only enforcement is misrepresented as already implementing ROADMAP-DONE-001 work-class completion rules;
11. unowned initially-BLOCKED work is documented as having a current `BLOCKED -> READY` command when no such command exists;
12. `/done` is documented as accepting a missing linked PR or as revalidating all ordinary handoff checks itself;
13. a bootstrap sentinel is treated as an authenticated holder without OWNER recovery binding it to the current actor;
14. `/release` is documented as reparsing the Work Contract state rather than using trusted `return_state`;
15. labels or mutable Work Contract state are documented as execution authority when trusted status is absent, rather than fail-closed bootstrap being required.

## Implementation boundary

This specification is grounded in the current `agent-work-claims.yml` behavior but does not modify that workflow. Current automation gaps are explicit rather than hidden:

1. unowned initially-BLOCKED work has no ordinary prerequisite-resolution command to READY;
2. bootstrap reconstructs historical holders with `github_actor: "bootstrap"`; an OWNER must recover them to establish current actor binding;
3. bootstrap can persist REVIEW with a linked PR but no exact head; OWNER recovery is required before normal actor-bound handoff/completion, and `/done` rejects a missing link;
4. SUPERSEDED/reopen transitions require a future authorized administrative path; and
5. `/done` does not enforce work-class completion evidence, which ROADMAP-DONE-001 (#233) owns.

Future owner-scoped coordination changes should implement those policies explicitly rather than pretending the existing command workflow already provides them.
