# CURR-001: active curriculum from recorded frontiers

## Outcome and boundaries

`investigation_world.curriculum` builds a bounded, reproducible curriculum from
actual retained public TRAIN experiences, measured task outcomes supplied as
CAP-001 records, a declared prerequisite graph, and a versioned policy. It records
why each candidate was scheduled, fixes stage order, and makes conditional
advancement decisions from held-out **development-validation** acquisition records.

This implements a controller, not a trainer, task generator, model runner,
execution attestor, capability qualifier, or release. A supplied outcome is not
independently verified model execution. Constructed fixtures can satisfy the
controller's recorded criterion and exercise advancement; they establish neither
real learning nor scientific/Frontier qualification. All qualification and model
execution attestations remain UNKNOWN. No paid compute or protected panel is used.

Only curriculum source/tests/docs are owned. Existing Foundry, CAP-001, selection,
derivation, canonical runtime/verifier and trainer providers remain unchanged.

## Reused providers and trust boundaries

`build_curriculum` freshly invokes SEL-001 `select_experiences` against the actual
retained source and gap-receipt inputs, preserving its TRAIN/privacy checks,
admission, deduplication, quota decisions and resource accounting. The supported
executable source is still the pinned public synthetic financial TRAIN recorder;
this is not a new multi-domain admission provider. Hard-negative analysis
candidates are not accepted as successful curriculum training examples.

The selected sources pass through LEARN-001 `compile_learning_assets` with its
versioned `next_state` transform. Accepted derivatives retain their exact source,
trajectory, verifier, native receipt, capability and material lineage. A rejected
derivative is not scheduled. Both full private provider reports remain in the
plan, so rejection, quota and cost information is not erased by the smaller
curriculum. Derivatives remain unqualified candidates: their `trainer_payload()`
still refuses export. No new grammar, answer or action is generated or executed.

The plan uses CAP-001 `PrerequisiteGraph`, `EvaluationPoint`, exact populations and
`AcquisitionCurve`; it reuses Foundry `frontier_priority` rather than inventing a
second difficulty estimator. Content hashes establish consistency, not authentic
measurement or prospective panel registration.

Consumers of saved plans must use `validate_curriculum` with **externally expected**
policy, graph, observations, panels, learner identity and retained sources. It
rebuilds selection and derivation against current artifacts. Parsing a self-hashed
envelope alone does not authorize execution or prove freshness. The underscored
engine seam used by constructed tests is not a source-admission API.

## Frontier observations and fallback

`FrontierObservation` accepts only binary-success TRAIN evaluations. Each
capability keeps one exact population and measurement semantics across attempts;
all points must bind the plan's exact learner/checkpoint. Unknown outcomes remain
unknown, not successes or dropped failures. Duplicate sequence slots and copied
outcome-evidence references cannot manufacture attempts. Task matching requires
the full capability specification, task ID and source-content digest.

The default success-rate target band is 0.10–0.70, representing challenging tasks
near/slightly above the supplied learner frontier, **not static easy/medium/hard
metadata**. The policy versions that band, minimum attempts, per-stage budget,
seed, selection settings and held-out advancement thresholds. Known, sufficiently
observed tasks in the band rank by the existing Foundry priority. Ties are seeded
SHA256 order. Unobserved, incomplete, sparsely observed, above-band and below-band
cases have separate explicit fallback reasons; bounded seeded selection remains
possible without fabricating a mastery estimate. A measured ceiling/floor is only
the supplied recorded success rate. Neither selector quota saturation nor a
derivation quota means empirical mastery, learning saturation or capability
coverage. Distinct selected examples of one task do not become distinct coverage:
the controller chooses at most one task identity/source digest per stage.

`random_control` uses the **same freshly validated selected candidate pool**,
fixed panels, prerequisite order and per-stage caps, but ranks by seeded hashes
rather than frontier priority. Keep the same policy except mode/seed and retain
the provider report identities to compare controls. Equal counts are not equal
compute cost or evidence of causal training benefit. Full selection accounting is
retained; missing compute, wall time and financial costs remain unknown.

## Panels, stage order and advancement

`FixedPanels` binds separate validation and final-test populations for every graph
capability. Both are HELD_OUT and disjoint by member ID **and source digest**.
These commitments are excluded from selection, derivation, TRAIN observations and
every stage intervention. They are declarations, not an independent split audit
or a near-duplicate detector. Sealed nested inputs reject; private outputs remain
private even if nested source references are public.

