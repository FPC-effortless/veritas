# World portability tooling

`tools/world_portability.py` is an additive standalone CLI for compiling, inspecting, executing, exporting, and checking Veritas operational worlds without registering anything in the root `veritas` CLI.

Run it from a Veritas checkout with the project environment available:

```bash
python tools/world_portability.py --help
```

The tooling fails closed. Unsupported portable semantics, malformed vectors, unavailable adapter trace surfaces, output collisions, and identity mismatches return a non-zero exit code and an `error[CODE]` message on stderr.

## Privacy default

The CLI accepts evaluator-bearing `PortableOperationalContract` files, but default terminal output is public-safe. It does **not** print:

- `private.semantic_state.initial_state`;
- private transition/precondition data;
- oracle metadata;
- private budget contracts or live budget status;
- verifier reward components;
- private reset/evaluator identities;
- Harbor full `contract_id` from trajectory headers.

Explicit operator-only switches exist for identity or runtime metadata where useful:

- `--include-private-identities`
- `--include-operator-metadata`

Those switches are intended for trusted operator terminals and logs only.

A full evaluator-bearing contract is written by `compile --output` because that is the command's requested artifact. Use `--public-output` to additionally emit the canonical `PortablePublicContract` serialization.

## Compile an operational episode

Input is a JSON serialization accepted by `OperationalEpisode`.

```bash
python tools/world_portability.py compile \
  --episode episode.json \
  --output portable-contract.json \
  --public-output portable-public.json
```

Compilation delegates to `compile_operational_episode`. Unsupported operational semantics are not simplified or widened; compilation fails with `COMPILE_UNSUPPORTED_SEMANTICS`.

The stdout summary contains only the public contract identity and public task/runtime metadata.

## Inspect a contract

```bash
python tools/world_portability.py inspect --contract portable-contract.json
```

Default inspection reports:

- schema/public contract identity;
- task/world/episode identity;
- objective, role, constraints, permitted systems and success description;
- public actions and runtime operations;
- deterministic-reset and terminal-operation declarations;
- structural public/private partition status.

To inspect only operator identities, without printing oracle state or transition truth:

```bash
python tools/world_portability.py inspect \
  --contract portable-contract.json \
  --include-private-identities
```

This adds `contract_id`, `reset_identity`, evaluator semantics identity and evaluator entrypoint.

## Validate the public/private partition

```bash
python tools/world_portability.py validate-partition \
  --contract portable-contract.json
```

The check validates the typed contract, visibility declarations, hidden-state public flags, canonical public serialization, and public-only MCP compilation. It fails if a `private` section appears in the serialized public contract or if evaluator-private components advertise the wrong visibility.

This is a structural partition check. It does not attempt unsafe heuristic secret scanning based on arbitrary scalar equality between public and private sections.

## Reset or run the generic portable runtime

Reset only:

```bash
python tools/world_portability.py run --contract portable-contract.json
```

Run a deterministic vector:

```bash
python tools/world_portability.py run \
  --contract portable-contract.json \
  --vector vector.json
```

Vector shape:

```json
{
  "seed": 17,
  "actions": [
    {
      "kind": "operation",
      "name": "search",
      "arguments": {"system": "ERP", "query": "pending"}
    },
    {
      "kind": "action",
      "name": "approve_order",
      "arguments": {"order_id": "ORDER-001"}
    },
    {
      "kind": "operation",
      "name": "submit",
      "arguments": {
        "conclusion": "approved",
        "claimed_state": {"order.status": "approved"},
        "evidence_ids": ["record-001"],
        "confidence": 1.0
      }
    }
  ]
}
```

Default runtime output includes public observations, aggregate reward when produced, termination/truncation, public failure status, state digests, and final public state. It omits budget status and verifier reward components.

Trusted operators can add:

```bash
--include-operator-metadata
```

That exposes budget status, reward components and private execution identities.

## Export to a runtime adapter

Supported adapter names are:

- `nemo`
- `openenv`
- `hud`
- `prime`
- `harbor`

