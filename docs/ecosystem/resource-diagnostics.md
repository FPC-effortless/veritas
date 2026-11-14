# Bounded CPU sessions and resource receipts

`trainlab.resource_diagnostics.run_command` supervises one trusted local command
on Linux. It measures direct elapsed session time, retains failed attempts, and
applies inherited CPU, virtual-address-space and file-size limits before exec.
It extends roadmap features 3, 19 and 20. It does not qualify an architecture,
measure GPU work, or implement a security sandbox.

## Usage

```python
import sys
from pathlib import Path
from trainlab.resource_diagnostics import EXECUTION, run_command

receipt = run_command(
    [sys.executable, "inference.py"],
    Path("new-session"),
    cwd=Path("project"),
    identities={"model": model_sha, "dataset": data_sha,
                "code": code_sha, "configuration": config_sha},
    workload_sha256=workload_sha,
    execution=EXECUTION,
    limits={"wall_seconds": 10, "cpu_seconds": 5,
            "address_space_bytes": 512 * 1024**2, "file_bytes": 1024**2},
)
```

Supply exact SHA256 identities, an absolute executable, an existing working
directory and a new output directory. The required execution declaration is
`{"device":"cpu","synchronous":true,"detaches":false,"remote_work":false}`.
This is a caller assertion; the meter does not attest what arbitrary code does.
Unsupported declarations are refused before an output directory is created.
Do not put secrets in retained command arguments, configuration or logs.

Limits are explicit: wall 0.05–3600 seconds, integer CPU 1–3600 seconds,
address space 64 MiB–1 TiB, and individual files 4 KiB–64 MiB. The worker sets
both soft and hard limits and disables core dumps. Resource ceilings already
imposed by a parent can prevent launch; that remains a failed attempt.

## Measurement and coverage

The wall interval begins immediately before launching the supervisor's fresh
worker and ends after leader reaping and process-group cleanup. It includes
worker startup, target import/loading, target preprocessing, updates, queries,
serialization, target shutdown and observed cleanup. It excludes preparation
of the request and final receipt serialization. Put all work relevant to your
claimed session inside the target. Costs of external services are unsupported.

Elapsed time is measured directly, never obtained by adding overlapping spans.
Linux `wait4` supplies user/system CPU and peak RSS for the leader and the
children it waited for. Peak RSS is **not** simultaneous aggregate process-tree
RAM. Address-space limits are **not** RSS limits. CPU/address-space limits apply
per process, and file size per file; they are not aggregate tree/storage quotas.

`MEASURED` means the declared synchronous CPU session completed with exit zero,
within the observed wall budget, with matching limit evidence, unchanged request,
retained logs and process usage. It says nothing about output correctness.
Independent scoring remains necessary. Any error, timeout, interrupt, unexpected
remaining process-group member or missing/changed evidence makes cost coverage
`INCOMPLETE`, retaining elapsed work rather than awarding a cheap successful run.
Signals do not identify the cause of failure on their own. The receipt deliberately
does not infer OOM or CPU exhaustion solely from an exit status.

The supervisor kills the target process group on timeout and reaps its direct
child. It also kills observed remaining members of that group after leader exit;
these runs cannot qualify as complete. Non-child descendants are not claimed to
be reaped by this code. Detached/reparented groups, remote work and untrusted code
are outside the contract. The supervisor must remain alive: a host loss or
SIGKILL can leave a STARTED receipt and unresolved work. There is no container,
cgroup, parent-death or aggregate process-tree accounting guarantee here. Place
any outer TrainLab timeout above the sum of inner budgets and cleanup allowance.

Receipts record the declared identities/workload, OS-reported CPU/platform,
boundary and limit identities, invocation, applied limits, raw times, RSS and log
hashes. Hardware identity is not proof of exclusive hardware or matched load.
An optional `hourly_rate={"per_hour":0.5,"currency":"USD","as_of":"2026-11-14"}`
adds a declared single-allocation wall-rate estimate. It is not a bill, energy
measurement, API price lookup or a claim that the supplied rate is accurate.

## Composed engineering example

After installing the ecosystem packages, run:

```bash
python integrations/trainlab/examples/diagnose_session_cost.py --root /tmp/new-cpu-sessions
```

Forge freezes 256 constructed public records. Only its validation view enters
these engineering sessions; no protected test scoring occurs. TrainLab runs a
workbench that measures direct dictionary updates and history replay at 8 and 16
events, each repeated 100 times. A separate prefix-history oracle scores every
saved prediction, including absent-key answers. Both are deterministic reference
programs, not learned models. A fifth no-op session exposes startup scale without
subtracting it or calling it a calibrated overhead study. All five attempts,
requests, applied-limit markers, logs and four prediction files are retained as
TrainLab artifacts. Research Lab indexes the Forge release, verified run and
report.

Quality–cost reports compare the two methods only within each identical workload,
hardware and boundary identity. Failed attempts remain incomplete. The four
measurements have no seed/repetition uncertainty estimate, controlled host
isolation or credible architecture-ranking interpretation. Most work is startup
at this size. The example proves evidence plumbing, not a lower inference-cost
result for CSM, LRC or another learned architecture. Zero model fits are performed.

## Qualification checks and remaining work

Unit controls exercise successful/nonzero executions, CPU exhaustion,
address-space denial, bounded file writes, timeout cleanup, orphaned members,
interrupted supervision, changed/missing evidence, Boolean/integer ambiguity,
supervisor delay beyond deadline and unsupported execution declarations. These
are bounded injected faults and clean controls; real-project sensitivity,
false-alarm rates and overhead remain unmeasured.

Outstanding: synchronized GPU tracing, aggregate process-tree RAM/CPU quotas,
energy, API quotas and retries, shared allocation billing, warm-server concurrent
request distributions, restart reconciliation, per-phase trace import, and native
learned-state quality–cost acceptance. Report these as unsupported or not measured;
do not infer them from the host wall clock or this command's exit code.
