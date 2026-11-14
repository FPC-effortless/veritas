# Observe a small training update and validation retention

`trainlab.training_observer.train_step` runs one bounded, opt-in dense
CPU PyTorch cross-entropy update. The module can be imported without PyTorch.
The actual trainer must supply a model and its optimizer. The wrapper owns
zeroing gradients, running forward and backward, and attempting one update.
This instrumentation changes execution cost. It may stop before an update
when it observes nonfinite values or missing trainable gradients.

A classification batch supplies `inputs`, one integer label per row, and
`mask=None`. A next-token batch uses integer input IDs and shifted integer
labels of shape [batch, sequence], plus a Boolean target mask. The final
position must be ignored. Non-target positions must equal the ignore index.
Observed target IDs must equal the next input token and fit the output
vocabulary. This contract covers ordinary next-token shift and does not
interpret every framework's padding or loss-mask convention.

Hooks inspect selected module outputs (leaf modules by default). The
report identifies the first observed anomalous activation, parameter,
gradient or loss, and counts missing gradients and changed parameters.
A completely unchanged attempted update is a failure in the declared active
optimization step. Deliberately frozen parameters are counted separately.
A caller can select an active update to avoid applying that expectation at
convergence. The wrapper removes hooks even when model or optimizer code
raises. State effects that occurred before such an exception are not rolled
back. Shape errors raise `LabError`. Sparse, CUDA, mixed precision, gradient
accumulation and distributed training need separate workflows.

`freeze_slices` binds validation row identities, labels, slice membership
and acquisition and regression thresholds. `slice_trajectory` accepts a
declared checkpoint order and exact prediction IDs. A partial slice has no
accuracy estimate for that step. The report preserves a known regression
even when other slices are incomplete, and reports the first observed
threshold acquisition and subsequent drop. It checks trajectories over a
fixed labeled panel. It does not infer what caused a drop.

```bash
python integrations/trainlab/examples/diagnose_training_observer.py \
  --root /tmp/trainlab-observer
```

The public CPU example executes normal classification steps and a valid
next-token step. It injects a nonfinite activation, a nonfinite backward
gradient, a zero-learning-rate update, and a wrong target shift. Results
preserve exact step evidence and a fixed labeled two-slice trajectory.
