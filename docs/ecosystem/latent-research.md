# Latent research diagnostics

The optional `trainlab.latent` package implements the diagnostic methods from the
latent atlas and research cycles 001–006. `veritas-latent` runs frozen plans using
the existing TrainLab Workbench. Forge retains source/split identity; TrainLab
provides process supervision and receipts; Research Lab indexes those receipts.

The package supplies numerical kernels, native hooks, input generators, training
audits, figures and saved-output replay. A new model needs the capabilities used
by its selected tests. Missing capabilities remain `UNSUPPORTED`. A completed
diagnostic does not automatically qualify a scientific claim.

## Install and run

```bash
python -m pip install './integrations/trainlab[latent,latent-tsne]' \
  ./integrations/forge ./integrations/research_lab
veritas-latent catalog

# Constructed inputs, zero fits, plots and exact offline replay:
python integrations/trainlab/examples/diagnose_latent.py \
  --root .trainlab/latent-demo

# Actual Forge -> TrainLab -> Research Lab evidence path, also zero fits:
python integrations/trainlab/examples/diagnose_latent.py \
  --root .trainlab/latent-ecosystem --ecosystem
```

Use a new destination for every run. The constructed example deliberately lacks
native model hooks: its native replay row must say `UNSUPPORTED`, while its five
numerical diagnostics complete. This is an executable coverage control.

Native adapters additionally need the model's frozen PyTorch runtime and trusted
source. The original-checkpoint conformance checks used Python 3.12.14,
NumPy 2.3.5 and CPU PyTorch 2.10.0. Runtime changes require fresh replay checks.
No checkpoint, corpus, or third-party model source is distributed here.

## Coverage of the research thread

The following are executable operations or compositions over the same stored
arrays. Detailed contracts are in [geometry](latent-geometry.md),
[learning and scoring](latent-learning.md), and [native adapters](latent-native.md).
Executed checks and their limits are recorded in [implementation validation](latent-validation.md).

