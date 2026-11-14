# Assessment-driven research checks

DIAGNOSTICS-009 ([#536](https://github.com/FPC-effortless/veritas/issues/536))
turns the November 14 assessment's comparison gaps into executable checks in
`trainlab.assessment_diagnostics`. It extends the existing
[comparison packs](experiment-diagnostics.md), [state repair checks](state-diagnostics.md)
and [CPU resource meter](resource-diagnostics.md). Standard library only; no model
architecture, trainer, accelerator or online service dependency.

| API | Result | Boundary |
| --- | --- | --- |
| `generalization_audit(training, evaluation)` | Seen/unseen row IDs for each categorical axis, extrapolation beyond declared numeric training ranges, overlapping IDs/groups | Labels for mechanisms, identities and generators are caller declarations. Renaming an ID does not establish independent composition. This inventories the supplied panel, not performance. |
| `paired_slices(rows, required_ids=..., required_seeds=...)` | Correct counts, rescued/damaged answers and query differences by seed, payload and template; leave-one-payload-out differences including each seed | Requires every declared seed/row pair exactly once and stable metadata. Query-weighted descriptive effects, no confidence intervals, causal attribution or complete-map computation. |
| `training_order_audit(arms)` | Exact example/supervision exposure multiset, update count, batch-size sequence, initialization and optimizer identity comparisons; changed order remains visible | Audits the submitted schedule, not its execution. Equal totals do not establish equal FLOPs, time, tuning effort or competence. |
| `measured_quality_session(...)` | Executes a bounded CPU command, scores its saved outputs, binds predictions/expected panel/receipt/scorer/query semantics and produces a context-bound quality–cost point | Trusted local synchronous CPU workloads. Startup/loading included; scoring excluded. Failed/incomplete sessions and malformed predictions retain receipts but yield no point. No GPU, warm-server or statistical speedup claim. |

Every report has schema/version, a canonical finite-JSON input hash and
`scientific_qualification=NOT_QUALIFIED`. Malformed observations raise `LabError`.
Hashes bind supplied evidence; they do not attest truthful metadata, code/model
identity, baseline competence or execution provenance. Reports may expose supplied
IDs and predictions; use only data authorized for the intended export.

## Generalization and sensitivity

Descriptor rows have `id`, `group`, `axes` (nonempty string-to-string mapping), and
`scales` (string-to-nonnegative-integer mapping). All rows must expose the same
keys. Useful axes include causal template/composition, payload class, individual
identity and generator family. Useful scales include active records, history
length and link depth. Declare those separately: a longer history with fixed
active information does not test increased active capacity. Encode exact mechanism
identity, not an arbitrary renamed example, in a mechanism axis.

An unseen composite label can still contain familiar primitives. An axis value
that encodes a whole identity set only tests novelty of that set; it does not
establish that each member identity is unseen. The caller must choose descriptors
at the level of the intended claim. Unknown or unavailable metadata should not be
invented to fill this strict contract; report that axis as uninspected externally.

Paired outcome rows contain `id`, `seed`, `group`, `payload`, `template`, and
Boolean `candidate`/`baseline` correctness from an independent scorer. Missing or
failed seeds belong in the existing comparison ledger, not invented outcomes.
Primitive-value probes can use their own template labels. Retain their measured
outcomes before attributing a lifecycle advantage to composition. Payload deletion
is a diagnostic sensitivity analysis, never permission to remove difficult values
from the primary result. Groups remain declared and correlated examples are not
treated as independent samples. Use the existing `paired_statistics` only with a
defensible sampling unit. Complete-map and uninterrupted multi-query evaluations
need separate protocols; query accuracy cannot substitute for either.

## Staged versus joint training

Each arm has `id`, `initialization_sha256`, `optimizer_sha256`, and ordered
`updates`. An update is a nonempty batch of `{example_sha256, supervision_sha256}`.
Hashes must bind the actual example and every answer/process/route/teacher label.
Optimizer identity must include loss weights, schedules, precision, clipping and
freeze masks. Initial-state identity must include model, optimizer and RNG state.
Use a separate comparison per model/seed; architecture comparisons generally have
different initial-state identities. The auditor allows different example order but
requires the same batch-size sequence and total exposures for a `TESTED` match.

Record tuning trials, selection rules, failed attempts and baseline competence in
`comparison_ledger`. This check alone cannot establish “well-trained alternatives.”
Evaluate behavior on prospective fresh and retained regression panels using
`verify_repair`; representation consistency never overrides behavioral damage.

## Measure the same workload

```python
from trainlab.assessment_diagnostics import measured_quality_session

report = measured_quality_session(
    [absolute_python, absolute_driver, "{inputs}", "{predictions}"], new_directory,
    cwd=project_directory, identities=exact_model_data_code_config_hashes,
    inputs=[{"id": "query-1", "input": public_input}],
    expected=[{"id": "query-1", "answer": expected_answer}],
    semantics={"query_mode": "fresh_replay", "operations": "lifecycle-v1"},
    limits=explicit_cpu_limits,
)
```

The driver receives ordered JSON input rows and writes ordered `{id, answer}`
rows to the provided prediction path. Null is a valid answer; missing output is
not. Canonical JSON equality distinguishes `true`, `1` and `1.0`. Every input and
expected row must match exactly by ID/order; duplicate or extra rows are refused.
The session owns a new output directory. Input mutation, symlink output, oversized
output and changed output during scoring prevent a point. No untrusted-code or
concurrent-writer security boundary is claimed. A missing run receipt after abrupt
host failure remains unresolved; there is no restart recovery here.

Workload identity includes inputs, expected answers, scoring semantics and
`fresh_replay` versus `continuous` query mode. Feed non-null points to the existing
`quality_cost`; different panels, expected values or query semantics cannot produce
a shared Pareto set. Preserve all attempts, including those without points. Do not
silently discard failures and compare successful retries as whole-workflow cost.
One call measures one attempt; cross-call retry aggregation is not implemented.
The target must actually honor its declared mode and include all claimed inference
work. Parent-side scoring and report writing are excluded, so these measurements
are inference-session costs, not total researcher workflow time.

## Executed acceptance and reproduction

From this checkout, no installation is required:

```sh
PYTHONPATH=integrations/trainlab/src python -m unittest discover -s integrations/trainlab/tests -p test_assessment_diagnostics.py
PYTHONPATH=integrations/trainlab/src python -O -m unittest discover -s integrations/trainlab/tests -p test_assessment_diagnostics.py
PYTHONPATH=integrations/trainlab/src python integrations/trainlab/examples/diagnose_assessment.py --root /tmp/new-assessment-run
```

The example executes two CPU sessions over 24 constructed queries covering COPY,
LINK, alias overwrite and deletion. The correct reference returns 24/24 expected
answers; the deliberately faulty snapshot-LINK control returns 12/24. Both use
the same query panel, and scoring is derived from their actual output files.
Independent expected answers follow explicit template semantics. Saved reports
also show matched reordered exposure, a rejected unequal schedule, declared
generalization coverage and a rejected behavioral repair despite an explicitly
constructed internal-improvement claim. The exposure plans and internal metric
are fixtures, not training runs or measured representation changes.

This qualifies bounded implementation behavior. It does not train CSM or the
pointer-slot control, test their unfamiliar compositions, establish equal FLOPs,
demonstrate staged-training superiority, measure native lifecycle economics or
prove diagnostic productivity on external projects. Those research executions
remain the next users of these checks, with source-specific admission gates.
