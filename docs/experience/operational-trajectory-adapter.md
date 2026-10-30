# Operational runtime → TrajectoryV2

**G-03 / #395 / PR #397** is a record converter, not an execution or scoring
engine. It consumes a closed `OperationalRuntime` (including
`NativeOperationalRuntime`) through `trajectory_v2_from_operational_runtime`.
The legacy `trajectory_v2_from_rollout_trace` API and behavior are unchanged.

## Ownership and prerequisite

The implementation, exports, tests and this document are the four G-03 paths:
`src/investigation_world/trajectory/adapter.py`,
`src/investigation_world/trajectory/__init__.py`,
`tests/trajectory/test_operational_runtime_adapter.py`, and this file.
Operational runtime, reverify, experience, qualification, portability and
Observatory sources remain read-only. The unrelated historical `.gitignore`
addition is removed, leaving no net change to that file relative to main.

Stop condition 3 was correctly reported by the earlier review: native submit
adds evaluator assertions not represented by agent action events. The separate
native-replay prerequisite #438 / merged #441 provides an immutable private
receipt and an existing replay transition. The owner-authorized 2026-10-30 Work
Contract revision permits consuming that path; it does not waive the round-trip
requirement or authorize a second engine, schema, vocabulary or inspector.

## Context and authoritative state

`OperationalRuntimeAdapterContext` requires the actual `EpisodeSubmission` and
returned `VerificationBreakdown`. The adapter does not call `submit`, recompute
scores, inspect artifacts, materialize workspaces, replay actions, or mutate the
runtime. Open runtimes and missing submission/evaluation context fail closed.

Ordinary runtimes do not retain authoritative pre-execution state. Capture
`stable_hash(runtime.state_snapshot())` **after constructing/mounting the runtime,
before executing actions**, and pass it as `initial_state_digest`. Omission raises
`ValueError`; using the current post-execution state as initial state is forbidden.
The oracle's nominal initial state is not a substitute for mounted substrate state.

Native runtimes retain `last_native_submission.initial_state_json`. Its digest is
derived automatically, including substrate state. A supplied initial digest must
match. The final native state comes from `receipt.final_state_json`, and a supplied
final digest must match that record. Ordinary final state is the closed runtime's
snapshot, unless explicitly supplied by the caller.

State digests use the existing replay `foundry.models.stable_hash`, not
`canonical_hash`. These functions have different serialization semantics;
`canonical_hash` remains the trajectory/event identity function. Digest scopes
default to `SEMANTIC`, not `PUBLIC_SEMANTIC`: oracle-derived state is private.
This explicitly resolves the earlier scope question, not an implicit downgrade.
Caller-provided public scopes require the caller to establish that state is public.

World/task identity comes from the runtime. Model, agent, harness, reset identity,
provider accounting, task split, elapsed time and failure attribution remain unknown
unless provided. World version and portable-contract identity are caller context;
world ID cannot be overridden. The default verifier identity comes from
`current_operational_verifier_binding()`, with the current main source pins intact.
A supplied verifier is retained for both the trajectory and original evaluation;
this is not a claim of registry authorization or qualification.

## Event mapping

| Source | Canonical mapping |
| --- | --- |
| Every `ActionEvent`, including blocked/no-effect attempts | One `act` event, in order; `step=sequence-1` |
| Action name and parameters | `method="act"`, `action_name=name`, `args=[name]`, `kwargs=parameters` |
| Action effect/blocked flags | Truthful public `success=bool(effect_applied and not blocked)` |
| Action cost | Exact recorded cost |
| Hidden consequences | `private_payload`: sequence, kind, system, state changes, side effects, forbidden, severity, effect/blocked flags and optional blocked reason |
| Native receipt | Exactly one private `native_submission` event after all acts, immediately before submit |
| Original submission | One zero-cost `submit`, with `args=[submission.model_dump(mode="json")]`, empty kwargs and success true |

The native event is the existing evaluator transition, **not an agent action**:

```python
TrajectoryEvent(
    step=len(acted),
    event_type="native_submission",
    payload={"method": "verify_native_artifact", "receipt_id": receipt.receipt_id},
    cost=0,
    state_before=StateDigest(digest=stable_hash(json.loads(receipt.pre_state_json))),
    state_after=StateDigest(digest=stable_hash(json.loads(receipt.final_state_json))),
    visibility=VisibilityClass.EVALUATOR_PRIVATE,
)
```

The implementation explicitly sets these digests' scope to `SEMANTIC`.
The existing decoder recovers each act's name/parameters. The merged engine
validates all attempted acts, rather than discarding unsuccessful attempts.
Budget totals retain all runtime charges, including search/read charges not
represented in the action log; the adapter does not invent those missing events.

Resource summaries reuse `_resource_call`/`_resource_id` for public events only;
unknown resource IDs remain `None`. Native evaluator events are excluded rather
than leaking their existence into public resource summaries. No second convention
or helper is introduced. Full episode metadata and the returned breakdown remain
in private provenance metadata, never public event fields.

## Existing reverify and MachineExperience integration

Before submission, compile `compile_operational_episode(runtime.episode)` after
native runtime construction has attached the descriptor, but before submission
injects native assertions. Capture the actual initial state at that same point.
After execution/submission:

1. Adapt the runtime, passing submission, returned breakdown and the portable
   contract identity (plus the initial digest for ordinary runtimes).
2. Construct existing `OperationalReplayEvidence` from that pre-submit contract,
   `canonical_hash(trajectory.events)`, actual initial/final states and their
   `stable_hash` digests, recorded actions, submission and exact budgets. For native
   runs set `native_submission=runtime.last_native_submission`.
3. Add `evidence.reference()` to the trajectory's references. Revalidate with
   `trajectory_id=""` so the identity includes the new reference. Then call
   `attach_operational_replay_evidence(referenced, evidence.for_trajectory(referenced))`.
4. Call existing `reverify_trajectory` with an authorized binding/registry.
   `machine_experience_from_trajectory` accepts the resulting trajectory with its
   normal `E0_TRACEABLE` default. Neither consumer is modified.

The private receipt and retained artifact paths must never enter public context.
Reverification independently inspects retained artifacts through the prerequisite's
existing offline path. The adapter itself does not inspect or regenerate them.
Missing or changed retained bytes remain fail-closed. A genuine artifact failure
can correctly reverify the original failed result; `REVERIFIED` does not mean the
agent succeeded. Native assertions and failure ordering are preserved.

## Verification and scope of claims

Regression tests first reproduced both ordinary initial-state mislabeling and
missing native state/transition handling. Actual adapter integration tests cover
all five domains × standalone/substrate × valid/genuinely corrupted artifacts,
including blocked attempts, original score parity, recorded digest binding,
deterministic repeated adaptation/reverification, public/private separation and
the unmodified MachineExperience consumer. The prerequisite's execution and
artifact-corruption helpers are reused; its hand-built trajectory is not used.
Legacy adapter/model tests and the Work Contract's broader test ladder remain
required. Exact-head CI/security and independent review are integration gates,
not inferred from local test success.

G-04, G-09 and G-10 can consume this trajectory but are not implemented or specified
here. This work produces no qualification evidence, maturity promotion, paid model
results, sealed-panel evidence, commercial release, Frontier claim or deployment.
