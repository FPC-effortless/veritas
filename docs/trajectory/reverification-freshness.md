# Fresh evidence for idempotent reverification

`reverify_trajectory` always validates the canonical input, exact authorized verifier
binding and replay evidence before computing a result. An existing record ID does
not bypass those checks or scoring.

Private metadata is intentionally excluded from record identity. Therefore an
existing same-ID record can contain absent or stale caller-retained annotations.
When fresh verification produces an existing ID, the engine returns the **freshly
computed verification private metadata** on the existing record, and replaces
the matching record in a validated returned
trajectory copy. `ALREADY_RECORDED` and `REVERIFICATION_RECORD_ALREADY_PRESENT`
mean no new record identity was appended, not that retained private evidence was
trusted.

The trajectory ID, record ID, record order/count, original evaluation and input
object remain unchanged. Non-private fields (including stricter visibility) and nested provenance
annotations on the matching record are preserved as archival context, not newly
authenticated evidence. Other records are preserved. Batch output propagates the
refreshed copy; callers constructing a `MachineExperience` from that copy retain
its experience identity and receive the same fresh evidence.

## Compatibility boundary

The matching record's top-level retained private annotations are replaced, not merged into
newly computed verifier evidence. Consumers needing archival annotations should
retain their original input separately. This deliberately changes returned
private metadata when it differs from fresh computation; it does not change
identity hashing, public serialization, scores, authorization or source gates.
Other historical records are not retroactively authenticated by this operation.

## Regression evidence

`tests/trajectory/reverify/test_reverification_freshness.py` uses only existing
public synthetic runtime fixtures. Missing/stale retained breakdown cases fail
on the pre-fix implementation and exercise record/trajectory consistency,
immutability, idempotence, ordering, unrelated record preservation, batch and
experience propagation, and rejected authorization/missing evidence. This is
implementation verification, not scientific qualification or a general security
certification.
