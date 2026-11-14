# Dataset distributions, reviewed corrections and transformation provenance

DIAGNOSTICS-006 (#530) extends the [dataset diagnostic view](dataset-diagnostics.md)
with four offline APIs in `forge_data.quality_diagnostics`. They run without a
model or optional ML dependency. Inputs are operator-authorized public
train/validation views, read under external SHA256 pins. TEST rows anywhere in
the document are rejected before a bounded scan. Finite plain JSON, 16 MiB and
32 nesting levels are enforced; existing view rules cap rows and field counts.

## Interfaces

| API | Required input | Output and boundary |
| --- | --- | --- |
| `distributions` | Reference/current paths and hashes; selected splits; feature kinds; numeric/categorical/missingness thresholds | Empirical KS or total-variation distance, known/missing/invalid counts, categorical rarity/novelty and explicit scan coverage. No significance or causal degradation inference. |
| `adjudicate` | Pinned view and explicit reviewer decisions with old/new labels, identity and rationale | New document, parent hash, new canonical hash, applied IDs and all decisions. Source remains unchanged. Reviewer identity and corrected truth are not independently verified. |
| `transformation_audit` | Pinned view, declared fit provenance and per-row/field availability | Evaluation-fit, target-derived and future-feature findings; unknown fit/time and uncovered fields remain unresolved. Does not inspect the trainer to discover undeclared transformations. |
| `near_duplicates` | Pinned view, text field, similarity threshold and pair/token bounds | Cross-split token-set Jaccard candidates and exact row witnesses. Similar words do not establish duplicate meaning or leakage. |

All reports are `forge.quality-diagnostics.v1` and bind parameters and source
hashes. `TESTED` means the scoped check completed, not that the dataset is
universally valid. `FAILED` marks an observed declared-rule violation,
`INCONCLUSIVE` marks unresolved evidence or review candidates, `UNSUPPORTED`
marks unavailable usable inputs, and `NOT_RUN` marks a zero search budget.
Scientific qualification always remains `NOT_QUALIFIED`.

## Distribution and missingness comparison

Declare `fields={"feature": "numeric"|"categorical"}` and all three thresholds:
`numeric`, `categorical`, `missingness`, each in `[0,1]`. Thresholds are descriptive
acceptance criteria, not universal defaults derived from a dataset's purpose.
Default splits are reference train and current validation. `max_rows` caps each
selected split independently and preserves available/selected counts.

Numeric distance is the maximum difference between the two empirical cumulative
distributions. Categorical distance is half the sum of absolute frequency
differences. Categorical identities use typed canonical JSON, so false and zero
are distinct. Numeric booleans and non-scalar categories are invalid observations,
not silently converted values. Missing/absent selected features are counted
separately; the missingness metric is the absolute missing-rate difference.

No usable values on either side leave distance unavailable. Missing values or
prefix truncation prevent a clean distribution status even when known values
match; observed violations remain failures. Up to 100 category counts are shown,
with complete total/rare/novel counts. Rare means current count at most the
declared `rare_count`; nothing is deleted. The method does not establish units,
source equivalence, independent sampling, statistical power or a connection
between drift and a model's performance. Group/error slice linkage is separate.

## Reviewed label versions

Each review contains `id`, `decision` (`accept`, `reject`, `unresolved`),
`old_label`, `new_label`, `reviewer`, and `rationale`. Every old-label precondition
must match typed JSON in the pinned source. Unknown IDs, duplicate decisions,
missing reviewer/rationale and stale labels are rejected before applying changes.
Only explicit accepted decisions change labels. Rejections and unresolved
decisions remain in the evidence; unresolved decisions keep the workflow
inconclusive. There is no model-disagreement-to-automatic-correction rule.

The returned `observations.document` is a new version in memory. Write it with
`forge_data.core.canonical` to reproduce `document_sha256`; the parent identity
is the exact source file hash. This is not an authenticated review service and
does not prove that a named person reviewed the item. Real users must obtain
actual review and verify corrections on fresh evaluation before claiming a
repair. The engineering example uses visibly constructed review records and
does not count them as human adjudication. `repair_effect=NOT_MEASURED` persists.

## Transformation and temporal evidence

Each transform declares `id`, `outputs`, `fit_scope`, `fit_ids`, and
`uses_target`. A stateless transform requires an empty fit list; a fitted
transform needs known fit rows. Unknown scope/IDs or empty fitted membership
remain unresolved. Known validation fit rows are flagged. `uses_target=true`
flags target-derived inputs for investigation; task-authorized supervision and
the intended feature boundary still require interpretation.

Every view row and selected feature needs an availability record containing
`id`, `field`, `available_at`, and `prediction_at`. Missing/null timestamps remain
unknown, while every supplied timestamp must be offset-aware and valid. Times
are normalized to UTC before comparison. Future availability is a failure;
duplicate row/field records are rejected. Missing availability and fields with
no transform declaration prevent `TESTED`. At most 100 finding/unknown witnesses
are shown, with complete counts. These are declarations, not execution attestation.

## Bounded lexical review

Near-duplicate search case-folds strings and compares sets of whitespace tokens.
It ignores ordering and token frequency and does not implement semantic,
embedding, edit-distance or modality-aware matching. Empty, nontext or overly
long rows are unsupported, not truncated into apparently valid text.

Only train-versus-validation pairs are searched, in declared row order, up to
`max_pairs`. Findings retain row IDs and similarity, capped at 100 witnesses
while match counts are complete over examined pairs. A prefix search cannot
claim absence of overlap. Candidates are `INCONCLUSIVE` pending review, not
automatic leakage verdicts; a full no-match result covers only this method.

## Composed controls and reproduction

```sh
python -m pip install -e . -e integrations/forge -e integrations/trainlab -e integrations/research_lab
python integrations/trainlab/examples/diagnose_data_quality.py --root /tmp/veritas-data-quality
python -m unittest discover -s integrations/forge/tests -p test_quality_diagnostics.py
```

Use a new directory. Forge freezes 128 constructed subjects and supplies only
train/validation views. TrainLab runs clean, fault and partial cases. The fault
case changes numeric/category distributions, introduces missingness and a lexical
duplicate, and declares evaluation-fit, target-derived and future-available
features. The partial case restricts scans, omits provenance and leaves review
unresolved. Corrected views are emitted separately with verified canonical hashes.

The workbench retains scan/persist operations; TrainLab retains reports, versions
and hashes; Research Lab links findings to both release and execution. Runtime
trees, source, selected view, protocol and recipe are bound. There are zero model
fits and no protected TEST scoring. This demonstrates bounded engineering
behavior, not real-world sensitivity, corrected label truth, research throughput
or frontier quality. Images/audio semantics, inferred identities, authentic
review services and external-tool engines remain separate work.
