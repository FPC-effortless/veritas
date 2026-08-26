# Continuous Agent Capability Observatory

The Veritas Continuous Agent Capability Observatory turns existing executable worlds and rollout traces into longitudinal capability measurements.

## Core experimental unit

A `LongitudinalCell` is the reproducible product of:

```text
world × scenario/seed × model × harness × verifier × execution config × time snapshot
```

Each cell receives a deterministic `cell_id`. A second deterministic `longitudinal_key` deliberately excludes the model snapshot and time snapshot while preserving the world, scenario, model family/configuration, harness, verifier, and execution configuration. Runs sharing a longitudinal key are therefore eligible for like-for-like temporal comparison.

This separation is intended to prevent a common benchmark error: attributing a score change to model capability when the harness, environment, verifier, taskset, or runtime changed at the same time.

## Scenario pools

The Observatory has three scenario-pool semantics:

- `anchor`: frozen scenarios repeatedly executed for high-sensitivity longitudinal comparison.
- `rotation`: refreshed scenarios from the same task distribution for generalization measurement.
- `sequestered`: hidden scenarios reserved for contamination-resistant evaluation.

The pool is independent of the existing train/IID/OOD/adversarial split so Veritas can separately represent distributional role and longitudinal exposure policy.

## Experiment matrices

`CellMatrixSpec` defines a Cartesian experiment over worlds, scenarios, models, harnesses, verifiers, execution configurations, and time snapshots. `materialize_cells()` deterministically expands the matrix into `LongitudinalCell` objects, while `experiment_from_matrix()` binds those cell identities into an immutable `ExperimentSpec`.

This makes longitudinal experiments explicit and reproducible rather than relying on handwritten loops or implicit benchmark configuration.

## Execution adapters

The execution layer deliberately separates three independently versioned concerns:

```text
RuntimeFactory → executable world instance
ModelProviderAdapter → model inference
HarnessAdapter → agent loop / tool-use semantics
```

`ExecutionRegistry` resolves those components from a cell's `WorldRef`, `ModelSpec`, and `HarnessSpec`. Exact world and harness versions are required: silently falling back across versions would make longitudinal comparisons scientifically ambiguous.

`CallableModelProvider`, `CallableHarnessAdapter`, and `CallableRuntimeFactory` are SDK-neutral integration points. They can wrap hosted provider SDKs, local inference, CLIs, custom agent harnesses, deterministic controls, or existing Veritas runtimes without adding provider-specific dependencies to the Observatory core.

Every cell gets a `ProviderSession`. It assigns deterministic request IDs and records provider-call count, token usage, reported cost, and latency. The session records usage metadata rather than provider credentials or raw secrets.

`ObservatoryExecutionEngine.execute_cell()` resolves the registered components, executes the harness, converts the resulting `RolloutTrace` into a `CapabilityRun`, attaches provider/harness execution metadata, and optionally persists the run.

## Local scheduler

`LocalObservatoryScheduler` turns an `ExperimentSpec` and its cells into deterministic execution jobs. It provides:

- bounded parallelism;
- per-cell retry limits;
- failure isolation so one failed cell does not abort the matrix;
- anchor/rotation/sequestered pool selection;
- completed-cell detection from `ObservatoryStore`;
- idempotent re-run skipping by default;
- serialized persistence when worker threads finish concurrently.

The scheduler does not pretend to enforce process-level hard timeouts. Time, token, tool-call, and cost limits remain part of `ExecutionSpec` and must be enforced by the harness/runtime/provider integration that owns those resources.

This is the local execution substrate. A later distributed scheduler can preserve the same `ExecutionJob`, adapter, and result contracts while moving work to remote workers.

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

## Repeated-seed aggregation

`aggregate_runs()` combines runs from one snapshot cohort while allowing scenario identity and seed to vary. The cohort freezes world version, model family/configuration, harness, verifier, execution budget, scenario pool/split, runtime version, and taskset version. This prevents infrastructure changes from being mislabeled as model drift.

For reward, cost, step count, and every available capability dimension, the aggregate records:

- sample count;
- mean;
- sample standard deviation;
- standard error;
- approximate 95% confidence interval;
- minimum and maximum.

`compare_aggregates()` then compares snapshot means within the same cohort, producing capability regressions, improvements, and efficiency deltas across repeated seeds.

## Drift analysis

`compare_runs(baseline, current)` requires both runs to share a `longitudinal_key` and rejects comparisons when runtime or taskset versions differ. It reports:

- per-capability absolute and relative deltas;
- detected regressions and improvements;
- reward delta;
- cost delta;
- step-count delta.

A model snapshot can therefore improve final reward while simultaneously becoming less efficient, or preserve reward while regressing on a verifier sub-capability.

## Persistence

`ObservatoryStore` provides the first append-only run store using JSONL. It is deliberately small and local so the schema can stabilize before adding DuckDB/SQL/object-storage backends. The API exposes run, cell, lineage, and latest-run lookup.

The persistence boundary is designed so the storage backend can change without changing the cell, run, scheduler, or drift models.

## Relationship to the capability foundry

The Observatory does not replace the Veritas foundry. It instruments it:

```text
World / Task Distribution
        ↓
Materialized Runtime
        ↓
Execution Registry
        ↓
Model Provider + Harness
        ↓
RolloutTrace
        ↓
Independent Verifier
        ↓
CapabilityRun
        ↓
Repeated-Seed Aggregate / Longitudinal Drift / Behavioral Fingerprint
        ↓
Failure Mining / Challenge Generation / Training Products
```

The same verified trajectories can continue into challenge generation, expert/verified trajectory curation, preference data, SFT/RL training products, counterfactual replay, and future VOPSD workflows.

## Current implementation boundary

Implemented now:

- `WorldRef`, `ScenarioRef`, `ModelSpec`, `HarnessSpec`, `VerifierSpec`, `ExecutionSpec`;
- deterministic `LongitudinalCell` and longitudinal lineage identity;
- anchor/rotation/sequestered scenario pools;
- `CellMatrixSpec`, deterministic matrix materialization, and `ExperimentSpec` construction;
- provider, harness, and runtime adapter protocols plus callable adapters and registries;
- per-cell provider sessions with deterministic request IDs and usage instrumentation;
- `ObservatoryExecutionEngine` for cell execution and trace-to-run conversion;
- deterministic execution jobs and a bounded local scheduler with retries, pool filtering, failure isolation, persistence, and completed-cell skipping;
- `CapabilityRun` and provenance;
- verifier-derived capability profiles;
- trajectory-derived behavioral fingerprints;
- single-run longitudinal drift reports;
- repeated-seed aggregation with mean, variance, standard error, and approximate 95% confidence intervals;
- aggregate longitudinal drift with frozen runtime/taskset comparability;
- append-only run persistence with run/cell/lineage lookup;
- unit coverage for identity, alignment, matrix generation, execution, scheduling, aggregation, drift, behavior, and storage.

Next implementation layers should add concrete hosted/local provider integrations, durable/distributed scheduling and cadence management, richer investigation-specific capability dimensions, capability-graph attribution, counterfactual/intervention experiment records, and a query/report surface over accumulated runs.
