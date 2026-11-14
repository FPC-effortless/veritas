# Evidence-bound competence panels

DIAGNOSTICS-010 ([#538](https://github.com/FPC-effortless/veritas/issues/538))
adds `trainlab.competence_panels`. It scores actual predictions against explicit
expected answers, computes query and whole-map accuracy, and checks frozen
thresholds in **every required seed × template cell**. It extends
[assessment checks](assessment-diagnostics.md),
[bound prediction artifacts](prediction-artifacts.md) and the
[comparison ledger](experiment-diagnostics.md).

This is a scoped behavioral screen, not a declaration that a model is well trained.
Passing a primitive panel does not establish composition, adequate tuning, fair
supervision, independent evaluation or general intelligence. Compare primitive
and composition templates separately before interpreting an architectural gap.

## API

| Function | Inputs | Result |
| --- | --- | --- |
| `freeze_panel` | Existing prediction request, cases, required seeds/templates, query mode, query/map thresholds | Defensive-copy panel and canonical SHA256 binding every field |
| `score_panel` | Panel, external panel hash, observed/missing/failed predictions | Per-cell and aggregate metrics, attainable bounds, witnesses and status |
| `score_artifact` | Panel/hash plus saved prediction artifact/path/hash | Same scoring after existing exact-byte/request checks; no model calls |

Each case contains `id`, `seed`, `map_id`, `group`, `template`, `payload`,
`query_id`, and `expected`. Cases must match the request's IDs and order exactly.
Every required seed/template cell must exist. Seeds must cover the same map IDs
and query-member sets, with consistent group/template/payload metadata for each
map. Duplicate members, unexpected IDs and malformed fields are rejected. A map
means exactly its declared query members; the code cannot establish that these
enumerate all possible identities, queries or operations.

Input hashes remain in the prediction request. For multiple model seeds, its
model/configuration identities should bind the complete checkpoint/seed-routing
manifest. The scoring engine does not load models or attest those declarations.
Different input realizations or expected values can occur across seeds; the
contract fixes map membership and metadata, not identical task content.

`fresh_replay` requires a stateless request surface: each row contains a complete
history/query and the target reconstructs state independently. A recurrent model
can satisfy this surface by resetting before each row. `continuous` requires a
sequential surface whose protocol declares all reset and stream boundaries.
The scorer cannot infer whether a target actually reset between queries. These
are bound declarations, not execution attestation. A complete replayed map must
never be presented as an uninterrupted multi-query interaction.

Thresholds have exactly `query_accuracy` and `map_accuracy`, each in `(0, 1]`.
Both apply independently to every required cell. Pooled scores cannot override
a failing seed or task. The panel hash binds thresholds, labels, seed/task
requirements, state semantics and exact request identities. Preserve that hash
before evaluation; the API itself does not prove chronological preregistration
or absence of tuning on this panel.

## Incomplete evidence and whole maps

`score_panel` accepts observations `{id, status, value}`. `status` is `observed`,
`missing` or `failed`; missing/failed rows require `value=null`. Omitted required
IDs are missing. An observed null is a legitimate answer. Canonical JSON equality
distinguishes `true`, `1` and `1.0`. NaN, Infinity, duplicate and extra IDs fail
validation instead of producing a favorable result.

A map is correct only if all declared members are observed and correct. One
observed wrong answer makes that map fail, even if another member is missing.
If no answer is wrong but some are missing, the map is unresolved. Query accuracy
is null when any query is unobserved. Map accuracy is exact only when every map's
outcome is known; this can include known-failed maps with missing members.

The report retains lower/upper attainable bounds:

- Query lower bound: observed correct / all required queries.
- Query upper bound: (observed correct + unobserved) / all required queries.
- Map lower bound: wholly correct maps / all required maps.
- Map upper bound: maps without an observed wrong answer / all required maps.

These are deterministic missing-data bounds, **not confidence intervals**. A cell
is `FAILED` when even its best possible completion misses a threshold;
`INCONCLUSIVE` when observations remain and failure is not inevitable; otherwise
`TESTED` when its complete scores meet both thresholds. Known failures outrank
incompleteness in the report status. No observed-only accuracy substitutes for the
declared denominator. Failed executions remain unresolved observations, not
invented incorrect answers or successes.

Reports retain wrong/missing/failed row IDs. The external plan maps each witness
back to its input hash, group and map. Correlated queries/maps do not create
independent evidence, and no seed uncertainty or population-level guarantee is
estimated. Use the existing unit-aware statistics only with defensible units.

## Ledger and artifact integration

The result envelope contains `report`, `report_sha256`, and
`competence_reference`. The latter uses the existing ledger shape:
`{status: supported|failed|unknown, evidence_sha256: report_sha256}`. Status maps
from `TESTED`, `FAILED`, `INCONCLUSIVE`, respectively. The reference means the
declared panel predicate was supported/failed/unknown; it does not grant broad
scientific admission. Retain the report and plan alongside the reference. The
ledger still does not independently open or verify evidence pointers.

`score_artifact` uses `read_predictions` to check actual bytes and the full request.
Changed model/data/code/configuration/input order or altered artifact bytes are
rejected. Both query and map metrics reuse that one prediction artifact. Direct
`score_panel` inputs remain explicitly `SUPPLIED_OBSERVATIONS`; neither route
attests truthful model execution, hidden metadata or reference-label quality.

Finite JSON is bounded to the existing 16 MiB contract, with at most 10,000 cases,
100 seeds and 100 templates. This is an offline trusted-input scorer, not a
process limiter or a privacy filter. Use authorized data; expected labels and
witness IDs are retained in the panel or reports.

## Reproduce the engineering example

```sh
PYTHONPATH=integrations/trainlab/src python -m unittest discover -s integrations/trainlab/tests -p test_competence_panels.py
PYTHONPATH=integrations/trainlab/src python -O -m unittest discover -s integrations/trainlab/tests -p test_competence_panels.py
PYTHONPATH=integrations/trainlab/src python integrations/trainlab/examples/diagnose_competence.py --root /tmp/new-competence-run
```

The example freezes plans before executing three CPU control sessions. Eighteen
queries cover nine two-member maps: primitive SET, COPY, and LINK under source
overwrite. It reuses the preceding lifecycle target and binds both driver files.
The correct control scores 18/18 queries and 9/9 maps. A snapshot-LINK fault
scores 15/18 queries and 6/9 maps: primitive and COPY pass, LINK fails. An explicit
output-value corruption control scores 0/18 and 0/9. A partial clean panel remains
inconclusive. A separate offline query recount reads the same saved artifact
without invoking any target. The example links measured-session reports, bound
prediction artifacts, competence reports and the comparison ledger.

Seed 0 labels a deterministic constructed control, not a trained model seed.
The target has no training or tuning; three reference-program executions are not
evidence about CSM, staged training, real-project diagnostic accuracy, external
adoption, or research productivity. Query-quality cost points come from the
existing session meter; complete-map accuracy is not silently substituted into
those points. Native learned-model acceptance remains a separate research step.
