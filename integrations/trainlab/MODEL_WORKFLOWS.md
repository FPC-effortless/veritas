# Model workflows across Forge, TrainLab and Veritas

Forge freezes source and temporal split bytes. TrainLab executes trusted model
commands and records their inputs, outputs, diagnostics and acceptance criteria.
Veritas supplies a separate evaluation and qualification boundary. Existing
framework trainers, distributed launchers and target runtimes remain responsible
for training and inference; this integration adds no replacement trainer or model
server.

## Outcome and acceptance contract

This feature adds workload-aware recipes, metric acceptance checks, finite-value
inspection, and named-module timing without changing v1 recipe behavior. The
runner, CLI, dashboard and saved-record verifier share the same validation path.
A zero exit code with a metric outside its declared bounds must fail, retain
metrics/artifact hashes, and return a nonzero CLI status. A changed workload or
acceptance declaration in a stored run must fail verification against its saved
recipe. Old recipes and Research Lab consumers must continue to work.

The falsifiers are the workflow/diagnostics tests and the constructed Forge model
lifecycle. The implementation reuses the existing runner, artifact hashing,
point-in-time dataset reader, and standard library. No framework dependency,
cloud provisioning, paid compute, protected TEST evaluation, model serving or
scientific promotion is in scope.

## Optional real framework execution

The [PyTorch backend](PYTORCH.md) supplies tensor/gradient/activation checks,
automatic module instrumentation and a separate real-framework acceptance path.
Its CPU example exercises supervised/fine-tuning, two-rank Gloo training, exact
optimizer/RNG replay and version-bound model export in offline containers. The
base workflows below continue to require no framework installation.

## Recipe v2

Use the existing recipe fields with `schema: trainlab.experiment.v2`, plus:

```json
{
  "workload": {
    "kind": "train",
    "training_method": "fine_tuning",
    "execution": "single_process"
  },
  "checks": {
    "validation_loss": {"max": 0.25},
    "accuracy": {"min": 0.9, "max": 1.0}
  }
}
```

This is a fragment, not a complete recipe. Every check must reference a declared
metric. Bounds are inclusive finite numbers; booleans, unknown metrics, empty
bounds and reversed intervals are rejected. `{}` explicitly means no threshold
checks. All declared metrics must still be finite and present. Checks represent
operator acceptance criteria, not independent Veritas qualification. Failed
threshold checks retain the observed metrics and declared artifacts for debugging.

| Workload kind | Typical command/artifacts | Training method |
| --- | --- | --- |
| `train` | Existing framework trainer; checkpoint, optimizer/RNG state, learning curves | Required |
| `debug` | Short reproducible run; numerical checks, anomaly report, stderr | `null` |
| `profile` | Instrumented model; named module timings, memory report or framework trace | `null` |
| `test` | Validation/regression harness; predictions and test report | `null` |
| `export` | Existing converter; exported model and parity/operator report | `null` |
| `deployment_check` | Foreground target acceptance command; local inference/parity evidence | `null` |

Training methods are `supervised`, `self_supervised`, `fine_tuning`,
`distillation`, `reinforcement`, `continual`, and `custom`. Execution is
`single_process`, `distributed`, or `external`. These are **declarations** about
the command, not measured or automatically configured capabilities. For example,
a reviewed `torchrun` argv can launch distributed training through the same
runner. The command must initialize framework seeds, wait for all workers, save
its declared outputs and propagate failure. Only supervised and fine-tuning
commands are exercised by the included constructed model example.

An external runner adapter must wait for remote completion, fetch and verify its
outputs, propagate failure, and implement remote cancellation. A local timeout
cannot cancel an external provider's job. Distributed/GPU resource provisioning,
multi-node recovery, arbitrary checkpoint resume, actual device measurements and
untrusted-job isolation are not supplied by these labels.

V2 records use `trainlab.run.v2`. V1 recipes and records keep their original
shape. Comparisons flag differing workloads and checks; missing v1 declarations
are not inferred. The dashboard displays workloads and acceptance bounds, and
search matches kind, training method and execution. File verification binds the
v2 declarations to `experiment.json`; local hashes are not signatures and cannot
prevent an operator rewriting both record and recipe.

## Debugging values and profiling modules

Instrument the existing model code explicitly:

```python
from trainlab.diagnostics import ModuleProfiler, require_finite
from trainlab.runner import write_json

require_finite("parameters", parameter_scalars)
require_finite("gradients", gradient_scalars)
profile = ModuleProfiler()
with profile.measure("encoder"):
    encoded = model.encoder(inputs)
with profile.measure("decoder"):
    predictions = model.decoder(encoded)
write_json(output / "profile.json", profile.report())
```

`require_finite` rejects empty/non-numeric/nonfinite scalar iterables without
printing their values. Convert tensors explicitly using the relevant framework;
this helper never copies tensors from devices automatically. It complements the
framework's anomaly detection and debugger. Run interactive debugging separately;
TrainLab jobs use a noninteractive stdin and preserve stdout/stderr.

The profiler records call count, failed calls, total/min/max seconds for up to
256 explicitly named regions. Use one profiler per worker/thread. Nested regions
have inclusive time, so summing them double-counts nesting. Warm up the model
before measuring. Timing uses the host wall clock and includes instrumentation
overhead. Asynchronous accelerators require explicit synchronization, for example
`ModuleProfiler(synchronize=torch.cuda.synchronize)` on the selected CUDA device.
For kernel/operator traces, allocation/peak memory, throughput, accelerator events
or distributed rank attribution, use the framework profiler and declare its
report/trace as a recipe artifact. Host timing is not physical-device qualification.

## Run the integrated example

From the repository root, choose a new output directory:

```bash
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python integrations/forge/examples/model_workflow.py --output /tmp/model-workflow
python -m trainlab serve --runs /tmp/model-workflow/runs \
  --experiments /tmp/model-workflow/recipes/test
```

This creates a pinned Forge release with 30 constructed subjects. Seven real
foreground commands train a two-parameter model, fine-tune its saved checkpoint,
check finite parameters/predictions, time encoder/affine/output modules, check
validation error, export a tiny JSON model and check local export parity. Each
stage has an independently rerunnable recipe, fixed split identity, declared
inputs and hashed artifacts. Later stages pin the checkpoint bytes from the
previous successful training run. Fine-tuning starts a new seeded fit; it does
not claim uninterrupted optimizer/RNG resume. The scripts read train/validation
examples only; the local constructed TEST file is verified for dataset integrity
and never used for fitting or metrics.

Inspect profiles under `runs/<id>/output/profile.json` and errors in the run's
stderr log. Change a copied recipe's bound to exercise the failure path. Existing
demo directories are refused. To rerun any stage, pass its `recipe.json` to
`trainlab run`; replay requires both installed packages or absolute PYTHONPATH
entries. Generated timing artifacts are naturally nondeterministic.

The export is an illustrative affine JSON format, not ONNX or a shipping SDK.
The deployment stage performs local host inference only; it starts no service,
contacts no target and authorizes no production deployment. All results remain
`CONSTRUCTED_ONLY` / `NOT_QUALIFIED`. Authentic source rights, protected TEST,
independent Veritas evaluation and target-device performance require separate
execution evidence.

## Verification

```bash
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python -m unittest discover -s integrations/trainlab/tests -v
python -m unittest discover -s integrations/forge/tests -v
```

The lifecycle test also changes exported weights and requires the numerical parity
check to fail despite successful process completion. The existing TrainLab CI
runs these tests, package installation and browser checks. This feature does not
create a new Veritas release or authorize merge, release or deployment.
