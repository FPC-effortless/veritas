# Roadmap dependency semantics

ROADMAP-DEPS-001 defines how Veritas roadmap dependencies affect execution readiness. A dependency edge is a typed coordination predicate, not merely a statement that one item is related to another.

This policy governs roadmap scheduling only. It does not turn code merge, CI, labels, or roadmap metadata into scientific, Frontier, training, commercial, release, sealed-evidence, paid-compute, legal, or external-account authority.

## 1. Core rule

A work item is claimable only when every dependency edge whose kind is **claim-blocking** is satisfied by the authority defined for that edge.

Non-blocking relationships may affect scope, preference, convergence order, or replacement history without serializing otherwise safe work.

Dependency interpretation therefore requires all of:

- the provider or external target;
- the dependency kind;
- the predicate that satisfies that kind;
- whether the predicate blocks claim, handoff, convergence, merge, or none of those stages;
- the authority allowed to assert satisfaction;
- optional scope/evidence notes.

A bare reference such as `#123` or `FOO-001` is insufficient for new machine-readable policy unless its dependency kind is supplied by canonical metadata. Legacy untyped edges should fail conservatively until classified; they must not silently become `soft_preferred` merely to increase parallelism.

## 2. Canonical dependency kinds

### `hard_merge`

Use when the consumer requires provider repository semantics that are not safely available until the provider is merged into the consumer's required base.

**Claim-blocking:** yes, unless the Work Contract explicitly authorizes a reviewed stacked-branch relationship.

**Satisfied when:**

1. the canonical provider PR is merged;
2. the merged commit is reachable from the required consumer base; and
3. any required provider identity/version named by the consumer is present on that base.

An open PR, an approved PR, or green provider CI does **not** satisfy `hard_merge`.

If an explicitly authorized stack is used, the edge remains unsatisfied for final independent-review/merge evidence until the provider is merged and the consumer is synchronized onto the required canonical base.

### `hard_evidence`

Use when execution depends on evidence or a qualification result whose authority is separate from ordinary implementation state.

Examples include a scientific qualification, private evaluation result, verified dataset receipt, expert QA decision, or other named evidence gate.

**Claim-blocking:** yes unless the Work Contract explicitly allows a disjoint preparation subtask before evidence exists.

**Satisfied when:** the named evidence authority records the required terminal result with an auditable evidence reference.

A code merge, green CI, `DONE` implementation ticket, or roadmap label cannot satisfy `hard_evidence` unless the evidence contract explicitly defines that event as the evidence itself.

If the evidence result is negative, inconclusive, expired, revoked, or superseded, the dependency is not satisfied merely because an artifact exists.

### `soft_preferred`

Use when the provider is useful but not semantically required for the consumer to proceed safely.

**Claim-blocking:** no.

**Satisfied when:** the preferred provider condition is available.

If work proceeds before satisfaction, the consumer must record the resulting scope reduction, assumption, compatibility limitation, or follow-up obligation when material. A soft edge must not be interpreted as permission to edit the provider's owned paths.

A `soft_preferred` edge may become hard only through an explicit Work Contract/roadmap policy change. Agents must not promote it to a blocker from personal preference.

### `convergence_after`

Use when independent feature work may proceed in parallel, but a shared or serialized convergence action must occur after named providers reach the required integration state.

**Claim-blocking for feature lane:** no.

**Claim-blocking for designated convergence lane:** yes.

**Satisfied when:** each named provider reaches the convergence prerequisite declared by the convergence ticket, normally merged-to-current-main plus required exact-head evidence.

This relationship is appropriate for shared exports, root CLI registration, package metadata, shared workflows, root documentation, and other `convergence_only` surfaces. It does not grant a feature lane permission to edit those surfaces early.

### `external_authority`

Use when satisfaction requires authority outside ordinary autonomous repository execution: external account access, legal/commercial approval, owner decision, paid resource authorization, private/manual evidence, or equivalent authority.

**Claim-blocking:** yes for the external/manual action itself. A separate, explicitly scoped preparation ticket may be non-blocked if it does not exercise the withheld authority.

**Satisfied when:** the designated authority records `SATISFIED` with a non-secret auditable reference under the canonical external/manual-authority policy.

