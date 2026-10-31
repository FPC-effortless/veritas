# Experience Foundry candidate derivation (LEARN-001)

Implements the candidate-transform boundary from [#160](https://github.com/FPC-effortless/veritas/issues/160).
This is **implementation conformance**, not evidence of training usefulness, model
competence, scientific qualification, causal improvement, procedure induction or
abstraction transfer. No trainer is imported or run by this compiler.

## Outcome and ownership

The observable outcome is one actual supported recorded experience producing multiple
independently policy-versioned, reproducible, material-content-bound candidate assets.
Falsifiers include accepting a stale source or retained receipt, losing exact lineage,
promoting a failed source to a qualified demonstration, exporting private derived material,
using caller-declared PASS as verification, or silently treating unknown saturation as zero.

Only `experience_foundry` source, tests and docs are changed. Canonical experience,
trajectory/runtime/verifier, legacy Foundry training products, trainer implementations,
shared exports, Frontier and investigation-data are read-only providers.

The existing [verified-learning bridge](verified-learning-bridge.md), its successful-TRAIN
`admit_experience`, public allowlisted SFT bytes, external checkpoint receipt and paired
panel evaluation remain separate and unchanged. Candidate compilation does **not** add
training uses to `VerifiedTrajectory`, create `TrainingBundle` examples, alter legacy
`training_product` eligibility, or advance MachineExperience readiness/maturity.

## Validated input boundary

`compile_learning_assets` supports the original public financial TRAIN recorder
profile and the two independently regenerated [v2 structural profiles](public-profiles.md).
It reuses `experience.counterfactual.validation.verify_recorded`, which validates
source, companion, installed runtime, capability/portable contract, adapter identities,
original evaluation and retained native artifact, then freshly reverifies successes **and
failures**. Canonical split/runtime/model unknowns remain unknown; the separately captured
recorder evidence establishes the supported TRAIN profile without overwriting them.

Counterfactual receipts are freshly validated against their exact input source and all
retained baseline/alternative/repeated artifacts. Only executions already supplied by the
caller are inspected: compilation creates no new actions, counterfactual runs or trainers.
Missing/altered artifacts, stale identities, mutated receipt summaries, unsupported or
held-out source profiles and explicitly supplied frozen-panel overlaps reject the operation.
Exclusions cover the original source and every validated baseline/alternative/repeated
execution contributing derivative material, not only the original rollout.
The supplied frozen exclusions are content-bound declarations, not proof of an independently
frozen or complete held-out population.

Diagnostics come from #153. Repeated failure-family/gap envelopes are recomputed by the
#153 producer and #157 ingestion API against actual source/receipt material, not accepted
from a caller's serialized candidate. Their task association is **declared**, frequency is
counted recorded protocols, and causal/model-capability qualification remains UNKNOWN.
A lone source has no invented family/gap. #158 and #159 are optional unavailable providers;
their feature switches cannot manufacture procedure or abstraction qualification.

## Transform evidence

| Transform | Material and evidence boundary |
| --- | --- |
| `negative` | Actual submitted action sequence/submission and fresh explicit failed target/violation feedback; successful executions are not negative examples. |
| `verifier_feedback` | Fresh explicit outcome, target counts, residual violation reasons and component scores. No caller cached PASS. |
| `evidence_selection` | Actual submitted evidence IDs, available public record IDs and explicit missing-evidence feedback. Optimal selection/utility remains UNKNOWN. |
| `next_state` | Retained initial state plus actual action-event state changes. Targets are **observed simulator states**, not validated predictive models. |
| `alternative_action` | Actual changed action and public-at-cut evidence from a validated executed contrast. |
| `counterfactual` | Actual baseline/alternative action sequences, state/outcome differences and verified simulated repeatability; not a general causal effect. |
| `recovery` | Only a changed contrast with failed baseline and clean valid alternative, as diagnosed by #153. Explicitly counterfactual outcome restoration, **not** a retry observed in the source trajectory. |
| `preference` | Only the provider's supported non-NONE candidate preference with actual actions, target counts and residual violations. Not scalar reward alone or a training-admitted preference pair. |
| `structured_repair` | A validated outcome-restoring replacement with observed state/outcome deltas. |
| `curriculum` | An observed bound-task failure challenge linked to a freshly recomputed exact family/gap envelope; not a generic curriculum generator. |
| `procedure`, `abstraction` | Disabled by default. Enabling a request still returns `PROVIDER_UNAVAILABLE`; no synthetic success result. |

Unsupported/missing evidence produces a reasoned rejection for each requested transform.
The narrow source profile cannot consume arbitrary LLM prose or arbitrary MachineExperience
wrappers as learning assets. Other profiles and observed retry transforms need equivalent
source admission evidence before extension.

## Identity and privacy

`TransformRule` has an independently pinned policy `revision` and a fixed implementation
version. Changing one rule revision changes that kind's assets without reidentifying
unrelated kinds. `TransformPolicy` binds the rule set and filtering requirements.

Every `CandidateLearningAsset` commits to its full material, exact rule and lineage:
source experience and trajectory content, original companion, fresh verifier/reverification,
diagnostic report, native receipt, full portable contract, full capability specification,
recorded runtime, and applicable counterfactual/family/gap envelope identities and digests.
Family membership is never guessed from a label or aliased to a different recorded source.

The compilation additionally binds the policy, source/receipt occurrence counts, supplied
frozen exclusions, complete diagnostics/envelopes, optional measurement declarations,
selected candidates, rejected candidates and count reconciliation. Input order does not
change the result; multiplicity does. Material fingerprints omit lineage only for explicit
within-compilation semantic duplicate filtering. They do not replace exact asset identities.

**All candidate material, lineage, rejection evidence and compilations are evaluator-private**,
even when the original task was public. SEALED declarations anywhere in supplied source,
receipt, policy or measurement trees reject before references/material are derived; even
hashes of such declared inputs are not reclassified evaluator-private. Root visibility is a fixed literal. Public and
buyer-safe projections withhold the entire record, including IDs, hashes, paths, counts and
private feedback. `model_dump` is an evaluator-side serialization, **not** a trainer/public
export. `trainer_payload()` refuses. `training_qualified` is always false and
`training_usefulness` is UNKNOWN. Existing public successful-SFT export is a different API.

Parsing/checking a content-bound object is not fresh execution verification. Consumers
requiring current integrity must use `validate_compilation` with independently pinned
sources, receipts, policy, measurement declarations and exclusions; it recompiles against
retained artifacts. A caller who recomputes a hash after inventing material still fails this
comparison. Compilation does not attest which model executed a protocol.

## Filtering and unknowns

* **Input duplicates:** validate before deduplication; retain per-identity occurrence counts.
  Conflicting content for an identical source/receipt identity rejects.
* **Family source aliases:** when freshly validated receipts prove an omitted source has
  the same semantic protocol fingerprint as an actual family member, reject that alias's
  transform requests with exact alias/member/receipt/envelope evidence. This also prevents
  a different contrast from the alias bypassing the member's quota. Do not fabricate family
  membership for a source omitted by the provider's semantic deduplication.
* **Material duplicates:** same transform kind and exact material are deduplicated across
  source identities. Prefer an actual evidence-bound family member, then stable asset ID,
  so a path-distinct unbound alias cannot displace available family provenance and evade
  that family's quota. Rejections retain the full discarded candidate and representative ID.
  This is not a generalized near-duplicate/contamination detector.
* **Trivial contrasts:** identical original/replacement actions reject explicitly. Failed
  executions or observed no-effect transitions are not indiscriminately called trivial.
* **Optional family/transform quota:** counts accepted candidates with exact evidenced family
  membership. Quota rejection names the policy, family, limit and accepted candidate IDs.
  A quota is a data-volume policy, **never empirical saturation or learner mastery**.
* **Saturation:** optional CAP-001 `AcquisitionCurve` declarations are reparsed and matched to
  the source capability content. SEALED root or nested measurement evidence rejects rather
  than being reclassified evaluator-private. Their model-execution attestation remains UNKNOWN; a
  declared flat curve does not prove saturation. `counts['saturated']` is `None`, not zero.
  Default output remains private, unqualified candidates. Setting
  `require_saturation_evidence=True` fails closed with `SATURATION_UNKNOWN` rejections;
  no current provider can satisfy this empirical gate. A qualified saturation provider is
  an explicit future integration, not a fabricated PASS in this implementation.

`proposed = selected + candidate-bearing rejections`. Other rejections describe unsupported
or missing-evidence transform requests before material is produced. The report separately
counts duplicate/semantic-alias/trivial/quota/unknown-saturation decisions. Empty input returns an explicit
empty, unqualified compilation, not a successful training run.

## Use and verification

```python
from investigation_world.experience_foundry.derivation import (
    TransformPolicy, compile_learning_assets, validate_compilation,
)

policy = TransformPolicy()
result = compile_learning_assets(recorded_sources, receipts=executed_receipts, policy=policy)
# Retain result only within the authorized evaluator boundary.
validate_compilation(result, sources=recorded_sources, receipts=executed_receipts, policy=policy)
```

The tests use the actual public native recorder and executed contrast provider, not
handwritten PASS summaries. Coverage includes multiple derivatives, independent rule
revisions, source immutability, actual retained-artifact mutation, cache/identity/receipt
forgery, held-out and frozen overlaps, private export/eligibility refusal, exact family/gap
binding, source and material duplicates, lineage-preserving deduplication, trivial no-op
contrasts, count tampering, quota accounting, constructed curves and UNKNOWN saturation.

```sh
python -m pytest tests/experience_foundry
python -m pytest tests
ruff check src/investigation_world/experience_foundry tests/experience_foundry
mypy src/investigation_world/experience_foundry --follow-imports=silent --ignore-missing-imports
python tools/quality_baseline.py check
```

Also build a wheel and run copied tests outside the checkout without `PYTHONPATH=src`.
Exact-head results and review evidence belong in the PR. No protected panel, model run,
training efficacy study, paid compute, release or deployment is part of these checks.
