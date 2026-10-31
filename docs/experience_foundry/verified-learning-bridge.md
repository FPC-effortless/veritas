# Verified-learning bridge (bounded implementation)

Implements approved proposal [#445](https://github.com/FPC-effortless/veritas/issues/445)
through the separately enrolled [#446](https://github.com/FPC-effortless/veritas/issues/446)
(`LEARN-BRIDGE-IMPL-001`). The earlier proposal remains a design/history record;
its trusted status was not manually rewritten. #160 adds a separate
[candidate-derivation boundary](candidate-derivation.md), without relaxing this bridge's
successful-TRAIN admission or public trainer projection.

## Supported source, not a generic inverse

Only the **first financial_spreadsheet / dcf_formula_repair TRAIN case** from the
existing public procedural generator is supported. `public_training_fixture()` pins the
small config (seed 73, one case per domain/split) and takes only the first iterator yield;
it never generates held-out cases. The exact regenerated source, capability binding and
portable contract must match, not merely a caller-provided TRAIN label. This is a public
synthetic fixture for implementation conformance, not protected TEST or benchmark evidence.

`PublicTrainingRecorder` runs the actual `NativeOperationalRuntime` and retains an original
`RolloutTrace` during `act`/`submit`. Callers supply actions; this is not a policy or trainer.
The real merged `trajectory_v2_from_operational_runtime` produces the canonical record,
which is wrapped by `machine_experience_from_trajectory`. It is not replaced by handcrafted
canonical test summaries.

| Companion fact | Evidence |
| --- | --- |
| task seed / split | exact `OperationalDistributionCase` returned by generator |
| taskset / environment version | generated episode's distribution version |
| harness version | actual `veritas.public-financial-training-recorder.v1` protocol |
| runtime version | digest of actual installed runtime/native-runtime source bytes |
| state hashes / evaluator transition | retained native receipt snapshots |
| events / submission / cost | captured actual runtime calls, submit input and budget |
| source / capability / contract | exact regenerated public fixture and merged binding/compiler |

Canonical unknown seed, split, taskset/harness/runtime versions remain **unknown**. The
private companion enriches provenance without rewriting canonical facts or inventing
observations, seeds, timestamps, state hashes or success flags. Other profiles reject.

## Admission and export

Admission revalidates canonical identities and companion/source bindings, then invokes
`reverify_trajectory` with `AuthorizedVerifierRegistry`. Prior caller verification history is
ignored for the new invocation (execution identity unchanged), avoiding reliance on a
caller-edited cached private breakdown. Admission requires explicit invariant definitions,
no invariant/process/forbidden-action/missing-action/missing-evidence violations, positive
and complete target assertions, successful outcome, terminal submission and no truncation.
`assess_trace` and its missing-invariant defaults are never used.

The result uses existing `ExpertiseAssessment`, `VerifiedTrajectory`, `TrainingUse.SFT`,
`TrainingRecipe` and `compile_training_bundle`. Recipe widening, other trainer kinds,
held-out/mixed input, duplicates and frozen-panel overlap reject. Existing compilation
semantics are retained. No maturity/readiness/qualification value is promoted.

`compile_verified_bundle` emits two deliberately different surfaces:

* `bundle` and `provenance` are evaluator-side interchange/provenance. They are **not** a
  trainer-safe serialization and must remain in the source's authorized boundary.
* `trainer_bytes` is deterministic JSONL containing only an allowlisted public objective,
  public record fields/action schema and actual action/parameter sequence. It has no
  oracle, private replay/native receipt, private seed, hidden source identity or arbitrary
  annotation. No fabricated observations or model-specific result schema are supplied.

Do not pass these companion traces to `ArtifactTrainerAdapter`: it serializes full traces
and expects a different submission schema. The new byte projection is not a second trainer.
Repeated compilation of identical pinned inputs preserves exact lineage and bytes; different
native artifact locations can change evaluator evidence identities and are different inputs.

## External receipt: integrity, not execution attestation

`validate_external_receipt` uses existing `TrainingRunManifest`/`TrainingRunResult`. The
caller independently supplies the expected manifest, base revision, bundle and exact input
bytes plus explicit local paths. The validator reads bounded nonempty regular files and
binds input/checkpoint digests, whole-bundle contents, trainer/version/config/seed/run identity.
It rejects failed/incomplete/not-run/unknown status, substitutions, missing files and
nonfinite fields. Missing resource measurements remain `None`, not zero. Receipt commands,
URLs and artifact references are never executed or fetched.

A successful report means **byte_integrity_checked**, not a real training run, legitimate
data rights, independent execution attestation, model quality, training gain or qualification.
Resource values and base-model revision remain externally declared even when consistent.
Constructed local fixture files deliberately demonstrate this distinction. No model download,
paid compute or scientific training run is performed.

## Paired panels: preserve failed and unknown outcomes

`FrozenPanel` is a content commitment supplied by an authorized evaluator, not a clock or
signature. A separate caller-pinned expected manifest must commit to its panel ID before
an intervention. Complete unique baseline/checkpoint attempts must match the same panel,
source/runtime/contract/verifier/config identities and receipt checkpoint identities. Unknown
canonical fields stay unknown; explicit evaluation-source enrichment remains declared
provenance. Training task/source IDs **and source digests** are derived from the actual training bundle
and its complete lineage, whose full content hash must match the receipt. Caller-provided
omitted identity sets cannot bypass disjointness.

Each attempt is freshly reverified by the authorized registry. Successful-task training
admission is **not** used: real failed outcomes, regressions, timeout/termination metadata,
and unknown technical results remain in the report. Missing/duplicate/substituted cases,
changed protocol and unauthorized verifiers reject. Unknown replay yields an unscored row,
not a dropped failure or zero. All scored deltas are descriptive verifier-outcome differences.

Byte/identity matching does **not** independently attest which model produced an execution
or prove panel chronology/causal training gain. Those attestations stay UNKNOWN;
`training_validated` is false and `capability_gain` is null. TrainLab self-reported metrics
are not independent held-out evidence. PR #28's transfer experiment remains a separately
owned external runner; this bridge neither duplicates nor runs it.

## Verification

Tests in `tests/experience_foundry` cover the real public native roundtrip, unauthorized and
unsuccessful admission, invariant/identity/companion drift, held-out and recipe rejection,
actual trainer-byte private sentinels, deterministic no-mutation compilation, bounded
constructed-file receipt integrity, paired completeness and preserved negative/unknown
outcomes. Run with the repository's test environment:

```sh
python -m pytest tests/experience_foundry
ruff check src/investigation_world/experience_foundry tests/experience_foundry
mypy src/investigation_world/experience_foundry --follow-imports=silent --ignore-missing-imports
```

Clean installed conformance must copy these tests outside the checkout and run against a
built wheel without `PYTHONPATH=src`. Exact-head test/CI/Security/independent-review evidence
belongs in the implementation PR, not an unconditional PASS declaration in this document.
