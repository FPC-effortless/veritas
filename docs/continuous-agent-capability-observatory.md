# Continuous Agent Capability Observatory

The Veritas Continuous Agent Capability Observatory turns existing executable worlds and rollout traces into longitudinal capability measurements.

## Core experimental unit

A `LongitudinalCell` is the reproducible product of:

```text
world × scenario/seed × model × harness × verifier × execution config × time snapshot
```

Each cell receives a deterministic `cell_id`. A second deterministic `longitudinal_key` deliberately excludes the model snapshot and time snapshot while preserving the world, scenario, model family/configuration, harness, verifier, and execution configuration. Runs sharing a longitudinal key are therefore eligible for like-for-like temporal comparison.

This separation is intended to prevent a common benchmark error: attributing a score change to model capability when the harness, environment, verifier, or budget changed at the same time.

## Scenario pools

The Observatory has three scenario-pool semantics:

- `anchor`: frozen scenarios repeatedly executed for high-sensitivity longitudinal comparison.
- `rotation`: refreshed scenarios from the same task distribution for generalization measurement.
- `sequestered`: hidden scenarios reserved for contamination-resistant evaluation.

The pool is independent of the existing train/IID/OOD/adversarial split so Veritas can separately represent distributional role and longitudinal exposure policy.

## Capability run

Existing `RolloutTrace` objects are converted into `CapabilityRun` objects. A run contains:

- complete cell identity;
- trace and runtime provenance;
- verifier-derived capability dimensions;
- total reward and cost;
- a behavioral fingerprint;
- start/finish timestamps;
- termination reason and metadata.

The first behavioral fingerprint implementation measures:

- total steps;
- event/tool distribution;
- state-change rate;
- verification activity;
- recovery activity;
- explicit failure signals;
- mean step cost.

This is intentionally trajectory-derived: two agents may obtain the same outcome while using materially different strategies.

## Drift analysis

`compare_runs(baseline, current)` requires both runs to share a `longitudinal_key`. It reports:

- per-capability absolute and relative deltas;
- detected regressions and improvements;
- reward delta;
- cost delta;
- step-count delta.

A model snapshot can therefore improve final reward while simultaneously becoming less efficient, or preserve reward while regressing on a verifier sub-capability.

## Persistence

`ObservatoryStore` provides the first append-only run store using JSONL. It is deliberately small and local so the schema can stabilize before adding DuckDB/SQL/object-storage backends. The API exposes lineage queries and latest-run lookup.

The persistence boundary is designed so the storage backend can change without changing the cell, run, or drift models.

## Relationship to the capability foundry

The Observatory does not replace the Veritas foundry. It instruments it:

```text
World / Task Distribution
        ↓
Materialized Runtime
        ↓
Agent + Harness
        ↓
RolloutTrace
        ↓
Independent Verifier
        ↓
CapabilityRun
        ↓
Longitudinal Drift / Behavioral Fingerprint
        ↓
Failure Mining / Challenge Generation / Training Products
```

The same verified trajectories can continue into challenge generation, expert/verified trajectory curation, preference data, SFT/RL training products, counterfactual replay, and future VOPSD workflows.

## First implementation boundary

Implemented now:

- `WorldRef`, `ScenarioRef`, `ModelSpec`, `HarnessSpec`, `VerifierSpec`, `ExecutionSpec`;
- deterministic `LongitudinalCell` and longitudinal lineage identity;
- anchor/rotation/sequestered scenario pools;
- `CapabilityRun` and provenance;
- verifier-derived capability profiles;
- trajectory-derived behavioral fingerprints;
- longitudinal drift reports;
- append-only run persistence;
- unit coverage for identity, alignment, drift, behavior, and storage.

Next implementation layers should add experiment-matrix materialization, repeated-seed aggregation with uncertainty, scheduler/provider adapters, richer investigation-specific capability dimensions, capability-graph attribution, counterfactual/intervention experiment records, and a query/report surface over accumulated runs.
