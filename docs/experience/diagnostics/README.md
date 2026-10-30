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

## Explicit remaining acceptance gap

This is **not a claim that all of #153 is complete**. No source currently supplies
an independently bound MachineExperience intervention receipt suitable for
intervention-supported causal candidates. Existing `execute_counterfactual` is
real execution, but its returned runtime is not such a receipt. Retained
reverification folds recorded state changes and verifies outcomes; two matching
reverified runs alone are not controlled intervention proof. This package does
not replace #156 by inventing intervention linkage or replay orchestration.

Causal candidates therefore remain unavailable; capability gaps/prerequisites
are not promoted. Reference qualification and truth/calibration-quality evidence
are also not fabricated. Completion of those acceptance portions requires a
supported exact-source intervention/qualification evidence provider, not an
unconditional UNKNOWN implementation being counted as completed capability.

### Sequencing decision required, not an automatic dependency waiver

The original #153 requires causal candidates where valid intervention evidence is
available; #156 explicitly depends on #153 merged and owns the exact-source
counterfactual/alternative-experience linkage. Counting this partial foundation
as full #153 completion merely to unblock #156 would conceal that dependency loop.
The smallest proposed sequencing option is an **owner-accepted diagnostic
foundation milestone** comprising this observed-evidence producer, then a bounded
#156 evidence-linkage implementation using existing replay, followed by #153's
intervention-supported consumer and full acceptance review. Alternatively, an
explicitly authorized joint #153/#156 implementation can resolve both together.
Neither option is authorized by this document. All original requirements remain;
no #156 contract/status/paths are changed, and no `/done` is warranted here.
