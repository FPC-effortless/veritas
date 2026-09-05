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
required-UNKNOWN task away. A material change to the frozen world identity, Gold-10
task manifest, verifier source, target source, or verifier-target contract changes the
bound qualification identity and invalidates stale evidence.

## Deterministic compiler

`compile_task_qualification(case_id)` constructs canonical verifier fixtures and two
replays per fixture for one frozen Gold-10 task. `compile_gold10_verifier_qualification()`
executes the same protocol across exactly ten unique tasks and emits the fail-closed
candidate aggregate.

Every semantically applicable generic falsifier category is exercised. The suite
includes the scripted reference, partial and plausible-invalid submissions,
unrelated-target reward laundering, target/state drift, missing cited evidence,
deterministic perturbation, malformed JSON, and adversarial edge cases. Confidence-role
inversion is retained explicitly as adversarial verifier evidence. On the calibration
case, a separate adversarial fixture uses unbound generic uncertainty; on
non-calibration cases, the semantic adversarial fixture uses a duplicate-claim attack.

The valid scripted reference is predeclared to score exactly at the frozen pilot reward
ceiling (`0.75`). Negative fixtures are predeclared to fail at zero reward. The compiler
does not derive its expected ranges from observed outputs. That makes changed verifier
behavior a qualification failure rather than an updated expectation.

## Applicability

Gold-10 is a read-only investigation submission protocol. Three generic taxonomy
surfaces are not represented and are therefore omitted rather than fabricated:

- `alternative_correct_strategy`: this pilot has not established a genuinely different
  semantic solution strategy; reordering the reference submission is not an
  alternative strategy;
- `authority_process_violation`: Gold-10 exposes no authority/process transition
  surface; confidence-role inversion is tested under adversarial semantics instead;
- `forbidden_side_effect`: Gold-10 exposes no mutable side-effect surface.

The corresponding generic gates remain `UNKNOWN` in the underlying canonical report
and are explicitly classified `NOT_APPLICABLE` by the Gold-10 wrapper. The generic
`falsifier_fixture_coverage` gate is likewise `UNKNOWN` because those taxonomy entries
are deliberately absent and is explicitly marked `NOT_APPLICABLE` with rationale.
`NOT_APPLICABLE` can never erase an observed FAIL. Any other UNKNOWN remains required
and keeps the task and candidate UNKNOWN.

## Evidence identities

Per-task environment identity binds the exact frozen `world_id` and `world_version`
from the merged pilot contract separately from its content SHA-256. The content digest
also includes the reconstructed Gold-10 task and task manifest SHA-256. A semantic
world-version drift therefore changes both the declared environment version and the
content-bound identity rather than being aliased to a task-manifest digest.

Verifier identity binds the verifier ID/version, verifier-target contract SHA-256, and
SHA-256 digests of the exact imported Gold-10 verifier and target source files. Fixture
payloads, replay outputs, generic reports, per-task records, and the ten-task candidate
are all content-bound.

## Downstream use

A clean exact-head run of this lane is the input to independent Gold-10 red-team work.
Scientific qualification must still consume the same frozen task/verifier identities,
retain all red-team findings, and treat missing scientific evidence as UNKNOWN. This
lane provides no authority to skip #178 or promote directly to Frontier/training use.
