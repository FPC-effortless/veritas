# Dataset diagnosis before model fitting

DIAGNOSTICS-003 (#523) adds a local, dependency-free exact-content pack to Forge.
It complements release integrity: different source/subject IDs can still conceal
identical input content or a shared entity. The pack produces inspectable findings
before a model is trained. It does not establish overall dataset quality, truthful
labels, causal independence, scientific validity, or frontier qualification.

## Input and local use

Provide one ordinary finite JSON document and its independently retained SHA256:

```json
{
  "schema": "forge.diagnostic-input.v1",
  "feature_fields": ["measurement", "condition"],
  "group_fields": ["entity", "generator"],
  "rows": [
    {"id": "train-1", "split": "train",
     "features": {"measurement": 4, "condition": "warm"},
     "groups": {"entity": "machine-a", "generator": "template-a"}, "label": 1},
    {"id": "validation-1", "split": "validation",
     "features": {"measurement": 4, "condition": "warm"},
     "groups": {"entity": "machine-b", "generator": "template-a"}, "label": 0}
  ]
}
```

```bash
python -m forge_data.diagnostics --input view.json --sha256 EXPECTED_SHA256 \
  --max-rows 10000 --max-findings 100 > findings.json
```

Or call `forge_data.diagnostics.diagnose(path, sha256=pin, max_rows=10000,
max_findings=100)`. The input hash binds the exact row order and feature/group
contract. Keep it in a protocol or execution receipt, not merely inside the file
being checked. Row IDs must be globally unique within this view. Group values are
scalar JSON identities; no cross-source identity resolution is inferred.

Select prediction-time features, excluding labels and record IDs unless they are
deliberately part of the question. Including a unique ID can mask every duplicate;
omitting meaningful context can create irrelevant apparent conflicts. The tool
cannot decide which projection represents your scientific task.

`label` and `groups` may be omitted. Missing/null labels are unknown, not a class;
missing/null groups are unknown, not a shared group. Empty strings are literal
values. Required selected features distinguish absent from null; both produce
findings. Extra feature fields are retained in the input identity but excluded
from equality comparisons. Values such as integer `1` and float `1.0` have
different canonical JSON signatures. No unit conversion, numeric tolerance,
normalization, embedding similarity, or semantic matching occurs.

The pack supports only explicitly selected train/validation views. A TEST row
anywhere in the document is rejected even if it falls beyond the diagnostic row
budget. This is a local guard, not permission to open or export protected data.

## Reading the report

| Check | Observation and status |
| --- | --- |
| Completeness | `FAILED` when declared required features are missing/null; otherwise `TESTED` only after complete scanning. |
| Exact duplicates | Repeated complete selected features produce `INCONCLUSIVE` review findings; intended repeated observations may be valid. |
| Split content | `FAILED` means an exact feature signature crosses train/validation. It is an observed disjointness violation, not automatic proof of causal leakage. |
| Declared groups | `FAILED` means a supplied entity/generator identity crosses splits. The grouping itself remains an unverified declaration. |
| Label consistency | Different known labels for identical complete features produce `INCONCLUSIVE` findings. No label is declared wrong or changed. |
| Unavailable access | Missing labels/groups across a complete scan produce `UNSUPPORTED`; partial availability produces `INCONCLUSIVE`. |
| Unimplemented checks | Near duplicates, preprocessing leakage, semantic units, and drift remain `NOT_RUN`. |

`TESTED` only establishes the named predicate on the selected view. No conflicts
does not prove labels correct. Different generator IDs do not establish independent
mechanisms. No group overlap does not prove the supplied identities are reliable.
A feature mismatch can hide leakage that exact-content checks cannot detect.

Each finding contains the check kind, interpretation, affected row IDs, split,
zero-based input index and canonical row hash. It retains a small witness: the
first pair demonstrating a duplicate, cross-split overlap, or label conflict.
It does not enumerate every affected pair. Summary counts are unique content/group
signatures; duplicate `additional_rows` counts rows beyond the first per signature.
This avoids quadratic all-pairs work. Finding IDs bind the input hash and witness,
so reordered input has a new identity and may select different witness pairs.

Raw feature/label values are omitted from the report. IDs, field names and hashes
can still identify people or enable guessing of low-entropy values. This is not
an anonymizer, safe-publication certificate, or private-data approval. Retain the
original selected view within its authorized boundary for local reproduction.

## Budgets and incomplete coverage

The file is bounded to 16 MiB and 100,000 rows; at most 32 feature and 32 group
fields are selected. Full parsing and structural validation occur before scanning.
`max_rows` bounds the examined prefix, not input parsing cost, RAM or CPU time.
Use an outer supervised TrainLab process for wall-time termination.

A shortened prefix produces `state=PARTIAL`. Observed failures remain failures,
but absence of a finding never becomes `TESTED` for the whole view. Zero rows
scanned produces `NOT_RUN`. Split-disjointness checks require both train and
validation to be represented; a one-split input cannot yield a clean comparison.
Incomplete feature vectors do not enter exact-content or label-conflict groups.

`max_findings` bounds retained witnesses from zero to 1,000. Aggregate counts and
statuses still include every scanned row; `findings_omitted` exposes truncation.
There is no resumable scan cursor in this version. An interrupted process may have
only a partial Workbench operation journal, not a completed dataset report. The
normal row-budget return preserves observed findings; hard termination has a
separate execution boundary.

## Composed acceptance workflow

Install the four ecosystem packages from the same checkout, following the
[ecosystem quickstart](README.md), then run:

```bash
python integrations/trainlab/examples/diagnose_dataset.py --root NEW_DIRECTORY
```

Three actual TrainLab executions use clean, injected-fault, and bounded-prefix
public tabular controls. All changes are made before Forge freezes the release.
The worker reconstructs the selected train/validation view through Forge and
compares it with the pinned view, verifies runtime source/version identities,
records diagnostic execution in Workbench and retains the detailed dataset report.
Research Lab links each finding report to the dataset and run receipts.

The fault release deliberately places equal features and a shared entity across
different Forge subjects/splits, changes the corresponding label, and includes a
null feature. Forge release integrity can hold while these content findings remain.
The prefix run must not present its unexamined suffix as clean. No model is fitted;
no protected TEST rows are selected or scored. Constructed TEST bytes are verified
only for the public release's file integrity.

Workbench `scan_execution=TESTED` means the report was generated. Inspect
`dataset-report.json` for actual data findings and coverage. Run completion is not
dataset acceptance or permission to start a scientific comparison.

## Existing tools and next extensions

The input is plain JSON so existing data projects can export a selected view
without changing trainers. These inexpensive exact checks require no service,
model download, accelerator, or account. They are not an implemented Cleanlab,
Deepchecks, Evidently, DVC or MLflow integration. Those replaceable engines need
their own pinned import contracts, applicability checks, versioned evidence and
clean/fault qualification. Near-duplicate, label-quality estimation, drift and
preprocessing investigation remain separate roadmap items.
