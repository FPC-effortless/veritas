# Qualified Environment Package

`QualifiedEnvironmentPackage` is Veritas's generic procurement package object. It composes existing environment, verifier, maturity, quality-scorecard, portability, conformance, attestation, provenance, licensing, and optional diagnostic/reverification identities without becoming a second authority for any of them.

## Core rule

Packaging is descriptive, content-bound composition. It does **not** upgrade an environment's maturity. A package may truthfully contain `FAIL` or `UNKNOWN` qualification facets and remain a valid package object.

The operator package retains canonical source records as well as their concise bindings. Validation revalidates those records and rejects any copied claim that differs from its canonical source, even if the outer package ID is cleared and recomputed. Opaque source IDs alone are not accepted as proof of a copied claim.

The package binds:

- exact environment and verifier identities;
- a buyer-safe or public `PortableEnvironmentManifest` projection;
- the canonical `MaturityRecord` identity and its failed/unknown gates;
- every canonical quality-scorecard dimension and outcome;
- runtime conformance certificates when available;
- qualified environment attestations;
- optional reference, reverification, diagnostic, installation, and reproduction evidence references;
- source, licensing, image, dependency, and SBOM content references where available;
- a separate operator-only private evaluator reference;
- buyer-safe known limitations.

## Public/private boundary

The full `QualifiedEnvironmentPackage` is an operator object and can bind private or sealed identities. `buyer_safe_manifest()` creates a separate, independently content-addressed projection that:

- retains only `PUBLIC` attestations, evidence references, and supply-chain references;
- discloses maturity status, policy, failed/unknown gates, and scorecard dimension outcomes as summaries, without private-backed maturity/scorecard identities or hashes;
- omits canonical source snapshots entirely; they remain operator-only;
- exposes only whether a private evaluator is present, absent, or unknown;
- never exports the private evaluator reference, version, or digest;
- does not include the operator package ID or digest, so a private-only package mutation cannot create a buyer-visible fingerprint;
- revalidates the complete package before projection so stale `model_copy(update=...)` mutations fail closed.

Known limitations are treated as buyer-safe disclosure text by construction; callers must not put evaluator-private case details or answer-bearing material into them.

## Content identities

The operator package ID is derived from the complete package semantics. Material changes to the environment, verifier, portability binding, maturity record, scorecard, conformance certificate set, attestations, evidence, supply-chain references, private evaluator reference, or limitations therefore re-key the operator package.

The buyer-safe manifest has its own content-derived identity over only the information authorized for that projection. Changes confined to undisclosed source evidence or provenance do not change that identity. Changes to disclosed outcomes, private-evaluator status, or explicitly `PUBLIC` references do change it. Public attestations keep their already-public canonical identities; callers must authorize their disclosure rather than labeling a private attestation public.

## Qualification boundary

This namespace consumes validated outputs from canonical authorities. Source validation establishes consistency with canonical content identities, not issuer authentication, signature verification, or independent experimental confirmation. The buyer summary is a disclosure view, not a standalone replacement for the operator-held qualification evidence. It does not:

- recompute maturity gates;
- turn scorecard `UNKNOWN` into `PASS`;
- promote scientific evidence to Frontier or training evidence;
- infer commercial release from package existence;
- alter verifier scoring;
- rewrite portability/exporter semantics;
- publish or release packages.

Commercial-release qualification remains a separate downstream gate. Shared/root exports, CLI integration, release documentation, and release workflows are intentionally left to the serialized convergence lane.
