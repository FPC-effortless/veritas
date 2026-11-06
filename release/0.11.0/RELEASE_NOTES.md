# Veritas 0.11.0

Veritas 0.11.0 is the commercial-portability release.

It makes qualified Veritas environments distributable without requiring a buyer to adopt the full development repository or a Veritas-hosted SaaS backend. The first exact proof SKU is the qualified, frozen SRE v4 evaluation pack.

## Release scope

- carries forward the 0.9 native-artifact runtime and 0.9.1 experimental-integrity hardening;
- carries forward the 0.10 benchmark-qualification system and qualified SRE v4 release;
- adds vendor-neutral portable environment, taskset, release, capability, reset, verifier, artifact and metering contracts;
- adds deterministic content-derived task, run, package, qualification-evidence and metering identities;
- adds collision-safe opaque task identity for sealed cases that share public digests;
- adds buyer-safe qualification evidence with no private scenario rows or hidden labels;
- adds standalone HUD v6 packaging with live task start/grade execution;
- adds Prime Verifiers v1 packaging plus a compatibility-only legacy bridge;
- proves deterministic reset and exact canonical reward parity on the sealed SRE v4 release;
- adds explicit Apache-2.0 public licensing and a documented commercial boundary for private benchmarks, customer evaluation outputs and generated training data;
- adds release-identity consistency gates and procurement-grade GitHub release packaging.

## Pinned SRE portability identities

The release attaches `PORTABILITY_IDENTITIES.json`, which pins the exact SRE v4 candidate, evidence manifest, qualification report, private panel/release identity, source bundle hash, portable manifest, portable qualification evidence, HUD package and Prime package IDs validated by PR #64.

## Procurement artifacts

The GitHub release contains:

- Python wheel and source distribution;
- SHA-256 checksums for release files;
- GHCR image identity and immutable image digest;
- CycloneDX SBOM;
- machine-readable release provenance including source commit and portability identities;
- licensing policy;
- release notes.

## Scope boundary

0.11.0 does not claim universal industrial simulation. Live cloud/Kubernetes control planes, broader Excel semantics, deeper enterprise replicas, browser/OCR investigation surfaces, raster/PostGIS GIS execution, third-party security certification and other higher-cost fidelity/procurement work remain later milestones.
