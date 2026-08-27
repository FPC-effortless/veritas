# Woyengi WorldBundle integration

This integration consumes a standalone Woyengi `woyengi.world-bundle-artifact.v0.1` and produces a Veritas `OperationalEpisode` without a running Woyengi service.

## Status

The cross-repository P0 fixture is now pinned and the adapter maps the representable v0.1 semantics explicitly rather than approximating them.

Final upstream pin from Woyengi issue #9:

- artifact identity: `world-bundle-artifact:sha256:62b94e85103ef8522ef9eb87f1a6825b2e98fca36fbd57b5aadce06e0f5ab719`
- exact fixture-byte SHA-256: `3577aa29266dac59921c31e65d22ad657c4b7a9191011e9f5448aed32781e10b`

Veritas tests copy those exact bytes into `tests/integrations/woyengi/fixtures/veritas-adapter-v0.1.json` and verify the byte hash before decoding or adaptation.

Passing this adapter/parity gate is **not** Veritas scientific qualification, frontier qualification, production readiness, or authority to make Woyengi semantic commits/effects. Those remain independent gates.

## Authority boundary

Woyengi remains authoritative for persistent operational semantics and the WorldBundle contract. Veritas owns evaluation execution, evaluator-private oracle projection, scientific qualification, frontier qualification, replay, and benchmark-specific measurement.

The adapter therefore follows these rules:

1. No Woyengi database, runtime, API, or service is required.
2. The WorldBundle manifest and member contracts are the visibility/semantic authority.
3. Public task semantics are derived only from public Woyengi material.
4. Evaluator-private target assertions, invariants, action effects, locators, private member hashes, full artifact identity, and exact complete-fixture hash remain evaluator-side.
5. `OperationalEpisode.public_payload()` must contain none of those private-bound values.
6. Unsupported or non-lossless mappings fail closed; the adapter does not invent defaults to satisfy Veritas types.
7. `HiddenOracle` is a Veritas evaluation projection, not a replacement for Woyengi's canonical operational state/authority model.

## Final v0.1 mapping

| Woyengi | Veritas projection | Treatment |
| --- | --- | --- |
| bundle `id` | `episode_id`, `world_id`, `task.task_id` | Stable identity preserved. |
| `sourceSpecRef`, `sourceSpecVersion`, compatibility, public provenance | episode/task metadata | Preserved as public traceability metadata. |
| `public.objective` | `task.objective` | Direct mapping. |
| `public.actorRoles` | `task.role` + ordered metadata | Veritas's single role string is a runtime projection; canonical role list remains metadata. |
| action `id` | `PublicActionSpec.name` | Stable Woyengi action identity is the Veritas dispatch identity so private `actionRef` bindings remain exact. |
| action `name` | `PublicActionSpec.description` | Human-readable name preserved. |
| action `kind` | `ActionKind` | Explicit enum mapping; unknown kinds fail closed. |
| action `systemRef` | `PublicActionSpec.system` | Preserved directly; no synthetic `WOYENGI` system default. |
| action `parameterNames` | `PublicActionSpec.parameter_names` | Preserved directly. |
| public action cost | `PublicActionSpec.cost` + canonical action metadata | Only exact non-negative integer-compatible USD values are projected by v0.1; unsupported currency/number mappings fail closed. |
| public observation refs | public records/metadata | Agent-visible references preserved. |
| public `EVIDENCE_RECORD` | `OperationalRecord` | Materialized with exact evidence identity, system, record type, fields, searchable text, and provenance. |
| artifact descriptors | public `OperationalRecord` descriptors + metadata | Public descriptors preserved without resolving private bytes. |
| public constraints/success assertions | `TaskContract` projection + exact metadata | Human-facing fields are projections; exact structures remain metadata. |
| public budgets | `HiddenOracle.max_cost/max_tool_calls` enforcement projection + exact public metadata | Integer-compatible limits map conservatively; no invented limit. |
| target assertions | `HiddenOracle.target_state` | Structured path/operator/value mapping; unsupported paths/operators fail closed. |
| evaluator invariants | `HiddenOracle.invariants` | Assertion, description, severity and scope preserved. |
| hidden action transitions | `HiddenOracle.action_effects` | Action ref, parameters, state preconditions, prior actions, state mutation, observable/blocked results, side effects and consequence metadata preserved. |
| required public evidence | `HiddenOracle.required_evidence_ids` | Accepted only when an agent-visible record with the same identity is actually materialized. |
| private evidence locator refs/material | `WoyengiHiddenOracle` private fields | Evaluator-only. |

## Complete-artifact secrecy

The full artifact identity and exact fixture SHA-256 bind evaluator-private bytes. They therefore stay on `WoyengiHiddenOracle` for portable artifacts and are deliberately excluded from public episode metadata.

The older logical compatibility seam may expose its fixture hash in public metadata because its private evaluator payloads arrive separately and are not bound by that logical fixture hash. This compatibility exception must not be generalized to complete portable artifacts.

The adapter verifies after projection that the exact portable fixture SHA-256 is absent from `public_payload()`. Existing leakage falsifiers also cover private evaluator identifiers, target values/effects, private evidence locators, and private member material.

## Pinned fixture usage

```python
from investigation_world.integrations.woyengi import adapt_pinned_world_bundle_fixture

PINNED_SHA256 = "3577aa29266dac59921c31e65d22ad657c4b7a9191011e9f5448aed32781e10b"

episode = adapt_pinned_world_bundle_fixture(
    fixture_bytes,
    expected_sha256=PINNED_SHA256,
)
```

Hash verification happens before UTF-8 decoding and JSON parsing. Portable artifacts already materialize their members, so a caller cannot inject a separate `member_payloads` sidecar into this path.

## Acceptance/falsifiers

Final issue #67 acceptance requires, on the exact pinned bytes:

- objective and actor/role parity;
- logical system, action kind, parameter and public-cost parity;
- constraints/budgets/success-assertion parity;
- public materialized evidence identity parity;
- target assertion and invariant assertion/severity/scope parity;
- executable hidden-effect parity;
- artifact descriptor and source provenance traceability;
- deterministic seeded replay;
- no evaluator-private artifact/member identity, locator, target truth, hidden effect, or exact complete-fixture hash in `public_payload()`;
- no live Woyengi/network dependency for adaptation.

`tests/integrations/woyengi/test_pinned_fixture.py` is the final cross-repository positive parity test. `test_worldbundle_adapter.py` retains synthetic compatibility, deterministic replay, exact-hash and leakage falsifiers.

## Qualification boundary

A successful Woyengi adapter proves only that the pinned operational artifact can be consumed with the tested semantic/visibility parity. Whether the resulting environment is scientifically valid, calibrated, frontier-discriminating, or suitable for a particular training/evaluation claim remains owned by Veritas qualification systems.