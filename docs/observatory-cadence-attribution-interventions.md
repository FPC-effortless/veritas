# Observatory Cadence, Capability Attribution, and Interventions

This layer extends the Continuous Agent Capability Observatory from one-off live runs into a repeatable experimental system.

It keeps four concepts separate:

```text
cadence                 = when a frozen observation should be repeated
longitudinal drift      = what changed across comparable time/model snapshots
capability attribution  = which declared capability dependencies are consistent with that drift
intervention effect     = how behavior changes when the environment is deliberately perturbed
```

## Cadence management

`CadencePolicy`, `CadenceCheckpoint`, `CadenceStore`, and `CadencedObservationRunner` provide deterministic, persisted due-state for recurring anchor observations.

The cadence layer deliberately does **not** run its own background thread. It is an idempotent scheduling boundary designed to be invoked by cron, GitHub Actions, a queue worker, Kubernetes, or another orchestration service.

A cadence stores stable policy identity, last start/completion/failure times, the last cycle ID, and consecutive failure count. The cadence identity fingerprints the frozen CompanyWorld bundle plus execution/provider configuration while excluding only time-varying snapshot fields and storage paths. A configuration or world change therefore starts a new cadence lineage instead of inheriting an unrelated checkpoint.

`run_companyworld_cadence()` creates a fresh UTC time snapshot only when the cadence is due. Calling it again before the interval expires does not create another cycle unless `force=True`.

## Capability graph diagnostics

A `CapabilityGraph` is a versioned directed acyclic graph of declared capability dependencies. Nodes may map to verifier-visible dimensions and edges declare prerequisite relationships.

The initial CompanyWorld investigation graph includes evidence selection, fact precision/recall/resolution, calibration, appropriate abstention, and investigation efficiency.

`attribute_drift()` returns directly observed dimension deltas, regressed declared prerequisites, propagated diagnostic scores, and candidate upstream roots.

This is **diagnostic attribution**, not causal attribution. A graph result says that an observed regression is structurally consistent with particular prerequisite regressions under the declared capability model. It does not prove that one capability caused another to fail.

Every CompanyWorld `ObservationCycleReport` can include these attribution artifacts automatically.

## Counterfactual intervention materialization

An `InterventionSpec` identifies one source scenario and one or more controlled mutations. CompanyWorld currently supports truth-preserving interventions for:

- record reordering;
- distractor injection;
- optional-field redaction with verifier-supporting records protected;
- budget tightening;
- scheduled tool failure;
- scheduled permission revoke/restore transitions.

`materialize_companyworld_intervention()`:

1. loads the privileged source episode;
2. extracts only its public payload for mutation;
3. protects private-verifier supporting records when truth preservation is requested;
4. validates system-specific mutations against the task's permitted systems;
5. applies deterministic mutations and records `MutationLineage`;
6. preserves the private oracle unchanged evaluator-side;
7. fingerprints the resulting bundle as a distinct world version.

Multiple permission transitions are preserved in order. Tool failures preserve one-shot versus persistent semantics.

## CompanyWorld runtime-v2 intervention semantics

`companyworld-runtime-v2` executes the previously declarative failure/permission schedules.

Intervention steps are zero-based attempted public tool-operation indices. Failed attempts advance the intervention operation index but do not consume CompanyWorld tool budget. This makes a one-shot failure recoverable by retry while still making the failure observable.

### Tool failure

A scheduled tool failure specifies:

```json
{
  "system": "ERP",
  "at_step": 3,
  "persistent": false
}
```

A one-shot failure affects the matching operation and can recover on a later retry. A persistent failure remains active from `at_step` onward.

### Permission changes

A permission transition specifies:

```json
{
  "system": "ERP",
  "at_step": 2,
  "action": "revoke"
}
```

A later `restore` transition can reinstate access. `search_system`, `open_record`, and cross-system `search_all` respect revoked systems. Outside a declared intervention, lookup semantics and CompanyWorld budget costs remain aligned with the baseline runtime.

### Failure-aware trajectories

`TracingRuntimeProxy` records failed public operations before re-raising them. A failed call therefore becomes a trace event such as `search_system_error` with argument, state, cost and exception metadata.

`behavior_from_trace()` recognizes a successful repetition of the same method after a failed event as a recovery. The Observatory can therefore distinguish:

