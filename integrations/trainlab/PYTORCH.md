# Optional PyTorch model backend

This integration exercises the existing TrainLab v2 runner with real PyTorch
commands. Forge still owns the pinned temporal data handoff, the framework owns
training/distributed execution/export, and Veritas retains independent evaluation
authority. The base TrainLab package remains dependency-free and does not import
PyTorch. This adds no general trainer, model server, remote compute provisioning
or protected TEST access.

## Outcome and falsifiers

The requested next step is actual framework and target validation beyond workload
labels. In scope are optional tensor/module diagnostics, a bounded neural example,
CPU distributed execution, checkpoint replay, an offline exported-model check and
a separate CPU container. Existing recipes, the default Alpine service image and
qualification boundaries must continue to work.

Acceptance requires actual two-rank Gloo execution with equal final replica
states; parameter/gradient/activation checks that fail on nonfinite values;
module hooks removed after success/failure; matching uninterrupted versus resumed
stochastic CPU fits; and a fresh offline container loading the exported graph
without the original Python model or eager checkpoint. Injected rank failure,
NaN activations and changed export weights must fail their runs. The optional
unit/integration tests and container acceptance command are the runnable falsifiers.

The implementation reuses the existing runner, ModuleProfiler, Forge Dataset
reader and constructed source generator. PyTorch supplies hooks, DDP, profiler,
optimizer/RNG serialization and export. No alternate trainer/harness is added.
All data and results are constructed operational checks, never independent
capability, source-rights, scientific or commercial qualification.

## Supported execution and limits

| Path | Concrete implementation | Evidence boundary |
| --- | --- | --- |
| CPU single process | Tiny encoder/Tanh/head network; supervised fit and checkpoint-initialized fine-tuning | Constructed fixture only |
| CPU distributed | Real `torch.distributed.run`, two local Gloo ranks, equal nonempty subject partitions, synchronized gradients and final replica-state hashes | One host; no multi-node allocation/recovery |
| CPU checkpoint resume | Model, Adam state, CPU RNG and step restored against the same pinned dataset | Exact 80+5 versus 85-update replay test; no arbitrary trainer/device guarantee |
| Debugging | Tensor, parameter, gradient and selected activation finiteness checks | Inspection synchronizes GPU booleans; keep separate from timing |
| Module profiling | Selected module hooks plus the existing host-wall profiler; framework operator/memory trace | Instrumented inclusive wall time; no automatic target qualification |
| Export/inference | Dynamic-batch `torch.export` graph, numeric parity and separately hashed reference predictions | Version-bound PyTorch graph; not ONNX, Android or a shipping SDK |
| CUDA | Explicit device checks, selected-device synchronization and conditional adapter test; example command selects local-rank CUDA for NCCL | Unvalidated without GPU hardware and a separately reviewed CUDA runtime |

The demonstrated model has 13 learned parameters. Training uses 80 Adam updates
with eight randomly selected examples per rank/update. Single-process and
DDP runs have different global sample exposure and are not a matched scientific
comparison. The second fit initializes weights from the first checkpoint and
starts a new optimizer/RNG sequence. `--resume` instead restores the saved Adam,
RNG and step; the example allows it only for single-process checkpoints on the
same CPU/CUDA device type. Only CPU replay is validated. Generic architecture,
optimizer, data-loader, scheduler, gradient-scaler, distributed or mid-update
resumption is not promised by this example.

## Install the validated CPU runtime

The CPU lock targets **CPython 3.12, Linux x86_64**, with PyTorch 2.15.0+cpu
and NumPy 2.5.4 for tensor/array interoperability.
Its transitive dependency versions and wheel hashes are frozen. Other Python
versions, architectures and accelerator runtimes need a separately reviewed lock.

From the repository root, in your chosen virtual environment:

```bash
python -m pip install --require-hashes -r integrations/trainlab/requirements-pytorch-cpu.txt
python -m pip install ./integrations/forge './integrations/trainlab[pytorch]'
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python integrations/forge/examples/torch_workflow.py --output /tmp/torch-workflow
python -m trainlab serve --runs /tmp/torch-workflow/runs \
  --experiments /tmp/torch-workflow/recipes/test
```

