# Roadmap completion rules by work class

ROADMAP-DONE-001 defines when an agent-work item may transition to `DONE`.
`DONE` is a coordination state: it means the work contract's completion condition has
been satisfied and recorded. It does **not** imply scientific validity, Frontier
qualification, training value, commercial readiness, release authority, or a
successful product outcome unless the work contract explicitly makes one of those
an evidence prerequisite.

## Principles

1. Completion is evaluated from the work item's declared `work_class` and the
   evidence authority for that class.
2. A merged pull request is sufficient only for ordinary implementation work whose
   completion rule explicitly permits merge completion.
3. Code, CI, and review cannot satisfy manual, private, paid, legal, commercial,
   scientific, Frontier, or training evidence by implication.
4. Missing required evidence is `UNKNOWN`/incomplete and fails closed.
5. Negative experimental results may still complete an experiment when the
   preregistered experiment was executed correctly and the required evidence was
   retained.
6. `DONE` records completion of the work item, not whether its hypothesis or desired
   external outcome was positive.
7. Completion evidence must bind the exact relevant PR head, merge commit, report,
   run, artifact, decision, or external/manual evidence reference required by the
   work contract.

## Canonical work classes

### `implementation`

Use for additive or corrective repository implementation where the work contract
permits code-merge completion.

Required before `DONE`:

- the linked implementation PR is merged;
- the merged candidate is the exact handed-off/reviewed head required by repository
  policy;
- required exact-head CI, security, quality, and scoped validation gates have passed;
- required independent review is complete;
- ownership and dependency requirements remain satisfied at integration time.

A green PR that remains open is `REVIEW`, not `DONE`.

### `review_migration`

Use for review, reconciliation, migration, supersession, or disposition work whose
purpose is to resolve another lane rather than to create a standalone feature.

Required before `DONE`:

- the target PR/issue/artifact has reached the disposition named by the work
  contract, such as merged, rejected, closed, migrated, or superseded;
- the disposition and exact target identity are recorded;
- any required follow-up/interface-gap work is linked rather than silently omitted.

A review that finds a blocker is not complete merely because the review comment was
posted when the work contract also requires correction and re-review.

### `experiment`

Use for preregistered experiments, benchmarks, calibration studies, and hypothesis
checks.

Required before `DONE`:

- the preregistered protocol was executed or terminated under its declared stopping
  rule;
- required seeds/replicates and controls were completed or the recorded protocol
  explicitly permits early termination;
- raw/derived evidence required by policy is retained with exact run identities;
- failures, null results, and negative results are preserved;
- deviations and missing evidence are disclosed.

A negative hypothesis result may still be `DONE`. `DONE` means the experiment was
completed correctly, not that the hypothesis passed.

### `scientific_qualification`

Use when the work item itself adjudicates scientific qualification or maturity.

Required before `DONE`:

- every mandatory scientific evidence gate in the work contract/policy is resolved
  by its designated authority;
- the qualification report binds the exact environment/task/verifier/evidence
  identities under evaluation;
- `FAIL` or `UNKNOWN` gates remain explicit and are not overwritten by aggregate
  success;
- the final qualification disposition is recorded.

A qualification ticket can be `DONE` with a final `FAIL` or `NOT_QUALIFIED` result
when the adjudication itself is complete. Merged qualification code alone is not
completion evidence for this class.

### `frontier_qualification`

Use when the work item evaluates Frontier usefulness or capability separation.

Required before `DONE`:

- the applicable Frontier evidence contract has been executed;
- required strong-agent/model, non-saturation, separation, diversity, harness, and
  control evidence is resolved as required by policy;
- exact model/harness/runtime/environment/verifier/panel identities are bound;
- the final Frontier disposition is recorded, including `NOT_YET_QUALIFIED`,
  `FAIL`, or `UNKNOWN` when appropriate.

Code merge or weak-model evidence cannot complete a Frontier qualification item.

### `training_qualification`

Use when the work item adjudicates training usefulness or a training maturity
transition.

