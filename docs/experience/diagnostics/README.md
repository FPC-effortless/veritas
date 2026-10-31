# Evidence-bounded semantic diagnostics (EXP-002 / #153)

This package produces **diagnostic evidence**, not scientific, training, Frontier,
capability, or release qualification. It reuses `MachineExperience`,
`ExperienceDiagnostics`, `FailureMechanism`, `FailureFamily`, and Observatory's
`diagnose_failure`. It does not introduce a recorder, runtime, replay engine,
trainer, or capability graph. Canonical inputs and evaluations remain immutable.

## Supported computation

```python
from investigation_world.experience.diagnostics import (
    diagnose_experience, buyer_safe_diagnostics, failure_family_candidates,
)

report = diagnose_experience(experience)
# Optional: existing AuthorizedVerifierRegistry executes fresh authorized verification.
report = diagnose_experience(experience, registry=registry, reference=reference_experience)
```

* **Origin:** preserves existing Observatory attribution, probabilities and
  uncertainty. Low reward is not model blame. Mechanism candidates remain
  HYPOTHESIZED; canonical root mechanisms stay UNKNOWN.
* **Gold-10:** the exact supported `veritas.gold10.evidence-discipline@0.3.0`
  component set yields recorded evidence/hypothesis/calibration/rights-temporal
  deficits. These are OBSERVED score symptoms, not independently verified causes.
  A joint rights/temporal component does not distinguish missing evidence from
  hindsight. A reward ceiling or differently ordered valid citations is not a
  failure. Missing/invalid component sets cannot yield these observations.
* **Explicit invariant/process/evidence reasons:** optional fresh authorized
  reverification produces exact-record, evaluator-private reason evidence. Prior
  attached reverifications are removed from the *local verification input* so an
  `ALREADY_RECORDED` result cannot substitute caller-modified private reasons.
  The original experience is never changed.
* **Reference divergence:** compares structured action arguments/parameters,
  not prose similarity, under equal recorded world/task/runtime/verifier/reset
  and initial-state identities. Runtime and world versions must be known. Both
  action sequences need complete linked pre/post-state digests. A supported first
  aligned difference is `observed_reference_action_difference`, explicitly
  **not** a policy-error, failed-strategy or causal claim. Different total lengths
  do not hide an earlier supported difference; unsupported unmatched suffixes
  yield no divergence assertion. A reference is not automatically qualified.
* **Observed recovery:** only the native retained-receipt profile is supported.
  Existing authorized native verification must bind the receipt, contract,
  source events and retained artifact. A blocked attempt must have a later
  successful retry with the exact same action and parameters. The complete
  contiguous event range, receipt and fresh verifier record are referenced.
  Explicit terminal/nontruncated outcome, positive fully met target assertions,
  actual invariant definitions and no invariant/process/required-action/evidence
  or forbidden-action violations are required. A historical `blocked_required`
  penalty is **not erased**, even if the retry succeeded. Missing receipts,
  nonmatching retries, sequence gaps, unknown/unauthorized results and unresolved
  violations cannot yield successful recovery. This is OBSERVED recorded retry
  recovery, not general recoverability, causal proof or independent execution
  attestation. Other recovery classes remain unsupported.
* **Belief protocol quality:** reports complete paired-snapshot coverage,
  confidence consistency, evidence availability at/before the revision, and
  change in explicitly reported hypothesis contradiction counts. Ambiguous
  latest priors or missing history do not pass. Contradiction reduction measures
  what the protocol reports, not verified resolution or truth correctness.
* **Evidence efficiency:** counts distinct event-referenced evidence and duplicate
  reference fraction; cost per distinct event reference is available only when
  all evidence-bearing events have finite recorded costs. Global-only references
  cannot dilute the denominator. This measures recorded reference activity, not
  relevance, novelty of information, utility, or causal information gain.
* **Failure families:** groups repeated distinct experiences by hypothesized
  mechanism, retaining each symptom's exact source reference. Duplicate source
  IDs cannot create frequency; conflicting same-ID diagnostics fail closed.
  Family IDs use the existing canonical contract. Severity is maximum recorded
  unit-interval component deficit, **not independently assessed harm**. Affected
  capability, origin, recoverability and prerequisites are not invented. These
  are HYPOTHESIZED family candidates, not capability-gap promotion.

Gold-10 currently has three coarse events and one submission snapshot. It cannot
supply longitudinal belief revision, state-grounded action divergence, or native
recovery evidence. Tests combine real public Gold-10 inputs with explicitly
synthetic protocol histories and an actually executed TRAIN-derived native
fixture with an added optional prerequisite probe. No protected split is generated.

## Privacy and identity

Reports are internal; explicit verifier and recovery evidence is evaluator-private.
Internal source digests bind the exact experience including annotations, while
canonical experience identity remains unchanged. Evidence identities also bind
source experience IDs. Never publish raw report `model_dump()` output.

