# Agent-work coordination state machine

Status: coordination policy only. This document governs repository work ownership and handoff. It does not define environment maturity, scientific qualification, Frontier qualification, training qualification, commercial readiness, release state, or sealed/private evidence state.

## Authority and canonical state

For an enrolled `<!-- veritas-agent-work -->` issue, the preferred canonical coordination authority is the latest trusted `<!-- veritas-agent-work-status:v1 -->` record authored by `github-actions[bot]` when such a record exists, with the `work:*` label maintained to match it by `.github/workflows/agent-work-claims.yml`.

When no trusted status record exists, current automation has a weaker fallback. `canonicalStatus()` first accepts exactly one present `work:*` state label as canonical state and only falls back to the issue body's Work Contract `State` if there is not exactly one such label. Bootstrap creates trusted status comments only for reconstructed CLAIMED/REVIEW lanes, so READY, BLOCKED, DONE, and SUPERSEDED work can remain on this label-based authority path. Policy forbids arbitrary/manual state-label edits, but current automation cannot distinguish such an edit from a workflow-maintained label before a trusted status record exists; an externally relabeled no-status issue can therefore affect the next command's canonical state.

The issue body's `Claim holder` and `Linked PR` fields are bootstrap metadata rather than mutable execution authority after a trusted status record exists. The issue body's `State` field is **not fully bootstrap-only in the current workflow**: every command reparses the current issue body, and `/release` uses the freshly parsed `contract.initialState` value to choose whether the released issue becomes READY or BLOCKED. Editing the Work Contract `State` after trusted status exists can therefore alter a later release target. This is a current automation limitation, not intended policy.

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

The policy model requires an explicit audited way to move an unowned dependency-blocked item to READY when its prerequisites are resolved. The current `agent-work-claims.yml` does **not** implement that unowned `BLOCKED -> READY` transition. `/claim` requires READY, and `/release` requires an active holder. When the issue body's currently parsed Work Contract `State` is BLOCKED, holder release returns the item to unowned BLOCKED rather than READY. Until an administrative/prerequisite-resolution mechanism is implemented, the workflow has no ordinary command that makes such an unowned initially-BLOCKED item READY.

### READY

The work contract is available for a permitted agent claim. READY carries no owner and no implementation authority beyond eligibility to claim.

Before a trusted bot status record exists, READY may be obtained by the current single-`work:*`-label fallback. Policy requires that state label to be maintained only by authorized coordination automation, but current enforcement does not cryptographically or structurally prove that provenance before using the label.

### CLAIMED

For an ordinary `/claim`, one agent ID under one authenticated GitHub actor owns the issue's coordination lane. The trusted status records the agent ID, branch, claim time, heartbeat, and authenticated actor. A claim grants work ownership only; it does not grant merge, release, payment, external-account, sealed-data, or qualification authority.

There is a bootstrap exception. When `canonicalStatus()` reconstructs a pre-existing declared holder before a trusted status record exists, it records `github_actor: "bootstrap"` rather than the actor that originally created the historical lane. The current `isHolder()` accepts that sentinel for any otherwise-authorized GitHub actor presenting the matching agent ID. Therefore bootstrap preserves a reservation, but it is not equivalent to the stronger actor binding established by an ordinary `/claim`. Consumers must not describe every bootstrapped CLAIMED/REVIEW holder as authenticated to one specific GitHub actor.

### REVIEW

On the ordinary command path, the current holder has handed off an open PR whose head branch matches the recorded claim branch and whose body references the issue and Work ID. REVIEW reserves the work lane while implementation is independently reviewed, corrected, merged, or otherwise dispositioned according to the work contract.

Bootstrap can also reconstruct a pre-existing REVIEW lane directly from issue metadata. Such a bootstrapped REVIEW status may have a declared holder and may have `linked_pr: null`; it therefore does not universally prove that the ordinary `/handoff` validations already ran.

REVIEW is not DONE and does not imply that required CI, security, exact-head review, merge authority, scientific evidence, or external/manual conditions have passed.

### DONE

