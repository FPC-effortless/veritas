# Continual-learning experiment protocol (CL-001)

This is an **offline, evaluator-private protocol**, not a trainer, evaluation
runner, execution attestor, or evidence that a model continually learns. It
consumes canonical `ExperienceSequence`, CAP-001 `AcquisitionCurve` /
`EvaluationPopulation` / `RetentionLink`, exact Experience Foundry bundles and
selection reports, and optional canonical training-qualification reports.
No backend is launched and no experience/environment maturity is changed.

## Outcome and falsifiers

A caller can commit an ordered experiment, retain complete multi-step and
multi-seed outcomes, calculate descriptive retention/transfer, and append report
snapshots without silently replacing recorded history. Tests reject omitted
steps/panels, panel drift, substituted checkpoints or runs, repeated observation
evidence, replay/test overlap, lost replay lineage, altered reports and broken
history commitments. Falling training loss is not an input metric.

Only these lanes belong to this implementation: `src/investigation_world/continual_learning`,
`tests/continual_learning`, and `docs/continual_learning`. No trainer, canonical
runtime/verifier/trajectory, Woyengi memory, Frontier, shared export or release
contract is modified. Implementation verification is separate from scientific,
training, Frontier and commercial/release qualification.

## Frozen plan and external steps

`ContinualPlan` binds the full canonical `ExperienceSequence`, at least two
ordered `ScheduledStep` records, a pinned model and baseline revision, expected
seeds, and fixed held-out target and unrelated guardrail populations. New
experience IDs, in order, must equal the sequence exactly. Replays are separately
identified and must refer only to previously introduced experiences. The
`reference_step` for a target is its **first scheduled acquisition step**, not a
post-hoc best score or an assertion that acquisition succeeded. Guardrails refer
to the initial checkpoint and cannot be trained target capabilities.

Each step retains an exact `TrainingBundle` and TRAIN `EvaluationPopulation`.
The existing Foundry membership validator checks every bundle example's source
identity/digest and TRAIN split; population membership must match that mapping.
The ordered experience partition must cover the bundle's complete lineage.
Replayed lineage must be identical to the earlier record, not a new source
substituted under an old experience ID. Bundle source/fixture digests and
source/task/experience IDs are checked against all evaluation panels.

Replay requires the complete `SelectionReport`, with exactly the selected
experience IDs and the original **fixture** hashes. The selection provider's
`source_fixture_digest` binds Foundry's `fixture_digest`, **not** its separately
hashed post-execution `source_digest`. Native artifact verification can make
these hashes different. Both retain their meanings. The selection policy must
exclude every committed evaluation source. This validates supplied lineage and
content consistency; it does not rerun the selector, authenticate arbitrary
caller-created reports, or upgrade candidate assets to training qualification.

`ExternalLearner` pins backend ID/revision, configuration digest and metadata
evidence. Each replicate supplies one `StepRun` per scheduled step, preserving
the existing `TrainingRunManifest` and exact before/after checkpoint revisions.
`run.declaration_reference` hashes the entire manifest and checkpoint pair.
Each corresponding CAP `TrainingIntervention` must include that exact reference,
plus any other intervention evidence. All capability panels at that step must
share the same full intervention declaration, timings and references. Run IDs
and step-observation references cannot be reused across steps or seeds. This is
a **declaration binding**, not a receipt proving execution.

A backend can be changed by constructing a new pinned plan and manifests; none
of the measurement formulas or matrix semantics depend on backend implementation.

## Complete capability × step × replicate matrix

Each present `Replicate` has one CAP acquisition curve for every fixed panel and
exactly `N + 1` evaluation points, numbered `0..N`, for `N` interventions.
Population identity fixes members, capability contract, metric semantics,
environment and verifier revisions. Every panel at a given step binds the same
model checkpoint; all replicates start from the declared baseline. Failed and
unavailable case outcomes remain in the full population. An absent replicate is
explicitly missing against `expected_seeds`; it never disappears from a required
denominator or yields a full-population PASS.

Scored **case observation** identities and digests must be distinct across
outcomes, matrix cells, controls and replicates. Panel/protocol/paired-report
context references may be shared, as in #162's `reverified_acquisition_curve`.
Unscored provider markers are not counted as independent observed evidence.
Context hashes, score values and all references still contribute to each full
point identity. Exact repeated scores are permitted; reusing an underlying
scored observation is not. Declared chronology is checked globally across every
known step/panel timestamp, even when intermediate timestamps are absent.

The caller assembles the longitudinal CAP curves from externally supplied
observations and exact intervention declarations. Per-step paired providers do
not supply a multi-step schedule or attest execution; preserve their outcome and
context references when adding the explicit schedule index and run declaration.
Do not invent observations or discard mismatched boundary evaluations to make
pairs fit. Unknown model execution and chronology remain unknown.

