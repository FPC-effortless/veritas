# LE-002: LearningEfficiencyReport

This is a bounded, evaluator-private **reporting contract**, not a trainer, billing
integration, model runner, cost estimator, execution attestor, qualification gate,
or comparison showing that Veritas is more efficient than a baseline.

## Outcome and falsifiers

The report binds an exact experiment, the complete #162 `TrainingReport`, existing
#189 selection and #160 derivation evidence when supplied, external run-receipt
identities when supplied, and explicit resource observations. It retains model,
checkpoint, method/configuration, environment/verifier, population and metric
semantics through those full provider records, not favorable scalar summaries.

Owned paths are only `src/investigation_world/learning_efficiency/**`,
`tests/learning_efficiency/**`, and this documentation. Existing trainers, provider
billing integrations, Observatory, Frontier and shared exports are unchanged.

The implementation reuses `ScienceRecord`, `TrainingReport`, CAP acquisition and
retention records, `validate_selection`, `validate_compilation`, and the existing
strict `compile_verified_bundle` admission path. Standard-library arithmetic is
sufficient; no dependency, second evaluator, or generic adapter framework is added.

Falsifiers include a changed panel/checkpoint/configuration hidden behind an old
report; dropping a missing/negative seed; money inferred from a unitless receipt;
selected-only generation costs presented as full-pool costs; alias double charging;
training loss used as capability; and recomputing a hash to legitimize forged
provider outputs or an altered training bundle.

## API and revalidation

`EfficiencyStudy` includes:

- experiment identity and the entire training qualification report;
- optional full selection and learning-asset compilation reports;
- optional `RunReceipt(seed, receipt=ReceiptValidation(...))` values binding the
  exact manifest, bundle, base revision and final checkpoint;
- optional CAP `RetentionLink` values anchored to exact before/after pairs already
  in this study (not an unsupported later checkpoint or changing panel);
- optional declared `iid`/`adversarial` designations on exact existing held-out/
  transfer population IDs, remaining-gap references and limitations.

There is no IID or adversarial inference from a distribution's name. Unclassified
held-out records stay unclassified. OOD summaries preserve declared structural
shift versus within-family-only evidence. Designations remain declarations, not
proof that an adversarial generator or IID sampling protocol was validated.
Remaining-gap references are declarations, not automatically remeasured deficits.
The complete per-panel values, unknown/zero-score counts, failures, transfer
classification and guardrail/exploit policy results remain in the training report.

```python
from investigation_world.learning_efficiency import (
    ResourcePlan, ResourceObservation, assess_efficiency, resource_components,
    validate_efficiency,
)

plan = ResourcePlan(
    metric="gpu_hours",
    unit="GPU-hour",
    unit_definition=retained_hardware_and_meter_definition,
    stages=("training",),
)
components = resource_components(study, plan)
# Supply measured/reported records covering those exact components, including
# zero-use observations where actually recorded. Do not manufacture observations.
report = assess_efficiency(
    study, plans=(plan,), observations=retained_observations,
    **actual_provider_inputs,
)
validate_efficiency(
    saved_report,
    study=independently_expected_study,
    plans=independently_expected_plans,
    observations=independently_retained_observations,
    **actual_provider_inputs,
)
```

A selection report requires the actual complete candidate pool, all gap-source
pairs, and an **externally expected** selection policy. Its saved decisions/costs
are freshly recomputed. A connected training bundle is freshly compiled from its
exact selected successful recordings under the existing narrow admission recipe;
the **entire bundle** must equal the supplied bundle. Thus selecting one experience
cannot authenticate arbitrary caller-authored trainer bytes or unrelated lineage.
Selected-but-unused experiences remain counted. Hard negatives and candidate
learning assets do not become admitted training examples.

A derivation report requires actual sources/receipts and an externally expected
transform policy, then fresh provider recomputation. When linked to selection,
every derivation source must be exact selected material. Orphan source/receipt
inputs are rejected rather than ignored. Missing/deleted artifacts or changed
inputs invalidate old reports. Existing provider boundaries still exclude
held-out/nonpublic inputs from admitted training and preserve the pinned public
financial TRAIN profile; no broader admission profile is invented here.

`checked()`/model parsing revalidates full nested identity and recomputes numerical
results, **not** current artifact availability. Consume saved reports through
`validate_efficiency` with independently retained expectations and actual provider
inputs. Passing a saved report's altered contents back as all the expectations is
not independent validation. External measurement and receipt authentication remains
outside this contract; no caller `attested=True`, trusted callback or PASS flag exists.

## Resource dimensions, units and scope

Each `ResourcePlan` pins the metric, exact unit-definition reference, stages and
optional seed. Hardware/meter configuration belongs in GPU unit definitions;
tokenizer/counter identity belongs in token unit definitions; currency and billing
basis belong in monetary unit definitions. There is **no automatic conversion**
between units, currencies, hardware classes, meters or tokenizers.

Supported measured/reported dimensions are training tokens, GPU-hours, FLOPs or
CPU-core-hours, teacher calls/tokens/cost, human review examples/hours, actual
monetary cost and wall time. Count observations must be integral. Monetary units
require an explicit three-letter currency code; the schema does not authenticate
that currency's issuer, invoice, exchange rate or payment. Equivalent-compute units
are allowlisted; arbitrary budget counters cannot masquerade as compute.

