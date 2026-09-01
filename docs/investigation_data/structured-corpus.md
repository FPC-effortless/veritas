# Canonical structured investigation corpus

The structured-corpus compiler converts already acquired CSV, JSON, JSONL, or XLSX investigation data into separate public and verifier projections without creating a second source-policy authority.

## Authority boundary

`investigation_world.investigation_data.SourceCatalog` remains authoritative for source identity, acquisition policy, redistribution policy, AI-use policy, redaction requirements, truth semantics, and declared artifacts.

A `StructuredSourceProfile` must bind to an existing canonical `source_id` and `source_artifact_id`. Compilation fails closed when either identity is absent from the catalog, acquisition, redistribution, or AI use is blocked, metadata-only policy is incompatible with the declared artifact, a canonical `expected_sha256` does not match the exact local bytes, or required rights/redaction review evidence cannot be validated.

When a source policy requires review, `rights_review_id` is only a reference. It must resolve to exactly one separately supplied `StructuredRightsReviewEvidence` record. That record must bind the same source and artifact IDs, the complete set of applicable review scopes, a SHA-256 digest of the current canonical rights/redaction policy, and a SHA-256 digest of the selected canonical artifact definition. Wrong-source, wrong-artifact, stale/wrong-policy, incomplete-scope, duplicate/missing, and unsolicited review references fail closed. The exact validated review record is retained in the compiled corpus and public manifest so the authorization remains auditable after materialization. Supplying a review reference does not itself create review authority.

`REVIEW_REQUIRED` redistribution therefore needs validated review evidence. `ATTRIBUTION_REQUIRED` must have the canonical attribution flag and is retained in the public manifest with the license expression and terms URL.

The compiler does not download data, does not issue rights approvals, and does not reinterpret source rights. Acquisition continues through the canonical investigation-data acquisition layer. Review-evidence authenticity and issuance remain an external operator/repository authority boundary; this compiler validates the supplied record against the selected canonical source/artifact/policy before using it.

## Canonical artifact identity

If the selected canonical `AcquisitionArtifact` declares `expected_sha256`, the compiler hashes `input_path` before parsing and requires an exact digest match. Modified or substituted local bytes therefore cannot be materialized while claiming the canonical artifact identity. When no expected digest is declared, the exact observed local SHA-256 is still retained as provenance but is not treated as a canonical byte-identity proof.

## Fail-closed field classification

Every top-level source field must have exactly one declared exposure:

- `PUBLIC` — eligible for the agent-facing evidence record;
- `VERIFIER` — emitted only to the evaluator projection;
- `IGNORE` — deliberately discarded from both projections.

Unexpected source columns are errors. Non-ignored target names must be unique, so two source fields cannot silently overwrite one projected field.

Structural title/location/date fields must be public. Source-case identity fields may be public or ignored but cannot be verifier-only, preventing buyer-visible case identity from depending on hidden labels.

## Stable case identity

The opaque case ID is derived from the canonical source ID plus the source's stable case-identity fields. It does not use row position or verifier values. Reordering a source snapshot or changing an evaluator-only label therefore does not change the public case identity.

The original source-case identity and row number remain evaluator-side. Public records expose only the opaque case ID.

## Provenance

Each compiled corpus records:

- canonical source ID;
- canonical source artifact ID;
- SHA-256 of the exact local source artifact;
- digest of the canonical source catalog;
- canonical redistribution policy, attribution obligation, license expression, and terms URL;
- the complete validated rights-review evidence record when review is required;
- deterministic public corpus hash.

The public manifest never contains the verifier hash. A verifier projection is optional and must be requested explicitly by the operator.

## Qualification boundary

Successful compilation proves only deterministic projection and the declared policy/schema/provenance boundary. It is not verifier qualification, scientific qualification, Frontier qualification, training-value evidence, rights-review issuance, or commercial release authorization.

Before a compiled corpus becomes a Veritas environment, downstream construction still needs temporal information cuts, evidence provenance, public/private leakage tests, verifier falsifiers, contamination/duplicate analysis, executable semantics, quality scoring, and the applicable maturity/qualification gates.