Use a new output directory; existing directories are refused. The workflow runs
supervised training, checkpoint-based fine-tuning, two-rank training, debugging,
profiling, validation, export and a fresh-process export check. Every stage gets
its own recipe, pinned Forge split, declared inputs, run receipt and artifact
hashes. Only train/validation examples enter model code; the constructed TEST
file is verified for release integrity and is never used in fitting or metrics.
Inspect `runtime.json`, per-rank reports, checkpoints and the profiler's Chrome
trace `operators.json` under each run's output directory.

Copied recipes require installed packages or absolute PYTHONPATH entries. The
runtime report records actual PyTorch version, device, process-group backend,
rank/world size and adapter source SHA256. Hashing a requirements file records a
declaration; use the hash-locked installation or image to establish the installed
runtime. The receipt does not attest a complete environment or source authenticity.
Exported model/checkpoint files are trusted operator artifacts, not untrusted-code
sandboxes. Checkpoints are loaded with `weights_only=True`; do not change that
boundary to accept arbitrary pickled Python objects.

## Instrument an existing model

```python
from trainlab.pytorch import check_model, check_tensor, check_activations, profile_modules
from trainlab.runner import write_json

with check_activations(model, names=["encoder", "head"]) as activations:
    loss = criterion(model(inputs), targets)
    check_tensor("loss", loss)
    loss.backward()
check_model(model, gradients=True)

# Use a separate warmed-up pass for timing.
with profile_modules(model, device="cpu", names=["encoder", "head"]) as profiler:
    model(inputs)
write_json(output / "profile.json", profiler.report())
```

By default, hooks select leaf modules. Explicit names select existing entries
from `model.named_modules()`; use `<root>` for the root module. Select at most
256 distinct names, each at most 120 characters. For larger models select the
regions you need. Nested dict/list/tuple tensor outputs are checked; other output
leaves are ignored. Empty inspection fails. Parameters/gradients must be nonempty
dense CPU/CUDA tensors. Gradient checks require gradients for every trainable
parameter, so run them after backward and before zeroing; frozen parameters need
no gradient. Unused trainable parameters deliberately fail this check.

Profiling supports one execution thread/device per context, with one context per
DDP rank. It never moves tensors. Selected parameters, buffers, inputs and outputs
must match the requested device. `device="cuda:N"` checks actual availability and
synchronizes that device around measured regions; there is no silent CPU fallback.
Nested selected regions have inclusive time. An unfinished selected forward or a diagnostic-hook failure invalidates the
context even if the caller catches the original error. Context exit removes all installed
hooks, including on failure. Timing includes hooks/synchronization overhead;
for kernel events, memory attribution or throughput use the framework profiler
and retain its artifacts. The example also captures a framework operator/memory
trace independently of numerical checks.

## Offline CPU container

The existing Alpine image remains the small dependency-free workbench. The
separate `Dockerfile.torch` pins a Wolfi glibc base, versioned CPython 3.12 system
packages and hash-locked CPU wheels. Python dependencies live in a private virtual
environment. The build-only system pip packages are uninstalled through APK;
the runtime retains the APK database and Python distribution metadata for scanning.
It runs as UID/GID 10001, includes Forge and the neural example, and removes pip
and ensurepip. It is not a CUDA image. Build from the repository root:

```bash
docker build --build-arg VCS_REF="$(git rev-parse HEAD)" \
  -f integrations/trainlab/Dockerfile.torch -t trainlab-pytorch:reviewed .
python integrations/trainlab/tests_torch/container_acceptance.py --image trainlab-pytorch:reviewed
```

The Dockerfile accepts the optional BuildKit `proxy_ca` secret. When a build proxy
needs additional trust, pass a combined CA bundle containing the normal roots and
the proxy root. It replaces the CA bundle only during the networked build step;
session trust material stays out of image layers. A dedicated context
allowlist excludes credentials, run stores, private Veritas assets and Git data.
Only trusted public package sources/examples enter the image.

Acceptance executes eight stages inside a non-root container with networking
disabled, read-only root, dropped capabilities, two CPUs, 2 GiB RAM, 128 PIDs,
128 MiB shared memory and 512 MiB writable temporary space. A second identically
restricted container mounts outputs read-only, verifies the receipts, then loads
only the exported graph and reference predictions. It needs neither the original
model class nor an eager checkpoint. Both temporary containers and their generated
volume are removed on exit. This proves local offline CPU operation; it does not
start a public model service or qualify a production installation.

For authenticated workbench hosting, use the existing [production contract](PRODUCTION.md)
and change its chosen image/build to this Dockerfile. Budget the larger CPU image
and per-framework process/memory/shared-memory needs explicitly; the default 1 GiB
Compose limit is not validated for this PyTorch workflow. TLS/identity, operator
acceptance, storage quotas, image security scan and host/device requirements
remain production deployment gates. No image is published or infrastructure created
by these checks.

