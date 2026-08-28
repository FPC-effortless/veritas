# Trajectory v2 metadata completeness audit

TRACE-001 audits **producer/path completeness**, not merely the fields available in `TrajectoryV2`.

Audit base: `fbdb74db7080a078c945506a6c759305f4cd1f78`.

Evidence paths:

- canonical schema: `src/investigation_world/trajectory/models.py`;
- legacy producer: `src/investigation_world/trajectory/adapter.py` plus Foundry `RolloutTrace`;
- portable runtime: `src/investigation_world/portable_runtime/models.py`;
- external adapter: `src/investigation_world/exporters/hud/adapter.py`.

## Coverage semantics

- **PRESENT** — the path emits or deterministically derives the fact without extra caller evidence.
- **CONDITIONAL** — the fact is captured only when a caller/integration supplies or retains additional evidence. This is not counted as complete.
- **ABSENT** — the path does not currently preserve the fact.
- **UNSUPPORTED** — the path does not expose that kind of fact as part of its current responsibility/interface.
- **UNKNOWN** — evidence was insufficient to classify the path. UNKNOWN never becomes a completeness PASS.

Reward components are optional in this audit; the remaining listed dimensions are required for the intended replay, diagnostics, harness-comparison, accounting, or provenance use when the corresponding path participates in trajectory construction.

## Producer/path matrix

| Metadata dimension | Legacy Foundry → TrajectoryV2 | Portable runtime direct | HUD operational adapter |
| --- | --- | --- | --- |
| world/environment identity | CONDITIONAL | CONDITIONAL | PRESENT |
| task identity | PRESENT | CONDITIONAL | PRESENT |
| model identity | CONDITIONAL | ABSENT | ABSENT |
| agent identity | CONDITIONAL | ABSENT | ABSENT |
| harness identity | CONDITIONAL | ABSENT | ABSENT |
| harness config identity | ABSENT | ABSENT | ABSENT |
| runtime identity | CONDITIONAL | ABSENT | CONDITIONAL |
| verifier identity | CONDITIONAL | ABSENT | ABSENT |
| seed/reset identity | CONDITIONAL | CONDITIONAL | CONDITIONAL |
| observations | CONDITIONAL | PRESENT | PRESENT |
| action/tool/resource calls | PRESENT | CONDITIONAL | CONDITIONAL |
| provider calls | CONDITIONAL | UNSUPPORTED | UNSUPPORTED |
| provider request ID | CONDITIONAL | UNSUPPORTED | UNSUPPORTED |
| artifact/evidence references | CONDITIONAL | CONDITIONAL | CONDITIONAL |
| state digests/transitions | PRESENT | CONDITIONAL | CONDITIONAL |
| reward/components | PRESENT | PRESENT | CONDITIONAL |
| token usage | CONDITIONAL | UNSUPPORTED | UNSUPPORTED |
| cost usage | CONDITIONAL | UNSUPPORTED | UNSUPPORTED |
| time usage | CONDITIONAL | UNSUPPORTED | UNSUPPORTED |
| termination/truncation | CONDITIONAL | PRESENT | PRESENT |
| failure origin/classification | CONDITIONAL | CONDITIONAL | CONDITIONAL |
| public/private visibility | PRESENT | UNSUPPORTED | CONDITIONAL |
| provenance/source references | PRESENT | ABSENT | CONDITIONAL |

None of the three audited paths is unconditionally complete across the required metadata dimensions.

## 1. Canonical TrajectoryV2 capacity

The canonical schema is substantially richer than the legacy producer. It can represent:

- world, task, model, agent, harness, runtime, verifier, and reset identities;
- state digests and before/after event state;
- observation/evidence references;
- provider and resource calls;
- provider request IDs;
- token/cost/time usage;
- evaluation, termination, failure classification;
- public/private visibility; and
- provenance/reverification records.

That representational capacity is **not evidence that every producer fills those fields**.

One schema-level gap is proven: `HarnessIdentity` contains `harness_id` and `version`, but no harness configuration digest. Exact harness configuration therefore cannot currently participate in `TrajectoryV2` semantic identity even though HARNESS-001 requires exact harness ID/version/config identity for conformance comparison.

## 2. Legacy Foundry RolloutTrace adapter

`trajectory_v2_from_rollout_trace()` is a real deterministic `TrajectoryV2` producer. It correctly refuses to invent legacy facts.

Native/derived coverage includes:

- task identity and task seed;
- environment/harness/runtime versions;
- event payloads, state before/after digests, and event cost;
- deterministic resource-call summaries;
- verifier component scores and scalar reward;
- environment cost;
- termination reason;
- capability tags; and
- content-bound source provenance.

