# Generic HUD operational export

The generic HUD exporter packages a `PortableOperationalContract` as a HUD protocol environment without introducing a HUD-specific world runtime.

## Architecture

The exported deployment has two trust surfaces:

1. `public/` contains only `PortablePublicContract`, the exact shared MCP-compiler surface, deterministic HUD/task identity, and compatibility metadata. It is safe to distribute with the evaluated task.
2. `operator/` is the HUD container build context. It contains the full evaluator-bearing portable contract, the pinned shared portable runtime/compiler source needed to execute it without a Veritas checkout, and the HUD control/MCP daemons. This directory is private evaluator infrastructure.

At runtime:

- `tasks.start` calls `PortableRuntimeProtocol.reset(seed=...)` and yields a prompt made only from the public contract plus the public reset observation.
- HUD publishes one `operational-tools` MCP capability. Tool names and input/output JSON schemas come from `compile_mcp_surface(contract.public)` unchanged. Calls go through `dispatch_mcp_tool`; no HUD transition logic exists.
- `tasks.grade` converts the HUD answer to `PortableSubmission` and calls `PortableRuntimeProtocol.verify`. The returned portable reward is the HUD score; HUD never recomputes reward.
- if the MCP terminal `submit` operation was invoked first, the adapter caches the portable terminal result and `tasks.grade` returns the same reward rather than evaluating twice.
- optional metering observes only public IDs, state digests, tool names and returned reward/termination flags. Metering exceptions are isolated and cannot alter runtime semantics.

The generated Dockerfile uses an immutable Python base-image digest. The operator package vendors the exact shared source modules required by the portable runtime's semantic source pins; it does not install from, mount, or reference a Veritas developer checkout.

## Identity and reset

Environment and task-template names are content-bound to `PortablePublicContract.public_id`. Public and operator package IDs are deterministic content IDs over their metadata and generated file fingerprints, so runtime/template changes change package identity. `tasks.start` is a direct reset of the portable runtime, so the same task and seed produce the same public observation, state digest and budget state as direct portable execution.

HUD capability tunnels do not carry the HUD control-session ID to the backend MCP service. The generated operator container therefore fails closed on a second concurrent task session. Deploy one operator container per rollout/task session, which is the sealed-evaluation deployment model assumed by this exporter.

## Private-data boundary

Never publish or mount `operator/contract.json` into an agent-visible workspace. The agent reaches the operator image only through HUD's control protocol and its tunneled MCP capability. The public bundle deliberately omits `contract_id`, private state, evaluator metadata, transition truth, private evidence and verifier inputs.

## Declared compatibility gaps

The exporter does not edit shared contract/runtime/MCP code to paper over host-protocol limitations.

### `HUD_MCP_PROTOCOL_VERSION_LAG`

HUD 0.6.15 registers its built-in MCP client as `mcp/2025-11-25`, while the shared Veritas MCP compiler declares `2026-07-28`. Advertising `mcp/2026-07-28` would make current `HudClient.open()` reject the capability because its client registry keys exact protocol strings. The operator therefore uses HUD's supported 2025 transport label but keeps the compiler protocol version and catalog intact in metadata.

### `HUD_MCP_LEGACY_STRUCTURED_OUTPUT_OBJECT_ONLY`

HUD's MCP 2025 stack models `structuredContent` as a JSON object. The Veritas portable runtime legitimately has non-object outputs (`search` and `search_all` return arrays). Wrapping those arrays in an object would change the compiled output schema, which is forbidden. The generated MCP server therefore lists the exact array schema and emits the canonical array observation as JSON text. Object-valued observations are also emitted as structured content.

This is a transport fidelity gap until HUD adopts the 2026 MCP result shape; it is not resolved by schema widening or output wrapping.

### `PORTABLE_MCP_SUBMIT_RESULT_ENVELOPE_GAP`

The shared compiler describes the MCP `submit` tool output as a full verifier-breakdown schema, while `dispatch_mcp_tool(...submit...)` returns `PortableStepResult`. That step result contains reward/components/termination but not every field required by the compiled verifier-breakdown schema. The HUD exporter will not invent those fields. `tasks.grade` is therefore the lossless grading path, and the exact shared submit tool remains visible/dispatchable with the limitation recorded in metadata.

## Build and deployment

```python
from pathlib import Path
from investigation_world.exporters.hud import build_hud_operational_export

result = build_hud_operational_export(contract, Path("dist/hud-task"))
```

The output directory must be empty; the exporter fails closed instead of leaving stale or undeclared files in a package. Build the private operator image from `dist/hud-task/operator` and expose its HUD control port `8765`. Do not expose the internal MCP port separately; HUD tunnels the `operational-tools` capability through the control connection.