| Research method | Implementation | Essential control or interpretation |
| --- | --- | --- |
| Model, checkpoint, tokenizer, panel and representation inventory | `analysis.inventory_models` | Comparison groups require aligned tokenizer/panel/representation declarations |
| Head inputs, embeddings, intermediate stages, CSM state and COG bank views | `native.module_adapter`, `torch_hook_adapter`, `language_adapter` | Native extraction/readout replay; unchanged weights; repeated stages retained |
| Native captures to aligned token rows | `data.prepare_token_rows` | Exact input identity; padding masks; source record/window/position IDs; decoder context selected in the same order |
| PCA 2D/3D, variance spectra, effective dimension, rank90, norms, duplicate rows | `geometry.latent_geometry`, `pca_fit` | Observed sample geometry; centered, unscaled, unwhitened PCA |
| t-SNE and seed/perplexity sensitivity | `geometry.tsne_projection`, repeated frozen jobs | Fidelity checked against the original high-dimensional vectors |
| Trustworthiness and neighborhood overlap | `geometry.neighborhood_quality` | Stable index tie handling; declared neighborhood sizes |
| Natural, intermediate and controlled-response CKA | `linear_cka`, `cka_matrix`, `cka_bootstrap` | Matched rows; whole-record resampling; degenerate similarity stays undefined |
| Current-token conditioning and nuisance controls | `token_conditioned_geometry`, `conditional_permutations`, `window_derangement`, `matched_context_pairs` | Calibration-only nuisance fits; common support; token/domain/position controls |
| Cross-fitted PCA compression, mean-only, random subspaces and norm matching | `geometry.compression_diagnostic` | Source-record folds, full-width replay, native decoder, no evaluation-based rank choice |
| Same-rank decoder-aware compression and metric rotation | `decoder_metric_fit`, `decoder_metric_reconstruct`, `compression_diagnostic` | Weighted base-logit objective is separate from held-out NLL; bias/softcap/mixture retained |
| COG bank, successor, head-only, gate-only and donor-swap controls | `calibration.component_readout_diagnostics`, `interventions.native_component_sweep` | Frozen native trajectories and explicit head/gate decoder context |
| Signed bank-gain and post-mixture temperature grids | `calibration.bank_gain_diagnostics`, `select_calibration_settings` | Calibration-only selection, fixed evaluation settings, selection bootstrap and boundary flags |
| CSM one-step and persistent component lesions | `interventions.component_lesions` | Distinct state semantics; native states, local-history and foreign-memory controls |
| Same-suffix history transplants and shuffles | `suffix_intervention`, `history_sweep` | Frozen donor map, unchanged current/suffix/future input, preserved absolute positions |
| Stored state versus head/output sensitivity | `state_distances`, `response_metrics`, `retrieval_sweep` | Values, links, cursor, history and position remain distinct observations |
| Initially unread rows and later access | `read_footprint`, `unread_future`, `retrieval_sweep`, `analyze_future_access` | Cursor/read1/read2/destination footprint; shared true continuation; sham and no-effect-before-access checks |
| Literal cue panels and short competence controls | `panels.select_training_cues`, `make_cue_panel`, `make_copy_panel` | TRAIN-only whole-word selection; swapped assignments; full-vocabulary pair scoring |
| Full two-byte key binding, family splits, overlap strata and local3 | `association_families`, `split_association_families`, `make_association_panel`, `audit_association_panel` | Every familiar key covered; family disjointness; exact parser/oracle; matched position offsets |
| Training, balancing, language replay and LM-only controls | `learning.training_recipe`, `audit_matched_recipes`, `audit_training_events`, `audit_first_update`, `audit_seed_panel` | Pinned parents/schedules; fresh optimizer; fixed final update; labels, updates and compute kept separate |
| Execution of a trusted training recipe | `learning.runner_config`, `run_training_recipe`; existing TrainLab runner | Research adequacy remains required; no alternate trainer or admission bypass |
| Training gradients, updates, learning trajectories and resume | Existing `training_observer`, `pytorch`, `resume_equivalence` plus learning audits | Missing instrumentation stays unverified; optimizer/RNG/first-update evidence required |
| Native individual and complete counterfactual-pair metrics | `scoring.counterfactual_metrics`, `summarize_counterfactual` | Full-vocabulary primary; candidate-only secondary; ties and same-answer failures visible |
| Domain/record language panels and exact overlap | `data.language_panel`, `language_overlap`, `hierarchical_means`, `source_record_folds` | Explicit short-record policy; no inserted separators; all training substring offsets scanned |
| Language retention, confidence, answer mass, Brier and fixed-bin ECE | `classification_metrics`, `calibration`, paired statistics | Equal-record/domain estimands; ECE per model; domain gates separately enforced |
| TRAIN-byte coverage and additive NLL accounting | `panels.training_byte_frequency`, `scoring.additive_nll_decomposition` | Exact integer frequency boundaries; unconditional contributions sum to total change |
| Correctness transitions | `scoring.correctness_transition_masks`, native response metrics | Reference/right -> comparison/left direction; descriptive accounting, not mediation |
| Position offsets, query/filler reset, prefix, phase and space controls | `panels.position_conditions`, `condition_prompt`, `position_contrasts`, `interventions.position_sweep` | Same physical mask for ID-only edits; explicit recurrent identity aliases |
| Paired effects, interactions, fixed-seed and stratified uncertainty | `statistics.BootstrapPlan`, `fixed_seed_mean`; `analysis.*estimate`, `linear_contrast`, `factorial_contrast` | Reused recorded draw indices; seeds averaged before resampling; interval population explicit |
| Sign-flip sensitivity and multiplicity | `analysis.sign_flip`, `holm` | Symmetry assumption and declared comparison family retained |
| Competence plus retention on one checkpoint | `scoring.competence_retention_gates` | Every required delay/stratum/domain; metric identity; missing evidence yields UNKNOWN |
| Native latency and quality-qualified cost | `interventions.latency_sweep`, `analysis.timing_summary`; existing `quality_cost`/`reliability_cost` | Warmups, raw repeats, synchronization, unchanged weights; quality gate separate |
| Reports, latent atlas and numerical figures | `reporting.render`, `draw_figure`, `atlas` | Saved source data; PNG/SVG/PDF, Markdown/HTML/PDF, CSV; failed figures retained |
| Exact evidence preservation and offline reproduction | `artifacts`, `suite.reanalyze`, `export_bundle` | Pinned plan/code/input inventories; no pickle; zero model calls on reanalysis |

“Implemented” in this table means an executable method and its required contract.
It does not mean every possible architecture exposes every hook, or that all old
training campaigns were rerun during this engineering change. The archived
research results retain their original scientific status.

## Frozen plan format