The adapter explicitly depends on `RolloutTraceAdapterContext` for facts not present in the legacy trace, including model/agent identity, harness ID, runtime ID, verifier identity, world/artifact identity, reset ID/index, provider calls, observation/evidence references, elapsed time, terminated/truncated booleans, and failure classification.

Important fail-closed behavior already present:

- ambiguous termination is not automatically classified as model/environment failure;
- missing provider accounting remains unknown;
- partial provider cost accounting does not become a fabricated total;
- private legacy metadata is retained as private provenance metadata.

Remaining producer gap: legacy `TraceEvent` conversion does not populate `TrajectoryEvent.duration_s`, so event-level timing is unavailable even when overall elapsed time is supplied.

## 3. Portable operational runtime

`PortableOperationalRuntime` is a semantic execution surface, **not a TrajectoryV2 producer**.

Its reset/step result models preserve high-value environment facts such as:

- observation;
- state digest;
- reward and optional reward components;
- terminated/truncated flags;
- budget state; and
- structured runtime failure status.

But result models do not carry model/agent/harness/provider identities, provider calls, request IDs, tokens, elapsed time, trajectory visibility, or trajectory provenance. World/task identity is available through the bound portable contract rather than the individual result object, and reset seed/request identity must be retained by the caller.

This is not a defect in the portable runtime contract. The gap is the absence of an additive **portable interaction → TrajectoryV2 capture adapter** that binds requests, results, contract identity, runtime identity, calling harness/model metadata, usage, and provenance without changing runtime semantics.

## 4. HUD external adapter/harness path

`HudOperationalAdapter` delegates semantic execution to the shared portable runtime. Its public metering event records:

- phase;
- public contract ID;
- task ID;
- tool name where applicable;
- post-state digest;
- scalar reward; and
- terminated/truncated flags.

Adapter metadata additionally exposes adapter version, HUD wire protocol, pinned HUD SDK, MCP capability protocol, environment/task identity, public contract identity, and compatibility gaps.

However, HUD metering is intentionally an out-of-band observer, not a `TrajectoryV2` producer. It does not capture model/agent/harness execution identity, provider calls/request IDs, token/cost/time accounting, complete tool request/result summaries, verifier identity, or canonical trajectory provenance. Full `PortableStepResult` contains more information than the public meter, so a calling harness can retain additional facts, but that is conditional integration evidence rather than current producer completeness.

Public-only metering must not be generalized into a claim that all associated metadata is safe for public trajectory serialization. `TrajectoryV2` visibility must still be assigned at the canonical trajectory boundary.

## Interface-gap requests

### TRACE-GAP-HARNESS-CONFIG — trajectory schema authority

**Request:** add a content-bound harness configuration identity to canonical trajectory identity, or an equivalent content-addressed harness artifact reference, without weakening visibility boundaries.

**Why:** HARNESS-001 compares exact harness ID/version/config. Current `TrajectoryV2.HarnessIdentity` cannot represent config identity.

This audit does not change the schema. A separate interface issue is required.

### TRACE-GAP-PORTABLE-PRODUCER — trajectory/portable integration

**Request:** define an additive `PortableOperationalRuntime` interaction-to-`TrajectoryV2` capture adapter.

It should preserve request/result ordering, reset seed/identity, contract/runtime identity, observations, state transitions, rewards, failure status, artifact/evidence references, usage evidence supplied by the calling harness, and source provenance. Missing harness/provider evidence must remain unknown rather than receive defaults.

### TRACE-GAP-HUD-CAPTURE — HUD harness integration

**Request:** capture harness/model/provider/accounting events around HUD execution before constructing `TrajectoryV2`.

The integration should retain public HUD metering but supplement it with the calling harness's model/provider/tool/usage evidence. It must not mutate HUD semantic results or treat HUD public metering as proof that unrelated provider/private metadata is public-safe.

## Relationship to cross-runtime conformance

The existing cross-runtime conformance suite proves that Prime, OpenEnv, HUD, Harbor, and NeMo can preserve the same canonical environment semantics for the deterministic vector.

That is a different claim from trajectory completeness. A runtime can preserve observation/state/reward/termination/evidence semantics while emitting none of the model/harness/provider/accounting metadata required for trajectory diagnostics or learning-efficiency analysis.

Therefore:

**semantic conformance ≠ trajectory metadata completeness**.

Both should eventually be bound to the same exact runtime/harness versions, but neither score substitutes for the other.

## Evidence boundary

TRACE-001 is a completeness audit. It does not:

- redesign the canonical trajectory schema;
- modify Foundry, portable runtime, HUD, or any exporter;
- claim that missing optional metadata is a defect;
- treat schema presence as producer evidence;
- treat public serialization support as proof that arbitrary private metadata is safe; or
- establish scientific, Frontier, training, fidelity, commercial, or release qualification.
