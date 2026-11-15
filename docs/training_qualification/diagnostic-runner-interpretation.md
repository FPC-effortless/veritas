# Historical v3 diagnostic runner: interpretation safeguards

Issue #43 is historically superseded by TRAIN-001/#162; #203 remains a separate
blocked Gold-10 experiment. These changes harden existing diagnostic tools rather
than restart either research lane or qualify model training.

`tools/run_training_value_v3.py` already measures TRAIN before/after and held-out
before/after with the same in-process scorer. It now refuses duplicate observation
IDs before paired aggregation, records full generated episode-serialization hashes,
and separates a descriptive interpretation from scientific qualification.

## Target sanity and ceiling

`--minimum-reference-score` is an optional explicit threshold in (0,1]. If omitted,
existing invocation syntax still works but the interpretation is
`pipeline_sanity_unassessed`, not a claim of failed fitting or successful transfer.
The exact SFT target is already scored by the same scorer. Every reference case
must meet the declared threshold with zero parse failures before interpreting model
score changes. Missing parse-failure counts or per-case parse flags stay unassessed; malformed
counts/flags or count-versus-case contradictions refuse. This remains a caller-declared threshold, not authenticated preregistration
or proof that the scorer is scientifically valid.

A perfect TRAIN baseline and perfect TRAIN result are labelled
`already_at_training_score_ceiling`, not failure to fit. Other outcomes describe
score improvement/non-improvement under this recipe, never architectural incapacity.
Positive train and held-out gains remain observations on these generated panels,
not broad generalization. Report schema version0.3.2 marks this intentional interpretation-semantics change;
existing0.3.1 inputs remain historical. Labels are intentionally more conservative than the old
`training_fit_with_heldout_transfer` wording; downstream consumers must not treat
either old or new strings as qualification.

## Preserved evidence limits

- Episode-ID and exact serialized-content disjointness do not establish semantic,
  template, group-level or near-duplicate disjointness. Content hashes include
  identifiers; renamed copies can remain equivalent. Canonical TRAIN-001 provides
  stronger source membership/lineage checks and still leaves near-duplicate
  qualification UNKNOWN.
- `parsed` means a nonempty decoded JSON object, not schema-valid claims or correct
  answers. No scoring/parser behavior was changed by these fixes.
- Audit output is the first N examples per phase, not a randomized or full replay
  sample. N=0 remains supported and visibly provides no raw audit coverage.
- No tiny-overfit control is performed by this runner. The report says so. A
  deliberate small TRAIN fit would test pipeline learnability only, not transfer.
- Aggregates reject duplicate per-episode IDs and preserve per-seed interpretation
  or explicit legacy-unassessed state. They still consume supplied summaries and
  must not replace canonical TRAIN-001 recomputation/qualification.

`training_qualification` remains NOT_QUALIFIED_USE_CANONICAL_TRAIN_001. Reuse
TrainingEvidence/reverified_acquisition_curve, exact scorer/checkpoint identities,
complete expected seeds, contamination/exploit and guardrail gates for any future
qualification integration. Local assurance e692367's TRAIN-only classifier capture
cannot satisfy a held-out transfer claim.

## Verification scope

`python -m unittest discover -s tests/training_value_diagnostics` runs only stdlib
constructed-record tests; repeat with `-O`. CLI `--help` works both as a script and
module without loading models. Existing broad v3 helper execution in the inspected
default environment was blocked by missing `pyproj`; this is not a full test-suite
pass. No model execution or protected TEST access is needed for these regressions.
