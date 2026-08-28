# Observatory Trajectory Diagnostics

This package adds diagnostic analysis over canonical `TrajectoryV2` and append-only
`ReverificationRecord` data. It lives under the isolated
`investigation_world.observatory.trajectory_diagnostics` namespace and does not modify existing
Observatory execution, provider, harness, store, Foundry, Frontier, portable runtime, exporter, or
qualification code.

## Inputs and existing Observatory abstractions

The primary input is `TrajectoryV2`. A trajectory may optionally be wrapped in
`TrajectoryDiagnosticInput` with the existing Observatory `CapabilityRun` and
`ProviderSessionSummary` values that produced it. The wrapper validates identity alignment for the
world/task, model, harness, verifier, and provider session. It does not define a replacement run,
provider, harness, or runtime abstraction.

External `ReverificationRecord` values can be supplied to the report builder without mutating the
canonical trajectory. Records must reference a trajectory included in the diagnostic report.

## Failure taxonomy

Diagnostics use the canonical `FailureCategory` taxonomy unchanged:

- model;
- harness;
- tool/action;
- environment/runtime;
- verifier;
- task/dataset;
- infrastructure/provider;
- budget/termination;
- unknown.

An explicit non-`UNKNOWN` `TrajectoryV2.failure` classification is preserved. When that
classification carries confidence below 1.0, the residual probability remains `UNKNOWN`. A
non-unknown category becomes the report's primary category only at confidence >= 0.80.

When the canonical classification is `UNKNOWN`, the diagnostic engine uses only narrowly
structured signals:

| Structured signal | Qualified probability mass |
| --- | --- |
| unsuccessful provider call | 0.65 infrastructure/provider, 0.35 unknown |
| unsuccessful resource call | 0.375 tool, 0.375 environment/runtime, 0.25 unknown |
| explicit recognized budget/limit truncation | 0.70 budget/termination, 0.30 unknown |

Multiple structured signals are averaged rather than compounded into artificial certainty. These
heuristic signals therefore remain qualified and cannot cross the 0.80 primary-attribution
threshold on their own.

The implementation deliberately does **not** infer a model failure from low reward, infer a
verifier failure from a score change, parse arbitrary free-form error text into blame, or convert
plain truncation into a budget failure without a recognized structured termination reason.

## Ambiguous cases

A failed resource operation is the canonical ambiguity example. The same record can be consistent
with a tool/action defect or environment/runtime failure, and the trajectory alone may not contain
enough evidence to choose between them. The result therefore keeps probability mass on both
categories and retains `UNKNOWN` as the primary category.

Likewise, simultaneous provider and resource failures are not treated as independent evidence that
can be multiplied into high confidence. They remain a qualified distribution.

## Comparison views

### Same model, different harness

`compare_same_model_different_harness()` groups trajectories only when world, task, model, agent,
runtime, verifier, reset, and initial state identity match. Harness identity/version is the sole
excluded control dimension. It reports reward deltas and canonical failure labels, with an explicit
statement that the association does not establish harness causality.

### Same harness, different model

`compare_same_harness_different_model()` uses the analogous controlled identity key with only model
identity/snapshot excluded. The resulting model association is not promoted to causal blame.

### Same trajectory, different verifier version

`compare_same_trajectory_verifier_versions()` compares the immutable original evaluation with
appended or externally supplied reverifications for the same `trajectory_id` and verifier ID when
the verifier version differs. It reports reward and common-component deltas.

A score change is verifier-version **sensitivity**, not proof that either verifier is defective and
not proof that the task, model, or original score is invalid.

## Distribution views

`failure_category_distribution()` reports both:

- integer primary-category counts; and
- fractional expected counts/rates from the full qualified probability distributions.

The fractional view prevents ambiguous cases from being silently forced into one bucket.

`capability_conditioned_failure_profiles()` applies the same calculation independently for each
canonical `TrajectoryV2.capability_tags` value. A multi-tag trajectory contributes to each tagged
profile. Untagged trajectories are represented under `__untagged__` rather than discarded.

## Integrated report

`build_trajectory_diagnostics()` returns:

- per-trajectory failure attributions;
- same-model/different-harness comparisons;
- same-harness/different-model comparisons;
- same-trajectory/different-verifier-version comparisons;
- the overall failure-category distribution;
- capability-conditioned failure profiles; and
- IDs of externally consumed reverification records.

Duplicate trajectory IDs are rejected so repeated input cannot silently skew distributions.
Reverification records for trajectories outside the report are rejected rather than ignored.

## Scientific boundary

These outputs are diagnostics, not causal proofs. Controlled comparisons reduce obvious
confounding but still report associations. Probabilistic attribution is retained when evidence is
non-unique. `UNKNOWN` is an intended result whenever the available trajectory does not establish a
unique cause.

This package makes no Frontier Qualification, benchmark-readiness, model-readiness, or deployment
qualification claim.