`buyer_safe_diagnostics` is a deliberately conservative allowlist. Mixed/private
source trajectories, private buckets, semantic-private state digests or private
histories yield only UNKNOWN/source-not-fully-buyer-safe, with no source IDs,
private-derived hashes or reason strings. Fully buyer-visible sources yield only
fixed observation/metric fields. The projection hash binds only rendered scalar
observations/metrics, not private annotations or opaque full-source identity.

## Validated controlled-contrast consumer

The merged #156 provider supplies `CounterfactualReceipt` v1. Use
`diagnose_counterfactual(receipt, source=recorded_source)` and
`intervention_failure_families([(receipt, recorded_source), ...])`. These APIs call
`validate_counterfactual_receipt` on every input, freshly verifying retained native
artifacts and recomputing exact source, companion, capability, runtime, cut,
unchanged prefix/suffix/submission, baseline reproduction and alternative-repeat
bindings. Parsing a receipt or attaching a prior PASS is insufficient. Missing
artifacts, forged source/capability/bindings and inconsistent evidence raise errors;
they cannot generate a diagnostic. No recorder or replay engine is duplicated.

The typed evidence status is **OBSERVED_CONTROLLED_CONTRAST**, mechanism status is
**HYPOTHESIZED**, and causal status remains **UNKNOWN**. A canonical
`StructuralRecord(record_type="causal_candidate")` retains the bound action
replacement hypothesis, target-count direction and all residual violation lists.
Direction has typed basis `verifier_target_counts_only`, not overall success or
preference: more met targets may coexist with residual process violations.
No-effect and worse alternatives are retained, not filtered for positive results.
An identical replacement has no causal candidate or action-divergence assertion.
This is a simulated, content-bound executed contrast, not cryptographic independent
execution attestation, a model mechanism, or general causal qualification.

The first divergence is the exact changed call at the validated common cut state;
its reference type is `controlled_action_difference`. It is not proof the source
policy erred. A failed baseline and changed alternative with complete target success
and no remaining violations supports `counterfactual_valid_outcome_restoration`.
This references a valid alternative execution sequence, **not** a retry that happened
inside the original trajectory. A successful alternative is a task-local valid
reference, not an optimal or generally qualified policy. Failed alternatives,
unchanged actions and already-successful baselines do not count as recovery.

## Capability association and failure-family candidates

The receipt authenticates the full `CapabilityContract` and its portable task
binding, rather than trusting caller tags. Typed mapping scope is
**DECLARED_TASK_ASSOCIATION**: these are observations about tasks exercising a
declared capability, not measured agent competence. Native verification extends the
target set beyond the original contract's success terms. Existing verification
supplies target counts, not individual failed target IDs; individual failure and
contract-term attribution remain UNKNOWN. Severity is normalized unmet-target
fraction, not general harm. Residual invariant/process/evidence reasons remain
explicitly available without claiming they identify the model's root mechanism.

Families group failed sources with the same capability ID **and content digest**,
retain canonical source IDs and exact receipt references, and require at least two
distinct semantic source protocols. Artifact paths, baseline copies and independent
repeats cannot inflate frequency. Deterministic representative selection uses source
ID then receipt ID; duplicate-protocol receipts are not independent evidence.
`CapabilityFailureCandidate` wraps the canonical family and `CapabilityGap` with
HYPOTHESIZED status and OBSERVED_BOUND_TASK_FAILURES evidence. Frequency means
sampled distinct protocols, not independent agents, environments, a population
failure rate or demonstrated generalization. Prerequisites, missing procedures and
abstraction deficits are not invented; no capability graph or qualification state
is changed.

All contrast reports, candidate records, families, gaps and evidence references are
evaluator-private. Both public and buyer-safe methods return only a fixed UNKNOWN
withholding reason; no receipt/source hashes, paths, private reasons or parameters
are rendered. Raw model dumps are private evaluator material, never trainer/export
payloads. Canonical source experiences, evaluations and maturity remain unchanged.

## Acceptance and qualification boundary

The original #153 requirements remain in force. This consumer removes the former
missing-provider implementation gap without treating coarse Gold-10 snapshots as
longitudinal evidence. The conditional computations have positive, negative and
unsupported-input tests; no unconditional UNKNOWN placeholder is counted as an
implemented causal consumer. Gold-10 still demonstrates recorded component symptoms;
synthetic paired histories demonstrate protocol metrics; actual public TRAIN native
execution demonstrates bounded intervention/recovery. These do not demonstrate
truth/calibration accuracy, general recoverability, training usefulness, scientific
causality, Frontier performance or measured capability deficits. Those empirical
claims remain UNKNOWN pending their separately authorized evidence programs.

No document or passing test itself closes #153 or grants formal review/merge authority.