Repository code, CI, a claim, PR approval, or merge never satisfies this edge by implication.

Secrets, credentials, protected private material, and sensitive command output must not be copied into dependency metadata.

### `supersedes`

Use to state that one Work ID replaces another canonical work item or policy. This is a replacement relationship, not an execution prerequisite.

**Claim-blocking:** no by itself.

**Satisfied:** not applicable.

When supersession becomes effective, coordination state should be changed through an explicit audited supersede mechanism. Historical dependency/evidence references to the superseded item remain historical facts; they must not be silently rewritten to the replacement if semantic equivalence has not been established.

## 3. Stage-specific blocking

A Work Contract may state that an otherwise non-claim-blocking edge becomes mandatory at a later stage. The allowed stages are:

- `claim` — must be satisfied before ownership is granted;
- `handoff` — implementation may proceed, but the PR cannot be handed off as review-ready until satisfied;
- `convergence` — independent implementation may complete, but designated shared integration waits;
- `merge` — review may occur, but final merge evidence is invalid until satisfied;
- `none` — relationship is informative/preferred only.

The dependency kind supplies the default stage. A Work Contract may make the rule **stricter**, not weaker, without an explicit policy exception.

## 4. Machine-readable edge model

ROADMAP-002/ROADMAP-004 implementations may represent dependencies with an object equivalent to:

```json
{
  "target": "PORT-004",
  "kind": "hard_merge",
  "blocks_at": "claim",
  "required_state": "DONE",
  "evidence_ref": null,
  "authority": "github_merge_state",
  "scope_note": null
}
```

External/manual example:

```json
{
  "target": "external:prime-listing-account",
  "kind": "external_authority",
  "blocks_at": "claim",
  "required_state": "SATISFIED",
  "evidence_ref": "authority-record:prime-listing-2026-08",
  "authority": "external_authority_record",
  "scope_note": "Repository-only preparation is a separate Work ID"
}
```

Soft preference example:

```json
{
  "target": "TRACE-001",
  "kind": "soft_preferred",
  "blocks_at": "none",
  "required_state": null,
  "evidence_ref": null,
  "authority": "roadmap_state",
  "scope_note": "Proceed without audit only with reduced metadata-coverage claim"
}
```

The field names above are normative semantics, not a requirement that the checked-in roadmap use this exact JSON layout before ROADMAP-004 implements the schema.

## 5. Satisfaction authorities

Dependency satisfaction must be derived from the authority appropriate to the edge; no single roadmap state is universal authority.

| Kind | Canonical satisfaction authority | Events that are insufficient by themselves |
|---|---|---|
| `hard_merge` | GitHub canonical PR merge + required base ancestry | PR open, CI green, REVIEW, approval |
| `hard_evidence` | named evidence/qualification authority | implementation merge, CI, roadmap DONE |
| `soft_preferred` | provider availability defined by consumer | absence does not block |
| `convergence_after` | provider merge/evidence prerequisites named by convergence ticket | provider branch exists, PR merely open |
| `external_authority` | designated external/manual authority record | code, CI, PR/merge, claim state |
| `supersedes` | explicit audited supersede transition for replacement effect | title/body text mentioning replacement |

When two authorities disagree, the stricter unsatisfied result wins until the conflict is reconciled. Automation must not guess that one authority implicitly overrides another.

## 6. Readiness algorithm

Given a Work ID `W`:

1. Read its canonical dependency edges.
2. Validate that every internal target resolves to exactly one canonical Work ID or alias.
3. Reject cycles across execution-blocking dependency edges.
4. For each edge, evaluate its satisfaction predicate against the edge's designated authority.
5. Collect unsatisfied edges whose `blocks_at` includes `claim`.
6. If that set is non-empty, `W` is dependency-BLOCKED and ordinary `/claim` must reject.
7. If the set is empty, dependency policy does not prevent READY. Other blockers—ownership conflict, authority policy, branch rules, explicit issue state, qualification-specific constraints—may still prevent a claim.
8. Recompute when an authoritative provider/evidence/authority event changes, not merely when comments are posted.

Pseudo-code:

