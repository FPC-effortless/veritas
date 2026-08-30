# Roadmap dependency readiness notifications

`ROADMAP-NOTIFY-001` adds a narrow reconciliation pass for roadmap work that is waiting on repository coordination dependencies.

The notifier is **not** a scheduler, claimant, merge train, or qualification engine. It may perform only one execution-state transition:

```text
unowned trusted BLOCKED -> unowned trusted READY
```

It never creates a holder, branch reservation, linked PR, `DONE`, `SUPERSEDED`, merge/release authority, or scientific/commercial qualification state. The existing `agent-work-claims.js` coordinator remains the only ordinary claim/release/handoff/done transition engine.

## Why this exists

The coordination system already records dependencies and can reject unsafe claims, but legacy dependency-blocked issues can remain trusted `BLOCKED` after their prerequisites finish. That forces an owner to edit/reconcile state manually and prevents the GitHub-only queue from becoming self-maintaining.

The notifier closes that narrow gap while remaining fail-closed.

## Triggers and serialization

`.github/workflows/roadmap-dependency-notifications.yml` runs:

- after pushes to `main`;
- when an issue is closed;
- on explicit `workflow_dispatch`.

The workflow uses the same non-cancelling `agent-work-coordination` concurrency group as claim automation. A readiness write therefore cannot intentionally run in parallel with a claim/release/handoff transition.

Permissions are limited to:

```text
contents: read
issues: write
pull-requests: read
```

There is no Actions write, deployment, package, release, secret, payment, external-account, or training authority.

## Candidate boundary

The first implementation is intentionally conservative. Automatic dependency satisfaction is limited to roadmap entries where:

1. the consumer belongs to the `coordination` program;
2. the checked-in roadmap has at least one curated `hard_dependencies` edge;
3. the consumer has a trusted bot-authored `BLOCKED` status;
4. that status is unowned: no GitHub actor, agent ID, branch, or linked PR;
5. every hard dependency also belongs to the `coordination` program;
6. every provider has trusted `DONE` status with an exact linked PR/head;
7. the linked PR is actually merged and its head still matches the trusted handoff head; and
8. the PR merge commit is reachable from current canonical `main`.

Provider and consumer trusted statuses must also bind to the exact roadmap Work
ID. Consumer transition sequence metadata must be a non-negative integer, and
the unowned predicate rejects any actor, agent, claim timestamps, branch,
linked PR, or linked PR head. Missing or malformed decisive metadata is not
defaulted or synthesized.

This deliberately does **not** infer that non-coordination, evidence, manual, paid, sealed, external-authority, scientific, Frontier, training, or commercial dependencies are satisfied merely because code merged or a roadmap item says `DONE`. Those cases remain blocked until a future typed-authority reconciler has sufficient evidence.

The checked-in roadmap supplies dependency graph metadata only. Its stored execution state is not trusted as current; provider state is read from live trusted GitHub status comments and merge ancestry is verified live.

## Ownership and collision gate

Before publishing READY, the notifier reparses the consumer Work Contract for the same machine-checkable positive-ownership grammar used by claim coordination. The candidate must have a concrete branch and either concrete backticked repository paths or one exact allow-listed no-source ownership form.

It then checks candidate paths against:

- the trusted global active-reservation registry on #150; and
- changed files of every open PR.

A newest bot-authored reservation record bearing the trusted marker must have
valid JSON, schema identity, and an entries array. Malformed marked authority
fails closed; the notifier never falls back to an older registry that could
omit a newer active reservation.

Exact and ancestor/descendant path overlaps remain blocking. A collision leaves the item `BLOCKED` and posts one deterministic audit notice for that exact reason. Repeated runs do not spam duplicate collision comments.

This check does not reserve the candidate. It only proves that dependency readiness can be published without immediately advertising work whose owned surface is already occupied.

## Status-first publication

The transition order is fail-closed:

1. update the existing trusted bot status to `READY`;
2. record a `veritas.dependency-ready-event.v1` object containing the transition sequence, verified hard Work IDs, and canonical base SHA;
3. reconcile the discovery label to `work:ready`;
4. post the dependency-ready audit notification.

The trusted status is written before the label, so a partial label failure cannot make a label the execution authority. A later run recognizes the embedded dependency-ready event, repairs the READY discovery label, and ensures the deterministic notification marker exists.

Repair requires the event sequence to match trusted status, the recorded hard
dependencies to exactly match the current roadmap edge list, and the recorded
canonical base to be a concrete commit SHA. A schema string alone is not enough
to authorize READY label or notification repair.

The audit comment states that no claim or reservation was created. Optional `Watchers:` GitHub handles in the Work Contract are mentioned only in that notification; watchers never receive ownership automatically.

## Idempotence

A normal candidate is considered only while its trusted state is unowned `BLOCKED`. Once transitioned, subsequent runs do not repeat the transition.

READY records created by this notifier contain a transition-scoped event marker. Reconciliation can therefore repair missing labels or notification comments after partial failure without issuing another READY transition.

Collision notices use a deterministic digest of the blocking reason so observing the same collision repeatedly produces at most one audit comment.

## Live acceptance case

`ROADMAP-PROGRAM-001` / #239 is the intended post-merge acceptance case. Its hard dependencies `ROADMAP-002` / #196 and `ROADMAP-AUDIT-001` / #209 are already trusted DONE with merged PR evidence, while #239 remains an unowned trusted BLOCKED record.

After this notifier is merged and triggered, #239 must become trusted READY without changing #239's Work Contract `State` field to READY and without an OWNER `/roadmap-bootstrap`. If it does not, ROADMAP-NOTIFY-001 is not complete.

## Evidence boundary

Dependency readiness means only that the supported coordination prerequisites and collision checks no longer prevent a claim. An authorized agent must still issue `/claim`, receive an accepted CLAIMED transition, obey positive/negative ownership, satisfy exact-head review requirements, and obtain separate authority for any release, sealed/private-data, paid-compute, external-account, scientific, Frontier, training, or commercial action.
