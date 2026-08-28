# Adapter Conformance Certificates

`ConformanceCertificate` turns the existing fail-closed `AdapterConformanceReport` into a
content-addressed, buyer-safe portability artifact.

The certificate does not weaken the underlying report. It adds exact source/adapter/runtime identity
and explicit parity requirements so a target cannot receive a lossless certificate merely because a
subset of fields happened to compare successfully.

## Required identities

Each certificate binds:

- portable **public** contract schema version, public contract ID, and public-content SHA-256;
- adapter name, version, and implementation/content SHA-256;
- target runtime name, version, and installed/package/image content SHA-256;
- canonical conformance test-vector hash;
- exact `AdapterConformanceReport` content identity.

The evaluator-private full portable contract ID is intentionally not part of the buyer-safe source
reference. This preserves the existing rule against exposing a digest that commits to private,
low-entropy evaluator semantics.

## Lossless policy

A certificate is `PASS` only when all of the following hold:

- `semantic_losses` is empty;
- `unsupported_fields` is empty;
- state parity is explicitly proven;
- reward parity is explicitly proven;
- termination parity is explicitly proven;
- evidence parity is explicitly proven.

Any semantic loss or negative parity assertion is `FAIL`. Missing parity evidence or a declared
unsupported surface is `UNKNOWN`. `UNKNOWN` must not be advertised as lossless portability.

Generated target-native metadata may be declared without failing the certificate as long as it does
not alter required Veritas semantics.

## Shared evidence

`conformance_evidence_record()` wraps a certificate in the shared evidence contract with exact
portable-contract, adapter, and runtime subjects plus hashed report/certificate artifacts. The
certificate can therefore be consumed by VQ-003 scorecards and Qualified Environment Packages
without defining a second procurement-specific conformance envelope.

## Relationship to current conformance

The existing cross-runtime harness remains the semantic authority. It compares observations, state
digests, evidence, action parameters/outcomes, termination/truncation, budgets, invariants, target
assertions, process/evidence requirements, reward weights, verifier components, and aggregate reward.

PORT-002 only productizes that already-implemented evidence. It does not repair adapters, suppress
semantic losses, or infer PASS from unavailable traces.