```text
claim_blockers(W) = {
  edge in dependencies(W)
  where blocks_at(edge) == claim
    and not satisfied(edge, authority(edge))
}

can_be_dependency_ready(W) = claim_blockers(W) is empty
```

Dependency readiness is necessary but not sufficient for claimability.

## 7. `hard_merge` details

For a provider `P` and consumer `C`, the edge is not satisfied merely because `P.state == DONE` in a roadmap snapshot. The merge itself must be verified against the canonical repository and the consumer's required base.

The normal sequence is:

```text
P implementation
→ P exact-head gates
→ independent review
→ authorized merge
→ C observes new canonical base
→ C claim/base validation
```

A stacked exception must explicitly name:

- provider Work ID;
- provider PR and exact head;
- consumer branch;
- merge order;
- ownership relationship;
- requirement to synchronize and rerun final evidence after provider merge.

Unrelated feature heads are never valid substitutes for the canonical base.

## 8. `hard_evidence` details

Evidence dependencies should name the proposition being required, not merely an artifact path. For example:

```text
bad:  depends on report.json
better: hard_evidence: QUAL-001 result == PASS under qualification contract vX
```

The edge should preserve:

- evidence/qualification identity;
- required outcome;
- version or policy identity where material;
- expiration/revocation semantics when relevant;
- private/public reference boundary.

The roadmap may record an opaque evidence reference. It must not copy sealed/private evidence into public coordination metadata.

## 9. Soft dependencies and reduced scope

A soft provider being absent must not force BLOCKED. To keep that freedom auditable, a consumer that proceeds early should record any material consequence, for example:

- one adapter omitted;
- one comparison unavailable;
- fallback interface used;
- validation panel reduced;
- documentation deferred;
- later convergence/retest required.

The recorded reduction cannot contradict the consumer's acceptance criteria. If the missing provider makes an acceptance criterion impossible, the relationship was misclassified and should be a hard edge.

## 10. Convergence semantics

`convergence_after` prevents shared surfaces from becoming an implicit serialization point for feature work.

Example:

```text
PORT-A ─┐
PORT-B ─┼─ feature lanes proceed in parallel
PORT-C ─┘
          ↓
CONV-001 owns shared __init__.py / CLI / package metadata
```

The feature lanes use their own exclusive paths and, where needed, `interface_request` under the path-ownership policy. CONV-001 remains BLOCKED until its provider conditions are satisfied.

A provider finishing does not transfer ownership of shared files to that provider.

## 11. External/manual authority

`external_authority` is deliberately orthogonal to implementation completion.

Examples:

```text
repository preparation: READY and agent-owned
external seller/account action: BLOCKED on external_authority
private evaluator execution: BLOCKED on manual/private authority
paid strong-model experiment: BLOCKED until spend authority
```

If the external action is deferred, downstream work that truly requires its result remains blocked. Marking the external ticket `DEFERRED` does not mean `SATISFIED`.

## 12. Supersession

`supersedes` must not be added to the blocking DAG. Otherwise a replacement can create meaningless cycles such as old work depending on its replacement while the replacement "depends" on the old work.

Validators should keep replacement edges in a separate relation graph and check:

- replacement target exists;
- no Work ID is silently superseded by multiple incompatible canonical replacements;
- supersession does not rewrite historical evidence;
- active ownership is released through the audited state transition.

## 13. Legacy dependency text

Existing Work Contracts may contain prose such as:

```text
Dependencies: #151 merged; #196 follow-on, not blocker
```

A synchronizer may extract references for discovery, but it must not infer that every extracted reference is a hard dependency. Until typed metadata is present, implementations should preserve conservative classifications already explicitly curated and surface ambiguous edges for reconciliation.

In particular:

- phrase occurrence is not sufficient evidence of `hard_merge`;
- an issue number mentioned as context is not necessarily a dependency;
- "merged", "optional", "follow-on", "not blocker", and similar prose must not be discarded when migrating to typed metadata;
- automated migration should fail closed on ambiguous blocking semantics rather than inventing a stronger or weaker edge.

## 14. State interaction

Dependency state and coordination state are related but distinct.

