# Shared Evidence Contract

The shared evidence contract is the common evidence envelope for Veritas qualification, task QA,
conformance, trajectory/reverification, diagnostics, training-value evidence, procurement, and future
Qualified Environment Packages.

It does **not** replace the domain report that produced the evidence. A verifier report, conformance
report, trajectory, expert-QA report, or training result remains the authoritative domain artifact.
`EvidenceRecord` gives those artifacts one content-bound, privacy-aware way to be referenced and
composed by higher-level systems.

## Design goals

- one evidence identity model instead of subsystem-specific evidence envelopes;
- exact subject, producer, policy, and artifact binding;
- fail-closed `PASS` / `FAIL` / `UNKNOWN` classification;
- `OBSERVED` for evidence that has not yet been classified under a policy;
- deterministic content identities independent of collection ordering;
- append-only observation history without changing the underlying semantic evidence identity;
- explicit `public`, `operator_private`, and `sealed` visibility;
- no raw evaluator truth or filesystem/service locator in the shared envelope;
- composition through content-addressed evidence dependencies;
- compatibility with the existing environment maturity state machine.

## Identity model

An `EvidenceRecord` carries two identities:

- `evidence_id` / `evidence_content_sha256` bind semantic evidence: type, outcome, visibility, claim,
  subjects, exact producer, optional policy, artifact digests, and evidence dependencies;
- `record_id` additionally binds observation time and provenance.

Repeating the same exact evidence under the same producer and policy therefore retains the same
`evidence_id` while producing a distinct auditable `record_id` when observation metadata changes.

Subjects are content-bound references such as environment, verifier, task, trajectory, adapter,
policy, or package identities. Artifacts are opaque IDs plus SHA-256 digests and optional media type.
The shared record intentionally does not carry a path, URL, private row, expected label, hidden oracle
payload, decryption material, or secret.

## Outcome semantics

`EvidenceOutcome` has four states:

- `OBSERVED`: the artifact exists but has not been classified under a decision policy;
- `PASS`: the evidence satisfies the stated policy/claim;
- `FAIL`: the evidence contradicts or fails the stated policy/claim;
- `UNKNOWN`: the policy cannot resolve the claim from available evidence.

An `OBSERVED` record cannot be used directly as maturity-gate evidence. It must first be classified
by the owning subsystem under an explicit policy. This preserves the repository rule that missing or
uninterpreted evidence never implies PASS.

## Privacy

`serialize_public_evidence()` emits only records explicitly marked `public`. Operator-private and
sealed envelopes, including their IDs and claims, are omitted rather than redacted field-by-field.
The producing subsystem remains responsible for ensuring that a record marked public contains only
buyer-safe subjects, claims, provenance, and artifact references.

## Maturity compatibility

`investigation_world.evidence.maturity.maturity_gate_evidence_from_record()` projects classified
shared evidence into the existing VQ-001 `MaturityGateEvidence` envelope. The adapter requires exactly
one content-bound environment subject and verifier subject and rejects policy-version mismatch.

Maturity is therefore a **view over evidence**, not a second evidence authority.

## Intended consumers

New work should prefer the shared envelope when emitting evidence intended to cross subsystem
boundaries. In particular:

- VQ-006 / VQ-005 expert and task QA;
- VQ-003 environment quality scorecards;
- PORT-002 conformance certificates;
- TRACE-003 reverification summaries;
- VQ-004 frontier qualification inputs;
- TRAIN-001 training-value qualification;
- PROC-001 / PROC-002 Qualified Environment Package evidence and attestations.

Existing mature domain report models do not need an immediate rewrite. They can be wrapped by shared
records at their composition boundary, allowing migration without weakening or duplicating their
current semantics.
