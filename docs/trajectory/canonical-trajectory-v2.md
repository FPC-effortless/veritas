# Canonical Trajectory v2

`TrajectoryV2` is Veritas's canonical, versioned trajectory/evaluation record. It is an additive
layer over Foundry's existing `RolloutTrace`; it does not replace `RolloutTrace`, tracing, runtime,
or verifier behavior.

The contract is designed for four uses:

1. bind a run to the exact model, harness, runtime, verifier, task, world, reset, and ordered events;
2. preserve legacy trace provenance while allowing richer runtime/provider accounting;
3. support append-only offline reverification without changing the original evaluation;
4. provide explicit public/buyer-safe serialization boundaries for evaluator-private material.

## Schema and identity

The schema identifier is `veritas.trajectory.v2`. Canonical IDs are formatted as
`TRAJ-V2-<SHA256 prefix>` and are recomputed from immutable run semantics at model validation.
Supplying an ID that does not match the content is rejected.

The identity payload binds:

- environment/world identity;
- WorldBundle and PortableOperationalContract identity when supplied;
- task, taskset, and split;
- model provider/id/snapshot;
- agent, harness, runtime, and original verifier identity/version;
- reset/seed identity;
- initial state digest;
- ordered events, including state transitions and semantic private payloads;
- provider/resource calls and observation/evidence references;
- usage accounting where known;
- original verifier component scores and reward;
- termination/truncation state;
- final state digest;
- failure classification;
- capability tags.

Event order is semantic. Reordering otherwise identical events changes `trajectory_id`.

The ID intentionally does **not** bind provenance annotations/timestamps, visibility labels,
public/private metadata buckets, or appended reverification records. Those can be added without
changing what run the trajectory identifies. Private semantic payloads are different: they are
part of the canonical identity even though safe serializers never expose them.

## Legacy `RolloutTrace` adapter

Use `trajectory_v2_from_rollout_trace(trace, context=...)`.

`RolloutTrace` fields map directly as follows:

| RolloutTrace | TrajectoryV2 |
| --- | --- |
| `trace_id` | buyer-safe source provenance, not canonical identity |
| `environment_version` | `world.environment_version` |
| `task_id`, `taskset_version`, `split` | `task` |
| `task_seed` | `reset.seed` |
| `harness_version` | `harness.version` |
| `runtime_version` | `runtime.version` |
| `initial_state_hash` | `initial_state` |
| `events` | ordered `TrajectoryEvent` records |
| `verifier_components`, `total_reward` | `original_evaluation` |
| `termination_reason` | `termination.reason` |
| `final_state_hash` | `final_state` |
| `total_cost` | environment and total usage cost |
| `capability_tags` | canonicalized `capability_tags` |
| `metadata` | private source provenance metadata |

The adapter does not guess facts that `RolloutTrace` cannot represent. Supply those facts through
`RolloutTraceAdapterContext`: model/snapshot, agent, harness/runtime IDs, verifier identity,
WorldBundle identity, PortableOperationalContract identity, provider calls, references, duration,
termination/truncation flags, or an explicit failure classification.

If no failure classification is supplied, the result remains `UNKNOWN` even when the legacy
termination reason contains words such as `error` or `failure`. A termination string alone is not
enough evidence to attribute blame.

Legacy event payloads are treated as public interaction payloads because Foundry's tracing proxy
records public runtime operations. Arbitrary `RolloutTrace.metadata` is **not** promoted to public
metadata; it is preserved under private provenance by default.

## Failure taxonomy

`FailureClassification.category` is a closed enum. The supported categories are:

- `model_failure`;
- `harness_failure`;
- `tool_action_failure`;
- `environment_runtime_failure`;
- `verifier_failure`;
- `dataset_task_defect`;
- `infrastructure_provider_failure`;
- `budget_termination_failure`;
- `unknown_unattributed` (`FailureCategory.UNKNOWN`).

Unsupported free-form categories fail validation. `UNKNOWN` cannot carry positive attribution
confidence. Diagnostics may still preserve a free-form `code` or `detail`, but those fields do not
turn uncertainty into an attributed category.