Required before `DONE`:

- the canonical training-value protocol required by the work contract is complete;
- train/eval identities, model/training method, verifier version, seeds, held-out
  panels, exploit checks, and regression evidence are bound as required;
- held-out capability evidence rather than training loss determines the final
  disposition;
- negative/no-transfer results remain first-class evidence.

Implementation or CI success cannot complete this class.

### `external_manual`

Use when completion depends on an account, legal/commercial decision, private/manual
evidence, paid-compute authorization, owner decision, or another non-agent authority.

Required before `DONE`:

- the exact external/manual condition named by the work contract has been completed
  by an authorized actor;
- a non-secret evidence reference or explicit owner decision is recorded;
- no secret, credential, private benchmark row, protected customer data, or similar
  sensitive material is copied into roadmap metadata.

Repository preparation may be completed in a separate implementation subtask, but
it does not complete the external/manual parent item.

### `convergence_release`

Use for serialized shared-surface integration, release convergence, packaging, or
other work where provider lanes must already be integrated.

Required before `DONE`:

- all hard provider/convergence prerequisites are satisfied;
- the candidate is synchronized to the required current base;
- all full integration/release gates required by the work contract pass on the exact
  candidate;
- shared/root ownership is held by the designated convergence lane;
- required merge/release/publish authority has been exercised separately and
  explicitly;
- the final integrated/released identity is recorded.

A release candidate can remain `REVIEW` or `BLOCKED` despite green CI when authority
or external evidence is still pending.

## Machine-readable completion metadata

Roadmap tooling should be able to represent completion without inferring semantics
from issue prose. A work item should expose equivalent metadata to:

```yaml
work_class: implementation
completion:
  rule: merged_exact_head
  required_evidence:
    - exact_head_checks
    - independent_review
    - merged_pr
  authority: repository_merge
```

Other classes may name evidence authorities such as `experiment_report`,
`scientific_policy`, `frontier_policy`, `training_policy`, `external_authority`, or
`release_authority`. The schema may evolve, but automation must not silently map an
unknown class/rule to ordinary implementation completion.

## `/done` evaluation contract

A `/done` request must fail closed unless all of the following are true:

1. the requester is authorized for the current coordination state;
2. the work item's `work_class` and completion rule are known;
3. the rule's required evidence is present and exact-identity-bound;
4. all required dependency/ownership constraints remain satisfied;
5. the linked PR/run/report/evidence object has the state required by the rule.

For `implementation`, a merged exact handed-off PR may satisfy the rule when the
work contract permits it. For all other classes, `/done` must consult the designated
evidence authority rather than treating a merged PR as universal proof.

Until claim automation consumes structured completion metadata directly, maintainers
and agents must apply this policy manually and reject ambiguous completion.

## Examples

- A verifier implementation PR merges with exact-head review: its
  `implementation` ticket may become `DONE`; a separate scientific qualification
  ticket stays open.
- A preregistered experiment produces no improvement but all required runs and
  evidence are complete: the `experiment` ticket becomes `DONE` with a negative
  result.
- A Frontier evaluation lacks strong-model evidence: it remains incomplete if that
  evidence is required to adjudicate the work item; implementation CI cannot close
  it.
- A seller onboarding preparation PR merges while the seller account is still
  pending: the preparation subtask may be `DONE`, but the `external_manual` item is
  not.
- A scientific qualification completes with a defensible `FAIL`: the qualification
  work item may be `DONE` because adjudication is complete, while the environment's
  scientific state remains failed/not-qualified.

## Falsifiers

This policy is violated if any of the following occurs:

- every merged PR is treated as equivalent completion;
- a failed hypothesis keeps a correctly completed experiment permanently open;
- CI or code merge silently satisfies scientific, Frontier, training, manual,
  commercial, or release evidence;
- missing evidence is treated as PASS;
- `DONE` is reported as a universal statement of product success;
- sensitive external/manual evidence is copied into roadmap metadata to prove
  completion.
