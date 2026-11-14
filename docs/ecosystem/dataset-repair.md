# Evaluate reviewed label changes and feature drift

Use `trainlab.dataset_repair` with pinned Forge diagnostic views and local
TrainLab prediction artifacts. The two comparisons have different evidence
requirements.

## Training label repair

`compare_label_repair` reruns Forge adjudication against the pinned parent
and checks that the proposed revision matches the reviewed result. Accepted
edits may change training labels. Row identities, selected features, validation
labels and memberships must remain identical. The train and validation rows
must have complete selected model features and be disjoint by ID, exact
selected features and known declared groups.
An unresolved review or an unknown matched outcome leaves the result
inconclusive.

`classification_request` constructs the exact request for each view and
fitted model. The evaluator must retain one bound prediction record per
validation row. Predictions and labels are nonempty strings or null. Both
arms retain the same declared code and configuration identities. The report
recomputes paired correctness, which rows improved or regressed, and per-slice
scores. An unknown output or label contributes to missing coverage. A
`TESTED` comparison may show improvement, damage, or no change.

## Drift and model outcomes

`compare_drift_performance` runs Forge distributions on two pinned validation
panels and scores bound predictions from the same fixed model. Missing model
features leave coverage inconclusive. The panels
must be disjoint by identity, exact selected features and available declared
groups. Both reports can slice by a declared string-valued reporting field. The
leakage check ignores this field so it cannot disguise identical model
features. Prediction requests bind declared input and reporting fields. A null
slice value identifies unassigned rows. A missing slice has no invented
accuracy. Inspect drift and performance side by side. Feature distances and
accuracy differences do not identify the cause of a performance change.

## Reproduce the public acceptance example

Install Forge, TrainLab and scikit-learn. Run with a new output directory.

```bash
python integrations/trainlab/examples/diagnose_dataset_repair.py \
  --root /tmp/veritas-dataset-repair
```

The Wine example uses two fixed 36-row validation panels and 106 training
rows. Rotate training labels, restore original labels using explicit fixture
oracle decisions, and fit standardized logistic regression on the clean, faulted and repaired
views. Verify that the repaired fit matches the independent clean fit. Evaluate all fits on the same untouched 36 rows. For the drift control,
the repaired model predicts on the second held-out panel after a defined
alcohol feature shift. The reporting slice uses the original alcohol value.
Scaler fit excludes both evaluation panels. The output
retains the views, reviews, bound outputs, configuration, comparison results
and an independent recount. The original dataset and its redistribution
license are credited in metadata. Review decisions are constructed controls.
The interfaces do not authenticate human reviewers or prove that a supplied
panel was untouched during development.
