# Woyengi WorldBundle integration

This integration consumes standalone Woyengi WorldBundle v0.1 artifacts without requiring a running Woyengi service. It supports two deliberately distinct projections:

- `adapt_pinned_world_bundle_fixture(...)` preserves the existing WorldBundle -> Veritas `OperationalEpisode` compatibility path.
- `compile_pinned_world_bundle_contract(...)` additionally consumes Woyengi's public language-neutral `ACTION_SCHEMA` members and produces the canonical Veritas `PortableOperationalContract` with exact typed public action schemas.

## Status and cross-repository pins

The action-schema consumer is pinned to the first merged Woyengi A1 action-schema contract and the merged Veritas A2 Portable Operational Contract integration point:

- Woyengi action-schema source commit: `b3d51e446dc376cea57ebe3c9eec1a84b37de811`
- Veritas Portable Operational Contract integration commit: `eac820395b69c2b2d3be593aa85760e61fb38b71`
- current Woyengi fixture artifact identity: `world-bundle-artifact:sha256:41e6c9b1b583112161d244de00d470a6fa5155f709c74782eb9117a060981462`
- current exact fixture-byte SHA-256: `62172d94b6e5d34774714b3c3da7c3fc61d71c61d7798f71d5a94a8243177a86`

Veritas copies those exact A1 bytes into `tests/integrations/woyengi/fixtures/veritas-adapter-v0.1.json` and verifies the byte hash before adaptation.

The previous pre-action-schema fixture is retained separately as `veritas-adapter-pre-action-schema-v0.1.json`, pinned to `3577aa29266dac59921c31e65d22ad657c4b7a9191011e9f5448aed32781e10b`. That old artifact remains intentionally valid for the `OperationalEpisode` compatibility adapter, but the typed portable-contract entrypoint rejects it because executable public actions do not have `ACTION_SCHEMA` bindings. Compatibility is therefore explicit rather than silently defaulted.

Passing this adapter/parity gate is **not** Veritas scientific qualification, frontier qualification, production readiness, or authority to make Woyengi semantic commits/effects. Those remain independent gates.

## Authority boundary

Woyengi remains authoritative for persistent operational semantics and the WorldBundle contract. Veritas owns evaluation execution, evaluator-private oracle projection, scientific qualification, frontier qualification, replay, and benchmark-specific measurement.

The adapter follows these rules:

1. No Woyengi database, runtime, API, or service is required.
2. The WorldBundle manifest and member contracts are the visibility/semantic authority.
3. Public task and action schemas are derived only from public Woyengi material.
4. Evaluator-private target assertions, invariants, action effects, locators, private member hashes, full artifact identity, and exact complete-fixture hash remain evaluator-side.
5. Neither `OperationalEpisode.public_payload()` nor `serialize_public_contract(...)` may contain those evaluator-private values.
6. Unsupported or non-lossless mappings fail closed; the adapter does not invent defaults or infer types from parameter names.
7. `HiddenOracle` is a Veritas evaluation projection, not a replacement for Woyengi's canonical operational state/authority model.
8. The Portable Operational Contract package remains read-only to this integration. If a future Woyengi schema cannot be represented by its public API, the correct response is an interface-gap handoff rather than a local contract fork.

## Action-schema contract

Woyengi A1 adds one public member for every executable public action:

```text
member.kind = ACTION_SCHEMA
member.partition = public
payload.contract = woyengi.world-bundle.action-schema.v0.1
payload.actionRef = world-action:...
payload.inputSchema = JSON Schema draft 2020-12 structural data
payload.outputSchema = JSON Schema draft 2020-12 structural data
```

The integration mirrors Woyengi's fail-closed v0.1 subset. It accepts scalar JSON Schema types plus objects and arrays using `properties`, explicit sorted `required`, `items`, and `additionalProperties: false` for objects. Unknown keywords, dialects, types, contract versions, malformed structures, unsafe property names, and evaluator-private schema material are rejected instead of reinterpreted.