```text
failure without recovery
failure -> retry -> successful recovery
persistent unavailability
permission loss -> alternate strategy
permission loss -> later restored access
```

The runtime version is intentionally bumped to `companyworld-runtime-v2`; old v1 runs must not be silently mixed with runs whose runtime semantics changed.

## Executable A/B intervention experiments

`run_companyworld_intervention()` executes baseline and treatment arms with the same model, harness, verifier, execution specification, time snapshot, scenario identity, task identity and seed. Only the world may differ.

The comparator refuses a result if one of those frozen dimensions changed. It also rejects a budget-tightening experiment when an explicit `world_cost_budget` override would mask the treatment.

Each `InterventionEffectReport` records treatment-minus-baseline deltas for reward, cost, trajectory steps and every common verifier capability dimension.

Intervention effects are explicitly distinct from longitudinal model drift.

## Repeated-seed paired intervention statistics

The correct sampling unit for a robustness intervention is the **paired effect** within a scenario seed:

```text
Delta_i = treatment_i - baseline_i
```

`InterventionEffectSample` stores one such pair. `aggregate_intervention_effects()` groups samples from the same intervention family and `ModelSpec`, then estimates the mean paired effect across unique scenario/seed pairs.

The aggregate includes:

- sample count;
- mean effect;
- sample standard deviation;
- standard error;
- approximate 95% confidence interval;
- min/max;
- per-capability paired-effect estimates;
- dimensions with positive/negative mean intervention effects.

An intervention family intentionally ignores scenario identity and RNG seeds while retaining mutation kinds, ordered mutation parameters, truth-preservation semantics and the family name. This allows the same perturbation design to be evaluated across many independently generated worlds.

`run_companyworld_intervention_suite()` executes and persists such a repeated-seed suite as an `ISUITE-*` artifact.

## Model x intervention interaction

`compare_model_intervention_effects()` compares two model-specific aggregate effects for the same intervention family.

For each metric:

```text
interaction = mean_effect_model_2 - mean_effect_model_1
```

This measures **differential sensitivity**. For example, two models can have similar baseline success while one degrades much more under source failure or permission loss.

The interaction report uses an independent-group normal approximation for its standard error and approximate 95% interval. It is not labeled causal model superiority and it is not longitudinal drift.

`compare_companyworld_intervention_suites()` persists these comparisons as model-interaction artifacts when a storage root is supplied.

## Persisted artifacts

```text
<store>/runs.jsonl                         raw CapabilityRun records
<store>/cycles/CYCLE-*.json               longitudinal observation cycles
<store>/cadence/cadence.json              recurring observation checkpoints
<store>/interventions/IREPORT-*.json       single paired intervention experiments
<store>/intervention_suites/ISUITE-*.json repeated-seed paired-effect aggregates
<store>/intervention_interactions/*.json  model x intervention comparisons
```

## Scientific separation

Veritas maintains three experimental axes:

```text
Temporal axis:
    same world + same harness/runtime + different model/time snapshot

Structural diagnostic axis:
    observed drift + declared capability graph

Intervention axis:
    same model/harness/verifier/execution/time/seed + deliberately changed world
```

The third axis can then be aggregated across seeds and compared across models without being conflated with temporal drift.

## Implemented boundary

Implemented in this stack:

- persisted cadence checkpoints and due-state;
- cadence identity tied to frozen experiment configuration;
- versioned acyclic capability graphs and automatic diagnostic attribution;
- truth-preserving deterministic CompanyWorld intervention materialization;
- verifier-support evidence protection;
- executable runtime tool-failure semantics;
- executable permission revoke/restore semantics;
- failed-operation tracing and recovery detection;
- baseline/treatment A/B integrity guards;
- paired-effect aggregation across scenario seeds;
- model x intervention interaction estimates;
- persistent single-intervention, suite and interaction artifacts;
- regression tests for cadence, graph diagnostics, intervention materialization, runtime semantics, tracing/recovery and statistics.

Future extensions can add factorial multi-intervention designs, richer state snapshot/restore counterfactuals, learned/validated capability graphs, non-normal/bootstrap uncertainty estimates at larger sample sizes, and a durable query/dashboard surface over Observatory artifacts.
