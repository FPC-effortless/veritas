# TRAIN-001: content-bound training qualification evidence

This is a **bounded offline policy engine**, not a trainer, model runner, execution
attestor, or second environment-maturity framework. It evaluates supplied records
and supplies the existing maturity gates. It never calls a provider, accesses a
protected panel, changes canonical rewards, or promotes an environment.

## Outcome and falsifiers

Owned surfaces are `src/investigation_world/training_qualification/**`,
`tests/training_qualification/**`, and this directory. Existing training experiments,
Frontier, trajectory implementation, Experience Foundry and shared exports are
read-only dependencies. Implementation verification is separate from scientific,
Frontier, training, commercial, and release qualification.

Falsifiers include loss-only evidence; training memorization without held-out gain;
a successful seed hiding a failed/missing seed; substituted/dropped population
members; mismatched model, checkpoint, method, configuration, environment, verifier,
or source identity; reused exploit replay; known exploit success; omitted guardrails;
and calling a within-family distribution shift broad structural transfer.

The minimal reuse path is the existing `ScienceRecord` content binding/private
projection, CAP-001 fixed populations and acquisition records, LEARN-003 bundle and
fresh paired replay, `monitor_exploits`, and `MaturityGateEvidence`. No new runtime,
trainer, dependency, or automatic promotion is introduced.

## API and required evidence

`assess_training(TrainingEvidence(...), policy=TrainingPolicy(...))` returns an
immutable, content-addressed `TrainingReport`. Its full evidence and policy are
included, not just favorable summaries or unbound filenames. Every consumer reparses
nested provider models and recomputes report outcomes; resetting an ID cannot make
forged gate results valid.

A study binds:

- exact target capability contract, environment and verifier revisions/content digests;
- the complete training bundle and exact source ID → digest association;
- exact expected seeds, distinct run manifests, full configuration content hash,
  common base model/checkpoint and training method/revision;
- per-seed TRAIN and HELD_OUT acquisition curves, one before/after intervention each;
- learnability control on the exact held-out population;
- structural-transfer and unrelated-capability regression panels;
- fixed exploit corpus and distinct, checkpoint-bound before/after replay evidence.

Expected seeds are independent of observed seeds. Missing replicates remain missing,
not a reduced denominator. Population source identity, capability, metric definition,
environment and verifier semantics cannot drift across before/after or seeds. Post-training
checkpoints may differ by seed, but all panels of one replicate use the same checkpoint.
Known intervention timestamps must agree; missing timestamps never attest chronology.

The bundle lineage must cover the entire TRAIN population. TRAIN/evaluation and
separate evaluation panels must be source-disjoint. A digest permutation cannot
rename one source as another. Every `EvaluationPoint` covers its exact population
once, including zero scores, failures and unscored rows; no successful-case filtering
or implicit intersection occurs. Summaries report expected, known, unknown and
zero-score counts. A zero-score count is **not** a general task-failure classifier
for a non-binary criterion metric. Complete source outcomes remain in the report.

Bounds: at most 32 replicates, 512 members per panel, eight transfer panels and eight
unrelated-capability panels per replicate, and 512 observations per exploit phase.
Malformed/contradictory evidence is rejected. Absent evidence gives `UNKNOWN`.

## Gates and semantics

- **Baseline and train-before/after:** complete scored baseline and comparison records.
- **Learnability:** distinct declared model/checkpoint control scores meet the pinned policy threshold on the
  same held-out population, without reusing primary evaluation evidence. This is a
  declared control, not an authenticated expert claim.
- **Held-out improvement:** every observed seed meets the minimum gain; means never
  omit unknown rows or missing seeds.
- **Replication:** all expected seeds are present, at least the policy minimum (default
  three), each improves, and the gain range meets policy. The range and per-seed deltas
  are descriptive variability, **not** a confidence interval or causal estimate.
- **Overfit screen:** both the train-minus-heldout post-score gap and gain gap meet
  the maximum. Exact source disjointness is also enforced. These are useful screens,
  **not** a complete memorization or near-duplicate detector.
- **Memorization/near-duplicate probes:** explicitly `UNKNOWN`; no independently
  validated behavioral-probe/contamination provider is available to this adapter.
  A small score gap does not fill this evidence gap.