Every public action must have exactly one schema binding. `actionRef` must exactly identify a declared Woyengi public action. For input schemas, `properties` must exactly equal the action's `parameterNames`; there is no parameter-name-to-type heuristic. The explicit `required` subset determines required versus optional inputs. `additionalProperties: false` is projected as `PortableActionDefinition.additional_parameters_allowed = False`.

`outputSchema` is copied exactly into `PortableActionDefinition.output_schema`. It represents the Woyengi-declared agent-observable action result shape. It is never enriched from private transition effects, target state, evaluator locators, or hidden oracle values.

The existing `OperationalEpisode` model does not carry these language-neutral schemas. It therefore remains the compatibility/runtime intermediate, while `compile_pinned_world_bundle_contract(...)` is the lossless typed export path for downstream portable-runtime compilers.

## Portable compilation discipline

The typed consumer does not bypass the canonical Veritas compiler. Compilation is intentionally two-stage:

1. Adapt the exact pinned WorldBundle into the existing `OperationalEpisode` projection using the established v0.1 adapter and secrecy checks.
2. Run `compile_operational_episode(...)` unchanged. Its own semantic-roundtrip validator must pass before this integration proceeds.
3. Validate all public Woyengi `ACTION_SCHEMA` members against the A1 profile.
4. Rebuild only `PortableActionDefinition` schema fields from those public bindings while preserving action identity, kind, system, description, parameter names, cost, charges, and interaction mode.
5. Rebind `PortablePublicContract.public_id` and the complete `PortableOperationalContract.contract_id` through the canonical model validators.
6. Independently verify that the evaluator-private contract is unchanged, all non-action public fields are unchanged, the action set/count is unchanged, and every projected input/output schema equals its Woyengi source exactly.

This ordering makes loss during Portable Operational Contract compilation observable. The adapter does not claim parity merely because a Pydantic model can be constructed.

The currently merged `PortableActionDefinition` can represent the A1 public schema profile through its `input_schema` and `output_schema` fields, so no Portable Operational Contract interface-gap change is required for this version.

## WorldBundle v0.1 semantic mapping

| Woyengi | Veritas projection | Treatment |
| --- | --- | --- |
| bundle `id` | `episode_id`, `world_id`, `task.task_id` | Stable identity preserved. |
| `sourceSpecRef`, `sourceSpecVersion`, compatibility, public provenance | episode/task metadata | Preserved as public traceability metadata. |
| `public.objective` | `task.objective` | Direct mapping. |
| `public.actorRoles` | `task.role` + ordered metadata | Veritas's single role string is a runtime projection; canonical role list remains metadata. |
| action `id` | `PublicActionSpec.name`, then `PortableActionDefinition.name` | Stable Woyengi action identity is the dispatch/portable identity so private `actionRef` bindings remain exact. |
| action `name` | `PublicActionSpec.description`, then portable description | Human-readable name preserved. |
| action `kind` | `ActionKind`, then portable `kind` | Explicit enum mapping; unknown kinds fail closed. |
| action `systemRef` | action `system` | Preserved directly; no synthetic `WOYENGI` system default on complete portable artifacts. |
| action `parameterNames` | action `parameter_names` | Preserved directly and checked against `inputSchema.properties`. |
| `ACTION_SCHEMA.inputSchema` | `PortableActionDefinition.input_schema` | Exact public schema; explicit `required` controls required/optional semantics; no type inference. |
| `ACTION_SCHEMA.outputSchema` | `PortableActionDefinition.output_schema` | Exact public agent-observable result shape; private effects are never consulted. |
| input `additionalProperties: false` | `additional_parameters_allowed = False` | Exact closed parameter surface. |
| public action cost | `PublicActionSpec.cost` + canonical action metadata | Only exact non-negative integer-compatible USD values are projected by v0.1; unsupported currency/number mappings fail closed. |
| public observation refs | public records/metadata | Agent-visible references preserved. |
| public `EVIDENCE_RECORD` | `OperationalRecord` | Materialized with exact evidence identity, system, record type, fields, searchable text, and provenance. |
| artifact descriptors | public `OperationalRecord` descriptors + metadata | Public descriptors preserved without resolving private bytes. |
| public constraints/success assertions | `TaskContract` projection + exact metadata | Human-facing fields are projections; exact structures remain metadata. |
| public budgets | `HiddenOracle.max_cost/max_tool_calls` enforcement projection + exact public metadata | Integer-compatible limits map conservatively; no invented limit. |
| target assertions | `HiddenOracle.target_state` | Structured path/operator/value mapping; unsupported paths/operators fail closed. |
| evaluator invariants | `HiddenOracle.invariants` | Assertion, description, severity and scope preserved. |
| hidden action transitions | `HiddenOracle.action_effects` | Action ref, parameters, state preconditions, prior actions, state mutation, observable/blocked results, side effects and consequence metadata preserved evaluator-side. |
| required public evidence | `HiddenOracle.required_evidence_ids` | Accepted only when an agent-visible record with the same identity is actually materialized. |
| private evidence locator refs/material | `WoyengiHiddenOracle` private fields | Evaluator-only. |

