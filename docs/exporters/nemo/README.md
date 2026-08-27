# Native NeMo Gym operational export

This exporter maps a Veritas `PortablePublicContract` plus a
`PortableRuntimeProtocol` implementation to NeMo Gym's native Gymnasium-style
Resources Server protocol. It is intentionally an adapter: all task transition,
budget, verification, and reward semantics remain in the portable runtime.

## Target protocol

The implementation targets the NeMo Gym `gymnasium_agent` / `GymnasiumServer`
contract current on 2026-08-27:

- Resources Server `POST /reset` calls `reset(metadata, session_id)` and returns
  `observation` plus `info`.
- Resources Server `POST /step` passes the complete structured model response to
  `step(action, metadata, session_id)` and returns `observation`, numeric `reward`,
  `terminated`, `truncated`, and `info`.
- Tool results are returned in `info.tool_outputs` using the model function-call
  `call_id`.
- NeMo's `gymnasium_agent` accumulates per-step numeric rewards and preserves
  `terminated` and `truncated` as distinct fields.

Reference implementation:

- https://github.com/NVIDIA-NeMo/Gym/blob/main/resources_servers/gymnasium/base.py
- https://github.com/NVIDIA-NeMo/Gym/blob/main/responses_api_agents/gymnasium_agent/app.py

No NeMo source is copied into Veritas and importing this exporter does not require
NeMo Gym to be installed.

## Semantic mapping

| Veritas portable semantic | Native NeMo representation |
| --- | --- |
| task/environment identity | deterministic `environment_id`, `public_contract_id`, and public task identity in top-level `veritas` row metadata and `info.veritas` |
| reset seed | top-level `veritas.seed`, passed unchanged to `runtime.reset(seed=...)` |
| reset observation | canonical JSON text in NeMo reset `observation` |
| action/runtime operation | one NeMo Responses API `function_call` mapped through the shared MCP compiler's collision-safe alias to the exact portable canonical operation |
| action input schema | exact portable input JSON Schema in the NeMo function tool `parameters` field |
| action output schema | exact portable output JSON Schema retained in public `veritas.tool_bindings` extension metadata; runtime output validation remains authoritative |
| tool observation | canonical JSON in `info.tool_outputs[].output` |
| portable scalar reward | copied exactly when present; absence of a portable reward maps to NeMo's numeric additive identity `0.0` |
| verifier components | `info.veritas.reward_components` when the portable runtime emits them |
| `terminated` | copied exactly from `PortableStepResult.terminated` |
| `truncated` | copied exactly from `PortableStepResult.truncated` |
| public state | `info.veritas.state`, sourced only from `runtime.public_state()` |
| state digest | `info.veritas.state_digest` |
| budget state | `info.veritas.budget_status` |
| structured portable failure | `info.veritas.failure` and the corresponding tool result payload |

NeMo's model-facing function tool declaration has an input-schema slot but no
output-schema slot. The exporter therefore retains the exact portable output schema
in public extension metadata instead of deleting or weakening it. The shared MCP
compiler is the fail-closed schema gate; schemas it cannot represent are rejected
before a NeMo surface is produced.

## One portable transition per NeMo step

The generated task row sets `parallel_tool_calls` to `false`. The Resources Server
also rejects a model response containing more than one function call before any
portable invocation executes. This avoids inventing ordering or atomicity semantics
that are absent from `PortableRuntimeProtocol`.

A response with no exported tool call is adapter-truncated. An unknown transport
alias or malformed argument payload never dispatches into the portable runtime.
Typed argument validation that reaches a known tool remains the portable runtime's
responsibility, preserving its structured failure and non-mutation behavior.

## Public/private boundary

`compile_nemo_surface`, `compile_nemo_task_row`, and `NeMoOperationalAdapter` accept
`PortablePublicContract`, not `PortableOperationalContract`. The exporter never
stores the evaluator-private projection. Runtime metadata is built only from:

- the portable public contract;
- `runtime.public_state()`;
- `runtime.state_digest()`;
- `runtime.budget_state()`;
- the public result fields returned by reset/step/submit.

Hidden oracle state, evaluator bindings, target assertions, private transition rules,
and evaluator-only metadata are therefore not eligible for NeMo observations or
extension metadata.

## Constructing a task row

```python
from investigation_world.exporters.nemo import compile_nemo_task_row

row = compile_nemo_task_row(contract.public, seed=17)
```

The returned mapping is suitable for a NeMo Gym JSONL input row. It contains
`responses_create_params` plus top-level `veritas` metadata. The default prompt uses
only public objective/role/constraints/success data. A caller may supply explicit
public `input_messages` instead.

## Binding to NeMo Gym

The exporter avoids a hard import dependency on NeMo Gym. In the NeMo Resources
Server application, bind the installed `GymnasiumServer` dynamically:

```python
from resources_servers.gymnasium import GymnasiumServer

from investigation_world.exporters.nemo import (
    NeMoOperationalAdapter,
    bind_gymnasium_server,
)
from investigation_world.portable_runtime import PortableOperationalRuntime


def adapter_factory():
    return NeMoOperationalAdapter(
        contract.public,
        lambda: PortableOperationalRuntime(contract),
    )


ResourcesServer = bind_gymnasium_server(GymnasiumServer, adapter_factory)

if __name__ == "__main__":
    ResourcesServer.run_webserver()
```

The full contract is captured only inside the runtime factory, where evaluator-private
configuration belongs. The NeMo adapter itself receives only `contract.public`.
Each successful reset constructs a fresh portable runtime and binds it to NeMo's
session ID, preventing state leakage between concurrent rollouts.

## Compatibility path through Prime Intellect

A separate compatibility route exists when the generic Prime export is the desired
packaging format:

```text
Veritas PortableOperationalContract / PortableRuntimeProtocol
    -> Veritas generic Prime exporter
    -> Prime Intellect `verifiers` environment/package
    -> NeMo Gym `verifiers_agent` or NeMo's Prime/PI conversion path
```

NeMo Gym already provides a `verifiers_agent` for Prime Intellect `verifiers`
environments. NeMo Platform also exposes Prime/PI conversion workflows. This native
exporter does **not** import, wrap, or duplicate the Prime implementation.

The semantic conformance rule for the two routes is that both execute the same
portable task identity and portable runtime semantics. Compatibility tests should
compare reset identity for the same seed, public state digests, scalar reward,
verifier components where surfaced, and the separate terminated/truncated outcome.
Packaging differences are not permission to redefine the task.

References:

- https://github.com/NVIDIA-NeMo/Gym/tree/main/responses_api_agents/verifiers_agent
- https://docs.nvidia.com/nemo/rl/latest/guides/nemo-gym.html

## Falsifier coverage

`tests/exporters/nemo/test_nemo_operational_export.py` checks that:

1. exact public action/operation schemas are retained rather than simplified;
2. same task and seed reset deterministically and sessions remain isolated;
3. native action/submit state digests, reward, verifier components, termination,
   and truncation match direct portable runtime execution;
4. budget exhaustion remains truncation rather than termination;
5. private oracle/evaluator values do not appear in task rows, reset results, or
   step metadata;
6. invalid typed input preserves portable structured failure and non-mutation;
7. multiple tool calls fail closed before any partial portable transition;
8. the dynamic NeMo Gym binding delegates session cleanup correctly.

No shared-contract interface gap is required by the current NeMo Gym reset/step
protocol.
