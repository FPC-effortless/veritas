# Selective Agency in the Continuous Agent Capability Observatory

Selective Agency is designed to be measured longitudinally, not only as a one-time leaderboard. The Observatory bridge converts Selective Agency task distributions, verifier scores, and executable traces into the same `LongitudinalCell` and `CapabilityRun` substrate used by the rest of Veritas.

## Cell identity

For Selective Agency, one longitudinal observation is:

```text
selective-agency world version
× frozen scenario / task seed
× model family + snapshot
× harness version
× selective-agency verifier
× execution budget
× time snapshot
```

The scenario identity includes the exact task ID and generation seed. The longitudinal key freezes the scenario, harness, verifier, execution configuration, taskset version, and runtime version while excluding model snapshot and observation time. This makes model changes comparable without silently mixing benchmark changes into capability drift.

## Exposure policy

Selective Agency keeps distribution role and longitudinal exposure policy separate:

| Distribution split | Observatory pool | Intended use |
|---|---|---|
| train | rotation | development and training feedback |
| IID test | anchor | repeated like-for-like capability canary |
| OOD | sequestered | hidden transfer measurement |
| adversarial | sequestered | hidden pressure and shortcut-resistance measurement |

The IID anchor pool is the closest analogue to a longitudinal benchmark canary. The same hidden state-dependent cases can be rerun against successive model snapshots while keeping the harness and verifier frozen.

## Capability dimensions

`selective_agency_capability_dimensions()` converts a `SelectiveAgencyScore` into Observatory dimensions. Every dimension is oriented so **larger means better**, which is required for generic drift detection:

- `selective_agency` — overall selective-agency score;
- `judgment` — correct execute/answer/clarify/correct/reframe/decline/no-op decision;
- `outcome` — verifier-confirmed result;
- `epistemic_calibration`;
- `clarification`;
- `resource_proportionality`;
- `action_safety = 1 - consequence_severity`;
- `waste_avoidance = 1 - waste_penalty`;
- `unnecessary_action_avoidance`;
- `forbidden_action_avoidance`;
- `harmful_action_avoidance`.

This orientation matters. Raw consequence severity or harmful-action rate cannot be inserted directly into the generic Observatory capability profile because an increase would otherwise look like an improvement.

## Trace conversion

`selective_agency_trace()` converts one evaluated attempt into a normal Veritas `RolloutTrace`.

The trace includes:

- the initial task-state hash;
- the selected decision;
- individual runtime tool/action events where available;
- synthetic tool-call events when a harness reports calls without executable runtime records;
- state hashes before and after each executable action;
- per-step cost;
- a final independent-verification event;
- the Selective Agency verifier dimensions;
- total reward and cost;
- private evaluator metadata such as scenario family and state-flip variant.

These traces are evaluator-side artifacts. They are not part of the agent-visible task payload.

## Behavioral drift

Because the result is a standard `RolloutTrace`, the existing Observatory behavioral fingerprint can detect changes that a task score alone misses:

- more or fewer tool calls;
- increased state-changing behavior;
- higher cost;
- more failure signals;
- different tool mix;
- changes in verification or recovery activity.

Two model snapshots can therefore achieve the same final Selective Agency score while still displaying materially different operational behavior.

## Longitudinal regression example

A frozen anchor case may require an authorized restart because the target is unhealthy.

```text
Snapshot A
  judgment: execute
  outcome: repaired
  selective_agency: 1.00

Snapshot B
  judgment: no-op
  outcome: unresolved
  selective_agency: lower
```

If the world, scenario, seed, harness, verifier, execution configuration, runtime, and taskset remain unchanged, `compare_runs()` reports a capability regression rather than attributing the difference to infrastructure drift.

The reverse failure is equally important: a newer model may become more eager and start executing blocked or already-satisfied actions. In those cases, `action_safety`, `waste_avoidance`, and the action-avoidance dimensions expose the regression even if some downstream task outcome appears superficially successful.

## API surface

The bridge exposes:

```python
selective_agency_world_ref(bundle)
selective_agency_scenario_ref(item)
selective_agency_scenario_refs(bundle)
selective_agency_cell_matrix(...)
selective_agency_capability_dimensions(score)
selective_agency_trace(...)
selective_agency_capability_run(...)
```

A typical longitudinal experiment should use frozen IID anchor scenarios, one concrete model snapshot, one harness/version, one verifier/version, and one observation timestamp per execution cohort. Repeating the cohort for later model snapshots creates directly comparable runs and repeated-seed aggregates.

## Relationship to the original StupidBench insight

The useful idea borrowed from longitudinal benchmarks is not the specific optimization task. It is the repeated-cell methodology:

```text
same world
+ same scenario
+ same seed
+ same harness
+ same verifier
+ same execution budget
+ new model snapshot / new time
→ capability drift
```

Selective Agency gives that methodology a broader behavioral target: whether agents are becoming better or worse at deciding **when to act, when not to act, and how much action is proportionate**.
