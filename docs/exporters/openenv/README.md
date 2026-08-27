# Generic OpenEnv operational export

This exporter maps a `PortableOperationalContract` onto OpenEnv without implementing a second operational runtime.

## Boundary

The exporter has three layers:

1. `compile_openenv_export(...)` consumes the portable contract and compiles its **public** contract through the existing MCP compiler.
2. OpenEnv actions are transport envelopes keyed by the MCP tool transport name. Each `arguments` member retains the exact compiled MCP `inputSchema`; unknown tools and schema-widened arguments are rejected before dispatch.
3. `PortableOpenEnvEnvironment.step(...)` calls the existing MCP dispatcher, which delegates to `PortableRuntimeProtocol`. The adapter does not reproduce action transitions, budget accounting, submission evaluation, or reward calculation.

OpenEnv remains optional at the Veritas package level. The exporter models and local environment wrapper are importable without OpenEnv installed; `create_app()` requires OpenEnv at deployment time.

## Identity

A compiled export exposes deterministic identifiers derived from public portable material:

- `public_contract_id`;
- task, world, and portable episode IDs;
- domain;
- deterministic `export_id`;
- deterministic OpenEnv environment name.

The optional OpenEnv `episode_id` reset parameter is transport metadata only and does not override portable task identity. Reset semantics are therefore keyed by the portable task plus the portable runtime seed.

## Action mapping

The MCP compiler is the public action/operation naming authority. The OpenEnv action schema is a `oneOf` over compiled MCP tool names. Each branch contains:

- the exact deterministic MCP transport tool name;
- the exact MCP/portable input schema under `arguments`;
- optional OpenEnv action `metadata`;
- `additionalProperties: false` on the transport envelope.

The exporter does not hardcode domain action names or built-in operation names. The MCP dispatch table maps each transport name back to the canonical portable action/operation and submission mode.

## Reset, step, observation, and reward

`reset(seed=...)` delegates directly to `PortableRuntimeProtocol.reset`. The initial OpenEnv observation contains the portable public observation and opaque state digest. It has no reward.

`step(...)` delegates through `dispatch_mcp_tool(...)`. The resulting OpenEnv observation copies:

- portable observation/result;
- portable reward without recomputation;
- `terminated`;
- `truncated`;
- opaque state digest;
- a sanitized public failure status when present.

OpenEnv's compatibility `done` value is `terminated or truncated`; the two original flags remain separately available. No rubric or adapter-side reward function is used.

## State and secrecy

`PortableOpenEnvState` contains only agent-visible/public information:

- portable task/world/episode/domain identity;
- public contract/export identity;
- OpenEnv step count;
- `runtime.public_state()`;
- opaque state digest;
- `terminated` and `truncated`.

It intentionally excludes evaluator-private state, `HiddenOracle`, target assertions, transition rules, private process rules, evaluator binding, reward components, and private budget state. Failure `details` are also excluded from the OpenEnv observation because portable failure details can contain evaluator-side resource information.

## Server use

```python
from investigation_world.exporters.openenv import compile_openenv_export

export = compile_openenv_export(portable_contract)
env = export.create_environment()
initial = env.reset(seed=0)

# When OpenEnv is installed:
app = export.create_app()
```

For OpenEnv HTTP/WebSocket serving, use `create_app()` so each OpenEnv session receives a fresh portable runtime instance. The exporter marks the environment concurrency-safe because runtime state is instance-local and the factory does not share mutable runtime state.

## Verification invariants

Tests in `tests/exporters/openenv/` falsify the adapter if any of these occur:

- private oracle material appears in OpenEnv State/observations;
- same task + seed resets differently;
- OpenEnv argument schemas widen the compiled MCP schemas;
- an OpenEnv step differs from direct portable-runtime execution through the same compiled MCP surface;
- terminal reward changes;
- truncation is collapsed into termination;
- export/environment identity changes for the same public contract.

This is implementation verification only. It does not imply scientific, frontier, or commercial qualification of any exported environment.
