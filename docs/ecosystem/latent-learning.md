# Latent learning and counterfactual diagnostics

The `trainlab.latent` analysis modules turn the later latent research cycles into
reusable functions. They accept arrays and explicit observational identities;
they do not load model checkpoints or fit a new model during analysis. NumPy is
the only numerical dependency in these four modules.

Implementation verification is separate from scientific qualification. A passing
task or retention gate establishes only its declared criterion. It does not grant
frontier qualification, release readiness, or permission to access sealed data.

## Scoring a counterfactual task

```python
from trainlab.latent.panels import association_families, make_association_panel
from trainlab.latent.scoring import counterfactual_metrics, summarize_counterfactual

families = association_families(b"ab", b"ij")
panel = make_association_panel(
    families=families, delays=(8,), values=b"ABCD"
)
# Obtain logits with an adapter, grouping rows by exact length and position offset.
# Storage padding must never enter the native model input.
scored = counterfactual_metrics(
    logits, panel["target_ids"], panel["pair_ids"], panel["assignment"],
    candidate_ids=panel["candidate_ids"], unit_ids=panel["family_ids"],
    strata=panel["stratum_ids"],
)
summary = summarize_counterfactual(scored, draws=5000, seed=123)
```

Native complete-pair accuracy requires both swapped assignments to produce the
correct full-vocabulary argmax. Two-candidate accuracy is a separate diagnostic:
a model can prefer the correct candidate while generating another token. Native
ties follow first-index argmax and are reported; candidate ties fail. No function
silently converts candidate success into native success.

The raw result retains row and pair metrics, pair membership, and family/stratum
identities. The summary averages complete pairs within families before computing
intervals. Families must belong to one overlap stratum. The overall bootstrap
resamples within strata and preserves the observed stratum quotas.

## Frozen observational resampling

```python
from trainlab.latent.statistics import make_bootstrap, fixed_seed_mean, record_means

record_ids, before = record_means(before_token_nll, window_record_ids)
other_ids, after = record_means(after_token_nll, window_record_ids)
plan = make_bootstrap(record_ids, draws=5000, seed=60071)
effect = plan.paired(after, before, left_ids=other_ids, right_ids=record_ids)
```

`record_means` gives equal weight to positions within a window and windows within
a source record. `cluster_means` gives equal row weight within a family or other
explicit unit. `make_bootstrap` preserves the supplied unique unit order.
Passing IDs to `estimate`, `replicates`, or `paired` rejects misaligned records.

Save `plan.indices` alongside `plan.manifest()`. Import archived draws through
`make_bootstrap(..., indices=saved_indices)` to reuse the exact resamples. The
manifest records identities, strata, seed, draw count, quantile rule, and index
hash. Intervals are 95% percentile intervals conditional on fixed fitted models
and fixed training seeds. They are not training-seed population intervals and do
not include refitting uncertainty. For an arm mean, `fixed_seed_mean` first checks
that every prespecified seed occurs once and averages unit values across seeds;
bootstrap those unit means afterward.

`BootstrapPlan.contrast` applies named coefficients to aligned unit vectors.
`difference_in_differences(a,b,c,d)` evaluates `(a-b)-(c-d)` before resampling,
preserving exact zero for identical aliases. Equal-domain estimates should
combine the independently generated domain replicate vectors at the declared
domain weights, rather than pool records from unequal-size domains.

## Language diagnostics and same-checkpoint gates

`classification_metrics` computes target NLL, prediction/correctness, maximum
softmax confidence, native tie flags, and unscaled multiclass Brier score. An
explicit answer-token subset adds answer probability mass. Stable float64 metric
arithmetic preserves native argmax behavior. Large saved-logit arrays should be
scored in batches; the function limits each call to 20,000,000 logits.

`calibration` uses fixed equal-width confidence bins. The last bin includes 1,
empty bins contribute 0, and results are descriptive points. Average individual
model ECE values when reporting a fixed-seed arm; pooling seeds before taking
absolute errors changes the estimand.

`training_byte_frequency` derives byte groups from explicit TRAIN records only,
without inserted separators or text normalization. The groups are unseen,
seen frequency below 0.001, frequency from 0.001 to below 0.01, and frequency at
least 0.01. Integer count comparisons preserve exact boundary behavior.

`additive_nll_decomposition` accepts an exhaustive nonoverlapping group-mask
mapping and returns per-record contributions and group fractions. Each
contribution is an unconditional mean of `mask * (left_NLL-right_NLL)` with zeros
outside the group. Contributions sum to each record's total difference. Use
`correctness_transition_masks(left_correct,right_correct)` for CC/CW/WC/WW
accounting, with transitions directed from reference/right to comparison/left.
These outcome-conditioned groups describe losses; they do not identify a causal
mechanism.

