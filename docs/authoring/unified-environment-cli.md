# Unified environment CLI

`veritas env` is the stable developer-facing façade for operational environment compilation, validation, execution, export, conformance, and trajectory reverification.

It does **not** implement another runtime or adapter stack. Every command delegates to the existing `investigation_world.world_portability` command implementation, preserving one authority for portable execution semantics.

## Commands

```text
veritas env compile
veritas env inspect
veritas env validate
veritas env run
veritas env export
veritas env conformance
veritas env reverify
```

### Compile

```bash
veritas env compile \
  --episode operational_episode.json \
  --output portable_contract.json \
  --public-output public_contract.json
```

Compiles the canonical `OperationalEpisode` into the existing `PortableOperationalContract`.

### Inspect

```bash
veritas env inspect --contract portable_contract.json
```

The default inspection surface is buyer/agent safe. `--include-private-identities` is an explicit operator-side opt-in and still does not print evaluator-private state.

### Validate

```bash
veritas env validate --contract portable_contract.json
```

Delegates to the existing public/evaluator-private partition validation. Missing or invalid privacy boundaries remain failures rather than warnings.

### Run

```bash
veritas env run \
  --contract portable_contract.json \
  --vector canonical-vector.json
```

Runs the existing portable operational runtime. A seed may be supplied directly when no vector controls it.

### Export

```bash
veritas env export \
  --adapter openenv \
  --contract portable_contract.json \
  --output exported-environment
```

Supported adapters are the existing NeMo, OpenEnv, HUD, Prime, and Harbor adapters. The unified CLI forwards adapter-specific package metadata without changing adapter semantics.

### Conformance

```bash
veritas env conformance \
  --adapter harbor \
  --contract portable_contract.json \
  --vector canonical-vector.json
```

Runs the existing fail-closed semantic conformance harness. Semantic loss remains a non-zero exit.

### Reverify

```bash
veritas env reverify \
  --trajectory trajectory.jsonl \
  --contract portable_contract.json
```

Uses the existing deterministic trajectory replay/reverification path. Operator metadata and private identities require explicit flags.

## Compatibility

`veritas-portable` remains available as the lower-level compatibility entry point. `veritas env` is a façade over it, not a replacement implementation. This keeps existing scripts stable while giving developers one discoverable product CLI.

## Non-goals

This interface does not:

- create a second portable runtime;
- reinterpret verifier or reward semantics;
- duplicate exporter logic;
- weaken public/private partition checks;
- silently convert unsupported adapter semantics;
- expose evaluator-private state by default.

Environment scaffolding/authoring is owned by the fluent authoring API and can be surfaced under `veritas env` only after that API is integrated; this lane does not invent a competing scaffold format.
