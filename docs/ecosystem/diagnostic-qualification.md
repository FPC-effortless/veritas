# Measuring diagnostic accuracy and overhead

The qualification scorer compares a pinned fault panel with a separately
pinned observation file. A check can detect a problem at the check level while
failing to locate the actual fault. The scorer counts these outcomes separately.
It does not convert diagnostic accuracy into model or benchmark qualification.

## Prepare a panel

Freeze a `trainlab.diagnostic-fault-panel.v1` JSON object with distinct
`repeats` and `cases`. Each case contains `id`, `workload_sha256`, and
`targets`. A target names a `check`, an exact `location`, and a Boolean
`fault`. Include explicitly adjudicated negative locations. Keep this
reference away from the diagnostic execution.

## Capture observations and score

The `trainlab.diagnostic-fault-observations.v1` file contains `runs`. Each
run has `case`, `repeat`, `workload_sha256`, `checks`, and `timing`. Checks
name a `name`, `status` and observed `locations`. Status is `CHECKED`,
`INCONCLUSIVE`, `UNSUPPORTED`, `NOT_RUN`, or `EXECUTION_FAILED`. Supply
`CHECKED` only when the stated observation scope was covered. A positive
witness can be retained with incomplete coverage. Absent witnesses from an
incomplete check are unknown. Findings outside the adjudicated location set
are counted separately and make the report inconclusive.

```bash
python -m trainlab.diagnostic_qualification \
  --panel fault-panel.json --panel-sha256 PANEL_SHA \
  --observations observations.json --observations-sha256 OBSERVATIONS_SHA
```

Retain both hashes outside the evidence directory. Duplicate runs or
mismatched workload identities fail input validation. A missing repeat stays
unobserved and prevents completing the report. The computed rates expose their
numerators and denominators. Detection rate is over completed checks with
at least one expected positive location. Location recall and precision use
exact matches among adjudicated, observed targets. The false alarm denominator
is the set of observed negative targets. A zero denominator yields null.

Set `timing` to null when complete paired measurements are unavailable.
Otherwise provide `baseline_ns`, `diagnostic_ns`,
`baseline_work_sha256`, `diagnostic_work_sha256`, `hardware_sha256`, and
`boundary_sha256`. Overhead summaries require every declared repeat, matching
completed-work fingerprints per pair, and a common hardware and boundary
identity. They include the median and range of paired differences and the
median ratio. Those fingerprints and measurement declarations are produced by
the runner and remain caller-supplied evidence to the scorer.

## Run the public example

Install Forge, TrainLab and scikit-learn in a CPU environment, then run:

```bash
python integrations/trainlab/examples/qualify_diagnostics.py --root /tmp/veritas-wine-audit
```

The example uses the 178-row Wine dataset distributed with scikit-learn
and freezes a stratified train/validation split. Attribution: Aeberhard, S.
and Forina, M. (1991). Wine. UCI Machine Learning Repository.
[Dataset DOI](https://doi.org/10.24432/C5PC7J).
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The example uses scikit-learn's encoding and adds IDs, splits and fault variants.

It fits standardized logistic regression for clean, missing-feature,
cross-split duplicate, evaluation-fitted scaler, and constant-output cases.
The expected locations are written before fitting. Existing Forge exact-content
and transformation checks and TrainLab classification reports supply the
observed locations. Only the scaler receives validation records in the fit
leakage scenario. The constant-output case replaces the reported predictions
after fitting. The missing-feature case uses literal zero fill in both arms.

Each of five repeats per case runs a baseline and an instrumented fit. Arm
order alternates. The timed window includes view reading, preprocessing, model
fit and prediction, and work hashing. The instrumented arm additionally
includes diagnostic computation and finding conversion. Imports, source
preparation, report writes and post-run scoring are outside the measured
window. The retained evidence includes source and runtime identities,
workloads, a fault panel, raw reports and predictions, measured observations,
a separate recount, and a file manifest.

The missing feature removes one case from a complete overlap check. That
coverage gap remains visible in the overall result. Five repetitions of one
small dataset do not estimate sensitivity across projects or provide a
general overhead estimate. The panel's negative locations are explicit and
unadjudicated findings require follow-up.
