# Capability science evidence contracts (CAP-001 / #157)

This package structures **evidence about capability development**, not a trainer,
recorder, runtime, curriculum generator or scientific qualification engine. It
implements the original #157 contract in its three owned subtrees. Neither a
record's existence nor a passing synthetic test establishes measured capability,
prerequisite causality, training usefulness, Frontier usefulness or release readiness.

## Outcome and falsifiers

The observable outcome is a reproducible, content-bound record of declared
capabilities, evidence-bearing prerequisite relations, diagnostic candidates,
composition tests, ordered acquisition and retention measurements, hypothesis
history and explicitly scoped transfer. The tests fail if a cycle is accepted,
a stale identity survives, a supplied diagnostic candidate is trusted instead of
recomputed, a partial panel is silently selected, a negative result disappears,
or private evidence becomes public through a wrapper.

Reuse takes priority: `CapabilityContract`, `ExperienceReference`, existing
`FailureFamily` / `CapabilityGap` models, the merged diagnostic producers, their
counterfactual validation provider and Observatory `CapabilityGraph` remain the
canonical providers. No shared/root exports, Observatory internals, trajectory
recorder, verifier, trainer, Foundry executor or qualification policy is changed.

## Capability identity and prerequisite evidence

```python
from investigation_world.capability_science.core import CapabilitySpec
from investigation_world.foundry.models import CapabilityContract

spec = CapabilitySpec(contract=CapabilityContract(
    capability_id="evidence-acquisition",
    version="1",
    objective="Acquire the evidence required by the declared task",
    success_conditions=["required evidence is present"],
))
```

`CapabilitySpec` reparses the entire canonical contract. Its record ID binds all
material fields, schema and visibility; `contract_digest` is the full SHA256 of
the canonical contract payload, alongside the provider's existing truncated
`content_digest`. Equal names do not imply equal capability contracts. Contract
labels are declarations, not measured model competence or benchmark coverage.

`PrerequisiteGraph` wraps the existing Observatory DAG and uses its duplicate
node, unknown-node, self-edge and cycle checks. Every edge is an evidence-bearing
`PrerequisiteClaim`; duplicate edges fail closed. The structural
`observatory_graph()` view is **evaluator-side** and deliberately carries no
scientific status. Do not use that lossy view as a public or qualified graph.

Edge statuses distinguish `HYPOTHESIZED`, `OBSERVED_ASSOCIATION`,
`INTERVENTION_SUPPORT_REPORTED`, `REFUTED` and `INCONCLUSIVE`. Association cannot
be upgraded by renaming a status: reported intervention support requires a
matching `PrerequisiteIntervention` with distinct content-bound protocol,
with-prerequisite and without-prerequisite references, a fixed context commitment,
multiple reported replicates and a positive reported score difference. Zero and
negative contrasts can be retained as inconclusive/refuted evidence.

These are **externally reported study records**, not attestations that an
intervention happened or all confounders were controlled. The fixed context
commitment must cover model, environment, verifier, population and metric.
Reference bytes, intervention design, independence, uncertainty and replication
must be checked by the separate empirical qualification program. In particular,
`causal_qualification` remains `UNKNOWN`, even for reported intervention support.

## Diagnostic ingestion is source validation, not a name lookup

```python
from investigation_world.capability_science.diagnostics import (
    ingest_failure_family, ingest_capability_failure,
)

# Observed Gold-10/coarse-source symptoms:
# family = ingest_failure_family(provider_candidate, sources=experiences)

# Validated public TRAIN-derived controlled contrasts:
# gap = ingest_capability_failure(provider_candidate, sources=((receipt, source), ...))
```

Both functions recompute the merged producer and require exact equality with the
supplied candidate, including statistics and evidence references. Ordinary
`failure_family_candidates` retains unknown affected capability: the consumer
does not invent a binding from symptoms, prose, task names or a user label.
Gold-10 public fixtures demonstrate observed evidence/hypothesis/temporal score
symptoms, not a longitudinal acquisition curve or causal capability deficit.

