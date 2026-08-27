# Portable Runtime Protocol

`investigation_world.portable_runtime` is the generic executable façade between Veritas's canonical `PortableOperationalContract` and C-wave runtime-specific adapters.

It does **not** implement operational transition or reward semantics. Domain actions are executed by the existing `OperationalRuntime`; final evaluation is performed by the existing operational verifier through `OperationalRuntime.submit()`.

## Boundary

```text
PortableOperationalContract
        |
        v
PortableOperationalRuntime
        |
        +-- action/retrieval --> OperationalRuntime
        |
        +-- submit/verify ----> native seven-component verifier
        |
        v
NeMo / OpenEnv / HUD / Prime / Harbor adapters
```

The package has no dependency on any external runtime SDK. Exporters should depend on the `PortableRuntimeProtocol` rather than importing vendor libraries into this layer.

## Public API

```python
from investigation_world.portable_runtime import (
    PortableOperationalRuntime,
    PortableRuntimeProtocol,
    PortableStepRequest,
    PortableStepResult,
    PortableSubmission,
)

runtime: PortableRuntimeProtocol = PortableOperationalRuntime(contract)
initial = runtime.reset(seed=7)
step = runtime.step("approve_order", {"order_id": "ORDER-001"})
score = runtime.submit(
    PortableSubmission(
        conclusion="Order approved.",
        evidence_ids=["record-001"],
        confidence=0.9,
    )
)
```

The stable protocol is:

- `reset(seed=...) -> PortableResetResult`
- `step(request, arguments=None) -> PortableStepResult`
- `verify(submission) -> PortableStepResult`
- `submit(submission) -> PortableStepResult`
- `public_state() -> dict`
- `state_digest() -> str`
- `budget_state() -> PortableBudgetStatus`

`verify()` is an alias of `submit()`; it does not introduce a second verifier implementation.

## Step requests

`step()` accepts either an action shorthand:

```python
runtime.step("approve_order", {"order_id": "ORDER-001"})
```

or a structured request:

```python
PortableStepRequest(
    kind="operation",
    name="search",
    arguments={"system": "ERP", "query": "pending order"},
)
```

The operation form exposes the portable contract's built-ins (`search`, `search_all`, `open_record`, and `submit`) through the same result envelope used by domain actions.

## Canonical result envelope

`PortableStepResult` contains:

- `observation`: only the system-observable result;
- `reward`: aggregate verifier reward when a submission is evaluated, otherwise `None`;
- `reward_components`: the seven native verifier components when evaluated, otherwise `None`;
- `terminated`: true only for normal terminal submission;
- `truncated`: true when the run ended because the execution budget could not admit the requested charged operation;
- `state_digest`: opaque deterministic digest of evaluator state for conformance/replay checking;
- `budget_status`: per-resource usage, remaining capacity, and exhaustion status;
- `failure`: structured failure status or `None`.

The reward component vector is exactly:

```text
outcome
state
constraints
side_effects
process
efficiency
evidence
```

The façade does not expose the native verifier's private diagnostic fields such as target counts, invariant IDs, forbidden actions, process violations, or missing private evidence locators.

## Deterministic reset and state digest

Every reset creates a fresh `OperationalRuntime` from the contract-derived episode template. Prior events, native closed state, state mutations, and budget counters are discarded.

The digest is deterministic for the same full contract, seed, and native evaluator state. It is an HMAC-SHA-256 value keyed by the evaluator-private full contract identity rather than a plain hash of hidden state. This gives adapters a stable equality/conformance token without publishing hidden state bytes or a direct low-entropy oracle hash.

The current native operational semantics are deterministic and do not consume the seed. The seed is nevertheless bound into the digest so downstream runtimes can preserve an explicit reset-seed identity without this façade inventing stochastic behavior.

## Public/private boundary

`public_state()` returns the canonical agent-visible operational payload derived from the public contract: task, public records, and public metadata. It never returns the native `state_snapshot()`, hidden transition effects, target assertions, evaluator metadata, private budget contract, verifier binding, or the complete `contract_id`.

