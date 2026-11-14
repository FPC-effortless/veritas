# Architecture-agnostic diagnostic workbench

DIAGNOSTICS-001 (#519) supplies a bounded Python SDK and a reproducible public
acceptance example. It connects callable adapter capabilities, explicit diagnostic
coverage and measured session time. It is the first workbench slice, not the full
[24-feature roadmap](diagnostic-roadmap.md), a universal model-health score or
scientific/frontier qualification.

## Install and exercise the ecosystem

Install the four existing packages from one checkout as described in the
[ecosystem guide](README.md). The standard-library acceptance needs no API key,
downloaded model, GPU or new required runtime dependency:

```bash
python integrations/trainlab/examples/diagnose_models.py --root /tmp/diagnostic-demo
```

This freezes 128 public constructed scalar examples in Forge, selects validation
through the as-of reader, invokes CLI/store/wrong-model adapters through separate
TrainLab recipes, retains prediction files and diagnostic reports as hashed
artifacts, and imports receipts/findings into Research Lab. No training occurs.
Forge verifies all release files internally; protected TEST is not selected or
scored. These are invented software controls, not independent causal mechanisms.

When scikit-learn, NumPy and PyTorch are already installed, exercise those real
libraries as well:

```bash
python integrations/trainlab/examples/diagnose_models.py --root /tmp/diagnostic-all \
  --backends cli store sklearn torch wrong
```

The scikit-learn linear estimator and PyTorch linear module have fixed, explicitly
assigned coefficients for `y=2x`. Neither is trained. The generic CLI executes a
separate local Python process. The stateful control is an explicit record store
with clear/repopulate operations, **not native CSM, DPSL or learned memory**.
`wrong` returns `3x`: its execution can succeed while its answer check is FAILED.
Missing optional libraries expose missing capabilities rather than a clean pass;
the resulting incomplete run can also lack required prediction artifacts.

Look at `summary.json`, `runs/*/output/diagnostics/report.json`, corresponding
`predictions.json` files and `research_lab/lab.sqlite3`. The summary is navigation,
not a verified score authority. Verify the underlying TrainLab receipts before
using an artifact. The frozen protocol binds the four installed Python source
trees and selected dependency versions; it is not a complete OS/binary attestation.
The example's model identity names a fixed executable recipe, not a learned
checkpoint. Original recipe bytes, code, Forge manifest and configuration are
retained; report identities in the general SDK are caller declarations.

## Connect an existing model

`trainlab.research_diagnostics.Adapter` takes a bounded mapping of names to
callables and explicit state semantics: what persists, whether queries mutate
state and what reset means. There is no neural-network inheritance requirement.
Only supplied callable operations are capabilities; the SDK does not infer that
every PyTorch object exposes gradients or that every API supplies probabilities.

`Diagnostic(name, version, requires, check, scope)` declares a versioned check.
Its callback receives a context; calls go through
`context.invoke(capability, ..., phase="answer")`. Valid phases are setup,
preprocess, load, encode, update, retrieve, answer, decode, verify and persist.
Checks return `status`, a bounded `summary`, and finite scalar `metrics`.
Model/data/code/configuration SHA256 identities are required at construction.

```python
from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench

adapter = Adapter("existing-model", {"predict": model.predict}, {
    "persists": "frozen fitted parameters",
    "query_mutates": False,
    "reset": "not_applicable",
})

def compare(ctx):
    predictions = ctx.invoke("predict", inputs, phase="answer", condition="cold")
    correct = sum(a == b for a, b in zip(predictions, expected))
    ok = len(predictions) == len(expected) and correct == len(expected)
    return {"status": "TESTED" if ok else "FAILED",
            "summary": "Exact agreement on the declared control slice.",
            "metrics": {"correct": correct}}

report = Workbench(adapter, identities, "new-diagnostic-output",
                   max_calls=20, max_seconds=30).run([
    Diagnostic("control_agreement", "1", ("predict",), compare,
               "declared control slice; no broad capability inference")
])
```

The example assumes the caller supplies `model`, `inputs`, `expected` and the
four real hashes in `identities`. Input/output payloads and exception messages
are not copied into the generic report. Callers still own the privacy of check
summaries, metric names and adapter declarations; output directories are private
mode 0700. This is trusted local code, not a hostile-plugin sandbox.

## Coverage is explicit

| Status | Meaning |
| --- | --- |
| TESTED | The implemented predicate was satisfied in its declared scope. |
| FAILED | A check observed a failure; this is not an automatic causal explanation. |
| INCONCLUSIVE | The check lacked a conclusion, raised an exception or exhausted its budget. |
| UNSUPPORTED | One or more required callable capabilities were absent. |
| NOT_RUN | The check was unselected, pending at interruption, or stopped by an earlier budget limit. |

The report records every catalogued check, its version, scope, requirements,
missing capabilities, result and reason. It does not enumerate diagnostics that
the caller never placed in the catalog. No averaging into a health percentage is
performed. The example's unsupported gradient/reset checks remain visible.
Top-level COMPLETE means the controller finished iterating the catalog, not that
every check ran or passed. Read individual statuses and cost coverage separately.

## Cost and interruption semantics

Total session wall time is a direct monotonic interval after catalog validation
and output-directory creation through check completion. It includes diagnostic
overhead and prior journal writes; it is
**not the sum of operation spans**. Adapter construction, caller prework and the
catalog validation, directory creation and final report serialization are excluded.
The outer TrainLab process
elapsed time separately includes startup and imports before the SDK run boundary.
Framework loading inside the example's load operation is measured.

Each operation records a sequential ID, phase, diagnostic, caller-declared
cold/warm/unspecified condition, relative start/end, duration, success/failure and
an optional reference to an earlier failed matching operation. There are no
automatic inferences about cache warmth from the cold/warm declaration. A deadline
consumed by journaling or pre-call synchronization leaves a BUDGET_CANCELLED intent
and does not execute the operation callback. Attempt limits include such reserved
intents, not just callbacks that actually start. There are no
automatic retries. Nested or concurrent SDK operations are rejected; distributed
aggregation and overlapping span analysis are not implemented. Raw samples are
retained rather than implying statistically reliable tail latency from tiny runs.

Required phases are declared by the workload. Missing successful phases,
exhausted budgets, interrupted sessions or synchronization failures leave cost
coverage INCOMPLETE. Otherwise MEASURED describes only this declared interval and
phase coverage, never fair comparison, hardware attestation or cost optimality.
An asynchronous adapter needs an explicit `synchronize` callback for device
completion timing. Without one, host timing remains visible but device timing
is unverified and cost coverage is incomplete. Synchronization failures cannot
turn a failed call into success or replace the original model exception.

Memory, energy and monetary cost are explicitly NOT_MEASURED. Runtime reports
contain basic Python/OS/machine information; hardware device identity is not
attested. Provider billing, memory limits, GPU quotas, rates, hardware counters,
sampling uncertainty and timing-overhead calibration remain future work.

The SDK enforces an operation-count limit and checks wall time between calls.
An active callback can overrun; its full observed duration is retained. These are
cooperative limits, not hard preemption or provider API-call accounting. One
adapter operation can make multiple hidden internal calls. Run trusted code
through a TrainLab recipe timeout for process supervision and retain that receipt.

Atomic `report.json` updates record STARTED intent before callbacks. A killed
process can therefore leave an unfinished attempt with no invented end time.
Completed earlier observations remain available. A caught ordinary exception is
INCONCLUSIVE; process-level interrupts preserve PARTIAL state and propagate.
An output directory is single-use. No crash resume, cached PASS reuse or implicit
re-dispatch is supplied. Preserve the interrupted report before a new run.

Existing lifecycle preflight/review gates still govern that workflow. This SDK
does not grant experiment admission, training authority or an alternative route
around those gates. Native architecture comparisons still need qualified data,
controls, supervision, budgets, independent review and fresh evaluation.
