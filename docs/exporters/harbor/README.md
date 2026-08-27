# Harbor operational export

This exporter materializes a `PortableOperationalContract` as a Harbor task package for sealed operational evaluation. It is intentionally an adapter/orchestration layer: action semantics, reset semantics, termination, truncation, and reward remain owned by the shared portable runtime and MCP compiler.

## Architecture

The generated Harbor package uses three trust zones:

```text
Harbor agent
    |
    | agent-mcp internal network
    v
MCP sidecar
    |
    | runtime-control internal network
    v
Portable runtime-control sidecar
    |
    | append-only trajectory collected by Harbor
    v
Separate Harbor verifier (started after environment collection)
```

The `main` Harbor service is attached only to `agent-mcp`. The MCP service bridges `agent-mcp` and `runtime-control`. The runtime-control service is attached only to `runtime-control`, has no host-published port, and exposes only health plus shared MCP-dispatch execution. It exposes no verification endpoint.

Each Compose service also has a disjoint Docker build context. In particular, `main` builds from `environment/main/`, so the agent image build context does not include `environment/runtime-control/contract.json` or any other operational-private file.

The separate verifier is a Harbor `environment_mode = "separate"` verifier with a `no-network` baseline. Harbor collects `/tmp/veritas-runtime/trajectory.jsonl` directly from the runtime-control sidecar and rematerializes it at the same path in the verifier container.

## Public/private split

Agent-public generated files contain only the `PortablePublicContract`, instructions, immutable image references, and the MCP/network topology. The full `PortableOperationalContract` is emitted only into:

- `environment/runtime-control/contract.json`, whose derived image and build context are isolated from the agent network and agent image;
- `tests/contract.json`, whose derived image is used only by Harbor's separate verifier.

The MCP sidecar recompiles its tool catalog from `PortablePublicContract` using `compile_mcp_surface`. The runtime-control service also compiles the same surface and executes calls exclusively through `dispatch_mcp_tool` over `PortableOperationalRuntime`. The MCP wire response returns only the portable observation; reward, reward components, state digests, and verifier metadata are not forwarded to the evaluated agent.

The current shared portable runtime requires the complete operational contract to reconstruct operational hidden state. Therefore the runtime-control sidecar necessarily receives the full contract. This is isolated evaluator infrastructure, not the Harbor `main` container or MCP container. If the portable runtime later supports a smaller execution-only private projection, this exporter should narrow the runtime-control input accordingly rather than duplicating that semantic split here.

## Determinism and provenance

`HarborExportConfig` rejects mutable image tags. `agent_image`, `runtime_image`, and `verifier_image` must be `@sha256:` references. Generated text is canonical and timestamp-free, output file order is stable, and `HarborExportResult.package_id` is derived from contract identities plus file hashes and modes rather than output location.

`provenance.json` records:

- full and public portable contract identities;
- portable reset identity;
- MCP catalog/surface identities;
- source commit and portable compiler identity/version;
- immutable agent/runtime/verifier image references;
- reset seed;
- declared service/network boundaries.

The exporter refuses to write into a non-empty output directory. This prevents stale files from previous exports from silently entering a supposedly deterministic task package.

## Runtime image requirement

The exporter does not copy or mount a Veritas developer checkout. Instead, callers provide immutable runtime/verifier image digests. Those images must contain the installed `investigation_world` distribution corresponding to the contract's pinned operational model/runtime/verifier sources and this Harbor exporter implementation. `PortableOperationalRuntime` validates the native operational source pins from the contract and fails closed if they do not match.

The runtime images must be release/runtime images only: do not bake benchmark datasets, evaluator secrets, credentials, or unrelated sealed artifacts into them. Image construction is deliberately outside this exporter namespace.

## Verification and reward authority

Runtime-control records the deterministic reset and every successful shared-dispatch MCP tool call with the exact `PortableStepResult`. The separate verifier:

1. validates contract, public-contract, and MCP-surface identities;
2. recreates `PortableOperationalRuntime` with the recorded seed;
3. requires the reset result to reproduce exactly;
4. replays every tool through `dispatch_mcp_tool` and requires each recorded result to match exactly;
5. uses the terminal native reward if the agent submitted, otherwise calls `PortableOperationalRuntime.verify()` after replay;
6. writes that native reward to `/logs/verifier/reward.txt` and component details to `/logs/verifier/veritas-verifier.json`.

No reward formula is implemented in the Harbor exporter.

## Generated package layout

```text
<task>/
  instruction.md
  task.toml
  provenance.json
  environment/
    docker-compose.yaml
    main/
      Dockerfile
    mcp-server/
      Dockerfile
      public-contract.json
    runtime-control/
      Dockerfile
      contract.json              # operational-private
  tests/
    Dockerfile
    contract.json                # evaluator-private
    test.sh
```

`environment/docker-compose.yaml` is the Harbor compose definition and the primary service is named `main`. Its build context is `./main`; the MCP and runtime-control services use `./mcp-server` and `./runtime-control` respectively. `task.toml` declares the MCP sidecar as a `streamable-http` server at `http://mcp-server:8000/mcp`.

## Usage

```python
from pathlib import Path

from investigation_world.exporters.harbor import HarborExportConfig, export_harbor_package

result = export_harbor_package(
    contract,
    Path("out/veritas-task"),
    HarborExportConfig(
        task_name="my-org/task-001",
        agent_image="registry.example/agent@sha256:<64-hex-digest>",
        runtime_image="registry.example/veritas-runtime@sha256:<64-hex-digest>",
        verifier_image="registry.example/veritas-runtime@sha256:<64-hex-digest>",
        seed=0,
    ),
)
print(result.package_id)
```

Run the resulting task with a Harbor environment provider that supports Docker Compose and MCP sidecars. Harbor's local Docker environment is the compatibility baseline; current cloud providers generally do not support multi-container Compose tasks. Do not replace the digest-pinned image references with mutable tags for sealed evaluations.

## Falsifiers covered by tests

The owned tests fail if:

- evaluator-private markers enter agent-public package files;
- the agent image build context expands to include the private runtime-control subtree;
- mutable container image tags are accepted;
- `main` joins the runtime-control network or runtime-control publishes a host port;
- Harbor does not use a separate verifier;
- the generated MCP surface identity differs from the shared compiler;
- MCP dispatch results differ from direct portable-runtime results;
- deterministic reset/replay evidence does not reproduce;
- Harbor reward differs from native portable-runtime verification;
- an existing non-empty output directory can contribute undeclared stale files.
