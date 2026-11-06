# Offline trajectory reverification

Offline reverification re-scores an existing canonical `TrajectoryV2` without invoking the model,
provider, harness, or runtime. It consumes only evidence captured with the source trajectory and a
statically authorized local verifier binding.

The implementation lives in `investigation_world.trajectory.reverify`. It does not modify the
operational verifier, Foundry, Observatory, Frontier, or the core trajectory models.

## Safety and integrity contract

Reverification fails closed. A score is emitted only when all of the following are true:

1. the source `TrajectoryV2` still validates against its canonical `trajectory_id`;
2. the requested verifier ID **and exact version** resolve to an explicitly authorized binding;
3. the trajectory carries an evaluator-private replay-evidence payload;
4. that payload has an evaluator-private `TrajectoryReference` whose digest is part of the
   trajectory's canonical identity;
5. the payload is bound to the same `trajectory_id`;
6. the referenced `PortableOperationalContract.contract_id` matches the contract identity already
   carried by the trajectory;
7. task/world identity, ordered trajectory-event digest, action projection, submission, state
   digests, state-change replay, and known environment cost all agree;
8. the portable evaluator contract is deterministic; and
9. the authorized local verifier completes successfully.

Missing evidence returns `NOT_REVERIFIABLE`. Integrity ambiguity or verifier execution failure
returns `UNKNOWN`. Neither status contains a fabricated score or a new `ReverificationRecord`.
An unregistered verifier or version returns `UNAUTHORIZED`.

## Why public events are insufficient

Operational verification uses evaluator-private material that public runtime traces intentionally do
not contain: hidden state assertions, invariants, action consequence records, required evidence,
forbidden-action semantics, exact evaluator state, and budget counters. Reconstructing those values
from buyer-safe/public trajectory material would violate the secrecy boundary and could silently
invent evaluator truth.

For that reason reverification never synthesizes private truth from:

- `public_payload()` or `buyer_safe_payload()`;
- public observation/evidence records;
- provider/model call records;
- action names alone; or
- the portable contract's public partition.

The complete replay envelope is stored only under trajectory `private_metadata`. Its full digest is
also carried by an `EVALUATOR_PRIVATE` evidence reference. Safe serializers remove both the private
payload and the private reference.

## Replay evidence envelope

`OperationalReplayEvidence` contains the minimum exact inputs needed to rebuild the current
operational verifier call:

- full `PortableOperationalContract`, including its private evaluator partition;
- digest of the ordered `TrajectoryEvent` sequence;
- exact evaluator-visible initial and final runtime state plus their trajectory state digests;
- exact verifier-private `ActionEvent` sequence captured during execution;
- exact `EpisodeSubmission`;
- exact tool-call and cost counters at submission.

The evidence ID and digest are deterministic over those fields. `input_trajectory_id` is deliberately
excluded from the evidence digest so capture can be two-phase:

1. build `OperationalReplayEvidence` before the trajectory ID exists;
2. add `evidence.reference()` to `TrajectoryV2.evidence_references` so the evidence digest becomes
   identity-bearing;
3. construct the canonical `TrajectoryV2`;
4. bind the evidence to that ID with `evidence.for_trajectory(trajectory)`; and
5. call `attach_operational_replay_evidence(...)` to place the full payload in private metadata.

Step 5 returns a new immutable trajectory value and asserts that the `trajectory_id` did not change.
It never mutates the source object.

A trajectory created without the identity-bearing private evidence reference cannot later become
reverifiable merely by inserting private metadata. That prevents a buyer-safe trajectory or a
post-hoc payload from acquiring unbound private truth.

## Authorized verifier binding

`AuthorizedVerifierRegistry` performs exact `(verifier_id, version)` matching. It accepts only the
statically defined offline operational binding; it does not import an entrypoint named by trajectory
or evaluator data and does not accept arbitrary callables.

`current_operational_verifier_binding()` identifies the installed verifier by:

- entrypoint: `investigation_world.operational.verifier:verify_operational_episode`;
- version: the portable contract's exact verifier semantics ID, which includes the pinned Git blob
  SHA-1; and
- source Git blob SHA-1.

Immediately before scoring, the binding hashes the installed verifier source and refuses execution
if it does not match the authorized source identity. A different version string is not considered an
alias for the authorized verifier.

Future verifier implementations need a new explicit offline binding. They must define their own
required replay evidence and must not fall back to the current binding when versions differ.

## Deterministic evaluator input reconstruction

The reverify layer does **not** re-run action transition semantics. It converts the already-bound
portable private evaluator contract back into the existing `HiddenOracle` input shape and supplies
the captured `ActionEvent` records, final state, submission, and budget counters directly to
`verify_operational_episode`.

As an integrity check only, the captured `state_changes` are applied in action-event order to the
captured initial state and must reproduce the captured final state. This does not select effects,
interpret preconditions, or execute actions again.

The public projection of each captured action is also checked against the source trajectory call and
portable public action definition. Hidden consequence fields are never inferred from the public
trace.

## Result semantics

`reverify_trajectory(...)` returns `ReverificationOutcome`.

- `REVERIFIED`: a new `ReverificationRecord` was appended to a new trajectory value.
- `ALREADY_RECORDED`: the deterministic record already exists; no duplicate is appended.
- `NOT_REVERIFIABLE`: required replay/evaluator evidence is absent or structurally unsupported.
- `UNKNOWN`: identity/evidence integrity is ambiguous, or the authorized verifier failed.
- `UNAUTHORIZED`: the requested exact verifier identity is not registered.

On success, the record contains the new verifier identity and provenance records for:

- the original trajectory verifier ID/version;
- the replay-evidence ID/digest; and
- the authorized new verifier binding ID/version/source digest.

The original reward and component scores remain in `TrajectoryV2.original_evaluation` unchanged.
The new score exists only in the appended `ReverificationRecord`. The record's private metadata may
contain the full `VerificationBreakdown`; publication boundaries must continue to use the trajectory
safe serializers.

## No inference or provider calls

The reverification API has no model, provider, harness, runtime factory, network resolver, or dynamic
entrypoint parameter. The authorized binding calls only the existing local operational verifier.
Reverification therefore cannot trigger model inference as part of its supported execution path.

## Falsifiers covered by tests

`tests/trajectory/reverify/` covers:

- original scores remain unchanged after a new score is appended;
- duplicate reverification is idempotent rather than appended twice;
- missing replay evidence yields `NOT_REVERIFIABLE` with no score;
- buyer-safe output contains neither replay evidence nor private oracle material;
- wrong verifier versions are rejected rather than treated as equivalent;
- reordered trajectory events are detected even if a new trajectory ID is computed;
- private required-evidence rules still affect the reverified score;
- evaluator input reconstruction is deterministic; and
- arbitrary callable/provider-like verifier bindings cannot be injected into the registry.