## Visibility and buyer-safe output

Every classified reference/call/event can be marked `public`, `buyer_safe`, `internal`,
`evaluator_private`, or `sealed`. Sensitive payload material belongs in `private_payload` or
`private_metadata`, never in a public payload bucket.

Use:

- `trajectory.public_payload()` for public serialization;
- `trajectory.buyer_safe_payload()` for buyer-safe serialization.

Both serializers recursively omit `private_payload` and `private_metadata`. They also omit nested
objects whose visibility is above the requested level. The full Pydantic `model_dump()` is an
internal representation and must not be used as a publication/export boundary.

The legacy source trace ID/digest is classified `buyer_safe`: it is available to buyer-safe
consumers for audit correlation, but omitted from the stricter public payload. Legacy trace
metadata remains private in either serialization.

## Reverification records

`original_evaluation` is the score produced by the verifier attached to the original run. It is a
separate frozen field from `reverifications` and is never rewritten by reverification.

A `ReverificationRecord` contains:

- its own deterministic `record_id`;
- input `trajectory_id`;
- verifier identity/version;
- component scores;
- reward;
- optional timestamp;
- optional provenance and metadata;
- visibility classification.

`TrajectoryV2.with_reverification(record)` returns a new frozen trajectory value with the record
appended. It rejects a record for another trajectory and rejects duplicate record IDs. Appending a
reverification does not change `trajectory_id` or `original_evaluation`.

This branch deliberately does not implement a reverification engine, verifier dispatch, evidence
resolution, persistence service, or score selection policy.

## B4 consumer contract

B4 should treat `TrajectoryV2` as immutable verifier input and `ReverificationRecord` as its only
score output contract.

For each offline reverification:

1. resolve the canonical trajectory by `trajectory_id`;
2. use the full authorized trajectory view required by the verifier, not a buyer-safe projection if
   private evaluator evidence is required;
3. record the exact verifier ID/version used for the replay;
4. emit component scores and reward into a new `ReverificationRecord`;
5. attach timestamp/provenance only when actually known;
6. append the record; do not mutate `original_evaluation`;
7. keep uncertain failure attribution as `UNKNOWN` unless independent evidence establishes a
   supported taxonomy category.

B4 may use `record_id` for idempotency. Duplicate records are rejected by the trajectory model.
A later policy may choose which evaluation to display, but that policy must not collapse original
and reverified scores into one mutable field.

## Observatory consumer contract

Observatory already knows more execution identity than legacy `RolloutTrace`. When adapting an
Observatory run, construct `RolloutTraceAdapterContext` from the `LongitudinalCell` and provider
session rather than putting those facts into Foundry metadata:

- `cell.world` -> environment/world identity;
- `cell.model` -> `ModelIdentity(provider, model_id, snapshot)`;
- `cell.harness.harness_id` -> `harness_id` (the trace retains harness version);
- runtime registry/factory identity -> `runtime_id` (the trace retains runtime version);
- `cell.verifier` -> `VerifierIdentity`;
- `ProviderSessionSummary.call_records` plus model/provider identity -> `ProviderCallSummary`;
- scenario/reset facts remain bound through the trace seed/task identity;
- known elapsed time can populate `elapsed_s`;
- explicit evidence/observation handles can populate the typed reference lists.

The adapter has no dependency on `observatory/**`, so Observatory can adopt it without introducing
a reverse dependency. Existing `CapabilityRun` and longitudinal analysis can continue to use
`RolloutTrace`; `TrajectoryV2` is the richer canonical audit/reverification record alongside that
path.

For correlation, use:

- `trajectory_id` as the canonical run identity;
- `provenance[*].source_id` to recover the source `RolloutTrace.trace_id`;
- `original_evaluation` for the original verifier result;
- `reverifications` for later offline scores;
- buyer-safe/public serializers only at export boundaries.

## Compatibility boundary

This package does not modify Foundry, Observatory, OperationalEpisode, OperationalRuntime,
portability compilers, integrations, or root CLI behavior. It consumes the existing public Python
models and leaves those systems free to migrate incrementally.