Optional `StepRun.training_report` consumes the existing #162 `TrainingReport`;
its own validator recomputes its policy results. It must bind the exact one-seed
manifest, bundle and step. Every present held-out/guardrail/transfer curve must
be the exact corresponding matrix slice. A train-only curve must additionally
bind the TRAIN population, model/checkpoint pair, sequence indices and full
intervention signature; it cannot import a different run's negative or positive
result. Additional training/learnability observation evidence cannot substitute
for matrix/control observations. Missing reports or report gates remain UNKNOWN;
this layer does not reimplement the qualification engine.

## Descriptive arithmetic and policy

For a target with fixed reference step `r`, let `R[t]` be its full-population
recorded score at step `t`. Any unscored member makes that mean unavailable.

| Field | Definition and scope |
| --- | --- |
| `recorded_score` | Exact full-population score at the current step. |
| `recorded_retention` | `R[t]`, available at and after `r`; not training loss. |
| `recorded_backward_transfer` | `R[t] - R[r]`, at and after `r`. Negative values remain visible. |
| `recorded_forgetting` | `max(0, R[r] - R[t])`, against that fixed reference, **not the historical maximum**. |
| `recorded_forward_transfer` | Future target's score immediately before its first scheduled training step, minus an explicit independent prelearning control on the exact same population and baseline checkpoint. |

Later reference comparisons embed the canonical `RetentionLink`. Acquisition
curves, every seed and every step remain in the report. The final backward-transfer
mean includes only previously acquired targets (`r < N`) and is unavailable if
any expected seed or contributing score is missing. Per-cell replicate spread
is checked without selecting favorable seeds.

A forward control must refer to a target first introduced after step 1, use the
exact baseline checkpoint and index 0, and contain distinct case observations.
Known late controls are rejected. Missing controls, missing scores or unknown
necessary timestamps produce `None` / UNKNOWN, never a forward-transfer claim.
Even a valid numerical difference is **recorded pre-exposure change**, not causal
or independently demonstrated transfer; declared source assignments and
chronology are not attestations.

`ContinualPolicy` declares minimum replication (at least two), maximum forgetting,
catastrophic-forgetting threshold, allowed unrelated guardrail regression, and
maximum per-cell replicate score range. A decline **strictly greater than** its
threshold fails the relevant gate. Missing planned seeds make dependent gates
UNKNOWN unless an already-observed violation requires FAIL. Negative transfers,
catastrophic losses and guardrail failures remain first-class report results.

`assess_continual_learning(evidence, policy=...)` revalidates the complete tree.
`ContinualReport` recomputes its measurements and gates when parsed, so editing
an aggregate, dropping a failure, or asserting a passing status is rejected.
Known failure dominates UNKNOWN. No report can reach a scientifically successful
continual-learning conclusion through these descriptive checks:

- `execution_attestation_provider = "UNAVAILABLE"`;
- `demonstrated_continual_learning = "UNKNOWN"`;
- `capability_gain = None`;
- `e7_promotion = False`.

E7 `CONTINUAL_LEARNING_READY` concerns readiness for a protocol, not proof that a
particular model learns continually. This package performs **no E7 promotion**.
There is no caller-set PASS switch for execution, causality or maturity.

## Append-only history and storage responsibility

```python
from investigation_world.continual_learning import (
    ExperimentHistory, assess_continual_learning,
)

report = assess_continual_learning(evidence)
history = ExperimentHistory(plan=evidence.plan)
# Retain this independently in storage; do not derive it from a replacement input.
stored_commitment = history.record_id
updated = history.append(report, expected_previous_commitment=stored_commitment)
assert updated.revisions[:-1] == history.revisions
```

Every appended full report snapshot binds the same plan, a contiguous revision
index and the prior revision ID. Earlier snapshots are retained exactly; a new
snapshot can record newly available evidence or a correction without erasing the
original record. Parsing rejects broken, skipped or reordered links. Appending
rejects a previous commitment that does not match the supplied history.

This is an immutable **content commitment**, not persistent storage. Legacy nested
provider models contain mutable containers; the whole tree is reparsed at every
consumption boundary and mutations invalidate the commitment. A caller that
rebuilds an entirely new valid history can only be detected if storage retains
and supplies the original previous commitment. Hashes do not establish authorship,
prospective timing, independent execution, or durable append-only storage.

All records and raw serialization are evaluator-private. Public and buyer-safe
projection withhold the entire record, including source IDs, hashes, labels,
checkpoints, free text and paths. Sealed material is rejected rather than widened.
No data is fetched, published, trained on, or sent to any external service.

## Verification

Tests are explicitly **CONSTRUCTED**, including complete and negative arithmetic,
missing/failed seeds and cases, changed panel/checkpoint/manifest evidence, replay
lineage and overlap, unknown/late controls, exact #162 report integration, privacy,
and append-only history falsifiers. They are not empirical qualification.

```sh
python -m pytest tests/continual_learning
ruff check src/investigation_world/continual_learning tests/continual_learning
mypy --follow-imports=silent src/investigation_world/continual_learning
python -m pytest tests
python tools/quality_baseline.py check
```

The draft PR records actual focused, full-suite, installed-wheel, package-quality
and independent-review results. Formal review, merge, model runs, paid compute,
protected evaluation, scientific qualification and release authority remain
separate. No shared quality baseline is changed to hide new diagnostics.