## Complete-artifact secrecy

The full artifact identity and exact fixture SHA-256 bind evaluator-private bytes. They therefore stay evaluator-side for portable artifacts and are deliberately excluded from public episode/portable metadata.

The older logical compatibility seam may expose its fixture hash in public metadata because its private evaluator payloads arrive separately and are not bound by that logical fixture hash. This compatibility exception must not be generalized to complete portable artifacts.

Action-schema validation uses private evaluator references only as a rejection set: a public schema that contains a private reference or private semantic key fails closed. Those references are never used to enrich, specialize, or infer public input/output schemas.

## Pinned fixture usage

OperationalEpisode compatibility path:

```python
from investigation_world.integrations.woyengi import adapt_pinned_world_bundle_fixture

PINNED_SHA256 = "62172d94b6e5d34774714b3c3da7c3fc61d71c61d7798f71d5a94a8243177a86"

episode = adapt_pinned_world_bundle_fixture(
    fixture_bytes,
    expected_sha256=PINNED_SHA256,
)
```

Typed Portable Operational Contract path:

```python
from investigation_world.integrations.woyengi import compile_pinned_world_bundle_contract

contract = compile_pinned_world_bundle_contract(
    fixture_bytes,
    expected_sha256=PINNED_SHA256,
)

request_approval = next(
    action
    for action in contract.public.actions
    if action.name == "world-action:request-approval"
)
assert request_approval.input_schema["required"] == ["requested_role", "supplier_id"]
```

Hash verification happens before UTF-8 decoding and JSON parsing. Complete portable artifacts already materialize their members, so a caller cannot inject a separate `member_payloads` sidecar into that path.

## Acceptance and falsifiers

The exact A1 pinned fixture is tested for:

- objective, actor/role, constraints, budget, evidence, target, invariant, hidden-effect and provenance parity from the existing adapter;
- exact `actionRef` correspondence into `PortableActionDefinition.name`;
- exact input `properties`, required/optional semantics, and declared types with no name-based type invention;
- exact output schema preservation;
- duplicate action-schema rejection;
- unknown action-ref rejection;
- missing schema rejection for any executable public action;
- action parameter/schema-surface mismatch rejection;
- malformed or unsupported JSON Schema rejection;
- hidden/evaluator-private schema material rejection;
- exact new fixture byte pin plus explicit old-pin compatibility behavior;
- deterministic portable compilation and deterministic operational replay;
- no evaluator-private identifier, locator, target truth, hidden effect, complete artifact identity, or exact complete-fixture hash in the public portable serialization;
- a post-compilation tamper falsifier proving that schema loss is detected rather than silently accepted;
- no live Woyengi/network dependency for adaptation or compilation.

`tests/integrations/woyengi/test_action_schema_adapter.py` owns the A1/A2 schema-consumer tests. `test_pinned_fixture.py` retains the exact cross-repository semantic fixture parity test, while `test_worldbundle_adapter.py` retains synthetic compatibility, replay, exact-hash and leakage falsifiers.

## Qualification boundary

A successful Woyengi adapter proves only that the pinned operational artifact can be consumed with the tested semantic/visibility parity. Whether the resulting environment is scientifically valid, calibrated, frontier-discriminating, or suitable for a particular training/evaluation claim remains owned by Veritas qualification systems.