DONE means the coordination workflow accepted completion for the work item. Policy requires that the work-class-specific completion condition also be satisfied before DONE is legitimate.

The current `agent-work-claims.yml` implementation is narrower than that policy. `/done` currently requires REVIEW state, the current holder relation, and a supplied PR that is merged. If `status.linked_pr` is already non-null, the supplied PR must match it. However, `/done` does **not** require `linked_pr` to be non-null and does not repeat the `/handoff` branch/issue/Work-ID checks. A bootstrapped REVIEW record with `linked_pr: null` can therefore reach DONE using a merged PR without proving that the earlier ordinary handoff validation occurred.

The current workflow also does **not** evaluate the richer work-class completion rules tracked by ROADMAP-DONE-001 (#233). Until those owner-scoped extensions exist, a merged implementation PR can satisfy the current coordination command while still lacking scientific, Frontier, training, commercial, release, external/manual, or other class-specific evidence. Consumers must not infer those states from `work:done`.

### SUPERSEDED

The work item has been explicitly replaced by another canonical item or invalidated by an authorized administrative decision. SUPERSEDED is terminal for ordinary agent commands. Replacement identity and reason must be auditable.

The current claim workflow has no ordinary agent command that creates or reopens SUPERSEDED; such transitions therefore require a separately authorized administrative mechanism rather than being inferred from labels or inactivity.

## Transition graph: policy target and current enforcement

The policy target includes an audited prerequisite/administrative resolution edge for unowned BLOCKED work, but that edge is not implemented by the current command workflow:

```text
UNOWNED BLOCKED --policy prerequisite/admin resolution--> READY
                 [NOT IMPLEMENTED by agent-work-claims.yml]

READY   --/claim-->                            CLAIMED
CLAIMED --/handoff-->                          REVIEW
REVIEW  --/done with supplied merged PR-->     DONE

CLAIMED --/release-->                          READY, or BLOCKED according to the
                                                Work Contract State parsed at release time
REVIEW  --/release-->                          READY, or BLOCKED according to the
                                                Work Contract State parsed at release time
CLAIMED --/blocked <reason>-->                 BLOCKED (owner-held)
REVIEW  --/blocked <reason>-->                 BLOCKED (owner-held)
BLOCKED (owner-held) --/release-->              READY if the currently parsed Work Contract
                                                State is not BLOCKED; unowned BLOCKED if it is

CLAIMED --authorized supersession-->           SUPERSEDED [policy only today]
REVIEW  --authorized supersession-->           SUPERSEDED [policy only today]
READY   --authorized supersession-->           SUPERSEDED [policy only today]
BLOCKED --authorized supersession-->           SUPERSEDED [policy only today]
```

This distinction is material: an unowned initially-BLOCKED item cannot use `/release`, and `/claim` cannot make it READY. The desired prerequisite-resolution edge must therefore remain labelled as policy until a separately authorized workflow implements it.

The phrase "Work Contract State parsed at release time" is deliberate. Although the implementation property is named `initialState`, `parseContract()` is called against the issue's current mutable body for every command. The trusted status record does not freeze this release-target input.

## Command preconditions enforced by the current workflow

The repository workflow parses only exact single-line commands and checks the authenticated GitHub actor's repository association. For ordinary agent transitions it enforces these state preconditions:

| Command | Required current state | Required holder relation | Result |
| --- | --- | --- | --- |
| `/claim <agent> <branch>` | READY | none | CLAIMED with `github_actor` bound to the command actor |
| `/heartbeat <agent> [branch]` | CLAIMED, BLOCKED, or REVIEW | current holder; bootstrap sentinel also satisfies `isHolder()` for an authorized actor with matching agent ID | state unchanged |
| `/release <agent> [reason]` | CLAIMED, BLOCKED, or REVIEW | current holder; same bootstrap caveat | READY or BLOCKED according to the Work Contract `State` reparsed from the issue body for this command |
| `/blocked <agent> <reason>` | CLAIMED or REVIEW | current holder; same bootstrap caveat | BLOCKED |
| `/handoff <agent> <pr>` | CLAIMED | current holder; same bootstrap caveat | REVIEW only after open-PR, branch, issue, and Work-ID validation |
| `/done <agent> <pr>` | REVIEW | current holder; same bootstrap caveat | DONE when the supplied PR is merged; an existing non-null `linked_pr` must match, but null `linked_pr` is not rejected |

Commands outside their permitted source states are rejected rather than silently relabeling the issue. A malformed, multiline, unauthorized, non-holder, mismatched-branch, unresolved-PR, unmerged-PR, or otherwise invalid command must leave the canonical state unchanged.

The table describes **current automation**, not the full completion policy. In particular, `/done` itself does not universally prove that ordinary `/handoff` validation occurred, and ROADMAP-DONE-001 (#233) owns the extension that makes completion depend on work class rather than treating a merged PR as sufficient for every class.

Current canonical-state resolution also has an explicit pre-status limitation: if there is no trusted bot status record, exactly one present `work:*` label is consumed as canonical state before the Work Contract state fallback. Thus ordinary command state checks are fail-closed relative to the state they resolve, but the provenance of that no-status label is not itself validated.

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

The last rule is a **policy prohibition**, not a statement that the current workflow fully rejects externally mutated labels. Before a trusted status record exists, `canonicalStatus()` can consume one externally changed `work:*` label as current state. For example, manually changing a no-status BLOCKED issue to a single `work:ready` label can make the next `/claim` evaluate the issue as READY. That is an automation integrity gap and must not be interpreted as an authorized transition merely because a later command succeeds.

An owner-held BLOCKED lane may transition through `/release` according to the Work Contract `State` parsed at release time. That current behavior is distinct from the currently unimplemented prerequisite-resolution transition for an **unowned** initially-BLOCKED item, and it is weaker than the intended policy because that issue-body field remains mutable after trusted status exists.

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
- authenticated GitHub actor for ordinary claims, or the explicit `bootstrap` sentinel for reconstructed holders;
- declared agent ID;
- claimed branch;
- claim and heartbeat timestamps;
- linked PR and exact linked PR head when one has been validated/recorded;
- blocker or release reason;
- monotonically increasing transition sequence;
- triggering command comment ID;
- update timestamp.

The trusted status record is the durable ownership history, but current `/release` still depends on one live issue-body input that is not captured as immutable transition authority: the reparsed Work Contract `State`. Reviewers should therefore treat a release target as reflecting both the trusted prior status and the issue-body State present when the release command executed.

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
12. `/done` is documented as universally proving prior handoff/linked-PR binding even though null `linked_pr` bootstrap REVIEW is accepted;
13. a bootstrapped holder is described as strongly bound to one authenticated GitHub actor despite the current `github_actor: "bootstrap"` sentinel behavior;
14. issue-body Work Contract `State` is documented as frozen/bootstrap-only after trusted status even though `/release` reparses and consumes it;
15. arbitrary `work:*` label mutation is documented as impossible to influence execution even though a no-trusted-status issue can use a single state label as canonical state.

## Implementation boundary

This specification is grounded in the current `agent-work-claims.yml` behavior but does not modify that workflow. Current automation gaps are explicit rather than hidden:

1. unowned initially-BLOCKED work has no implemented prerequisite/admin transition to READY;
2. bootstrap reconstructs historical holders with `github_actor: "bootstrap"`, which is weaker than ordinary `/claim` actor binding;
3. bootstrap can persist REVIEW with `linked_pr: null`, and `/done` does not require a prior non-null linked PR or rerun `/handoff` binding validation;
4. SUPERSEDED/reopen transitions require a future authorized administrative path;
5. `/done` currently proves only REVIEW-holder plus supplied-merged-PR completion, while ROADMAP-DONE-001 (#233) owns work-class-specific completion enforcement;
6. `/release` reparses the mutable issue-body Work Contract `State` even after trusted status exists, so that field can still change the release target; and
7. when no trusted status record exists, exactly one `work:*` label is accepted as canonical state before the Work Contract fallback, so external/manual label mutation can influence the next command on those lanes.

Future owner-scoped coordination changes should implement those policies explicitly rather than pretending the existing command workflow already provides them.
