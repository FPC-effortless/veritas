# Latent geometry and native readout diagnostics

`trainlab.latent.geometry` and `trainlab.latent.calibration` provide the array
operations used by the observed latent atlas and the first two research cycles.
They accept measured arrays and explicit metadata. Model construction, checkpoint
identity, native-state interventions, artifact storage, and scientific admission
belong to the surrounding TrainLab research runner and adapter.

Analysis functions return `(report, arrays)`: `report` is finite JSON-compatible
metadata and metrics; `arrays` contains named NumPy arrays suitable for an NPZ
artifact. Scalar summaries return ordinary Python values. Transform functions
return arrays. The fitting functions follow the same `(report, fit_arrays)`
convention; only the second member is passed to reconstruction functions.

## Geometry operations

| Operation | Inputs and result | Qualification boundary |
|---|---|---|
| `pca_fit`, `pca_transform`, `pca_reconstruct` | Calibration rows, full centered SVD basis, fixed-rank coordinates/reconstruction | No scaling, whitening, target use, or held-out rank selection |
| `random_subspace` | Seeded Gaussian-QR full orthonormal basis | A specified control draw, not a null-population inference |
| `latent_geometry` | PCA map, spectrum, 90% rank, participation ratio, norms, duplicates and neighborhood fidelity | Observed representations, not every reachable model state |
| `neighborhood_quality` | Exact original-space Euclidean trustworthiness and neighbor overlap | Stable row-index ties; unavailable k is reported explicitly |
| `tsne_projection` | PCA-preprocessed t-SNE, settings/objective and original-space fidelity | Local neighborhoods; island gaps and areas are not semantic scales |
| `linear_cka`, `cka_matrix` | Centered similarity of aligned observations | Constant representations have undefined similarity (`None`) |
| `window_derangement` | Within-domain whole-window swap preserving position layout | Descriptive reference; no p-value |
| `conditional_permutations` | Token/domain-preserving derangements, optionally position bins | Does not preserve source-record dependence; no p-value |
| `matched_context_pairs` | Disjoint same-token/domain/position-bin pairs from different records | Context differences may include spelling, position and other nuisances |
| `token_conditioned_geometry` | Cross-fitted domain/token means, common support, R², raw/token/residual CKA | Current-token residualization does not isolate semantics |
| `cka_bootstrap` | Whole-record stratified bootstrap with re-centering on each draw | Fixed fitted representations; degenerate draws masked explicitly |
| `decoder_metric_fit`, `decoder_metric_reconstruct` | Same-rank reconstruction using trained output weights | Optimizes a calibration base-logit proxy, not NLL or nonlinear output KL |
| `compression_diagnostic` | Cross-fitted ordinary/decoder-aware PCA, norm/random controls and native decoder evaluation | Head reconstruction; no recurrent-state or runtime-savings inference |

NumPy is required by these modules. t-SNE additionally requires scikit-learn.
When SciPy is available, neighborhood distances use its exact distance kernel;
the NumPy fallback uses explicit row differences. Neighborhood and bootstrap
Gram matrices have explicit entry budgets. These are manual analytical operations,
not ordinary expensive model CI jobs.

### Cross-fitting and aligned observations

Every representation in a comparison must describe the same observations in the
same order. `token_conditioned_geometry` and `compression_diagnostic` require
source-cluster and fold identities; a `(domain, cluster)` cannot cross folds.
Different domains may reuse local record IDs. Token means are estimated only
from the other folds. By default, a held-out token/domain needs support from two
distinct calibration clusters. The eligible mask is identical across compared
models, and coverage distinguishes unseen from insufficient-support rows.

Token geometry retains raw, domain-centered, fitted token-component and residual
arrays, as well as calibration means and held-out reconstruction errors. Optional
bootstrap draws hold those fits fixed, re-center every sampled CKA, and retain
paired residual-minus-domain-centered contrasts and R² intervals. Optional
permutations and exact-position/bin16 matched pairs retain the actual row indices.

CKA point estimates use matched rows. Whole-record bootstrap draws preserve the
declared number of source records in each domain; they do not compute an average
of separate domain CKAs. Invalid zero-variance bootstrap pairs have `valid=False`.
Their stored numeric placeholder is zero and must be read together with that mask;
it is excluded from interval calculations. Reports include valid-draw counts.

### Decoder-aware objective

For output weights `W` with vocabulary rows, the metric uses
`Wc = W - mean(W, axis=0)` and
`M = Wc.T @ Wc / vocabulary + epsilon * I`, where
`epsilon = 1e-6 * trace(Wc.T @ Wc / vocabulary) / hidden_width` by default.
The method applies PCA to calibration `(H - mean(H)) @ sqrt(M)` and maps the
rank-k reconstruction back through the inverse square root. Fits retain numerical
identity, rank/idempotence, weighted-symmetry and objective checks, conditioning,
and calibration PCA-direction contributions to centered logit variation.

`compression_diagnostic` uses the **same per-fold calibration variance rank** for
ordinary and decoder-aware fits. An optional fixed orthogonal metric rotation
preserves its spectrum. Norm-matched PCA consumes an additional per-row norm
scalar; it is not a pure rank-k code. A zero projected vector remains at the
calibration mean. Random controls and full-width reconstructions are retained.

PCA's calibration orthogonality supports its saved logit-energy decomposition.
That decomposition is not silently applied to held-out energy with cross terms
removed. For a softcap or successor mixture, output weights describe only the
base-logit fitting proxy; evaluation must retain the original nonlinear decoder.

## Native readout callback

The required interface is:

