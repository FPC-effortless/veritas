# Score task behavior

TrainLab scores regression, ordered token sequences and retrieval from
rows of labels and model predictions. It binds the report to a SHA-256 of
the task, configuration and input rows in their declared order. Each row
has a unique string `id`, a string `slice`, a `label` and a `prediction`.
Use JSON null to declare an unavailable label or prediction.

```python
from trainlab.task_behavior import regression

report = regression(
    [
        {
            "id": "sample-17",
            "slice": "validation",
            "label": 3.0,
            "prediction": 2.5,
            "interval": [2.0, 3.5],
        },
    ],
    intervals=True,
)
```

The overall report and each slice give expected, observed, unobserved and
inapplicable counts. Partial scope suppresses the corresponding full-scope
score. The observed-only score retains its denominator so it can be read
alongside missing coverage. No default pass threshold is applied.

| Function | Input and metric definition |
| --- | --- |
| `regression(rows, intervals=False)` | Finite scalars with magnitude up to 10¹². Reports mean absolute error, root mean squared error, and mean prediction minus label. Set `intervals=True` and include a closed `[lower, upper]` or null per row to score empirical prediction interval coverage independently. |
| `sequence(rows)` | Ordered lists of up to 512 string tokens. Reports exact match, matching target positions divided by target positions, and mean unit-cost Levenshtein distance. Extra tokens affect exact match and edit distance. Position accuracy is undefined for an empty target denominator. |
| `retrieval(rows, cutoff=k)` | Each row is a query. `label` maps candidate IDs to relevant, irrelevant or unjudged using true, false and null. `prediction` is a deduplicated, ordered list of IDs, with ties resolved by the producer before scoring. Scores average precision at k with denominator `min(k, relevant)`, recall at k with denominator `relevant`, and reciprocal rank at k. It then averages across observed applicable queries. |

Retrieval scores require exhaustive binary labels within the declared candidate
set. An unjudged candidate leaves the query unobserved. A completely judged
query with zero relevant candidates is inapplicable. An empty prediction list
is an observed empty ranking. Inferences about collection-wide retrieval
require an independently justified candidate-set design.

All packs cap input at 2,000 rows and the shared finite JSON size limit.
Sequence processing also caps the cumulative edit-distance work. Outcome
metrics describe the declared data and carry no statistical or qualification
claim.
