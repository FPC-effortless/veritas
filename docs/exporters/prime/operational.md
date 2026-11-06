# Generic Prime Verifiers v1 operational export

## Scope

`investigation_world.exporters.prime` exports one or more merged
`PortableOperationalContract` values as a Prime Intellect Verifiers v1 taskset package.
It is intentionally generic: domain-specific labels, answer parsers, and SRE causal-classification
logic are not part of this adapter.

The pre-existing `investigation_world.portability.prime` SRE exporter is a compatibility path.
This lane does not import, modify, or replace it.

`replay_portable_requests_for_conformance(...)` retains the complete evaluator-side result sequence
for `AdapterConformanceReport` generation. The existing terminal `replay_portable_requests(...)`
helper is implemented over that trace and preserves its return behavior. Complete traces remain
operator-only and are not written into `public_tasks.json`, agent-visible Prime state, or MCP tool
responses.

## Prime v1 mapping

The generated package follows the current `verifiers.v1` decomposition:

| Portable concept | Prime v1 representation |
| --- | --- |
| public task definition | immutable `OperationalTaskData` row |
| durable task identity | `OperationalTask.key == "poc:<PortablePublicContract.public_id>"` |
| action/runtime operation | task-scoped MCP tool binding |
| rollout execution state | typed `OperationalState.requests` |
| runtime semantics | `PortableOperationalRuntime` |
| verifier/reward | one `@vf.reward` hook delegating to portable replay |
| task collection | `OperationalTaskset` |

`public_id` is content-derived by the portable contract, so Prime task identity is independent of
taskset row order and Prime's generated `idx` values. Exported rows are sorted by `public_id` before
indices are assigned.

## Action and operation surface

Every portable public action and runtime operation receives a deterministic Prime MCP tool name.
The row carries a lossless binding back to the original portable `kind`, `name`, `input_schema`, and
`output_schema`; the complete `PortablePublicContract` is also retained in the row.

Prime Verifiers v1 currently uses FastMCP 1.x, whose public `add_tool()` surface derives parameter
schemas from Python signatures rather than accepting arbitrary JSON Schema. The generated adapter
therefore registers a raw argument carrier, then replaces the registered MCP 1.x tool descriptor's
advertised input schema with the exact portable `input_schema`. Canonical validation is still
performed by `PortableOperationalRuntime`, not by the shim. This avoids translating or weakening
JSON-Schema semantics.

The generated distribution pins `mcp>=1.24,<2`, matching current Verifiers v1. If that MCP internal
descriptor is unavailable, the generated toolset fails during registration rather than exposing a
narrower schema.

## Runtime and reward parity

The tool server never implements transition rules. For each tool invocation it:

1. creates `PortableOperationalRuntime` from the evaluator-private contract;
2. resets it with the task seed;
3. replays the prior public invocation log;
4. sends the new action or operation through the portable runtime;
5. records the invocation for deterministic subsequent replay.

The Prime reward hook replays the same executed invocation log through
`PortableOperationalRuntime` and returns its `PortableStepResult.reward`. It does not recompute the
weighted components in Prime. Consequently the operational verifier remains the sole reward
authority.

A successful portable `submit` terminates according to portable runtime semantics. If no successful
submission produces a reward, the Prime reward hook returns `0.0`.

## Public/private separation

The generated package contains two distinct data files:

- `veritas_prime_operational/public_tasks.json` — Prime `TaskData` source. It contains only the
  public portable contract, prompt, deterministic bindings, and seed.
- `veritas_prime_operational/private_contracts.json` — evaluator-side full contracts used by the
  runtime and reward hook.

The full private contract is never copied into `TaskData`, the task prompt, tool bindings, or Prime
trace metadata. The task-scoped tool server returns only `PortableStepResult.observation` on
success, or a public failure code/message on failure. It does **not** return reward components,
evaluator-private budget state, hidden state, or state digests to the agent.

The generated wheel itself contains `private_contracts.json`; therefore it is an evaluator/operator
artifact when sealed truth matters. Do not make that wheel or file agent-accessible. Isolation of
the evaluator installation from an arbitrary code-execution harness remains a deployment
responsibility.

## Package independence

`build_prime_operational_package()` refuses a non-empty output directory so stale local files cannot
silently enter the generated package. All generated files are explicit and hashed in the returned
`PrimePackageBuildResult`.

The generated `pyproject.toml` declares Verifiers, MCP, Pydantic, and the Veritas runtime. The
default Veritas dependency is an immutable Git PEP 508 reference to commit
`7f7f2ec5d9618c6408f5d7aaca9329dc8f5ac5a5`, which contains the merged portable contract/runtime.
This lets installation resolve Veritas without a development checkout or undeclared local path.
Callers may provide an equivalent pinned registry requirement.

### Shared packaging gap

At implementation time there is no verified first-party `investigation-world` release on PyPI that
can replace the Git dependency. Solving that belongs to package/release metadata outside this
lane's ownership. The exporter therefore reports the dependency explicitly rather than modifying
root package metadata. A future first-party wheel/index can be adopted through the existing
`veritas_requirement` parameter without changing the portable/Prime semantic mapping.

## API

```python
from pathlib import Path

from investigation_world.exporters.prime import build_prime_operational_package

result = build_prime_operational_package(
    Path("dist/prime-operational"),
    contracts=[portable_contract],
)
print(result.package_id)
```

A custom dependency can be supplied without local paths:

```python
build_prime_operational_package(
    Path("dist/prime-operational"),
    contracts=[portable_contract],
    veritas_requirement="investigation-world==0.12.0",
)
```

## Fail-closed cases

Export raises `PrimeOperationalExportError` rather than guessing when:

- no contracts are supplied;
- a contract cannot be constructed by the merged `PortableOperationalRuntime`;
- two contracts have the same public identity in one export;
- a generated tool binding collides;
- the Veritas dependency is empty or points at a local/editable path.

A non-empty output directory raises `ValueError` before any generated file is written.
