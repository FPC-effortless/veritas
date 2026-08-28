# Batch and version-aware offline reverification

TRACE-003 extends the existing evidence-bound reverification engine from one trajectory to a
deterministic batch. It still performs no model, provider, harness, network, or dynamic-entrypoint
calls. Every requested verifier must resolve through `AuthorizedVerifierRegistry` to an exact local
binding before a score can be produced.

## Batch contract

`batch_reverify_trajectories(...)` accepts canonical `TrajectoryV2` values, one exact requested
`VerifierIdentity`, and the authorized registry. It returns:

- a content-addressed `BatchReverificationReport` sorted by `trajectory_id`;
- one content-addressed entry per input trajectory;
- new trajectory values containing any appended `ReverificationRecord` values.

The source trajectories and their `original_evaluation` fields are never rewritten. A repeated
record is returned as `ALREADY_RECORDED` rather than appended again. Duplicate trajectory identities
in one batch are rejected because they would make per-input accounting ambiguous.

Input order is not semantic. Reordering the same trajectory/verifier inputs produces the same batch
identity, entry identities, and output order. Timestamps are not added to semantic identities.

## Missing and failed evidence

Batch execution preserves the single-trajectory fail-closed statuses:

- `NOT_REVERIFIABLE` means required replay evidence is absent or insufficient;
- `UNKNOWN` means available material conflicts, is ambiguous, or the authorized verifier failed;
- `UNAUTHORIZED` means the exact verifier identity is not registered.

These entries contain no `record_id` and no candidate score. They are not converted to zero reward or
failure scores.

## Exact version comparison

`compare_reverification_versions(...)` compares exact baseline and candidate verifier identities.
Optional record IDs disambiguate multiple append-only records for one verifier version. A comparison
binds both snapshots to the same immutable `trajectory_id` and reports:

- reward delta;
- component deltas only where both snapshots contain that component;
- `unknown_components` where either side lacks a component;
- evaluator-private reason and replay-evidence provenance when the candidate verifier exposes a
  structured `verification_breakdown`.

An absent score returns `NOT_AVAILABLE`; multiple matching records return `UNKNOWN`. Neither case
contains fabricated deltas.

## Privacy projection

`BatchReverificationReport.buyer_safe_summary()` creates a separate content-addressed summary. It:

- includes individual status entries only for public or buyer-safe trajectories;
- aggregates internal, evaluator-private, and sealed trajectories without their trajectory, record,
  verifier, evidence, report, or batch identities;
- never includes verifier reason attribution or private replay payloads.

The buyer-safe summary has its own identity derived only from its sanitized contents, so a private
batch identity cannot become a digest side channel.

## Evidence boundary

This implementation establishes deterministic offline measurement behavior. It does not establish
verifier qualification, scientific qualification, Frontier usefulness, training value, or release
readiness. Those states require their own evidence and authority.