Development validation is allowed to guide advancement and therefore is **not an
untouched final test**. The API accepts no final-test scores for ranking or
advancement. Relabeling a panel TRAIN does not evade matching member/digest
exclusions. Actual untouched final evaluation, contamination assessment and
scientific claims require their separately authorized protocol.

Stages are deterministically topologically ordered over declared non-refuted
prerequisites. Hypothesized or reported edges are conservative scheduling
constraints, not causal discoveries. Each stage pins its capability, validation
population, selected task commitments, reasons and policy ID. Recomputed
scheduling rejects reordering even when an altered plan is rehashed. A changed
observation/policy creates a new plan identity, never silently rewrites history.

`advance_stage(plan, history, acquisition=..., prerequisite_evaluations=...)`
appends one immutable event for the next unfinished stage. It requires:

1. the exact fixed development-validation population and learner;
2. the current checkpoint as the before evaluation, and one exactly bound
   external intervention on the stage's selected TRAIN task population;
3. no backwards or rewritten within-panel evaluation sequence;
4. current-checkpoint validation for every declared prerequisite, with complete
   outcomes meeting the policy threshold;
5. complete before/after validation outcomes, the minimum after score, and the
   minimum recorded improvement (defaults: 0.80 and 0.05).

Missing acquisition or prerequisite evidence, incomplete scores, regression, flat
high performance and insufficient improvement hold the stage. Training reward is
not an input and cannot advance it. A failed prerequisite blocks the dependent
stage even when the dependent's own score improves. A valid unsuccessful
intervention updates the recorded checkpoint for the next attempt, not completion.

Before training, `stage_readiness(plan, history, prerequisite_evaluations=...)`
releases references for **only** the next unfinished stage. It can reuse exact
current-checkpoint prerequisite observations from validated history, or inspect
newer supplied validation. Missing/failed/unknown prerequisites withhold all task
references. Readiness is a conditional snapshot, not an external trainer lock:
callers must retain the newest evidence and must not ignore a newer observation.
Both readiness and advancement reject rewound/rewritten prerequisite evaluations,
known backwards timestamps and sealed evidence before projecting derived IDs.

`ADVANCE_RECORDED_CRITERION` means exactly that these supplied records satisfy the
controller rule; it is not capability acquisition or training qualification. The
external bundle/trainer digests remain external declarations, not independently
verified training bytes or execution. `validate_history` replays each decision
against the pinned plan and verifies sequence, previous-event linkage, evidence
and result. It rejects forged decisions, skipped/reordered stages and another
plan's history. Tuple/frozen content-bound records support append-only handling;
they are not an external tamper-proof storage service or proof of wall-clock
prospective commitment.

## Use and verification

```python
from investigation_world.curriculum import (
    CurriculumHistory, build_curriculum, validate_curriculum, advance_stage,
)

expected = dict(
    graph=declared_graph, panels=fixed_panels, observation=train_observations,
    model_id=pinned_model, model_revision=pinned_checkpoint,
    policy=curriculum_policy, gap_sources=retained_train_gap_sources,
)
plan = build_curriculum(actual_recorded_train_sources, **expected)
validate_curriculum(plan, actual_recorded_train_sources, **expected)
history = CurriculumHistory(plan_id=plan.record_id)
history = advance_stage(plan, history)  # HOLD: missing held-out acquisition evidence
```

`model_dump()` is evaluator-private serialization, not a public export API.
`public_payload()` and `buyer_safe_payload()` withhold the entire plan/history,
including counts, source/panel IDs, private-derived hashes, reasons and materials.

Tests use actual supported public native executions for provider integration and
explicitly constructed multi-capability records for controller logic. They cover
positive/negative/unknown advancement, prerequisite failure, measured band vs
fallback, seeded controls, stale/tampered evidence, exact panel/train disjointness,
history/order forgery, privacy and source-input bounds. No test result is reported
as learned model performance.

```sh
python -m pytest tests/curriculum
python -m ruff check src/investigation_world/curriculum tests/curriculum
python -m mypy src/investigation_world/curriculum --follow-imports=silent --ignore-missing-imports
python tools/quality_baseline.py check
python -m pytest tests
```

Also build a wheel and run the copied curriculum suite outside the checkout with
only the installed distribution on the import path. Exact-head CI, Security,
independent review and formal approval remain separate integration gates. None of
these checks grants merge, deployment, release, model-training or qualification
authority.
