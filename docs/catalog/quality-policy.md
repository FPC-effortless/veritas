# Catalog quality and maturity presentation policy

The Veritas catalog is a **view over canonical evidence**, not a qualification authority. A catalog
entry may present maturity, quality, optional fidelity/experience classifications, limitations, and
buyer-safe references, but it cannot create or upgrade any of those states.

## Canonical inputs

`CatalogEntry` consumes two existing authorities directly:

- a validated `MaturityRecord`, which binds the exact environment and verifier revisions, policy,
  gate outcomes, achieved maturity, and qualification identity; and
- a validated `EnvironmentQualityScorecard`, which preserves all canonical quality dimensions and
  their `PASS` / `FAIL` / `UNKNOWN` outcomes without averaging them into a scalar.

The catalog requires the scorecard's environment and verifier subjects to match the exact identities
in the maturity record. A scorecard from another environment or verifier revision is rejected rather
than presented as current.

At catalog boundaries the supplied Pydantic objects are reconstructed from their dumped
representations and revalidated. This is deliberate: `model_copy(update=...)` is not trusted as a
validation boundary. Stale copied maturity, scorecard, presentation, or identity state therefore
fails closed before filtering or buyer-safe serialization.

## Presentation classes

Presentation is derived only from canonical `EnvironmentMaturity`:

| Canonical maturity | Catalog presentation |
| --- | --- |
| `DRAFT` | `EXPERIMENTAL` |
| `EXECUTABLE`, `VERIFIER_VALIDATED` | `EXECUTABLE` |
| `SCIENTIFICALLY_QUALIFIED`, `FRONTIER_QUALIFIED` | `QUALIFIED` |
| `TRAINING_VALIDATED` | `TRAINING_VALIDATED` |
| `COMMERCIAL_RELEASE` | `COMMERCIAL` |

A caller cannot attach a stronger marketing class. If a supplied class disagrees with the canonical
maturity record, entry validation fails.

## Qualification facets

Scientific, Frontier, training, and commercial facets are machine-readable and derived from the
same maturity evidence. A facet is `PASS` only when the canonical achieved maturity has reached that
transition. If the canonical record assessed the facet and an applicable required gate failed, the
facet is `FAIL`. Missing, unmeasured, or otherwise insufficient evidence remains `UNKNOWN`.

This preserves an important distinction: a scientifically qualified environment can still have
`UNKNOWN` Frontier, training, and commercial facets. Catalog presentation never treats absence of
evidence as success.

## Quality is multidimensional

The buyer-safe view presents every canonical quality dimension separately, including failed and
unknown dimensions. There is intentionally no catalog `quality_score`, task count, environment
count, or other scalar proxy that can hide a severe failure or missing measurement.

Task volume can be useful operational metadata elsewhere, but it is not evidence of environment
quality and is not part of this catalog policy.

## Optional experience and fidelity classifications

Experience maturity and fidelity are optional because their provider contracts may be unavailable
for a particular environment or repository revision. The catalog does not define those semantics.
When supplied, each classification must be bound to a public, content-addressed opaque reference of
the matching `experience` or `fidelity` kind.

This provides a future integration hook without making the catalog a second Experience or Fidelity
authority.

## Buyer-safe references and serialization

Buyer-safe references are limited to public content identities for package, conformance, experience,
or fidelity records. They carry no URI, filesystem path, raw payload, or evaluator material.
Non-public references are rejected.

`serialize_buyer_safe_catalog(...)` exposes:

- catalog and environment content identities;
- domain and canonical maturity;
- derived presentation and qualification facets;
- scorecard identity/policy plus every dimension outcome;
- optional public experience/fidelity classifications;
- explicit limitations; and
- explicitly public opaque references.

It does **not** emit the maturity record's verifier identity, scorecard verifier subject, gate
provenance, raw evidence dependencies, or evaluator-private payloads. Catalog output therefore does
not widen the visibility of evidence merely because qualification exists internally.

## Filtering and sorting

`CatalogQuery` supports deterministic filtering by domain, minimum canonical maturity, and optional
fidelity value, plus sorting by maturity, domain, or environment identity. Filters operate only after
full entry revalidation; stale copied data cannot be used to enter a stronger catalog tier.

## Evidence boundary

Catalog correctness establishes truthful **presentation of existing evidence**. It does not establish
scientific qualification, Frontier usefulness, training value, commercial release authority,
package validity, or fidelity by itself. Those states remain owned by their canonical subsystems.
