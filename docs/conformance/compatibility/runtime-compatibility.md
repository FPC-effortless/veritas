# Runtime compatibility matrix and drift detection

PORT-004 defines a machine-readable compatibility layer for Veritas runtime adapters. It is
deliberately separate from semantic conformance.

A compatibility result answers:

> Is this exact adapter, portable-contract schema, target runtime version, protocol version, and
> target-interface snapshot inside evidence that Veritas actually validated?

A conformance certificate answers a different question:

> Did the adapter preserve the certified environment semantics?

`TESTED_INTERFACE_MATCH` therefore does **not** mean semantic conformance PASS. A report can
legitimately contain `status=TESTED_INTERFACE_MATCH` and
`conformance_status=FAIL`.

## Fail-closed statuses

`RuntimeCompatibilityStatus` is machine-readable:

- `TESTED_INTERFACE_MATCH` — all declared compatibility bindings match.
- `NO_POLICY` — the matrix has no policy for the adapter/runtime pair.
- `UNVALIDATED` — a policy exists, but complete validation evidence is absent.
- `ADAPTER_MISMATCH` — adapter name, version, or content identity changed.
- `PORTABLE_CONTRACT_MISMATCH` — the portable-contract schema binding changed.
- `RUNTIME_MISMATCH` — the observed target runtime is not the declared runtime.
- `VERSION_OUT_OF_RANGE` — the runtime version is outside the exact/ranged tested versions.
- `PROTOCOL_MISMATCH` — the protocol version is outside the tested protocol set.
- `INTERFACE_DRIFT` — the observed interface snapshot digest differs from the validated digest.

Unknown or unrecorded target package versions are not promoted to supported versions. Use an
`UNVALIDATED` policy with an explicit `evidence_gaps` entry until a target probe and exact
interface snapshot have been retained.

## Evidence bound by a validated policy

A `VALIDATED` `RuntimeCompatibilityPolicy` requires all of the following:

- adapter name and version;
- adapter content SHA-256;
- portable-contract schema version;
- target runtime name;
- a tested exact version set and/or semantic-version interval;
- target-interface snapshot SHA-256;
- exact validating repository commit SHA;
- validation date.

Protocol versions may additionally be bound as exact opaque identifiers. Known unsupported
semantics, known semantic losses, and evidence gaps remain explicit and are never converted into
a scalar quality score.

The policy, observation, report, and matrix are content-addressed. External evaluation and
serialization reconstruct complete Pydantic objects from dumped data before trusting derived
fields. This prevents stale `model_copy(update=...)` objects from retaining an old identity or
compatibility result after a semantic mutation.

## CI drift gate

A CI fixture or target probe should produce an `ObservedRuntimeInterface` from the interface under
test and evaluate it against the checked-in policy. Call:

```python
report = evaluate_compatibility_matrix(matrix, observed)
require_tested_interface_match(report)
```

The gate raises on `UNVALIDATED`, version/protocol changes, interface drift, binding mismatch, or a
missing policy. Updating a tested version range or interface digest is therefore an explicit
evidence change, not an automatic consequence of a dependency upgrade.

The probe itself owns the definition of the target-interface snapshot. It should hash a stable
canonical description of the target API/protocol surface rather than an arbitrary display string.
Internal implementation changes that do not change the probed interface should not perturb the
snapshot.

## Current repository signals

The merged adapters already expose useful version/protocol signals, but they do not all preserve
enough external target evidence to justify a support PASS by themselves:

| Surface | Repository signal | Interpretation |
| --- | --- | --- |
| Portable contract | `CONTRACT_SCHEMA_VERSION = "1.0.0"` | Exact portable schema binding is available. |
| MCP compiler | `MCP_PROTOCOL_VERSION = "2026-07-28"` | Exact compiler protocol identifier is available. |
| HUD | `hud/1.0`, `hud==0.6.15`, `mcp/2025-11-25` | Explicit target SDK/protocol pins exist; an interface snapshot is still required for a validated policy. |
| Harbor | task schema `1.4`, export schema `veritas-harbor-export-v1` | Schema signals exist; target package/version evidence is not inferred from them. |
| OpenEnv | export schema `openenv-operational-v1` | OpenEnv is optional and its external package version is not pinned by core package metadata. |
| Prime | adapter `prime-verifiers-v1-operational`, export schema `1` | Adapter schema is known; target Prime runtime version is not inferred. |
| NeMo | adapter metadata `veritas-native-nemo-gymnasium-v1` | Adapter identity is known; target NeMo package/version evidence is not inferred. |

These signals are inputs to compatibility evidence, not substitutes for it. A source constant or
adapter name alone must not create `TESTED_INTERFACE_MATCH`.

## Matrix rules

`RuntimeCompatibilityMatrix` permits one policy per adapter/runtime pair and sorts policies
canonically. This makes the matrix deterministic and prevents two competing compatibility
authorities for the same adapter/runtime pair.

Consumers may serialize the matrix and reports as canonical JSON with
`serialize_compatibility_matrix()` and `serialize_compatibility_report()`. Package or catalog
surfaces can consume these records later without modifying exporter implementations.

## Evidence boundary

PORT-004 establishes runtime/interface compatibility accounting only. It does not create semantic
conformance, scientific qualification, Frontier qualification, training value, fidelity,
commercial readiness, or release authority. Missing evidence remains `NO_POLICY` or `UNVALIDATED`.
