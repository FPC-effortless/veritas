# Private training-record assessment bridge

This adapter connects canonical TRAIN-001 policy recomputation with the existing
four-way training diagnostic interpretation. It is an **offline, evaluator-private
record-consistency check**, not a model runner, scorer, independent verifier,
training qualification, or held-out extension of the measured TRAIN-only capture.
No provider is unblocked and no scientific status is promoted.

## Use

Install the existing Veritas dependencies and the sibling TrainLab package. The
base dependency-free TrainLab runner does not import Veritas for other workflows.
The adapter deliberately requires the actual canonical engine, not a mock fallback.

```python
from trainlab.training_assessment import (
    assess_private_training, verify_private_training_assessment,
)
assessment = assess_private_training(canonical_training_report, diagnostic_records)
assert verify_private_training_assessment(assessment)
private_record = assessment.private_payload()  # evaluator-private, never a public export
assert assessment.public_payload() == {"visibility": "evaluator_private", "withheld": True}
```

`Controller.assess_private_training(report, diagnostics)` provides the same private
operation. It does not insert the report into the Research Lab public/readable
ledger, prepare a public bundle, sign, grant permissions, or promote a protocol.
Its result is not accepted by the scoped claim-promotion API.

The caller supplies a canonical `TrainingReport` or its private JSON payload. A
fresh canonical parse and `assess_training` recompute its nested evidence, policy,
populations, numerical gates and overall result. Edited statuses refuse rather
than being copied. Current TRAIN-001 providers leave execution/chronology and
memorization/contamination unavailable; `training_validated` remains false and
`capability_gain` remains null. Known failures stay FAIL even when some diagnostic
scores improve. Overall qualification remains `NOT_QUALIFIED`.

## Four-phase association

Every supplied diagnostic record has a unique `training_seed` from the independently
specified canonical expected seed list. It uses the existing v3 phase fields:

- `reference_target_sanity` on TRAIN;
- `train_before`, `train_after`, `heldout_before`, `heldout_after`;
- an explicit `minimum_reference_score` for descriptive target sanity;
- `canonical_binding`, containing the exact canonical `run_id` and a
  `point_sha256` map with all four phase names.

`point_identity(EvaluationPoint)` hashes the complete canonical point serialization,
including source membership/digests, model/checkpoint, scoring conditions and
outcomes. Before/after populations, scorer/metric and checkpoint consistency are
validated by TRAIN-001, not redefined here. Diagnostic per-member IDs and scores
must exactly match those canonical outcomes; no intersection, duplicate collapse,
mean-only association or missing-seed denominator reduction is permitted.

These association hashes are **caller-supplied associations**, not execution or
scorer authentication. They can establish that two supplied descriptions agree,
not that the model produced them. Neither a matching hash nor target-sanity score
proves a correct scorer, uncontaminated holdout or transferable capability.

Missing phase, seed, canonical replicate, target sanity or exact association stays
`UNASSESSED`; missing canonical outcomes are retained and not converted to zero.
Contradictory populations, values or bindings refuse. Failed target sanity is
`PIPELINE_INVALID`, never a positive transfer interpretation. A valid link returns
`DIAGNOSTIC_SCORES_LINKED`, which is not a qualification PASS.

Historical v3 reports usually lack exact canonical point associations. They remain
unassessed unless genuine corresponding evidence exists. Do not invent checkpoint,
scorer, source, review or phase metadata to fill those gaps. The helper implementation
is shared with existing v3 tools via a compatibility import, not a second diagnostic
rule set. Training-ceiling, parse-consistency and descriptive-label semantics are
unchanged.

## Privacy and supported boundary

Full canonical reports, supplied diagnostics and private identities are retained
only in the explicit private payload (bounded to 16 MiB). Public/buyer projections
and ordinary `repr` withhold the complete record, including IDs and hashes.
`verify_private_training_assessment` recomputes from retained sources and rejects
edited summary outcomes. Raw private JSON is not publication-safe; the API does not
write it, sanitize it or transmit it. No protected TEST panel is opened.

This does **not** implement prospective held-out execution, raw-output/scorer replay,
a native tiny-overfit control, semantic/near-duplicate detection, independent training
attestation, or additional measured-model adapters. Those remain missing providers,
not implied capabilities of this bridge. The existing measured assurance path is
still `TRAIN_ONLY_OBSERVED_CLASSIFICATION`. A signed scoped review cannot substitute
this private diagnostic object for missing transfer evidence.

## Verification

Constructed fixtures test canonical recomputation, failure preservation, missing
seeds/phases, unscored rows, duplicate/mismatched members and scores, checkpoint/
scorer point-binding mutation, failed target sanity, private projections and retained
assessment tampering. No models or protected data are used.