Plans contain four SHA256 identities, explicitly selected local artifacts, a
bounded operation budget, jobs and optional figures. For example:

```json
{
  "schema": "trainlab.latent-plan.v1",
  "title": "My checkpoint: latent geometry",
  "identities": {
    "model": "<checkpoint SHA256>",
    "dataset": "<frozen panel SHA256>",
    "code": "<native model source SHA256>",
    "configuration": "<filled by freeze>"
  },
  "artifacts": {
    "captures": {"path": "captures.npz", "sha256": "<filled by freeze>", "kind": "npz"}
  },
  "budget": {"max_calls": 1000, "max_seconds": 120},
  "jobs": [{
    "id": "head_geometry",
    "operation": "geometry.latent_geometry",
    "args": [{"artifact": "captures", "key": "hidden"}],
    "kwargs": {"dimensions": 3},
    "role": "secondary",
    "scope": "Observed held-out head vectors; no architecture-wide inference"
  }],
  "figures": [{
    "id": "head_pca",
    "kind": "scatter",
    "title": "Head-input PCA",
    "data": {"coordinates": {"result": "head_geometry", "path": [1, "coordinates"]}}
  }]
}
```

Replace model/data/source placeholders with real hashes. `freeze` fills input and
configuration hashes. Artifact paths are relative to the plan directory and may
not traverse symlinks. Supported kinds are `npy`, `npz`, `json` and `opaque`.
Opaque checkpoints/source files are verified and copied, and never unpickled or
executed by the offline analysis loader.

References to earlier results use a path of integer indices and string keys.
PCA/compression/calibration methods generally return `[report, arrays]` in saved
JSON, hence the `1` in the example. Literal byte arguments use
`{"bytes_hex":"414243"}`. Use `{"literal": ...}` for ordinary data objects whose
keys would otherwise be interpreted as reference syntax.

```bash
veritas-latent freeze draft.json --output plan.json
veritas-latent run plan.json --output diagnostic-run
veritas-latent verify diagnostic-run --sha256 BUNDLE_SHA256
veritas-latent reanalyze diagnostic-run --sha256 BUNDLE_SHA256 --output repeated-analysis
veritas-latent export diagnostic-run --sha256 BUNDLE_SHA256 --output evidence.zip
```

The returned bundle hash should be retained in the external TrainLab receipt or
other trusted research record. A hash inside its own editable directory does not
authenticate the operator.

The catalog is an allowlist. A plan cannot import an arbitrary Python function or
launch training as an analysis job. Training execution uses the separate existing
runner, with its declared purpose and adequacy gates intact.

## Native model execution

Use `examples/latent_native_factory.py` for the four recovered source interfaces,
or write an explicit factory for another trusted implementation. The factory
returns the existing `research_diagnostics.Adapter`. Its path, hash and factory
name are frozen in the plan. All model/source/checkpoint files must be explicitly
declared. Native execution requires the visible CLI opt-in:

```bash
veritas-latent run native-plan.json --output native-diagnostics --allow-native
```

This is trusted local code execution, with the same operating-system permissions
as a TrainLab recipe. Hash binding is not a sandbox or a source-rights judgment.
The supplied factory loads tensor weights with `weights_only=True`, checks the
checkpoint identity, rejects implicit dtype conversion, verifies every restored
state tensor against its saved value, and freezes model parameters.

Native captures have shape batch × time × features. A `data.prepare_token_rows`
job converts these into the aligned 2D rows required by geometry, compression
and calibration. Supply the original `input_ids`, one source record and domain
ID per window, and explicit aligned targets when scoring. Optional lengths and
Boolean masks exclude padding; no targets are inferred. The result includes
`hidden`, `logits`, `views`, `target_ids`, `record_ids`, `domains`, `positions`,
`context` and atlas `rows`. References to those fields can feed later jobs in the
same plan. Its `context` is already selected into returned-row order, which is
the index space used by decoder callbacks. The native validator exercises this
capture → preparation → PCA/readout/compression path on all four source interfaces.

`interventions.retrieval_sweep` accepts token arrays, an anchor, a continuation
horizon and a fixed donor map or donor input array. It constructs native states
internally; the manifest never serializes opaque model objects. The same helper
exposes retention, unread-row future access, paired values/full-memory patches,
persistent reset and sham controls.