- An unowned issue may be BLOCKED because a hard edge is unsatisfied.
- An owner-held issue may transition to BLOCKED because a newly discovered blocker appears; it retains ownership until release.
- Satisfaction of the dependency does not itself grant a claim. It makes the item *eligible* for READY after all other policy gates are checked.
- A stale heartbeat never satisfies or removes a dependency.
- A manual `work:ready` label does not satisfy a dependency predicate.
- DONE/SUPERSEDED provider labels are not enough for `hard_merge` or `hard_evidence` unless their designated authorities independently satisfy the edge.

## 15. Notification semantics for ROADMAP-NOTIFY-001

An unblocking notifier should emit a readiness notification only on a transition from at least one unsatisfied claim-blocking edge to zero such edges, after recomputing all claim-blocking predicates.

It should report:

- Work ID becoming dependency-ready;
- dependency edge(s) that changed;
- kind of each changed edge;
- authoritative event that satisfied it;
- remaining non-dependency blockers, if known.

It must not notify "READY" merely because a provider PR became green when the edge is `hard_merge`, or because implementation merged when the edge is `hard_evidence`/`external_authority`.

Repeated observation of the same authoritative state should be idempotent.

## 16. Validation requirements

ROADMAP-004 and later synchronizers should fail closed on:

- unknown dependency kind;
- unresolved internal Work ID/alias;
- duplicate contradictory edges to the same target/stage;
- blocking dependency cycles;
- `soft_preferred` configured as a claim blocker without explicit stricter policy;
- `supersedes` inserted into the execution-blocking DAG;
- `external_authority` marked satisfied solely from repository implementation state;
- `hard_evidence` satisfied solely from CI/merge when the evidence contract requires another authority;
- `hard_merge` satisfied by an unmerged provider PR;
- convergence work starting before its declared convergence prerequisites;
- an edge whose required authority is missing or ambiguous.

## 17. Issue-author guidance

Choose the weakest dependency kind that is actually correct, not the one that maximizes or minimizes parallelism.

Use `hard_merge` only when consumer semantics truly require merged provider code.

Use `hard_evidence` when the required proposition is evidence, not implementation.

Use `soft_preferred` when work remains valid with a recorded reduced scope.

Use `convergence_after` to keep feature lanes parallel while serializing shared integration deliberately.

Use `external_authority` when autonomous repository execution cannot legitimately satisfy the gate.

Use `supersedes` for replacement history, not execution order.

When uncertain whether a dependency is hard, the issue author should state the required proposition and falsifier explicitly before classifying it.

## 18. Worked examples

### Feature requires a merged provider API

```text
consumer: HARNESS-002
provider: HARNESS-001
kind: hard_merge
blocks_at: claim
```

HARNESS-002 does not claim until HARNESS-001's required interface is merged into its canonical base, unless a specifically approved stack exists.

### Audit is useful but not required

```text
consumer: TRACE-004
provider: TRACE-001
kind: soft_preferred
blocks_at: none
scope_note: proceed only with currently known metadata producers; reconcile audit gaps later
```

TRACE-004 may proceed if its own acceptance criteria remain achievable.

### Shared integration after feature lanes

```text
consumer: CONV-001
providers: [PKG-001, ATTEST-001, CAT-001, PORT-004]
kind: convergence_after
blocks_at: convergence
```

Provider feature work remains parallel; CONV-001 alone edits its designated shared surfaces once provider prerequisites are satisfied.

### Private evidence gate

```text
consumer: FRONTIER-GOLD-001
provider: QUAL-001
kind: hard_evidence
required outcome: PASS under named qualification contract
```

A merged QUAL-001 implementation does not satisfy this edge. The qualification evidence must exist under its own authority.

### External account action

```text
consumer: commercial listing execution
provider: external seller/account approval
kind: external_authority
```

Repository preparation may be a separate READY task. The actual external action stays BLOCKED until the designated authority record is satisfied.

## 19. Non-authority statement

Dependency metadata answers **when work may proceed relative to other prerequisites**. It does not answer whether the resulting implementation is correct, qualified, safe to publish, commercially approved, or authorized to use private/external/paid resources. Those decisions remain with their canonical authorities.