- **OOD:** declared structure identity changes, with non-regression under the policy.
  Merely renaming the distribution with the same structure yields
  `WITHIN_FAMILY_DISTRIBUTION_SHIFT`, not structural transfer PASS. Neither establishes
  broad external generalization. All panels retain declared-condition provenance.
- **Unrelated guardrails:** every independently declared required capability panel is
  present and does not regress beyond policy. An empty required set is `UNKNOWN`.
- **Exploits:** rerun `monitor_exploits` before and after using the fixed corpus and
  current policy. Missing or empty applicable coverage is `UNKNOWN`; succeeded
  exploits, canonical-score mismatch and severe unresolved findings are failures.
  Phase observations/evidence cannot be reused; known timing must bracket training.
- **Execution/chronology:** explicitly `UNKNOWN`. Caller declarations, hashes, byte
  receipts and constructed fixtures are not an independently validated execution
  or prospective-panel-attestation provider.

`FAIL` takes precedence over `UNKNOWN` when the supplied records expose a known
policy violation. `PASS` in a numerical gate means only that the supplied records
meet that conditional check. The current provider set cannot produce aggregate
`PASS` or `training_validated=True`; `capability_gain` remains `None`. A future real
PASS path requires a separately reviewed provider that validates the missing
execution/chronology and memorization/contamination evidence. There is deliberately
no caller-supplied `trusted=True`, PASS flag, callback, or attestor name bypass.

## Fresh replay adapter

`reverified_acquisition_curve` consumes the existing LEARN-003 `FrozenPanel`, complete
before/after `PanelAttempt` collections, exact manifest/bundle/receipt and an existing
`AuthorizedVerifierRegistry`. It calls `compare_frozen_panel`, which clears prior
reverification history and replays every attempt afresh. Original scores and
caller-inserted history cannot substitute for fresh replay. Missing replay evidence
remains an explicit unscored outcome. No timestamp is invented.

It additionally binds the supplied TRAIN population to the exact bundle lineage,
requires one exact environment/verifier identity per panel and canonical criterion
reward semantics, and converts complete paired rows to existing CAP-001 records.
The caller's capability/metric declaration remains a declaration. The adapter
preserves #449's unknown model execution, chronology, and capability gain. It does
not convert receipt byte integrity or offline scoring into proof that training ran.

## Environment Maturity integration and privacy

`training_maturity_evidence(report, qualification_policy_version=..., observed_at=...)`
produces independent content-bound evidence for:

1. `held_out_training_improvement`;
2. `multi_seed_stability`;
3. `reward_exploitation_regression`.

Each retains full-population/provenance and execution uncertainty; the held-out gate
also retains the missing memorization provider. One failed family does not overwrite
an unrelated family's evidence. The adapter does **not** call
`assess_environment_maturity` or change `DEFAULT_MATURITY_POLICY`. Existing ordering
still requires all lower stages, including `FRONTIER_QUALIFIED`, before
`TRAINING_VALIDATED`; training usefulness evidence is independently evaluated.

All evidence, reports, summaries, and adapter outputs are **evaluator-private**.
`public_payload()` and `buyer_safe_payload()` withhold the whole record, including
IDs, source hashes, labels, free text, model identities, and nested private material.
Raw `model_dump()` is an operator-private serialization, not a publication API.
`MaturityGateEvidence` has no visibility mechanism: treat this adapter's return values
as evaluator-private too; never publish its private report identity or provenance
without a separately authorized projection. No public qualification badge is emitted.

## Verification

Tests are explicitly `CONSTRUCTED`. They include conditional positive checks and
negative/missing/forged cases, plus the existing public deterministic runtime fixture
for fresh replay. No real training result or qualification is claimed by these tests.

```sh
python -m pytest tests/training_qualification -q
ruff check src/investigation_world/training_qualification tests/training_qualification
mypy --follow-imports=silent src/investigation_world/training_qualification
python -m pytest tests -q
python tools/quality_baseline.py check
```

The adapter test reuses `tests/experience_foundry/test_paired_evaluation.py`'s public
fixture; installed-wheel verification copies both test directories (and supporting
provider tests), never package source, then runs outside the checkout with installed
package import paths confirmed.