`competence_retention_gates` binds all evidence to one checkpoint identity. The
default historical criteria require native pair point accuracy at least 0.80,
lower 95% bound at least 0.70 in every overlap stratum and overall at delays 0 and 8,
copy-control point accuracy at least 0.80, and upper 95% bound of language ΔNLL no
greater than +0.10 nats in both Shakespeare and Alice. Thresholds are configurable,
inclusive, and compared before rounding. Missing cells produce `UNKNOWN`;
checkpoint mismatches raise `LabError`. Task and copy cells must declare the
metric `native_complete_pair`; retention cells declare `delta_target_nll`.
Missing metric identities produce `UNKNOWN`; candidate-only metrics are rejected.
A mean across different checkpoints
cannot supply a same-checkpoint success claim.

## Model-free panels and position controls

`association_families` constructs all unordered pairs of a Cartesian two-byte
key vocabulary. `split_association_families` samples prespecified stratum quotas,
checks disjoint families, and optionally requires every individual key in each
split. The default 64-key protocol produces 1,728 training, 96 validation and 192 test
families. Split attempts use identities only, never model outcomes. The split
generator is deterministic for its declared seed; it does not assert identical
RNG draws to a historical study.

`make_association_panel` includes every declared value in every selected family,
both binding orders, both query roles, and both swapped assignments. Optional
local3 controls retain the original absolute-position offset.
`make_copy_panel` supplies one-binding controls. Positive row and padded-byte
budgets are checked before constructing the panel.

`select_training_cues` recreates the lexical selection rule: literal lowercase
three-letter whole words from TRAIN, minimum counts, two distinct two-byte
prefixes sharing two completions, ambiguity rejection, deterministic frequency
ranking, and unique unordered key families. It fails if the requested number of
families is unavailable. `make_cue_panel` expands selected families into the
two-binding counterfactual and one-binding tasks. The cue protocol uses newline
filler; the full-key and position protocols use space filler. The independent
literal parser checks targets, query/order metadata, complete pairs, candidate
identity, matching suffixes, and matching byte histograms.

`position_conditions` and `condition_prompt` construct the eleven cycle 006
conditions. `position_contrasts` supplies sixteen named contrasts, including the
query/filler and gap/global interactions. Position-ID changes preserve physical
sequence order. Recurrent architectures without learned position embeddings must
mark these cells as identity aliases. Adapter engineering should verify native,
identity-hook, hook-removal, and saved-baseline parity before scientific scoring.

## Matched training through the existing runner

`training_recipe` freezes parent checkpoint, seed, objective weights, task and
language schedule hashes, label/update budgets, optimizer, learning-rate schedule,
clipping, reset policy, snapshots, and fixed-final checkpoint selection.
`audit_matched_recipes` checks explicitly declared invariants. Compare balanced
versus replay with the same association schedule and task budget; compare joint
versus LM-only with the same language schedule and language/update budgets. Extra
language supervision and equal compute remain separate facts.

`audit_training_events` checks contiguous updates, finite objective losses,
combined objective weights, gradient/weight finiteness, clipping flags, expected
batch identities, seed, fresh optimizer, reset policy, and source preservation.
Missing execution provenance produces `UNKNOWN`; mismatches fail. Caller-supplied
expected batch hashes must come from the pinned schedule, not the observed run.
`audit_first_update` compares logits, losses, gradients, norm, state, optimizer,
and RNG recursively and exactly. Convert adapter tensors to NumPy arrays or
ordinary nested values first. Empty or null required captures remain `UNKNOWN`;
nonfinite scalar and array values fail. A stateless optimizer may contain an
empty internal state map when its parameter groups are captured.
`audit_seed_panel` detects missing, extra, and
duplicate fixed seeds.

`runner_config` builds the existing TrainLab experiment schema and requires a
pinned research-adequacy pointer. The serialized learning recipe must be a
declared input. `run_training_recipe` checks recipe identity, seed, budget, purpose,
and workload, then calls `trainlab.runner.run_experiment`; all existing adequacy
and execution gates still apply. There is no second trainer or optimizer loop.

## Verification

The four tests under `integrations/trainlab/tests_latent/` exercise paired
identity, quota preservation, missing seeds, full-vocabulary versus candidate
failure, ties, NLL additivity, same-checkpoint gates, literal parser errors,
TRAIN-only selection, fixed budgets, and runner delegation.

Set `VERITAS_LATENT_ARCHIVE_ROOT` to a directory containing the completed study
folders to enable optional cycle 006 saved-array parity checks. These verify exact
family means/intervals with archived indices, exact bytes and position IDs for all
eleven position conditions, and numerical saved-logit NLL/Brier/confidence parity.
They do not invoke model forwards, training, or timing measurements.
