# Environment Quality Scorecard

The Environment Quality Scorecard is a multidimensional evidence view over one exact environment,
verifier, and optional portable public contract. It does not replace environment maturity,
scientific qualification, Frontier Qualification, or Training-Value Qualification.

The scorecard deliberately has **no default scalar quality score**. A strong result in one dimension
must not average away a verifier exploit, privacy failure, missing frontier evidence, or unknown
training value.

## Canonical dimensions

The v1 policy tracks independently:

- semantic completeness;
- verifier precision;
- verifier recall;
- reward-hack resistance;
- reset determinism;
- private-data isolation;
- task ambiguity;
- artifact fidelity;
- state fidelity;
- expert task QA;
- structural diversity;
- frontier headroom;
- failure diversity;
- generalization;
- training-signal density;
- runtime conformance;
- reproducibility;
- provenance completeness.

Every dimension is `PASS`, `FAIL`, or `UNKNOWN`. Missing evidence, unclassified `OBSERVED` evidence,
or explicit `UNKNOWN` evidence remains `UNKNOWN`.

## Evidence composition

The scorecard consumes only shared content-addressed `EvidenceRecord` objects. Each dimension policy
declares:

- the content-bound subject kind it must match (`environment`, `verifier`, or `portable_contract`);
- accepted shared evidence types;
- the minimum number of records required.

Evidence for another environment/verifier/portable-contract content digest is ignored rather than
reused. A failing matching record fails that dimension. If matching records are missing or unresolved,
the dimension stays `UNKNOWN`.

This keeps the scorecard downstream of evidence-producing systems:

```text
VQ-002 verifier qualification
VQ-005 task QA
PORT-002 conformance certificates
future Frontier/training/fidelity evidence
                 │
                 ▼
         Shared EvidenceRecord
                 │
                 ▼
     Environment Quality Scorecard
```

The scorecard does not reinterpret verifier reports, conformance reports, expert findings, or training
statistics. Those owning subsystems remain authoritative for their measurements and policies.

## Public projection

`build_environment_quality_scorecard(..., public_only=True)` considers only evidence explicitly marked
`public`. Private or sealed evidence is treated as unavailable: the dimension becomes `UNKNOWN` and no
private evidence ID is included.

This is intentionally different from copying a private result and redacting its payload. The public
projection does not reveal that a particular private evidence artifact exists.

## Completeness

`scorecard.complete` means no dimension is `UNKNOWN`; it does **not** mean the environment is qualified.
`failed_dimensions` and `unknown_dimensions` remain explicit. Environment maturity remains governed
by the separate VQ-001 maturity policy and its own evidence gates.

## Migration

Existing subsystem reports do not need to be redesigned. They should emit or wrap their buyer-safe or
operator-private result in the shared evidence contract at composition boundaries. This allows the
scorecard, future Qualified Environment Package, and procurement views to reuse the same evidence
identity without introducing another evidence model.
