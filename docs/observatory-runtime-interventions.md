# Observatory Runtime Interventions

This layer makes CompanyWorld failure and permission interventions executable rather than merely descriptive.

## Runtime provenance

All Observatory CompanyWorld runs now identify the runtime as `companyworld-runtime-v2`. Baseline worlds still use the standard `CompanyWorldRuntime`; only worlds containing intervention schedules resolve to `InterventionAwareCompanyWorldRuntime`.

That version bump is intentional. A v2 run must not be treated as directly comparable to a v1 run under longitudinal drift analysis because the runtime semantics changed.

## Tool failures

Tool failures are scheduled by attempted public-operation index:

```json
{
  "system": "ERP",
  "at_step": 0,
  "persistent": false
}
```

A one-shot failure raises on the matching attempt and then clears naturally because the operation index advances. A persistent failure remains active from its scheduled step onward. Failed attempts do not consume CompanyWorld budget.

The tracing layer records the failed call before re-raising it, so the harness can observe an error and choose whether to retry, switch tools, or submit without that evidence.

## Permission transitions

Permission schedules support `revoke` and `restore` actions:

```json
[
  {"system": "ERP", "at_step": 0, "action": "revoke"},
  {"system": "ERP", "at_step": 3, "action": "restore"}
]
```

Revoked systems are blocked in targeted search and record opening and removed from cross-system search results. Multiple transitions are preserved in the generated task constraints.

## Recovery measurement

A failed traced method followed by a later successful call of the same method counts as one recovery event. This makes runtime resilience observable in `BehavioralFingerprint` alongside failure signals, tool mix, cost and verifier outcomes.

## Repeated-seed intervention suites

`run_companyworld_intervention_suite()` executes one intervention family across multiple unique scenario/seed pairs. Each scenario contributes a paired effect:

```text
treatment - baseline
```

The suite aggregates those paired effects into mean, sample standard deviation, standard error, approximate 95% confidence interval and min/max statistics for reward, cost, steps and verifier dimensions.

## Model interaction

`compare_companyworld_intervention_suites()` compares two model-specific suites from the same intervention family. The reported interaction is:

```text
mean paired effect(model 2) - mean paired effect(model 1)
```

This measures differential robustness to the intervention. It is separate from longitudinal drift.

## Current validation boundary

The branch includes direct runtime tests, factory selection tests, end-to-end retry/recovery tests, paired-statistics tests, and a two-scenario suite execution test. Repository CI/security execution is still required before merge.