Observations bind the exact study and plan, measurement identity/digest, covered
components, nonnegative finite value or unknown reason, and provenance:
`EXTERNALLY_REPORTED`, `CONSTRUCTED`, or `UNKNOWN`. These are not authenticated
measurements. Constructed values must never be described as observed real spend.
Measurement digests must commit complete, uniquely identified charge/measurement
records, **not** bare numeric amounts. Identical numbers on distinct genuine
charges are not aliases; untrusted external records cannot establish billing truth.
The existing `ExternalRunReceipt.cost` is unitless and is **never** interpreted as
money; neither receipt elapsed time nor memory bytes become GPU-hours.

The five scope stages are generation, selection, derivation, training and
evaluation. Generation commits the **whole** selection report, including all
rejected candidate slots and gap-source work—not just the final selected subset.
Training binds each exact run manifest. Evaluation binds complete supplied point,
control and exploit records. Missing stage/run identities prevent complete coverage.
An observation can cover a shared charge across several components once; aliases
of the same measurement bytes are deduplicated, while conflicting identities,
amounts/scopes and overlapping distinct charges reject. Shared generation,
selection and derivation cannot be silently charged separately to every seed.
Splitting one component into multiple additive charges is deliberately unsupported:
aggregate its records into one retained measurement, with provenance, first.

Every denominator reports included/excluded stages, exact expected/known coverage,
measurement references, provenance, known subtotal, missing stages, unit definition,
and unknown reason. `COMPLETE_DECLARED_SCOPE` means only that the declared
components are covered by supplied records. It does **not** mean full experimental
cost, authenticated spend or a matched-budget comparison. Reporting/revalidation
compute itself is unmetered. `full_pipeline_accounting_complete` remains false.

Derived denominators are also emitted separately for raw candidate slots, selected
slots, unique training examples in the bundle, and the #189 native execution-budget
union. Example count is **not** processed epochs or token count. Candidate/rejected
slots retain multiplicity; repeated aliases of an authenticated recording do not
multiply execution cost. The native union deduplicates recordings shared between
candidate and gap pools. Candidate and gap subtotals are never added to that union.
Invalid/unexamined candidates keep full native accounting unknown while retaining
the known subtotal. Native runtime budget units are not compute, money or GPU-hours.

## Arithmetic, replication and evidence boundary

The numerator is only the complete recorded held-out metric delta from #162:

- a seed plan uses that seed's recorded delta / scoped resource;
- a cohort plan uses **mean recorded delta across all expected seeds / total scoped
  resource** (not mean per-seed ratios and not a causal gain estimate); this is not
  comparable across different replicate counts without an explicit matched protocol;
- each denominator remains separate—there is no universal efficiency scalar;
- positive, zero and negative deltas are retained, including known policy failures;
- a zero denominator is undefined, never infinity; missing resources are unknown,
  never zero; partial totals cannot produce a complete-scope ratio;
- missing/unknown seeds suppress the cohort numerator, rather than shrinking its
  denominator. An observed seed's own descriptive arithmetic remains inspectable.

Per-seed deltas, expected/observed/missing/unknown seeds, known range and sample
standard deviation are descriptive variability only. No confidence interval is
fabricated; the report explicitly sets it to `None`. The study may have failed
training gates; that is retained alongside negative descriptive arithmetic.

Current #162 cannot establish aggregate training PASS because independent execution,
prospective chronology and memorization/near-duplicate evidence providers are
unavailable. Consequently `capability_gain=None`, every verified-efficiency value
is absent, and `verified_capability_efficiency="UNKNOWN"` **always**. Numerical
arithmetic cannot promote environment/experience maturity, scientific/Frontier
qualification, commercial readiness or release authority.

## Privacy and verification

Every local record/report is evaluator-private. Public/buyer-safe projections
withhold the entire record, including hashes, model identities, references, counts,
paths and free text. `model_dump()` is private operator serialization, not export.
Tests use explicitly constructed records and public deterministic native fixtures;
no real model, paid compute, protected panel or private benchmark is run.

```sh
python -m pytest tests/learning_efficiency -q
python -m ruff check src/investigation_world/learning_efficiency tests/learning_efficiency
python -m mypy --follow-imports=silent src/investigation_world/learning_efficiency
python -m pytest tests -q
python tools/quality_baseline.py check
```

Installed-wheel tests run outside the checkout, copying tests only (including the
provider fixtures in `tests/training_qualification`, `tests/experience_selection`
and `tests/experience_foundry`). Full suite, wheel imports/tests, quality ratchet,
independent review and exact-head remote CI remain separate verification gates.

For the broader optional `tests/experience` installed suite, Gold-10 diagnostics
also require the repository's public fixture data, which is intentionally not wheel
content. Use `VERITAS_TEST_FIXTURE_ROOT` where supported and an isolated installed
layout whose Gold-10 default root links only to the existing public `data`/`docs`
fixtures. Existing catalog/owner-file lookups may additionally use an isolated
`src/investigation_world` link back to the **installed package**, never checkout
source. Keep `PYTHONPATH` pointed solely at installed package files and verify
module paths. A missing public-fixture root is a harness failure, not a reason to
fall back to checkout package imports or silently drop failing tests.