Compression and bank diagnostics receive an explicit decoder callback, for example
`{"capability":"readout","context":{"context":{"result":"capture","path":["context"]}}}`.
Declare `readout_kind` correctly: COG's successor mixture returns normalized log
probabilities. Biases, vocabulary slicing, softcaps and mixture gates are part of
the native decoder, not replaceable with an assumed linear layer.

Workbench's limits are cooperative between operations. A single SVD or trusted
callback can outlast that limit. Use the existing TrainLab recipe timeout for
process supervision. Native latency measures the actual native forward separately
from the directly measured whole diagnostic session. It does not claim GPU memory,
energy or monetary measurements that were not taken.

## Training and the full research cycle

Reuse the existing Research Lab protocol and queue for hypothesis, falsifier,
design, seeds, stopping rules, execution, independent review and the next question.
This package supplies the diagnostic jobs within those stages:

1. Freeze Forge inputs, source records, family splits and exposure declarations.
2. Freeze a model/seed/recipe grid and primary contrasts; run panel and source audits.
3. Run native replay, decoder, state, position and sham checks before measurement.
4. Execute admitted training commands through TrainLab when the research design
   requires fitting. Preserve all seed attempts, optimizer/RNG states and fixed
   final checkpoints. Audit the update schedule and matched objective exposure.
5. Capture native observations once, then reuse them for independent analyses.
6. Evaluate same-checkpoint competence and retention gates, with the required
   strata, delays, domains and full-vocabulary metric identity.
7. Produce source-bound tables, plots and reports; verify offline reproduction.
8. Import the actual TrainLab receipt into Research Lab and obtain independent
   review. Preserve negative/incomplete results and define the next falsifier.

The provided `--ecosystem` example executes the Forge/readout/analysis/receipt/
research-memory connection using constructed observations. It launches no workers
and authorizes no subsequent training campaign automatically.

## Evidence and visualizations

Each completed run includes:

- `inputs/plan.json` and exact selected input bytes;
- `implementation.json`, including numerical runtime and source/template hashes;
- `ledger/report.json`, including capability coverage, attempts and session budget;
- `results/*.json` and deterministic `.npy` arrays, including resample indices;
- `summary.json`, `metrics.csv`, `report.md`, `report.html`, and `report.pdf`;
- declared figures as PNG, SVG and PDF, with their numerical `.data.json` inputs;
- `atlas.html` when a scatter/trajectory is requested: view and color selection,
  3D rotation, point pinning, sequence paths and plotted-row CSV export;
- `bundle.json` and `SHA256SUMS`, followed by an optionally verified ZIP export.

Figure types are scatter, trajectory, spectrum, heatmap, forest, curve, reliability,
signed stacked contributions and empirical CDF. They cover the historical
compression curves, context similarity, intervention effects, delay/position
contrasts, retention/decomposition, calibration and future-access figures.

Offline replay verifies the complete source bundle and current analysis runtime.
It reuses native/callback captures and recomputes numerical jobs. It compares the
saved result JSON and array bytes exactly. Model forwards, training updates and
timing reruns are zero. Replaying a failed or unsupported row does not convert it
to a successful measurement. Figure rendering timestamps are not numerical replay
targets; the source numerical results are.

## Verification commands

```bash
python -m unittest discover -s integrations/trainlab/tests_latent -v
python -O -m unittest discover -s integrations/trainlab/tests_latent -v
python -m unittest discover -s integrations/trainlab/tests -v

# Optional read-only parity against the user's preserved thread archives:
VERITAS_LATENT_ARCHIVE_ROOT=/path/to/archives \
  python -m unittest discover -s integrations/trainlab/tests_latent -v
python integrations/trainlab/examples/validate_latent_archive.py \
  --archive-root /path/to/archives --output /new/path/archive-validation.json

# Explicit native conformance on original weights and synthetic inputs; no fitting:
python integrations/trainlab/examples/validate_latent_native.py \
  --archive-root /path/to/archives --output /new/path/native-validation
```

The archive validator checks all 49 saved atlas representations and all 1,188
cycle006 position metric point/interval estimates. The optional tests also cover
cycle002 calibration selection and all recorded bootstrap selection frequencies,
cycle006 position prompt/ID identity and saved-logit scoring. The native validator
passes actual source/checkpoint pins through the same manifest runner used by the
CLI, generates a geometry figure for each model, and checks exact offline replay.
These are implementation regression checks, not a new experimental result.
