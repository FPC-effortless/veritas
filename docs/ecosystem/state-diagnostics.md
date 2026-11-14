# State diagnosis, failure reduction and repair evidence

DIAGNOSTICS-005 (#528) advances the [24-feature program](https://github.com/FPC-effortless/veritas/issues/525)
with `trainlab.state_diagnostics`. It connects actual state operations to paired
observations, a bounded reproduction and explicit fresh/regression criteria.
This is a local standard-library workflow for trusted adapters. It does not
establish a learned memory advantage, universal state correctness or frontier
qualification.

## Five APIs

| API | Contract | Evidence and limits |
| --- | --- | --- |
| `lifecycle` | Run inside a workbench check; supply initial events/expected map, query panel, ordered steps with complete expected maps and touched query IDs, supported operation names | Retains actual before/after answers and wrong query IDs. Conditional damage counts only untouched facts correct before the update. Missing answers produce incomplete coverage; known faults survive interruption. |
| `write_intervention` | Reset/replay identical initial history, apply one write in normal arm and omit it in the second arm | Retains paired answers and changed query IDs, with reconstruction work in the operation ledger. Frozen weights and determinism are assumptions. An observed effect is not causal attribution of a learned capability. |
| `restore_isolation` | Source reset/update/query/snapshot plus independent peer reset/update/query/restore operations; distinct observable mutations for both recipients | Checks both arms after restore, source-to-peer and peer-to-source interference, and restoring the same snapshot again. Does not prove absence of undeclared shared backing. |
| `minimize_failure` | Bounded events plus deterministic predicate: true means failure, false means clean, null means unknown | Deletes chunks and then checks single deletions. Returned candidate is confirmed failing. Budget/unknown/exception retains the last confirmed failure, with no minimality claim. |
| `verify_repair` | Complete named fresh and regression panels, required row IDs, expected and before/after observations, freshness declarations, selection groups, hypotheses and linked intervention evidence | Checks fresh gain and damage conditional on previously correct regression items. Reused IDs/groups, missing observations and unknown freshness cannot produce a clean comparison. No independent freshness attestation or causal conclusion. |

All outputs use `trainlab.state-diagnostics.v1`, a version and an input hash.
`TESTED` applies only to the declared criterion. `FAILED` retains observed
violations. `INCONCLUSIVE` covers interruption or missing evidence; `UNSUPPORTED`
covers missing capabilities. Scientific qualification is always `NOT_QUALIFIED`.
Expected answers and operation semantics are supplied by the task author; these
APIs do not invent a history oracle or decide what deletion means for a model.

Persist the inner reports separately, as the example does. Workbench callback
outcomes accept `TESTED`, `FAILED`, or `INCONCLUSIVE`; declare `Diagnostic.requires`
for catalog-level unsupported checks, rather than returning an inner
`UNSUPPORTED` result directly as a callback outcome.

## State adapter and coverage

The first three APIs receive the active `Workbench` context. Their operations
are `reset()`, `update(event)` and `query(input)`. Lifecycle checks must declare
which event `op` values the adapter supports. A task can encode acquisition,
overwrite, delete, retract, retention or interference events using its own valid
semantics. Unsupported event types are rejected before execution.

Queries must be declared nonmutating. Mutable query-state architectures need a
different protocol and receive `UNSUPPORTED` here. Inputs are copied before
callbacks; finite JSON answers are copied immediately to preserve observations.
Opaque snapshots are not serialized or defensively copied: ownership defects
must remain observable. The restore probe requires `snapshot()`, `peer_reset()`,
`peer_update(event)`, `peer_query(input)`, and `peer_restore(snapshot)` on an
independently constructed peer. The caller must declare both peer and source
semantics honestly. A no-op mutation cannot establish isolation.

Every callback and synchronization uses the existing operation ledger. Exceptions
and cooperative time/call exhaustion preserve partial findings. The report marks
completed steps separately from started steps and records partial answer maps.
An empty eligible set produces a null conditional-damage rate, never zero damage.
Known wrong answers remain failures if a subsequent query raises. Final-operation
time overruns also prevent a `TESTED` completion. Use the outer TrainLab recipe
timeout for process supervision; these callbacks do not provide hard preemption.

## Reduction and repair

The reducer supports at most 128 events and explicit call/time budgets. The
predicate must reset all state for every trial and define the same failure
throughout. Malformed predicate results and exceptions are unknown outcomes.
Each trial retains candidate hash, size, outcome and error type. Single-deletion
minimality is conditional on a deterministic predicate, not a global minimum or
a proof that the remaining events explain the cause. Wrap the predicate in a
workbench operation to retain each call durably. Interrupting the whole process
can leave an incomplete outer receipt; no automatic resume is claimed here.

Repair rows have `id`, `group`, `expected`, `before`, and `after`. Both observations
carry `status` (`observed`, `missing`, or `failed`) and a finite JSON `value`.
Null is a valid observed answer; missing is represented by status. Every required
row must be present and paired before a complete comparison is possible.
Fresh and regression panels cannot reuse row IDs, and fresh groups cannot overlap
regression or declared selection groups. Identifiers alone do not prove semantic
independence; related generator mechanisms remain a separate admission question.

The default criteria require positive fresh accuracy gain and zero newly damaged
previously correct regression items. Explicit alternative thresholds are bound
into the input hash. With no previously correct regression item, retention is
inconclusive. Hypotheses and intervention observations stay distinct fields;
there is no automatic causal ranking, information-gain optimizer or repair
selection policy in this module.

Reports retain authorized predictions and observations. They are not a privacy
filter. Do not export sensitive task data without its existing authorization.

## Executable ecosystem controls

```sh
python -m pip install -e . -e integrations/forge -e integrations/trainlab -e integrations/research_lab
python integrations/trainlab/examples/diagnose_state.py --root /tmp/veritas-state-diagnostics
python -m unittest discover -s integrations/trainlab/tests -p test_state_diagnostics.py
```

Use a new output directory. Forge freezes 128 constructed subjects; only
train/validation readers are used. Four TrainLab workers exercise clean, stale
delete, collateral-damage and aliasing stores. The first validation subject is
used for diagnosis, the second for regression and a third distinct subject for
fresh repair checks. Diagnostic subjects are included among selection groups.
All share the same simple generator; this is an engineering acceptance example,
not a generalization experiment.

The reducer compares actual faulty-store predictions with a separate history
replay oracle. Noise writes precede the relevant state transitions. The stale
delete and collateral controls should reduce to short confirmed failures. The
alias fault is visible through the restore probe rather than this simple history
predicate. A clean store has no failure to minimize. Replacing a stale-delete
store with the clean implementation is checked on fresh and retained regression
subjects. Repair quality is not inferred from the lifecycle score alone.

TrainLab retains raw reports, operation receipts and hashes; Research Lab links
the findings to Forge and TrainLab identities. Source, selected view, recipe,
protocol and Python runtime trees are bound, with runtime checks before/after
execution. There are zero model fits. Timings include diagnosis and replay and
must not be presented as architectural inference-cost comparisons.

This slice advances lifecycle/intervention/reproducer/repair functionality.
Native learned-state adapter acceptance, a graphical failure browser, automatic
hypothesis ranking, distributed resource enforcement and population-level
diagnostic sensitivity/productivity remain outstanding.
