# Measured evidence, independent verification and scoped claim promotion

The assurance path extends research admission. A declared condition passing is not
an independently reviewed claim. The implementation deliberately separates:

1. **Plan admission:** frozen question, model/data/regime/budget and necessary criteria.
2. **Executed conditions:** measured counters reconciled against the exact plan.
3. **Evidence verification:** recomputed prediction scores and deterministic replay.
4. **Authenticated review:** an explicit accept from a separately trusted reviewer key.
5. **Scoped claim record:** the exact bounded conclusion, including valid negative results.

None is an aggregate training, frontier, deployment or scientific qualification
PASS. No finite instrumentation system guarantees truthful arbitrary programs or
the scientific sufficiency of a hypothesis. Unsupported mechanisms remain
unverified; they do not inherit assurance from successful file hashing.

## Reuse, not parallel infrastructure

- Forge creates the frozen release and selected TRAIN export.
- TrainLab's existing `training_observer.train_step` executes measured CPU steps;
  [native capture](adequacy-capture.md) owns the supported loop, not caller counters.
- TrainLab execution receipts and the four-dimensional adequacy gate bind inputs,
  observed work, predictions and runtime provenance.
- Research Lab's existing queue, independent clean-directory replay task, frozen
  protocol and `synthesize` recompute the complete candidate/control seed population.
- Existing diagnostic bundles and #555 OpenSSH signatures authenticate the
  [exact claim review](assurance-review.md), with a separately pinned recipient trust list.
- Research Lab records an immutable scoped result only after all prerequisites are
  recomputed. It does not alter the existing training-qualification engine.

## Supported measured path

The first native measurement adapter supports the exact dense CPU classification
modules and SGD regime documented in [adequacy capture](adequacy-capture.md).
Custom arbitrary architectures, accelerators, distributed training, accumulation
and other optimizers are not silently accepted as measured. They can be investigated
as explicitly unassessed engineering diagnostics while adapter support is developed.

For research recipes using this path, add the capture artifact to `artifacts` and
its declaration to the adequacy contract:

```json
{"capture": {"artifact": "capture.json", "adapter": "pytorch_cpu_classification_v1",
             "metric": "accuracy"}}
```

The loop records actual parameter shapes/counts, updates and exposures, model state
identities, sampled batches, final predictions and source/runtime identities.
Reconciliation rejects missing or under-run observations even when the process exits
zero. Prediction accuracy is recomputed from the retained exact TRAIN export rather
than copied from the producer's metric. It is **training accuracy**, not a held-out
or language-generalization result. This promotion adapter currently accepts only
that measured classification-accuracy metric, not inference-cost, general-language
or arbitrary user-defined metrics. The 12:1 inference priority is not a reason to
promote an unmeasured efficiency claim. Contamination and the source authenticity of
an export remain separate questions. Capture failure prevents assurance promotion.

Captured source bytes are local training evidence and may contain private training
data. They must not be published merely because a capture succeeded. The complete review
bundle described below includes exact source, criteria, captured TRAIN data and
run artifacts, not merely hashes. Its explicit `data_classification` applies to
all those materials. Do not select PUBLIC_AUTHORIZED unless those complete sources
are authorized for that review; this tool does not sanitize them or publish them.
Classification is a caller assertion, not privacy verification. These are local review
packages, not automatically public-safe exports or buyer-facing EvidenceRecords.
Private evaluator truth, confidential paths and hashes must not be released.
Distinct run IDs plus replay records establish the recorded execution structure,
not independent humans, independent hosts or cryptographic process attestation.
A bundle with more than 8 MiB of decoded materials is rejected, not silently reduced.

## Exact per-seed research recipes

`Controller.register` must not rewrite a seed after a contract has been reviewed.
Research protocols therefore supply `seed_recipes`:

```json
{"candidate": "candidate-1.json", "control": "control-1.json", "seeds": [1,2,3],
 "seed_recipes": {
   "candidate": {"1":"candidate-1.json","2":"candidate-2.json","3":"candidate-3.json"},
   "control": {"1":"control-1.json","2":"control-2.json","3":"control-3.json"}
 }}
```

The mapping must cover both arms and every expected seed exactly; each recipe must
have that seed and its own valid contract. Budgets, split/workload and purpose
cannot silently drift across seeds. Research Lab freezes every mapped input and
uses actual declared timeouts for admission/budget accounting. Its autonomous lane
registration uses the same resolver. Missing files, mutated input or a contract
whose seed was changed fail closed. Old explicitly non-scientific demo cloning is
not used for claim-bearing research.

## Prepare, review and promote

After all primary runs, clean-directory replays and the ordinary separate-session
review complete, call:

```python
package = lab.prepare_claim_review(
    protocol_id, destination, data_classification="CONSTRUCTED_PUBLIC"
)
```

The bundle includes byte-verified, inspectable source/recipe/contract and raw evidence
for the complete reviewed population. This recomputes source integrity, all expected arms/seeds, four-dimensional
reconciliation, native measurement, prediction scoring and deterministic replay
projections. It requires agreement on capture evidence, not just one matching score.
It preserves `BOUNDED_CONTRAST_NOT_SUPPORTED` as a valid negative conclusion.
Missing prerequisites are not negative research findings: they block preparation.

A real reviewer must inspect the exact bundle and sign using their own authorized
key via the existing `trainlab.signed_bundle_review.sign_review`. Production trust
is never generated by this workflow. The recipient supplies the expected signer,
allowed-signers file and its independently obtained hash. An `accept` verdict is
required. A valid signature over `inconclusive` or `request-changes`, a self-review
label, changed evidence, wrong trust policy or an arbitrary unrelated bundle cannot
promote a claim.

```python
result = lab.promote_claim(
    protocol_id, package["bundle"], package["manifest_sha256"], envelope_path,
    signer=expected_reviewer, trusted_signers=recipient_trust_file,
    trusted_signers_sha256=recipient_trust_hash,
)
```

The result is `SCOPED_CLAIM_REVIEWED`, with the exact claim and evidence identity;
`scientific_qualification` remains `NOT_QUALIFIED`. This means the bounded evidence
was measured, reproduced and explicitly reviewed under the supplied policy, not
that the architecture is generally superior. The immutable graph node is an audit
record, not perpetual authorization. `lab.verify_claim_review` must be called with
current source evidence and trust before relying on it. Changed/revoked trust or
changed evidence prevents revalidation. No external publication is performed.

## What independence means here

The replay worker executes a fresh directory through existing Research Lab machinery.
Its guaranteed scope is the same host/runtime, not a separate external laboratory.
Review worker/session separation follows the existing operator-asserted contract.
OpenSSH authenticates a recipient-authorized key; it does not prove separate humans,
independent institutions, absence of collusion or scientific correctness. Tests
using ephemeral keys prove acceptance mechanics, not actual human review.

## Executed acceptance

`integrations/research_lab/tests/test_claim_assurance.py` prepares a genuinely
constructed Forge release, selects TRAIN, executes six small CPU fits and six fresh
replays, obtains measured evidence, and tests the signed scoped-claim path. Identical
candidate/control pipelines correctly yield a **bounded negative** result. Changed
capture and signed inconclusive reviews are rejected. The signing keys are ephemeral
test fixtures only. Optional Torch absence causes a skip, never an assurance PASS.

## Private canonical training diagnostics

The separate [private training assessment](private-training-assessment.md) API
recomputes supplied TRAIN-001 records and links exact four-way diagnostic scores.
It never changes this measured TRAIN-only promotion path or upgrades unavailable
providers. Private evidence is not added to public review bundles. A descriptive
training/held-out score change is not a transferable-capability qualification.
