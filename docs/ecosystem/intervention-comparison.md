# Compare paired intervention outcomes

TrainLab compares baseline and treatment predictions on the same ordered
evaluation inputs. The comparison verifies the dataset, input IDs and
hashes, task, state contract and both prediction artifact pins. An exact
recipe file records the intervention. Put preprocessing or execution
changes in its description and bind the corresponding configuration in
the prediction requests.

`compare(design, recipe, panel, baseline, treatment)` accepts a path and
externally retained SHA-256 for the design, recipe and panel. The baseline
and treatment arguments also include the full expected prediction request.
The design uses these fields.

| Field | Meaning |
| --- | --- |
| `schema` | `trainlab.intervention-comparison.v1` |
| `mode` | `frozen` requires matching model identities. `retrained` requires two distinct declared training run pins. |
| `recipe_sha256` | Exact finite JSON intervention recipe bytes. |
| `panel_sha256` | Exact label and focal/collateral role declaration bytes. |
| `prediction_sha256` | Baseline and treatment artifact pins. |
| `training_run_sha256` | Null for frozen runs. An object with `baseline` and `treatment` pins for retraining. |

The panel has `labels`, a mapping from each evaluation ID to an object
with `role`, `labeled` and `label`. Valid roles are `focal` and
`collateral`. A labeled null is a legitimate expected output. An
unlabeled row must provide null and remains outside correctness counts.

The report retains changed prediction IDs and labeled rescues and harms.
Counts are broken down by focal and collateral cases. Unknown labels
leave the answer comparison incomplete. Artifact verification checks
exact declared identities. Refit provenance, elapsed training conditions,
coverage of independent mechanisms and causal isolation require separate
evidence.

```bash
python -m unittest discover -s integrations/trainlab/tests -p test_intervention_comparison.py
```

The local controls exercise two versions of a deterministic CPU fit, a
frozen treatment, a rescued focal answer, collateral damage, matching
null answers, and rejection of changed recipe, model or evaluation inputs.
