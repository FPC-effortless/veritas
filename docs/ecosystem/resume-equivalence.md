# Verify observed training state after a restart

TrainLab can compare a resume trace against an uninterrupted reference using
its pinned run context, checkpoint and measurement rules. The comparator
covers the checkpoint boundary and each declared continuation step. It
retains both missing observations and the first observed divergence.

```bash
python -m trainlab.resume_equivalence \
  --plan plan.json --plan-sha256 PLAN_SHA \
  --reference reference-trace.json --reference-sha256 REFERENCE_SHA \
  --resumed resumed-trace.json --resumed-sha256 RESUMED_SHA
```

A `trainlab.resume-plan.v1` plan contains `context_sha256`,
`checkpoint_sha256`, consecutive integer `steps`, and a component dictionary.
For each component, set `{"kind":"exact"}` for typed JSON equality or
`{"kind":"numeric","atol":0,"rtol":0,"length":1}` for elementwise
symmetric absolute/relative tolerance on a fixed-length finite numeric vector.
Choose tolerances before collecting comparisons. The first declared step
identifies the recorded checkpoint boundary.

Each `trainlab.resume-trace.v1` file has a `role` of `reference` or
`resumed`, the exact plan/context/checkpoint hashes, and `samples` ordered by
step. A sample contains `step` and `components`. Missing samples, missing
component values and nulls remain unobserved. A known discrepancy returns
`FAILED` even if a different channel has missing evidence. A complete
agreement returns `TESTED`. The comparison uses only captured channels.
For example, exactly matching RNG hashes does not independently establish
that all random generators were captured.

## Execute the CPU control

With TrainLab and CPU PyTorch installed, run:

```bash
python integrations/trainlab/examples/diagnose_resume.py --root /tmp/veritas-resume
```

The example uses a small constructed regression fit with Adam, dropout,
and an independently seeded shuffled sampler. The uninterrupted process
saves a checkpoint after update five and continues through update eleven.
Four fresh subprocesses consume the pinned checkpoint. One restores every
declared component, and the others each omit optimizer, Torch RNG, or sampler
restoration. Workers retain output and exit receipts. Saved state includes
weights, Adam moment vectors and counters, full RNG hashes, the sampler's
order, cursor and generator hash, and scalar loss. The run binds the driver,
fixture, runtime and training schedule in the context.

The example requires zero numeric tolerance and independently recounts the
first difference. Healthy continuation must agree on all seven captured
steps. Each omitted-state control must differ at the restored boundary.
This is a single-process CPU acceptance case. Mixed precision, GPU state,
distributed workers and arbitrary framework checkpoint schemas need their own
declared capture and execution controls.
