# Harness conformance contract

HARNESS-001 defines the minimum declaration and observation boundary required to compare model/agent harness behavior without forcing Veritas to own every harness implementation.

## What this contract proves

A `PASS` report means that one exact harness/version/config identity:

- declared every required harness behavior dimension;
- was exercised by the referenced deterministic fixture;
- matched the declared support/unsupported behavior for every required dimension;
- emitted the trace fields required to distinguish harness/provider/tool effects from model/environment outcomes; and
- reproduced the same deterministic fixture digest across the required replay count.

It does **not** mean the harness is universally better, that the underlying model is capable, that environment semantics are correct, or that an environment is scientifically, Frontier, training, commercial, or release qualified.

## Exact identity

`HarnessIdentity` binds:

- `harness_id`;
- `version`;
- `config_sha256`; and
- optional `implementation_sha256`.

Comparison is exact. Changing harness version or configuration requires new evidence; a display name alone is not a sufficient identity.

## Required behavior declarations

Every `HarnessDeclaration` must explicitly cover all of the following:

1. model transport;
2. tool/capability transport;
3. context assembly;
4. artifact visibility/access;
5. parallel tool behavior;
6. timeout/retry behavior;
7. system-prompt/skill injection;
8. state/reset visibility;
9. trajectory/event emission;
10. token/cost/time usage accounting; and
11. failure/provider-error reporting.

Each dimension is `SUPPORTED`, `UNSUPPORTED`, or `UNKNOWN`.

`SUPPORTED` requires observable semantics. `UNSUPPORTED` requires an explicit limitation. `UNKNOWN` requires an evidence gap and can never silently become PASS.

A harness is not required to support every architecture feature. For example, serial-only tool execution may conform if parallel calls are explicitly unsupported and the fixture observes the declared rejection behavior. The `UNSUPPORTED` enum alone is not evidence: every declared limitation must also appear as a content-bound fixture-observed behavior fact in `HarnessCapabilityObservation.semantic_facts`. An enum-only unsupported observation therefore fails conformance.

## Deterministic fixture evidence

`HarnessFixtureObservation` binds the exact harness identity to a content-addressed fixture and normalized observations.

The default policy requires at least two fixture replay digests. Matching digests establish deterministic fixture replay. One run remains `UNKNOWN`; divergent replay digests are `FAIL`.

Fixtures should inject representative success and failure behavior so trace obligations are actually exercised rather than inferred from schema presence. For unsupported capabilities, the fixture must preserve the observed limitation/rejection fact, not merely repeat the declaration's support enum.

## Trace completeness

The default policy requires capture of:

- model request/response events;
- tool request/result events;
- provider request identity;
- provider errors;
- retry attempts;
- timeouts;
- resets;
- artifact access;
- token usage;
- cost usage;
- time usage; and
- failure classification.

A missing required trace field is a conformance failure. This is deliberately stricter than merely exposing a trajectory object: a schema field that a producer never emits does not count as preserved behavior.

Harness-specific declarations may add further `expected_trace_fields`. These can only increase the observation obligation; they cannot weaken policy-required fields.

## Failure attribution boundary

HARNESS-001 does not redefine Veritas trajectory failure categories or environment semantics. Instead it requires the raw harness-side evidence needed for downstream attribution:

- provider errors remain visible;
- retries remain visible;
- timeouts remain visible;
- tool requests/results remain visible; and
- a failure-classification event must be emitted.

This allows diagnostics to separate harness/provider/tool effects from model/environment outcomes without the harness contract becoming a second trajectory authority.

## Fail-closed object boundaries

Pydantic `model_copy(update=...)` can bypass normal validators. For that reason evaluation and serialization reconstruct complete declarations, observations, policies, and reports from their dumped representation before trusting content-derived identity or derived status.

A copied object with stale identity/digest/status is rejected rather than treated as new evidence.

## Evidence boundary

Harness conformance is infrastructure/measurement evidence only. It does not establish:

- model capability;
- environment semantic correctness;
- verifier correctness;
- scientific qualification;
- Frontier qualification;
- training value;
- fidelity;
- commercial readiness; or
- release authority.