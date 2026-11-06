# Veritas Environment Maturity Model

The maturity model is a versioned, fail-closed qualification state machine. It prevents
implementation success, scientific validity, frontier utility, training value, and commercial
release authority from being collapsed into one status.

## Canonical states

```text
DRAFT
  → EXECUTABLE
  → VERIFIER_VALIDATED
  → SCIENTIFICALLY_QUALIFIED
  → FRONTIER_QUALIFIED
  → TRAINING_VALIDATED
  → COMMERCIAL_RELEASE
```

An environment receives the highest state for which every transition gate from `DRAFT` through
that state has content-addressed `PASS` evidence. Missing evidence is `UNKNOWN`; `UNKNOWN` and
`FAIL` both stop promotion. Evidence for a later transition cannot compensate for a missing lower
transition.

The canonical v1 transition requirements are:

| Transition | Required evidence gates |
| --- | --- |
| `DRAFT → EXECUTABLE` | Valid environment contract, runtime smoke, deterministic reset |
| `EXECUTABLE → VERIFIER_VALIDATED` | Verifier qualification, falsifier fixtures, reward-hack resistance |
| `VERIFIER_VALIDATED → SCIENTIFICALLY_QUALIFIED` | Scientific qualification, leakage/contamination checks, reproducible qualification panel |
| `SCIENTIFICALLY_QUALIFIED → FRONTIER_QUALIFIED` | Non-saturation, capability separation, frontier failure diversity |
| `FRONTIER_QUALIFIED → TRAINING_VALIDATED` | Held-out improvement, multi-seed stability, reward-exploitation regression |
| `TRAINING_VALIDATED → COMMERCIAL_RELEASE` | Procurement package, security/privacy, release attestation, licensing/release authority |

These names define evidence classes, not an assertion that the corresponding qualification
subsystems are already complete. VQ-002, VQ-004, TRAIN-001, and PROC-001 must supply their own
domain-specific reports before those gates can pass.

## Identity and reproducibility

Every `MaturityRecord` includes:

- current and previous status;
- target status;
- qualification policy version, content-derived policy ID, and the exact policy snapshot;
- required evidence, all evaluated evidence, completed `PASS` evidence, failed gates, and unknown
  gates;
- content-bound environment and verifier identities;
- a deterministic qualification identity;
- a timestamped record identity and provenance;
- the preceding record identity when the record is a requalification.

Gate evidence is valid only when its environment digest, verifier digest, and qualification policy
version match the assessment. Qualification identity excludes observation timestamps and narrative
provenance, so replaying the same content-addressed evidence produces the same qualification
identity. Record identity includes evaluation time and lineage, preserving an append-only audit
history.

`MaturityHistory` validates contiguous record lineage while retaining older versions and statuses.
A requalification may promote, retain, or downgrade an environment; it never overwrites the prior
record.

## Python surface

```python
from investigation_world.qualification import (
    EnvironmentIdentity,
    EnvironmentMaturity,
    VerifierIdentity,
    assess_environment_maturity,
)

record = assess_environment_maturity(
    environment_identity=environment_identity,
    verifier_identity=verifier_identity,
    evidence=gate_evidence,
    provenance={"runner": "qualification-service", "run_id": "..."},
    target_status=EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
)
```

Callers must persist the complete record, not only its `status` field. A status without the bound
policy, identities, gate classifications, and provenance is not a Veritas maturity claim.
