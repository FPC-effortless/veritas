# Authenticated review of exact claim assurance

`trainlab.assurance_review.verify_assurance_review` adds a narrow semantic check to
the existing [signed diagnostic-bundle review](signed-bundle-reviews.md). It does
not turn a valid signature into scientific admission.

The consumer first independently recomputes its run, capture, execution, replay and
claim prerequisites, serializes the exact assurance document, and supplies that
SHA256 as `expected_evidence_sha256`. It also supplies the expected author, reviewer
signer, and a separately pinned recipient-controlled OpenSSH allowed-signers file.
The reviewed bundle cannot choose those expectations or its own trust root.

```python
result = verify_assurance_review(
    bundle_root, manifest_sha256, signed_envelope,
    expected_evidence_sha256=expected_assurance_sha256,
    author=expected_author,
    signer=expected_reviewer,
    trusted_signers=recipient_allowed_signers,
    trusted_signers_sha256=recipient_trust_sha256,
)
```

The default pack and finding IDs are both `research-assurance`. The pack version
must be `1`, the finding kind `conclusion`, and its status `TESTED`. The finding
must point to the **entire** exact assurance source (`pointer: []`), not a favorable
subnode. The API accepts explicit alternative expected pack/finding IDs; these
must come from the consumer, not be discovered as a convenient passing finding.

## Evidence document

The bounded (at most 16 MiB) document has schema `research_lab.claim-assurance.v1`:

- `status: TESTED`, `author`, and `scientific_qualification: NOT_QUALIFIED`.
- `claim`: exact `protocol_id`, `protocol_sha256`, `scope`, `metric`, `direction`
  (`min`/`max`), nonnegative `minimum_effect`, distinct integer `seeds`, and
  `conclusion`, and `evaluation_scope: TRAIN_ONLY_OBSERVED_CLASSIFICATION`.
- `evidence_pin` and a nonempty `synthesis` object, freshly recomputed by the consumer.
- `runs`: unique task/run entries, each with `task_id`, `run_id`, `record_sha256`,
  `contract_sha256`, `capture_sha256`, and `execution_sha256`.
- `replay_scope: CLEAN_DIRECTORY_SAME_HOST_AND_RUNTIME`.
- `review_materials`: safe relative path → `{sha256, base64}` exact raw bytes,
  canonical strict base64, at most **8 MiB decoded in aggregate**. Oversize material
  is rejected, never omitted or replaced with an unsupported completeness claim.

Every run requires `run_id/run.json`, `contract.json`, `capture.json`,
`execution_adequacy.json`, `experiment.json`, and `plan.json`. The four assurance
row hashes must match their corresponding material bytes. These files must be
JSON objects; the recipe/input contract binding and plan/contract correspondence
are checked. The complete files/artifacts listed by each retained run record must
also be included under `run_id/<file>` and `run_id/output/<artifact>`. Canonical
aliases may duplicate those bytes, and count toward the decoded size limit.

All recorded input hashes must match `source/<input-relative-path>` material.
The producer supplies its full normalized protocol snapshot there, including
criteria and executable source, not merely a hash inventory. Paths containing
traversal, absolute paths or unmapped extra non-source files are rejected. This
layer verifies the recorded closure; the parent must also prove that the snapshot
really captures the full declared experiment and that no undeclared source was
needed. Inputs outside the bounded supported snapshot are not silently attested.

The explicit evaluation scope is **training-only observed classification**. A
signed report with this schema cannot label its machine-readable scope as held-out
generalization. This is intentionally narrower than a general model-quality claim.

This verifier checks the shape and exact content identity. The consuming admission
policy must verify the underlying evidence and synthesis semantics. Merely writing
hash-looking strings, setting TESTED, or passing an unchecked imported document's
hash back as the expected hash does **not** establish those prerequisites.

## Decision and boundaries

The function reuses `diagnostic_bundle._verified` byte snapshots and
`signed_bundle_review.verify_review`. It requires an authenticated, explicit
`accept` verdict over the same manifest and pack list. Missing/changed/unsigned
reviews, `request-changes`, `inconclusive`, changed trust, self-review labels, wrong
author, wrong evidence identity, missing capture/replay fields and selected-subnode
findings all fail closed. Known failed or incomplete prerequisite documents cannot
be accepted even when their signature is valid.

A valid **bounded negative scientific result** may still be reviewed and accepted.
`accept` means the reviewer accepts the exact evidence and its stated conclusion;
it never changes `BOUNDED_CONTRAST_NOT_SUPPORTED` into a positive result.

The result is `AUTHENTICATED_ACCEPT`, with `automatic_admission: false` and
`scientific_qualification: NOT_QUALIFIED`. This authenticates possession of a key
allowed for the expected signer. Different author/reviewer strings do not prove
different humans, organizations or sessions control the keys. The caller's trust
configuration and independent-review policy remain necessary. There are no
production keys, automatic signatures, remote identity lookups or new signing
infrastructure in this layer.

Only authorized, public-safe evidence belongs in diagnostic bundles. This layer
neither sanitizes sensitive data nor grants permission to publish evidence.

## Tests

`PYTHONPATH=integrations/trainlab/src python -m unittest discover -s integrations/trainlab/tests -p test_assurance_review.py`

Tests generate ephemeral local Ed25519 keys and verify exact positive/negative
review decisions, changed claims/trust/bytes, missing prerequisites and improper
finding mappings. They test software behavior, not real reviewer independence or
scientific validity. OpenSSH is required; tests explicitly skip if unavailable.
