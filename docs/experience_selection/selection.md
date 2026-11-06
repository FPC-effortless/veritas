# SEL-001: evidence-bound experience selection

## Outcome and limits

`investigation_world.experience_selection` selects a bounded, reproducible subset
of a **supplied actual rollout pool**, instead of treating every failure or all
available data as useful. It does not collect rollouts, generate model answers,
train models, modify a verifier/runtime, or export a new training format.

The current executable provider is the existing pinned **public synthetic financial
TRAIN** recorder. This is a deliberate provider ceiling, not general environment
coverage: another profile requires its own independently validated admission and
partition binding. The selector does not widen that provider or #160 transforms.
The implementation and tests demonstrate software behavior, not acquisition gain,
causal capability deficits, scientific/Frontier qualification, or learning value.

## Entry points

```python
from investigation_world.experience_selection import (
    SelectionPolicy, select_experiences, validate_selection,
)

policy = SelectionPolicy(seed=17, max_items=8, max_per_stratum=1)
report = select_experiences(
    actual_recorded_experiences,
    gap_sources=retained_train_receipt_source_pairs,
    policy=policy,
)
# Before consuming a saved report: supply the externally expected policy and
# the actual retained inputs, not a caller-authored PASS or a self-hashed envelope.
validate_selection(
    report, actual_recorded_experiences,
    gap_sources=retained_train_receipt_source_pairs, policy=policy,
)
```

Inputs are `RecordedExperience` values and optional `(CounterfactualReceipt,
RecordedExperience)` gap-evidence pairs. At most 256 candidate slots and 64 gap
protocol inputs are consumed; oversize inputs fail closed, including generators.
A fixed policy schema/version rejects unsupported versions/modes and invalid
budgets. Target full capability-contract digests, frozen held-out task IDs and
source digests are policy-bound. Empty target filters mean all **validated bound**
gaps, not all taxonomy labels.

Every invocation reparses the policy, freshly validates actual candidate sources
through #156 `verify_recorded`, and recomputes #153 intervention families and #157
`ingest_capability_failure`. A cached/serialized gap envelope is not accepted as
source authority. Validated gap evidence retains exact source, receipt, full
capability, family and gap identities. Distinct protocols are not independent
agents or population failure rates; task association is declared, mechanism
hypotheses and causal qualification remain UNKNOWN. All raw gap receipts are freshly validated before selector-side normalization
of verifier-relevant source behavior; provider fingerprints that include conclusion
prose cannot manufacture distinct failure evidence. One protocol, duplicate
behavioral protocols, no evidence, or no matching full capability digest yields zero eligible
items. Unbound observational family labels cannot manufacture a target capability.

## Partition and privacy boundaries

- Non-TRAIN, nonpublic source roots and declared frozen held-out overlaps are
  rejected **before evaluator/artifact access**. Actual provider validation also
  matches the pinned TRAIN source, so editing a split label cannot bypass the gate.
- Any such input in the *gap-evidence* pool aborts before receipt-outcome processing.
  Selection never receives or optimizes on held-out scores. Frozen exclusions are
  input commitments, not a claim that an external panel was independently audited.
- The canonical provider uses authorized verifier evidence. No hidden-chain-of-
  thought, label-text feature, model-answer synthesis or public oracle projection
  is introduced.
- Policy, selection report, gap/source/verification identities, decisions and
  resource accounting are evaluator-private, including identities derived from
  private material. Public/buyer-safe methods withhold the whole record, without
  counts, identifiers, hashes, paths or diagnostic reasons.
- `model_dump` is **private serialization**, not a release/export API. A consumer
  must retain the private boundary and use projection methods for public output.

## Eligibility, selection and controls

Default candidates must pass the existing `admit_experience` verified-success
path. Selection references are **not** trainer bytes, do not bypass bundle-level
checks (including duplicate-task checks), and do not establish training usefulness.

Optional `max_hard_negatives > 0` permits a bounded number of freshly verified,
explicit task failures as `private_hard_negative` **analysis candidates only**.
They never become successful demonstrations or public training examples.
Unexpected admission/integrity errors reject the source; they are not recast as
negative examples. `training_qualified` remains false and usefulness UNKNOWN for
the entire report, including successes.

Filters have explicit, limited meanings:

1. Missing useful **bound candidate-gap evidence**: `no_useful_gap`.
2. Nonadmitted failures by default: `failed_not_training_candidate`.
3. Fewer than the declared minimum executable actions: `trivial_action_count`.
   This is a policy complexity threshold, not measured educational usefulness.
