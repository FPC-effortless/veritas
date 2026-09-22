# Veritas Capability Decision Report — Template

## Executive decision

**Capability:**

**Evaluated system:**

**Decision:** `DEPLOY | DEPLOY_WITH_RESTRICTIONS | DO_NOT_DEPLOY | INSUFFICIENT_EVIDENCE`

**Predeclared threshold:**

**Observed result:**

**Bottom-line interpretation:**

State the decision in operational terms. Do not substitute a benchmark score for the decision.

## 1. Evaluation identity

| Field | Exact value |
|---|---|
| Capability contract | |
| Environment/world | |
| Task distribution/panel | |
| Verifier | |
| Model/revision | |
| Harness/configuration | |
| Prompt/policy identity | |
| Tool schema/config | |
| Permission envelope | |
| Run/replicate set | |
| Evaluation date/snapshot | |

Any material change to these identities is a new condition, not the same result.

## 2. Evidence state

Report only states established by current evidence.

| Maturity/evidence state | Status | Evidence / limitation |
|---|---|---|
| EXECUTABLE | | |
| VERIFIER_VALIDATED | | |
| SCIENTIFICALLY_QUALIFIED | | |
| FRONTIER_QUALIFIED | | |
| TRAINING_VALIDATED | | |
| COMMERCIAL_RELEASE | | |

Use `PASS`, `FAIL`, `UNKNOWN`, or `NOT_APPLICABLE` where the underlying contract permits. Missing evidence does not become PASS.

## 3. Capability scorecard

Report dimensions independently rather than hiding them inside one aggregate.

| Dimension | Result | Threshold / reference | Interpretation |
|---|---:|---:|---|
| Outcome | | | |
| Operational state | | | |
| Hard constraints / authority | | | |
| Harmful side effects | | | |
| Process | | | |
| Efficiency | | | |
| Evidence | | | |
| Recovery | | | |
| Reliability / repeats | | | |

When applicable, include uncertainty intervals, replicate variance, and relevant baseline/reference anchors.

## 4. Failure analysis

### Dominant failure mechanisms

For each material failure family record:

- failure family/mechanism;
- frequency or evidence strength;
- affected scenario pressure: normal, IID, OOD, adversarial, recovery;
- whether the failure is unsafe, correctness-critical, recoverable, or primarily inefficient;
- first reliable evidence of the failure;
- attribution confidence;
- representative buyer-safe trace reference;
- recommended intervention.

Do not infer causal model blame when the evidence only shows a failed outcome. Harness/tool/runtime attribution must be supported separately.

### Unsafe events

Separate:

- blocked unsafe attempts;
- actual applied harmful side effects;
- hard-invariant violations;
- authority/permission violations.

A blocked attempt may still be a policy failure, but it must not be reported as an applied harmful side effect if the world state did not change.

## 5. OOD, adversarial, and recovery behavior

**OOD result:**

**Adversarial result:**

**Recovery result:**

**Observed shortcut/exploit behavior:**

**Known untested pressures:**

Do not generalize beyond the evaluated structural or interface scope.

## 6. Cost and operational efficiency

Report only observed values.

| Resource | Observed value | Unit / provenance |
|---|---:|---|
| Tool calls | | |
| Input/output tokens | | |
| Inference cost | | |
| Wall-clock latency | | |
| Cost per verified successful workflow | | |
| Other | | |

If cost or usage was not measured, report `UNKNOWN`; do not insert estimated provider pricing as observed experiment evidence.

## 7. Authority recommendation

State the operational authority justified by evidence.

Examples:

- autonomous execution permitted within declared low-risk envelope;
- execution permitted only after authentication and eligibility preconditions are independently confirmed;
- human confirmation required before irreversible mutation;
- read-only/recommendation mode only;
- escalation required for ambiguity or restricted account state;
- deployment not justified.

**Recommended authority envelope:**

**Evidence supporting it:**

**Conditions that should revoke/escalate authority:**

## 8. Intervention comparison

Complete this section only when a baseline and a declared intervention were compared.

**Baseline identity:**

**Intervention identity:**

**What changed:**

**What remained fixed:**

| Metric | Baseline | Intervention | Delta | Interpretation |
|---|---:|---:|---:|---|
| Primary held-out capability | | | | |
| Reliability | | | | |
| Hard violations | | | | |
| Unsafe side effects | | | | |
| OOD performance | | | | |
| Adversarial performance | | | | |
| Recovery | | | | |
| Regression panel | | | | |

A before/after gain may be reported as an intervention result. Do not call it Veritas-caused training improvement unless the experimental design and training-value qualification establish that claim.

## 9. Training-value evidence

Complete only when a training experiment is in scope.

**Training bundle identity:**

**Training method/configuration:**

**Train/held-out separation:**

**Seeds/replicates:**

**Exploit monitoring:**

**Structural/OOD transfer evidence:**

**Regression evidence:**

**Training qualification status:**

Training loss alone is not capability evidence.

## 10. Learning-efficiency evidence

Complete only for matched-budget experiments with resource accounting.

| Denominator | Control | Veritas-directed treatment | Capability gain / resource | Evidence state |
|---|---:|---:|---:|---|
| Training examples/tokens | | | | |
| Compute | | | | |
| Teacher inference | | | | |
| Human effort | | | | |
| Money | | | | |

Disclose candidate-generation/selection overhead. Do not collapse separate denominators into one universal efficiency score unless a separately justified buyer utility function is explicitly declared.

## 11. Limitations and UNKNOWNs

List every material boundary that affects interpretation, including:

- untested workflow/state regions;
- insufficient sample size/replicates;
- contamination or held-out limitations;
- missing cost evidence;
- unsupported causal attribution;
- unavailable regression evidence;
- unqualified maturity stages;
- differences between synthetic/private reconstruction and the buyer's live system.

## 12. Recommended next action

Choose one primary next action and explain why it has the highest expected decision value.

Examples:

- deploy under restricted authority;
- repair a specific harness/tool failure and rerun the same frozen panel;
- construct fresh held-out OOD cases;
- run a training-value experiment;
- compare a smaller/lower-cost model;
- expand from qualification pilot to repeated regression monitoring;
- stop investment because the capability is currently below the required threshold.

**Next action:**

**Reason:**

**Evidence required to change the current decision:**