`state_digest()` and `budget_state()` are harness/runtime-control outputs. They expose no evaluator values. A C-wave adapter may return them as protocol metadata, but must not reinterpret them as agent-visible hidden state.

The full `PortableOperationalContract` is constructor-only evaluator configuration. It is deliberately not exposed through `PortableRuntimeProtocol` or `PortableOperationalRuntime`; C-wave adapters must use the stable runtime operations and separately supplied public contract/schema material rather than reaching through the runtime for evaluator-private configuration.

## Action validation

The façade validates every action against `PortableActionDefinition.input_schema` before calling the native runtime. Invalid names or inputs fail without charging budget or mutating state.

For action schemas, root `properties` must correspond exactly to `parameter_names`, while the root JSON Schema `required` set controls which inputs are mandatory. This is important for language-neutral Woyengi action schemas: typed and optional arguments are enforced by the portable schema, while the native runtime's missing-parameter guard is projected only from that required set. Hidden transition matching, preconditions, effects, event construction, and state mutation remain exclusively in `OperationalRuntime.act()`.

Schemas using assertions this package cannot enforce losslessly fail closed during runtime construction rather than being silently ignored.

## Retrieval semantics

Retrieval calls are delegated to the existing native runtime and retain its metering and ordering behavior. One unusual native rule is preserved intentionally: `search()` checks system permission before the open-state check or budget charge. An unpermitted system therefore returns an empty list without charge, including after normal submission. The portable validator validates the remaining request shape without converting that explicit permission result into an enum-validation error.

`open_record()` preserves native charge-before-`KeyError` semantics; the façade converts the missing record into structured `resource_not_found` status after the native charge has occurred.

## Termination versus truncation

These states are deliberately distinct:

- **terminated**: `submit()` evaluated a non-truncated episode and native runtime closure occurred normally;
- **truncated**: a charged operation could not be admitted by a declared runtime budget.

Budget exhaustion is never reported as successful termination and never receives a reward at the point of exhaustion. The native budget rejection itself does not close `OperationalRuntime`. The façade allows a subsequent `submit()` solely to obtain the canonical verifier score for the truncated trajectory; that result remains `truncated=True, terminated=False` even though the underlying native runtime is then closed by evaluation.

Any further execution step after either protocol outcome is rejected structurally.

## Failure status

Failures are data, not vendor-specific exceptions. Stable codes include:

- `invalid_request`
- `invalid_action`
- `invalid_action_input`
- `invalid_operation`
- `invalid_operation_input`
- `action_rejected`
- `precondition_rejected`
- `budget_exhausted`
- `resource_not_found`
- `episode_terminated`
- `episode_truncated`
- `invalid_submission`
- `contract_schema_unsupported`
- `output_schema_violation`
- `internal_runtime_error`

Precondition rejection exposes only the native **observable** rejection payload. Hidden precondition identifiers such as evaluator state keys and required prior-action internals are not copied into the failure details.

## Fail-closed native binding

The runtime verifies the operational model, runtime, and verifier Git blob identities pinned by `PortableOperationalContract.provenance`/evaluator binding. It also verifies the expected native budget rules, charges, builtin operations, termination rules, verifier entrypoint, reward component names, weights, and six-decimal reward semantics.

If these native semantics drift, runtime construction fails instead of executing an old portable contract against a changed implementation.

## C-wave adapter rules

NeMo, OpenEnv, HUD, Prime, and Harbor exporters should:

1. consume `PortableRuntimeProtocol` and the public action/runtime schemas;
2. translate vendor reset/action/observation envelopes only;
3. preserve `terminated` and `truncated` separately where the target supports both, or encode the distinction explicitly when it does not;
4. use `reward` and `reward_components` verbatim rather than recomputing scores;
5. preserve structured failures instead of treating rejected actions as successful transitions;
6. never access native `OperationalRuntime.state_snapshot()`, traces, `HiddenOracle`, or the portable private contract to invent target-specific semantics.

This keeps Veritas/Woyengi semantics authoritative and makes C-wave adapters compilation layers rather than alternate environment implementations.
