# Gold-10 verifier qualification

`GOLD-VQ-001` is the provider lane between the merged executable Gold-10 pilot and
Gold-10 scientific/red-team qualification.

It does **not** modify `src/investigation_world/gold10/**`. The verifier being judged
is frozen input. This package composes the canonical Veritas verifier-qualification
models with Gold-10 task identity and candidate aggregation.

## Authority

A successful candidate may establish only `VERIFIER_VALIDATED` evidence. It does not
establish scientific, Frontier, training-value, learning-efficiency, release, or
commercial qualification.

Per-task evidence is mandatory. The candidate cannot pass by averaging a failed or
required-UNKNOWN task away. A material change to a Gold-10 task manifest, verifier
source, target source, or verifier-target contract changes the bound qualification
identity and invalidates stale evidence.

## Deterministic compiler

`compile_task_qualification(case_id)` constructs canonical verifier fixtures and two
replays per fixture for one frozen Gold-10 task. `compile_gold10_verifier_qualification()`
executes the same protocol across exactly ten unique tasks and emits the fail-closed
candidate aggregate.

Every applicable generic falsifier category is exercised. The suite includes the
scripted reference, a semantically equivalent reordered valid submission, partial and
plausible-invalid submissions, unrelated-target reward laundering, target/state drift,
missing cited evidence, confidence-role inversion, deterministic perturbation,
malformed JSON, and an adversarial edge case. On the calibration case the adversarial
fixture specifically uses unbound generic uncertainty; on non-calibration cases it
uses a duplicate-claim attack.

Valid reference and equivalent-strategy fixtures are predeclared to score exactly at
the frozen pilot reward ceiling (`0.75`). Negative fixtures are predeclared to fail at
zero reward. The compiler does not derive its expected ranges from observed outputs.
That makes a changed verifier behavior a qualification failure rather than an updated
expectation.

## Applicability

Gold-10 is a read-only investigation submission protocol. It has no mutable operational
side-effect surface, so `forbidden_side_effect` is not fabricated as a fake fixture.
The generic `falsifier_fixture_coverage` and `side_effect_sensitivity` gates therefore
remain `UNKNOWN` in the underlying generic report and are explicitly classified as
`NOT_APPLICABLE` by the Gold-10 wrapper. The compiler verifies that every other generic
falsifier category is present. `NOT_APPLICABLE` can never erase an observed FAIL.
Any other UNKNOWN remains required and keeps the task and candidate UNKNOWN.

## Evidence identities

Per-task environment identity includes the complete reconstructed Gold-10 task and its
manifest SHA-256. Verifier identity binds the verifier ID/version, verifier-target
contract SHA-256, and SHA-256 digests of the exact imported Gold-10 verifier and target
source files. Fixture payloads, replay outputs, generic reports, per-task records, and
the ten-task candidate are all content-bound.

## Downstream use

A clean exact-head run of this lane is the input to independent Gold-10 red-team work.
Scientific qualification must still consume the same frozen task/verifier identities,
retain all red-team findings, and treat missing scientific evidence as UNKNOWN. This
lane provides no authority to skip #178 or promote directly to Frontier/training use.