## Verification

```bash
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python -m unittest discover -s integrations/trainlab/tests_torch -v
python -m unittest discover -s integrations/trainlab/tests -v
python -m unittest discover -s integrations/forge/tests -v
```

The optional framework suite is separate so base-package tests need no torch
installation. Missing PyTorch makes that suite fail rather than imply support.
CUDA tests explicitly skip when hardware is absent; a skip is **NOT_RUN**.
The manual `TrainLab PyTorch CPU acceptance` workflow performs framework, image,
existing workbench/recovery and image-security checks without publishing an image.
The tiny fits measure software operation, not authentic-data capability or
independent Veritas qualification. New release, GPU, multi-node and commercial
claims require their own evidence and authority.

## Local developer evidence — 2026-11-02

The optional CPU suite ran 13 checks: 12 passed and one CUDA check was skipped
because no GPU is present. Existing TrainLab (49), Research Lab (49), Forge (68)
and Forge workbench (22) checks passed. Wheel/sdist build, a base-wheel install
without torch, Ruff and the new-code Bandit check passed. The two offline
container checks completed all eight stages and the fresh exported graph matched
its reference with maximum error 0. The existing authenticated container,
restart and backup/restore acceptance also passed on the optional image.

**The original Debian candidate failed image security.** Trivy 0.76.1 scanned its
pinned Debian 13.7/glibc image, including its installed PyTorch 2.15.0+cpu metadata.
It reported
45 HIGH entries across nine unique advisories and zero CRITICAL entries, with no
vendor fixed versions listed. The findings cover system packages including
util-linux, ACL, ncurses, SQLite, systemd and Perl. The previous Debian 12 base
also had critical findings and was replaced. No finding was suppressed, no package
inventory was removed, and the manual workflow continues to fail on any HIGH or
CRITICAL result, including unfixed findings. The remediated runtime requires its
own fresh scan and functional acceptance; passing those checks does not confer
production deployment authorization. CUDA, NCCL/multi-GPU, multi-node execution
and physical-device qualification remain unrun.

## Image security remediation — 2026-11-03

The runtime change must clear the image scan without ignoring unfixed findings,
retain OS and Python package inventories, preserve the offline CPU workflow and
authenticated recovery checks, and leave the base package dependency-free. The
falsifiers are the failing Debian scan, tensor/NumPy interoperability, the real
framework suite and the two existing container acceptance commands.

The replacement pins a maintained Wolfi base by digest, CPython 3.12.16 system
packages and the original PyTorch CPU wheel. NumPy 2.5.4 is now hash-locked and
included in the optional `pytorch` extra: the previous image warned that NumPy
could not initialize and failed actual tensor/array interchange. The added check
failed before this dependency was supplied and passes in the rebuilt image.
Build-only pip is removed using the package manager; the APK database and
installed Python distribution metadata remain available to Trivy. Container
acceptance checks their presence and verifies that pip and ensurepip are absent.

Local checks used Trivy 0.76.1 with a newly downloaded database updated at
2026-11-03T01:30:30Z. The Debian baseline still failed with 45 HIGH entries across
nine advisories. The replacement reported **zero vulnerabilities at every
severity**, with 35 OS and 28 Python package records, including PyTorch and NumPy.
The manual workflow still rejects every HIGH/CRITICAL result, including unfixed
findings, and now retains the complete package inventory in its JSON artifact.
No ignore rule, severity override or inventory deletion was added.

Inside the actual non-root/read-only image, 14 optional framework checks ran:
13 passed, including exact optimizer/RNG replay and NumPy interoperability; the
CUDA check skipped. The two offline containers completed eight stages and the
independent graph load had maximum error 0. Authenticated workbench, Forge
handoff, restart and backup/restore checks passed. A parallel local run exhausted
workspace storage; recovery passed when rerun alone after discarded trial images
were removed. Existing TrainLab (51) and Forge (68) tests also passed.

These are recorded CPU software and image-security checks, not a timeless clean
bill of health or production deployment authorization. Each proposed image needs
a fresh scan and the operator gates in [PRODUCTION.md](PRODUCTION.md). CUDA/NCCL,
multi-node and physical-device qualification still require an available GPU
runtime and their own evidence; no GPU was attached for these checks.