4. Exact behavioral-protocol duplicates: `duplicate_protocol`. The key includes
   full capability/fixture, actual actions, state transition and fresh verifier
   breakdown (including evidence coverage), but ignores artifact location, ZIP timestamps
   free-form conclusion prose, and submission padding ignored by the verifier. Exact repeated inputs still have separate slots.
   This is verifier-relevant behavioral equivalence for the pinned profile, not
   full claim/evidence-choice equivalence or an unimplemented near-duplicate model.
5. Stratum quota saturation: `stratum_quota_saturated`. Strata are full capability,
   fixture and role. **Quota saturation is not empirical mastery or a learning
   plateau.** There is no evidence here to measure those stronger notions.
6. Explicit total/hard-negative budget limits are separately counted.

`representative` chooses from least-represented strata, then lower native recorded
cost, then a stable SHA256 seed/protocol tie-break. This produces compact balanced
representatives of available declared strata, not statistical population
representativeness or capability coverage. The current native provider has one
task; constructed scheduler unit tests exercise multiple artificial strata without
claiming real-world multi-capability evidence.

`random_control` uses seeded SHA256 ordering over exactly the same freshly
validated, deduplicated eligible pool and applies the same budgets, hard-negative
limit and stratum caps. It is a **quota-constrained random control**, not unrestricted
sampling from rejected/held-out records. For matched comparisons retain the same
pool ID, gap-input digest, eligibility digest, policy settings other than mode/seed,
and budgets. Selection count does not prove equal training/compute cost: consumers
must measure those costs and the held-out intervention separately. No selection
result implies causal or held-out gain.

Candidate input order and gap-input order do not change results. Repeated aliases
retain multiplicity via deterministic digest/occurrence slots. Pool identity binds
the full multiset of supplied candidate content, not just accepted records. Policy
identity binds its complete configuration; gap input identity binds every supplied
receipt/source pair; report identity binds all decisions, counts and accounting.
Changing content, membership, seed, policy or material gap evidence changes the
corresponding identity. `validate_selection` independently recomputes a saved
report against the actual pool/evidence **and externally expected policy**; hashing
an altered serialized report does not establish freshness or trusted execution.

## Learning-efficiency lineage and accounting

Every input slot has one selected/rejected decision. Rejected and duplicate slots
remain countable; rejection reasons sum exactly to `rejected_count`, and selected
plus rejected equals the full pool size. Decisions retain source/experience/full
input/protocol/fixture/capability/verification/gap lineage, including selected roles.
Report fields are suitable inputs to a later LearningEfficiencyReport, not a claim
that such an experiment or report has been completed.

Resources preserve:

- raw candidate-slot, unique material-snapshot and unique validated-recording counts;
- source-validation and success-admission invocation counts;
- raw and distinct normalized gap-protocol counts, receipt-validation and
  family-derivation invocation counts;
- all selected/rejected entries;
- fresh recorded native-budget cost for the **entire** candidate pool, including
  valid rejected candidates (not just selected ones);
- gap-source, baseline, alternative and repeated execution native-budget costs;
- a union of known exact recordings to avoid double charging the same authenticated trajectory/companion recording
  used in both pools; cached reverification/annotation changes do not multiply execution cost. Distinct recorded executions count separately, even if their
  behavioral protocols are duplicates; repeated aliases of one recording do not.

An invalid/unexamined candidate makes full candidate-cost accounting `None`;
known validated cost is retained separately. Empty pools have a known native cost
of zero. Native budget units are not dollars, tokens, GPU-hours or wall time.
Generation compute, teacher tokens, human hours, selector compute and wall time
are explicitly **unknown/null**, never fabricated zeros. Deterministic operation
counts expose selector/evidence overhead but are not complete replay operation,
CPU or monetary measurements. `accounting_complete=False` prevents a reader from
mistaking these partial denominators for a measured equal-resource comparison.

## Verification and falsifiers

Run ordinary synthetic tests with:

```sh
python -m pytest tests/experience_selection
python -m ruff check src/investigation_world/experience_selection tests/experience_selection
python tools/quality_baseline.py check
```

The suite exercises actual retained public TRAIN executions plus explicit
constructed scheduler/policy tests. Negative checks include receipt/source/policy
and report tampering, stale/deleted artifacts, held-out/private preflight, fixed
panel exclusions, input multiplicity, protocol deduplication, quota/budget/trivial
reasons, zero unsupported gaps, random-control comparability, and admission-error
fallback rejection. Tests do not alter canonical verifier results or run models.

Independent review, full repository tests, installed-wheel tests and exact-head
CI/security are separate integration gates. This document authorizes none of
merge, release, deployment, paid/protected/model execution or qualification.
