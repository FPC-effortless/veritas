# Observatory Cadence, Capability Attribution, and Interventions

This layer extends the Continuous Agent Capability Observatory from one-off live runs into a repeatable experimental system.

It adds three separate concepts that must not be conflated:

```text
cadence        = when a frozen observation should be repeated
longitudinal drift = what changed across comparable time/model snapshots
capability attribution = which declared capability dependencies are consistent with that drift
intervention effect = how behavior changes when the environment is deliberately perturbed
```

## Cadence management

`CadencePolicy`, `CadenceCheckpoint`, `CadenceStore`, and `CadencedObservationRunner` provide deterministic, persisted due-state for recurring anchor observations.

The cadence layer deliberately does **not** run its own background thread. It is an idempotent scheduling boundary designed to be invoked by cron, GitHub Actions, a queue worker, Kubernetes, or another orchestration service.

A cadence stores:

- stable policy identity;
- last start time;
- last successful completion;
- last failure;
- last cycle ID;
- consecutive failure count.

`run_companyworld_cadence()` creates a fresh UTC time snapshot only when the cadence is due and then executes the normal CompanyWorld observation path. Calling it again before the interval expires does not create another cycle unless `force=True`.

This separation matters because scheduling infrastructure should not change Observatory experiment semantics.

## Capability graph diagnostics

A `CapabilityGraph` is a versioned directed acyclic graph of declared capability dependencies. Nodes may map to verifier-visible dimensions and edges declare prerequisite relationships.

The initial CompanyWorld investigation graph includes:

```text
Evidence Selection
   ├──> Fact Precision ──┐
   └──> Fact Recall ─────┴──> Fact Resolution ──> Calibration

Appropriate Abstention
Investigation Efficiency
```

`attribute_drift()` combines this declared graph with a run-level or aggregate drift report.

It returns:

- directly observed dimension deltas;
- regressed declared prerequisites;
- a diagnostic propagation score;
- candidate upstream roots.

This is intentionally described as **diagnostic attribution**, not causal attribution. A graph result says that an observed regression is structurally consistent with particular prerequisite regressions under the declared capability model. It does not prove that one capability caused another to fail.

Every `ObservationCycleReport` can now include these attribution artifacts automatically. CompanyWorld live observations use the versioned CompanyWorld investigation graph by default.

## Counterfactual intervention records

An `InterventionSpec` identifies one source scenario and one or more controlled mutations.

The first executable CompanyWorld intervention set is deliberately restricted to perturbations whose semantics can be implemented without silently changing evaluator truth:

- record reordering;
- distractor injection;
- optional-field redaction with verifier-supporting records protected;
- budget tightening.

Tool-failure and permission-change mutations are not accepted as truth-preserving Observatory interventions yet because the current CompanyWorld runtime does not execute those Foundry constraint annotations as real runtime failures/permission transitions. Recording a mutation that the runtime ignores would create a false experiment.

### Materialization

`materialize_companyworld_intervention()`:

1. loads the privileged source episode;
2. extracts only its public payload for mutation;
3. protects records used by private verifier facts when truth preservation is requested;
4. applies deterministic Foundry mutations;
5. reattaches the unchanged private oracle evaluator-side;
6. fingerprints the resulting bundle as a new world version;
7. records every `MutationLineage`.

The resulting world is therefore distinguishable from the baseline world at the cell identity level.

## Executable A/B experiments

`run_companyworld_intervention()` executes two arms with the same:

- model specification;
- model snapshot;
- harness and harness version;
- verifier;
- execution configuration;
- source scenario;
- time snapshot.

Only the world differs:

```text
                   ┌─ baseline frozen world ───────> CapabilityRun
same agent stack ──┤
                   └─ intervention world ──────────> CapabilityRun
                                      ↓
                              InterventionEffectReport
```

The report records deltas for:

- reward;
- cost;
- trajectory steps;
- every common verifier capability dimension;
- degraded dimensions;
- improved dimensions.

Intervention reports are stored under:

```text
<observatory store>/interventions/IREPORT-*.json
```

The report explicitly states that intervention effects are not longitudinal model drift.

## Why the three measurements stay separate

A model can regress across time without being particularly sensitive to an intervention. It can also remain stable across time while being highly brittle under distractors or tighter budgets.

Veritas should therefore maintain three distinct axes:

```text
Temporal axis:
    same world + same harness + different model/time snapshot

Structural diagnostic axis:
    observed drift + declared capability graph

Intervention axis:
    same model/harness/time + deliberately changed world
```

Together these enable a more useful capability observatory than a scalar leaderboard.

## Current boundary

Implemented:

- persisted cadence checkpoints and due-state;
- cadence-gated CompanyWorld observation execution;
- versioned acyclic capability graphs;
- diagnostic graph attribution on run/aggregate drift;
- automatic CompanyWorld attribution in cycle reports;
- truth-preserving CompanyWorld intervention materialization;
- protected verifier-support evidence during optional redaction;
- separate intervention world fingerprints;
- executable baseline/intervention A/B runs;
- persisted intervention effect reports;
- regression tests for cadence, attribution, intervention integrity, and A/B execution.

Next layers should add:

- real runtime-level tool failure and permission-transition interventions;
- multi-intervention factorial experiments;
- statistical intervention aggregation across seeds;
- intervention × model interaction comparisons;
- capability graph learning/validation from accumulated experimental evidence rather than only declared structure;
- a durable query/report surface over cadence, drift, attribution, and intervention artifacts.