`intervention_failure_families` freshly validates every source, retained artifact
and counterfactual receipt via the canonical provider. The consumer binds the
**full** contract from the selected underlying sources, not just the candidate's
capability name or the canonical short digest. The envelope retains source and
receipt digests and hashes the full family/gap payload because legacy family/gap
IDs intentionally omit some statistics.

The following provider meanings are retained without promotion:

- `DECLARED_TASK_ASSOCIATION`: task-level contract association, not measured skill;
- `OBSERVED_BOUND_TASK_FAILURES`, with the original `HYPOTHESIZED` candidate status;
- frequency: distinct recorded protocols, **not independent agents, repeated
  independent trials or a population failure rate**;
- severity: normalized unmet-target fraction, **not general harm**;
- criterion scope: verifier target set, not exact failed contract conditions;
- causality, prerequisites, missing procedures and abstraction deficits: not inferred.

Missing artifacts, forged source or receipt bindings, changed contract material,
modified severity/frequency and unsupported candidates fail ingestion. Parsing a
saved envelope verifies content consistency only: it does not re-execute the
provider or attest current source validity. Use the ingestion functions again
when fresh source validation is required. Canonical experiences are never mutated.

## Acquisition, composition, retention and transfer

See [measurement records](measurements.md) for the fixed-population evaluation,
ordered intervention, retention/regression, composed-result and explicit
source/target transfer contracts. Complete case membership is checked, including
failed and unknown outcomes; raw task totals are not capability coverage. Model,
checkpoint, environment, verifier, metric, population and training identities are
bound. Declared chronology/provenance is not silently upgraded to an attestation.

In particular, the merged #449 paired-outcome provider reports unknown model
execution and panel chronology attestations and `capability_gain=None`. A wrapper
cannot turn those checked outcome pairs into demonstrated model acquisition.
Recorded score differences and genuine capability qualification remain separate.

## Falsifiable hypothesis history

`HypothesisRevision` records capability-spec identities, statement, falsifier,
optional intervention identity, evidence and status. `HypothesisHistory.append()`
returns a new history resolving capability IDs against its exact `specs`, preserving every earlier
revision and binding each next
revision to the previous record ID. Multiple hypothesis keys can coexist.
`FAILED`, `REFUTED` and `INCONCLUSIVE` revisions remain inspectable; reported support
is not scientific qualification. Broken, skipped or substituted revision chains
are rejected. This is an immutable history contract, not a persistent database:
external storage must retain the previous history commitment to detect wholesale
replacement or deletion of a complete hypothesis by a caller.

## Privacy and integrity

Records default to internal; diagnostic envelopes are unconditionally
evaluator-private. Raw `model_dump()` output is evaluator material, not an export.
`public_payload()` and `buyer_safe_payload()` revalidate the complete record, then
withhold **all** content if any nested record/reference is too private or contains
private metadata/payload. The withheld response is only
`{"status": "UNKNOWN", "reason": "evidence_not_visible"}`: no private label, source
ID, receipt ID, private-derived hash, local path, population member or reason text
is emitted. Public allows PUBLIC only; buyer-safe additionally allows BUYER_SAFE.
There is no implicit field-level declassification.

Full SHA256 identity detects content drift; it does not authenticate an author,
verify external reference bytes or prove execution/chronology. The constructor
and `checked()` boundary reparse nested canonical models, including mutable
containers inside frozen models. An intentionally rebuilt record has a new
identity and still needs its applicable external evidence checks.

## Verification boundary

Tests use explicitly constructed contracts, panels and study records, public
Gold-10 symptom fixtures, and cheap actually executed public synthetic TRAIN
native contrasts. They are implementation tests, not model training, protected
split evaluation, paid inference or empirical qualification. Run targeted tests:

```sh
python -m pytest tests/capability_science/
```

The PR records the exact-head targeted, provider-regression, full-suite, package,
installed-wheel, quality and independent-review results. Missing empirical
evidence stays missing; no test or document grants formal review, merge or release
authority.
