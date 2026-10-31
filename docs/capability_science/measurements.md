# Capability measurement evidence records

These CAP-001 records structure **supplied evidence**, not training execution or
scientific qualification. They add no trainer, model runner, runtime, replay
engine, or private-data reader. Their full-content identities establish payload
consistency, not that a model executed, that a split was held out prospectively,
or that an intervention caused a change.

## Fixed populations and ordered acquisition

`EvaluationConditions` binds environment and verifier identities/revisions, the
metric definition digest, distribution, structure, interface, and evidence.
Metrics are normalized per-case `criterion_score` or binary `success_fraction`;
task counts and training loss are not capability metrics. Condition, model and
trainer identity/revision fields reject common unpinned placeholders such as
`latest`, `main`, and `unknown`; unknown conditions cannot masquerade as a known
IID comparison.

`EvaluationPopulation` binds one full `CapabilitySpec` and a nonempty population
of unique member IDs **and source-content digests**. It explicitly declares TRAIN
or HELD_OUT. These are declarations backed by references, not split attestations
or a near-duplicate detector. Labels and digest inequality do not prove absence
of contamination.

`EvaluationPoint` binds the exact population, model/checkpoint, sequence index,
optional timezone-aware observation time, execution-provenance category, and
evidence. Every member must appear exactly once, with the matching source digest.
A missing measurement is a retained `CaseOutcome(value=None)` with a reason,
never an omitted failure. Known outcomes require content-bound evidence.
`recorded_mean` is absent if any outcome is unknown: no success filtering,
intersection-only comparison, imputation, or silent denominator change occurs.

`TrainingIntervention` records an **external** trainer and revision, configuration
and bundle digests, exact training population, before/after point identities,
optional start/end times, provenance and evidence. It launches nothing.

`AcquisitionCurve(points=..., interventions=...)` requires consecutive sequence
indices, the same full evaluation population and measurement semantics, and an
exactly bound intervention between every pair. Model identity stays fixed while
checkpoint revisions may change. Known times must satisfy before < start ≤ end
< after; known endpoints remain checked even if intermediate times are absent.
No time is invented. TRAIN curves are permitted but describe only those training
cases; they are not evidence of held-out performance or generalization. HELD_OUT
curves reject exact training overlap by either member ID or source digest.

```python
curve = AcquisitionCurve(points=(before, after), interventions=(external_step,))
deltas = curve.recorded_metric_deltas  # signed deltas, or None for incomplete pairs
assert curve.capability_gain is None
assert curve.model_execution_attestation == "UNKNOWN"
assert curve.chronology_attestation == "UNKNOWN"
```

All payloads are reparsed before derived arithmetic. Positive, zero and negative
changes remain equally representable. `DECLARED` or `CONSTRUCTED` provenance is
not an attestation. The schema does not accept a caller-supplied PASS attestation
or scalar `capability_gain`. In particular, #449 paired-outcome evidence retains
its unknown execution/chronology and absent capability gain when represented in
these records. There is no automatic import that upgrades those claims.

## Retention and regression

`RetentionLink` binds an earlier `acquired` evaluation to a later evaluation of
the same exact population, model and metric, together with intervening-action
references. Its signed `recorded_metric_delta` and `recorded_relation` preserve
regression and missingness. The field name `acquired` names the earlier anchor,
**not** a finding that a capability was acquired: 0 → 0 is RETAINED recorded
performance, not successful learning. It does not calculate significance,
causal forgetting, uncertainty intervals, or a qualification result.

## Compositional tests

`CompositionTest` declares the target and at least two distinct required
component specs. Each component needs its own evaluation; the composed target
needs a **separate** evaluation. All use the same model checkpoint and verifier/
metric semantics. Target-result references must be distinct by both identity and
digest from component-result references, preventing copied component scores from
masquerading as the composed result.

The explicit criterion digest and minimum score define a bounded recorded test.
`recorded_result` is PASS only when every component and composed evaluation has a
complete recorded mean meeting that criterion. A failed composed result remains
FAIL despite perfect components; missing data remains UNKNOWN unless another
complete evaluation already fails. This PASS describes the supplied criterion,
**not** independently verified execution, capability coverage, prerequisite
causality, or scientific qualification. `qualification` remains UNKNOWN. Raw
sample counts never establish compositional coverage.

## Transfer scope is not transfer qualification

`TransferEvidence` requires a recorded source TRAIN evaluation, a fixed held-out
target curve, explicit protocol references, matching capability and measurement
semantics, and source binding to every intervention's exact training population.
Training/target overlap by ID or source digest fails closed. A training-set score
cannot substitute for the target's before/after held-out measurements.

`classifications` describes changes in the **declared, evidence-referenced**
source/target conditions:

- `IID`: no declared environment/distribution/structure, interface, or model-ID change;
- `STRUCTURAL_OOD`: environment identity/revision, distribution, or structure changes;
- `INTERFACE_TOOL`: interface changes;
- `CROSS_MODEL`: source and target model IDs differ.

Multiple axes remain visible together. Changed verifier/metric semantics are
rejected rather than silently called IID. The classification basis is explicitly
`DECLARED_SOURCE_TARGET_CONDITIONS`; the record does not independently verify
those declarations or infer broad transfer from condition names. The signed
target `recorded_metric_delta` retains negative transfer candidates and UNKNOWN
results; `capability_gain` remains absent and `qualification` remains UNKNOWN.

## Privacy, tests and limits

Records default to INTERNAL. `public_payload()` and `buyer_safe_payload()` use
the shared conservative whole-record projection. A single restricted nested
capability, member, outcome, reference, or private metadata bucket withholds the
entire result, including private-derived hashes, source IDs, and reasons. A
public declaration cannot declassify its private evidence. Raw model dumps are
not an export permission.

`tests/capability_science/test_measurements.py` uses only explicitly CONSTRUCTED
records. It exercises positive, zero, negative, missing, forged, copied,
overlapping, reordered and privacy cases. Passing those tests verifies software
contracts, not empirical capability acquisition, retention, transfer, scientific
qualification, training usefulness, or Frontier performance. Replication,
uncertainty, independent execution/chronology, authentic source adjudication and
contamination assessment remain tasks for the separately authorized empirical
program.
