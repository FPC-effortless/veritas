# Supported native adequacy capture

`trainlab.adequacy_capture.capture_training` owns a bounded CPU training loop and
calls the existing `training_observer.train_step` for every attempted batch. It
does not accept caller-supplied update/exposure counters. This is an implemented
measurement path, not universal support for arbitrary training frameworks.

## Supported boundary

- PyTorch float32 dense CPU classification with cross entropy and owned SGD.
- Exact `Linear`, or `Sequential` containing exact Linear/ReLU/Tanh modules. Custom
  subclasses, overridden forward methods, external hooks, model buffers, dropout,
  GPUs, mixed precision, gradient accumulation and distributed training are unsupported.
- At most one million parameters, one million data scalars, 10,000 TRAIN rows,
  10,000 requested steps, and 1,024 examples per sampled batch.
- Authorized, pinned TRAIN export only. No protected TEST split is opened.

The export uses schema `trainlab.forge-train-export.v1`, `split: train`, the
`forge_manifest_sha256`, `feature_field`, integer `classes`, and `examples` in the
shape returned by Forge `Dataset.examples`: record/episode/subject identities,
features and target. The selected feature is a finite numeric vector and
`target.value` is an integer class. The export must be prepared through the
approved Forge process; this adapter hashes the actual export consumed but does
**not** independently reconstruct its lineage from an entire Forge release.
This limitation is retained as `EXPORT_DECLARED_NOT_RELEASE_RECOMPUTED`.

## API and receipts

```python
receipt, capture = capture_training(
    config, input_root, data_file="train.json", producer_file="producer.py",
    model=model, steps=4, batch_size=4, learning_rate=0.1, seed=7,
)
checked = verify_capture(capture, receipt, config, receipt["inputs"])
```

The recipe and every input are byte-bound to the frozen adequacy contract before
execution. Source mutation after execution yields an incomplete capture. The
wrapper constructs batches, owns the optimizer and records native step evidence,
actual parameter shapes/count, optimizer calls, changed/successful updates, target
exposures, sampling schedule hashes, dataset counts, optimizer settings and elapsed
training time. Model state hashes identify initial/final bytes. Python, Torch build
and observer/capture source hashes identify the runtime implementation.

`receipt` conforms to `trainlab.execution-adequacy-observations.v1`; retain it as
the execution contract's declared artifact. Retain `capture` separately as the
capture artifact. Callers must not turn `capture_complete: 0` into admission.
Nonfinite failures, unsuccessful steps, exceptions and source mutation remain
incomplete. After an exception, counters describe returned observer events only and
are lower bounds, not a claim that unreturned work did not happen. Actual captured counts must also meet the separate prospective
execution criteria: a clean two-step run does not satisfy a four-step experiment.

`verify_capture` replays per-step accounting, sampler hashes, parameter-shape
counts and receipt identity. It returns `valid`, `admissible`, `status` and a
`replay_sha256` derived from deterministic observations, source/data/config/model
identities and batch schedule. Timing is excluded from that replay identity;
complete-call timing comparisons remain separate. The verifier does not trust
the saved completion bit. Partial or failed capture cannot be admitted.

## Assurance limits

This is trusted synchronous local instrumentation, not process attestation.
Hashes cannot stop a malicious producer from fabricating a self-consistent trace.
Captured counters do not prove that the model size, optimization length or dataset
is scientifically sufficient. Dataset identity does not prove uncontaminated
splits, semantic coverage or correct labels. Prespecified criteria, native validity
checks, independent review and qualification remain required. Unsupported pipelines
must not inherit this adapter's measured-coverage claim.

## Executed acceptance

`test_adequacy_capture.py` runs a real tiny CPU Linear classifier, reconstructs
observed updates and targets, reproduces the deterministic trace from the same
initial state, and exercises under-run, nonfinite, mutation and forged-counter
controls. These are engineering acceptance tests, not general-language or model
quality results. Optional Torch absence is a skipped test, never a PASS.

## Owned final prediction scoring and private source retention

The wrapper evaluates the final supported model on **the same TRAIN export** and
retains ordered class predictions plus target/prediction digests. This is training
accuracy only, not validation, generalization or contamination evidence.
`verify_capture` reparses exact retained export bytes, checks their input SHA256,
recomputes row identities/count, distinct subjects, feature width, target sequence
and prediction accuracy. Its `metrics.accuracy` is independently recomputed from
those predictions; a producer's unrelated accuracy scalar cannot substitute for it.
Prediction evidence also enters the deterministic replay identity.

`training_groups` means groups available in the export. `sampled_training_groups`
means distinct groups selected by the wrapper's actual attempted batch schedule,
including a final attempted batch that fails. It is not an assertion that every
selected example completed a gradient update. Exposure/update counters separately
track returned observer events.

**Privacy:** the capture artifact now contains exact `data_source` TRAIN export
text, including training features, identities and targets, bounded to 1 MiB. Treat
it as private research evidence. Do not publish it or include it in a public review
bundle without separate authorization. Public summaries should contain only
approved metrics and content identities. A local byte identity is not permission
to disclose the underlying data. The whole capture uses the 16 MiB finite-JSON
bound; artifact readers must use that matching bound.

The sampling seed must equal the frozen recipe seed. Model initialization is
caller-owned: its initial state is measured and replay-bound, but its initialization
RNG seed is not inferred or certified from the sampling seed.

Deterministic replay identity includes the exact Python and platform strings,
Torch version/build, and observer/capture source hashes. A runtime/source change
therefore cannot silently match replay, even when predictions happen to match.
These are recorded environment identities, not cryptographic process attestation.