### NeMo

```bash
python tools/world_portability.py export \
  --adapter nemo \
  --contract portable-contract.json \
  --output out/nemo
```

This emits a public NeMo task row and public adapter metadata using `compile_nemo_task_row` and `compile_nemo_surface`.

### OpenEnv

```bash
python tools/world_portability.py export \
  --adapter openenv \
  --contract portable-contract.json \
  --output out/openenv
```

This emits the public compiled OpenEnv identity and shared MCP tool surface from `compile_openenv_export`.

### HUD

```bash
python tools/world_portability.py export \
  --adapter hud \
  --contract portable-contract.json \
  --output out/hud
```

This delegates package generation to `build_hud_operational_export`. The generated export contains a public subtree plus an evaluator/operator subtree; stdout prints only public/package identity information.

### Prime

```bash
python tools/world_portability.py export \
  --adapter prime \
  --contract portable-contract.json \
  --output out/prime
```

This delegates to `build_prime_operational_package`. `--veritas-requirement` can override the exporter's pinned default requirement. Local checkout/file dependencies remain rejected by the exporter.

### Harbor

Harbor additionally requires immutable image digests and a Harbor task name:

```bash
python tools/world_portability.py export \
  --adapter harbor \
  --contract portable-contract.json \
  --output out/harbor \
  --task-name my-org/task-001 \
  --agent-image registry.example/agent@sha256:<64-hex> \
  --runtime-image registry.example/veritas-runtime@sha256:<64-hex> \
  --verifier-image registry.example/veritas-runtime@sha256:<64-hex>
```

The command delegates to `HarborExportConfig` and `export_harbor_package`, preserving their fail-closed immutable-image and sealed-package rules.

## Adapter conformance

Conformance uses the merged `investigation_world.conformance` harness. A supplied vector is executed once through the canonical `PortableOperationalRuntime` baseline and once through the selected adapter path. Any non-empty `semantic_losses` fails the command.

```bash
python tools/world_portability.py conformance \
  --adapter harbor \
  --contract portable-contract.json \
  --vector vector.json
```

Stable public trace surfaces currently permit full operator-side conformance execution for:

- NeMo;
- HUD;
- Harbor;
- OpenEnv; and
- Prime Verifiers v1.

OpenEnv and Prime use explicit evaluator/operator-side replay extensions. OpenEnv evidence pairs the
actual public reset/step envelopes with private budget and verifier fields from the same server-side
runtime results. Prime evidence retains every result produced by its evaluator replay path rather
than only the terminal reward result. Neither extension adds private fields to agent-facing state,
observations, task rows, MCP tool returns, or generated public task data.

Conformance stdout includes the durable report fields:

- `mapped_fields`
- `preserved_fields`
- `generated_fields`
- `excluded_private_fields`
- `unsupported_fields`
- `semantic_losses`
- `test_vector_hash`

plus the adapter, public contract ID and derived pass/fail status. Private semantic values are never serialized into the report.

## Harbor trajectory and reverification identity inspection

Inspect a trajectory without a contract:

```bash
python tools/world_portability.py trajectory \
  --trajectory trajectory.jsonl
```

The default output reports only public contract/surface identity, seed and event counts. It does not print tool arguments, step results, budget state, reward components, or the private full contract ID.

Validate the trajectory against a contract:

```bash
python tools/world_portability.py trajectory \
  --trajectory trajectory.jsonl \
  --contract portable-contract.json
```

Reverify the recorded trajectory through Harbor's public replay verifier:

```bash
python tools/world_portability.py trajectory \
  --trajectory trajectory.jsonl \
  --contract portable-contract.json \
  --reverify
```

Default reverification output reports only success and replay count. A trusted operator may add `--include-operator-metadata` to print reward/component details, and `--include-private-identities` to print the trajectory's full `contract_id`.

## Root CLI integration

The installed `veritas-portable` entry point and `tools/world_portability.py` compatibility launcher
execute the same implementation.