```python
def readout(hidden, *, row_indices, **readout_kwargs):
    # Return the actual model's vocabulary scores for these observation rows.
    # Apply its trained bias, vocabulary slice, softcap and mixture semantics.
    ...
```

Declare `readout_kind="logits"` or `readout_kind="log_probabilities"`; semantics
are never guessed. Normalized log probabilities must be finite and normalize
within the declared numerical tolerance. `row_indices` select unchanged native
context such as prefix-causal successor IDs. The callback receives a copy of the
head input; model purity, frozen weights and source identities remain adapter
responsibilities.

`observed_native_scores` enables an independent replay check against untouched
native outputs, requiring both log-probability agreement and identical argmax.
Without them, the report says `NOT_VERIFIED`, not `PASS`. Full-width reconstruction
also checks target NLL and distribution KL; all argmax changes are disclosed.

```python
from trainlab.latent.geometry import compression_diagnostic

report, arrays = compression_diagnostic(
    measured_head_inputs, target_ids, native_readout,
    folds=source_record_folds,
    clusters=source_record_ids,
    domains=source_domains,
    ranks=(0, 1, 2, 4, 8, 16),
    decoder_weights=trained_vocabulary_weight,
    readout_kind="logits",
    observed_native_scores=untouched_native_logits,
)
```

Native targets go only to scoring. Each held-out row is scored exactly once per
condition. Returned arrays include losses, correctness, predictions, KL, total
variation, disagreement, hidden movement, centered-logit error where available,
source folds, calibration fits, and rank per fold. Point preservation uses
declared NLL/accuracy margins; interval preservation remains unset until the
source-cluster uncertainty analysis is performed.

## Calibration and prediction-path controls

| Operation | Coverage |
|---|---|
| `log_softmax`, `temperature_scale` | Stable conversion and positive post-mixture temperature with argmax invariance |
| `record_domain_weights` | Equal records/domain, equal domains; optional equal windows/record |
| `probability_metrics` | NLL, accuracy, confidence, entropy, multiclass Brier, KL/TV/disagreement and fixed-bin reliability/ECE |
| `native_readout_contrast` | Named changed head inputs through the exact callback, paired metrics and replay evidence |
| `component_readout_diagnostics` | Bank removal, successor removal, both, head-only, gate-only, donor bank swaps, factorial/path contrasts and strata |
| `select_calibration_settings` | Nonnegative gain, signed diagnostic gain, temperature-only and joint selection from calibration losses only |
| `bank_gain_diagnostics` | Gain/temperature grid; fixed/adaptive gates; calibration mean/centered bank; disjoint-source selection/evaluation; selection bootstrap; successor/confidence/domain strata |

Bank diagnostics require the callback to additionally honor:

```python
readout(hidden, row_indices=indices, context=native_context,
        gate_mode="adaptive", gate_hidden=separate_gate_input,
        no_mixture=False)
```

`hidden` reaches the native vocabulary head; `gate_hidden` reaches the gate.
`gate_mode="native"` uses the saved native gate in the supplied context.
`no_mixture=True` removes the successor mixture while preserving the native base
decoder. This permits head-only and gate-only controls without an affine
approximation. The adapter owns successor lookup causality and unchanged native
writer/backbone trajectories.

Donor controls enforce different source records in the same domain. Supplying
`positions` also verifies equal relative positions; otherwise that part is
explicitly unverified. Factorial contrast arrays retain
`both - bank - successor + native` and head/gate nonadditivity for later paired
cluster analysis. Correctness-defined successor strata are descriptive and may
not be used as deployable inference policies.

Gain changes `prebank + gain * bank_read`; the adaptive gate sees the changed
vector. Temperature is applied **after** native mixture probabilities, and must
preserve argmax. Mean-bank controls fit only calibration rows with record/domain
weights. The grid retains negative gains as diagnostics, while the nonnegative
selection excludes them. Selection ties prefer proximity to native gain and
temperature, then smaller gain, then smaller temperature. Boundary selections
and fixed-record bootstrap selection counts are retained.

The grid's descriptive all-row summaries are labeled separately from calibration
selection and held-out evaluation. Calibration and evaluation must have disjoint
source records. Changing held-out labels or activations cannot alter the fitted
bank mean, confidence-quartile boundaries, or selected settings. Selection
bootstrap uncertainty is separate from evaluation uncertainty conditional on the
chosen setting; row-level evaluation contrasts are retained for the latter.

NLL, Brier and ECE can move in different directions. None is promoted to a broad
calibration or memory-utility claim. All these analyses remain `NOT_QUALIFIED`
until the enclosing research contract's evidence and scientific gates are met.

## Cheap verification

Run the dedicated tests with the optional analytical dependencies installed:

```bash
PYTHONPATH=integrations/trainlab/src python -m unittest discover -s integrations/trainlab/tests_latent -p test_geometry.py
PYTHONPATH=integrations/trainlab/src python -m unittest discover -s integrations/trainlab/tests_latent -p test_calibration.py
```

Tests include low-variance but output-critical information, nonlinear native
decoders, split leakage, constant/degenerate geometry, explicit expanded-record
bootstrap agreement, head/gate separation, calibration/evaluation independence,
and donor/position invariants. If the archived study exists beside the checkout,
a read-only check also reproduces its saved CSM CKA result. No trained model
forward pass or new scientific experiment is needed for these checks. A second
optional archive check reproduces Cycle002's four selected bank/temperature
settings, calibration losses, and all 5,000-draw selection frequencies, and binds
the exact regenerated record-draw matrix to its SHA256 identity.
