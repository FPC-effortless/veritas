# Native submission evidence and offline reverification

Work Contract: **NATIVE-REPLAY-EVIDENCE-001 / #438**. Prerequisite for #435,
not completion of the held G-03 adapter (#395 / #397).

## Producer boundary

`NativeOperationalRuntime.last_native_submission` is `None` until submission,
then an evaluator-private `NativeSubmissionReceipt`. Its frozen fields contain
canonical JSON snapshots, not mutable nested dictionaries: the episode before
native assertions are injected, actual initial state (including mounted substrate
state), pre/post evaluator state, every recorded action attempt, submission,
budget totals, descriptor and `NativeArtifactVerification`. Its retained absolute
artifact path and snapshot contents must never be passed to an evaluated agent.
`public_payload()` is unchanged and does not include the receipt.

The receipt ID/digest binds these contents, including the retained path. It is
not a signature, a proof of authenticity or a proof that the recorded checks are
true. Original artifacts must remain available at that path. Moving, deleting or
changing the retained bytes invalidates reverification; this version does not
provide portable artifact storage or authenticity attestation.

Submission still performs the native evaluator transition separately from agent
actions, synchronizes it into an attached substrate, computes ordinary scores,
and only then appends native failure attribution. Receipt capture does not add
agent actions, charges or budget usage.

## Canonical trajectory integration

A producer integrating the receipt must compile the portable contract from the
native episode **before submission injects native assertions**, retain the actual
initial state, and project every recorded act attempt (including blocked/no-effect
attempts). Attach the receipt as `OperationalReplayEvidence.native_submission`.
The existing evaluator-private replay reference binds the entire evidence digest,
including the receipt; use the existing evidence `reference()` and
`attach_operational_replay_evidence()` machinery.

Include exactly one evaluator-private `TrajectoryEvent` immediately before the
successful submit event, after all acts:

- `event_type="native_submission"`;
- `payload={"method": "verify_native_artifact", "receipt_id": receipt.receipt_id}`;
- `cost=0`, `visibility=VisibilityClass.EVALUATOR_PRIVATE`;
- `state_before` / `state_after` contain the existing `stable_hash` of the receipt's
  pre/final state snapshots.

This event is an evaluator transition, never a fabricated `ActionEvent`.
The replay payload stays in `private_metadata`; buyer-safe/public serialization
omits both it and the private evaluator event.

## Independent verification

`current_operational_verifier_binding()` authorizes both the pinned ordinary
verifier and native artifact inspection. Explicitly constructed bindings default
to native inspection **unauthorized** unless the caller opts in with
`authorize_native_artifacts=True`. The registry still matches exact verifier
identity; it never imports arbitrary receipt-provided entrypoints.

The engine binds receipt snapshots to the contract, trajectory, action sequence,
states, submission and budgets. It replays all recorded acts with the ordinary
runtime and checks their hidden effects and pre-evaluator state. Search/read
charges remain in captured totals; replay does not pretend to reconstruct calls
not present in the action log.

The native inspector checks pinned source blobs for `artifacts.py` and
`parameterized_artifacts.py`, descriptor and artifact content hash, then reads each retained file once into a bounded evaluator-private byte snapshot
and calls the existing domain inspectors against that same snapshot. The content
hash binds the exact bytes inspected, not two observations of a mutable live path.
Snapshots permit at most 64 MiB in aggregate and 1,024 filesystem entries; larger
artifacts fail closed. Temporary copies are removed after inspection. It does **not** call
workspace constructors, `verify()`, `materialize()` or native action application.
Symlink paths and non-regular files are rejected. Snapshot copies are not artifact
regeneration or workspace materialization. The recomputed checks, measurements, validity and
post-inspection hash must equal the recorded result. Hash-consistent false checks
still fail. The independently established native assertions are added to the
ordinary oracle, and native failures are appended only after score calculation.

Missing/stale evidence, altered identity/content, invalid event placement and
unavailable/changed artifacts produce unscored fail-closed outcomes. Non-native
replay evidence retains its original digest semantics when the optional receipt
is absent.

## Evidence and remaining work

`tests/trajectory/test_native_submission_reverification.py` exercises actual
native artifacts in all five domains, including real corruption, standalone and
substrate score parity, blocked attempts, private serialization, tampering,
non-materialization and deterministic repeated reverification. These are
**receipt/engine integration tests**: canonical trajectory events are constructed
from real runtime records, not emitted by the held G-03 adapter.

#435 remains open until that adapter consumes the receipt, captures the actual
initial state, projects blocked actions correctly, and resolves its unrelated
`.gitignore` ownership change. This lane establishes implementation evidence only;
it does not establish scientific, Frontier, commercial or release qualification.
