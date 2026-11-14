# Training and comparison diagnostic packs

DIAGNOSTICS-004 (#526), part of the [24-feature program](https://github.com/FPC-effortless/veritas/issues/525),
adds six offline packs in `trainlab.experiment_diagnostics`. They accept finite,
bounded JSON observations from existing trainers and evaluators. No framework
dependency, online service or model-specific architecture is required.

Each result binds its full input and parameters with `input_sha256`, declares a
versioned pack manifest, and exposes per-check coverage, observations and findings.
`TESTED` means the stated predicate or measurement ran on the supplied scope;
it is not a model-health score. `FAILED` identifies an observed violation,
`UNSUPPORTED` identifies absent channels and `INCONCLUSIVE` identifies incomplete
coverage or unresolved inference. Invalid input raises `LabError`; it does not
produce a favorable report. All reports retain `scientific_qualification=NOT_QUALIFIED`.

## Catalog and evidence boundaries

| API | Supplied observations | What it establishes | Remaining limits |
| --- | --- | --- | --- |
| `training_diagnostics` | Ordered events, expected steps, frozen thresholds | First observed numerical, gradient, update or diversity violation; loss progress; acquisition and subsequent score regression | Active window and comparable validation panel must be declared correctly. No tensor shape/mask inspection, causal diagnosis, or universal norm threshold. |
| `benchmark_diagnostics` | Original/intervened answers, independent-reference outputs, expected changes, deficient-control outputs, group IDs | Reference agreement, expected sensitivity, number of sensitive groups and deficient-control accuracy | Does not execute interventions or verify reference/group independence. Deficient controls must be justified externally. |
| `comparison_ledger` | Arms, matched dimensions, required seeds, competence pointers and selection rules | Differences in declared information/budgets, omitted/failed seeds, missing competence evidence, prohibited test selection | A hash reference is not verification of baseline competence. Tuning trials and all unmatched attributes remain visible, not automatically equivalent. |
| `paired_statistics` | Complete required unit-by-seed paired outcomes | Equal-unit mean paired effect and whole-unit percentile bootstrap interval; per-seed effects | Conditional on observed seeds; seeds are not resampled. Assumes independent units. Selection, stopping and declared comparison family are not verified. |
| `classification_diagnostics` | Single-label predictions, class order, optional labels/probabilities/slices | Confusion matrix, errors, slice accuracy, prediction diversity, Brier score, natural-log NLL and binned ECE | Missing labels/probabilities reduce coverage. Bin/sample dependence remains. No classification-quality acceptance threshold. |
| `quality_cost` | Quality, measured session seconds, workload/hardware/boundary hashes | Descriptive nondominated points under identical declared context | No Pareto result with missing costs or mismatched context. No measurement attestation, uncertainty or architecture ranking. |

`PACKS` is a versioned discovery catalog with requirements and limitations. This
is a local API catalog, not a signed community plugin loader. Reports can be
attached to the existing workbench and Research Lab graph without converting
their findings into scientific admission.

Null matched ledger attributes mean unknown information, never known equality.
The benchmark's deficient-control ceiling must be below 1; perfect performance
by a declared deficient control always triggers its shortcut finding.

## Training event contract

Pass `expected_steps` and thresholds explicitly. Each event needs `step` and may
provide `loss`, `finite`, `gradient_norm`, `update_norm`, `missing_gradients`,
`learning_rate`, `predicted_classes`, and `validation_score`. Unavailable channels
are omitted or null. Encode nonfinite observations using `finite=false` and null
numeric summaries; JSON NaN/Infinity are rejected. Select an active optimization
window: zero updates can be expected during deliberate freezing or convergence.

Threshold keys are `min_loss_drop`, `min_gradient_norm`, `min_update_norm`,
`min_classes`, `acquired_score`, and `max_regression`. Loss progress uses
`(first_loss-last_loss)/max(abs(first_loss),1e-12)`, and remains inconclusive if
steps or losses are missing. Score acquisition/retention assumes a fixed panel.
Without post-acquisition observations retention is inconclusive. A score drop
does not establish catastrophic forgetting or its cause.

## Statistical contract

Declare both `required_units` and `required_seeds`; missing whole units, missing
seeds, duplicate pairs and extra units are rejected. Every seed contributes to
its unit mean, then bootstrap draws resample whole unit means. This preserves
candidate/baseline pairing and gives each unit equal weight, irrespective of
its example count. The API does not accept individual-example independence by
implication: choose the actual sampling unit and retain its provenance externally.

`alpha / comparisons` sets the Bonferroni-adjusted interval tail probabilities.
At least two units are necessary; fewer yield null intervals. If the requested
tail contains fewer than one expected bootstrap draw, uncertainty is inconclusive
even when descriptive endpoints are returned. This is a numerical resolution
check, not proof of finite-sample statistical coverage. No sequential stopping,
post-selection or seed-population guarantee is supplied. Retain failed executions
in the comparison ledger; do not replace them with invented paired scores.

## Classification and cost details

Probabilities follow the explicit class order and must normalize within `1e-8`.
Brier is the mean sum of squared errors over classes; ECE uses the probability
of the selected prediction, which need not be argmax. A zero true-class
probability yields infinite NLL, encoded as null with `zero_true_probability>0`.
This is distinct from missing probabilities. Metrics on known labels report
coverage against all supplied rows. Error IDs are capped at 100 but counts are
complete. Reports may contain supplied labels/attributes: authorize their export
before using sensitive data; these packs are not a privacy filter.

Quality/cost points require identical workload, hardware and boundary identities.
The boundary must include full inference-session work, failures and retries;
passing training-process wall time as inference time violates this contract.
Both ties remain on the Pareto set. A `MEASURED` declaration alone cannot prove
the timing is accurate or that two quality values have comparable meanings.

## Reproduce the composed acceptance example

From a clean checkout, install the four ecosystem packages and run:

```sh
python -m pip install -e . -e integrations/forge -e integrations/trainlab -e integrations/research_lab
python integrations/trainlab/examples/diagnose_experiments.py --root /tmp/veritas-experiment-diagnostics
python -m unittest discover -s integrations/trainlab/tests -p test_experiment_diagnostics.py
```

The output root must be new. Forge freezes 128 public constructed scalar examples;
only train/validation readers are used. TrainLab runs two fresh workers: 20 actual
full-batch scalar gradient-descent updates, and 20 attempted updates with writes
deliberately frozen. Their live loss/gradient/update/validation telemetry feeds
the training pack. This is two engineering fit attempts, not CSM training or a
new architectural comparison. Five other packs consume explicitly marked
constructed fixtures. Their ledger deliberately lacks competence evidence and
their session costs remain `NOT_MEASURED`.

The workbench records three operations per worker (train, inspect, persist),
binds code/data/configuration identities, and retains its coverage report.
TrainLab retains training events, pack reports, metrics and artifact hashes.
Research Lab links findings to both the Forge release and the TrainLab receipt.
The frozen runtime and selected Forge view are checked before execution, and
runtime identity is checked again afterwards. Forge may retain an unscored test
partition as a release artifact; this example never reads it for scoring.

The injected fault and clean controls qualify bounded implementation behavior.
They do not estimate real-project false-alarm rates, diagnostic productivity,
general scientific validity, or frontier performance. See the
[remaining roadmap](diagnostic-roadmap.md).
