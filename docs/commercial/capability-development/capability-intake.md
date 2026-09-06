# Capability Intake Contract

Use this intake before proposing or building a Veritas engagement. The purpose is to turn a broad request such as “evaluate our agent” into one falsifiable operational capability and one decision.

## 1. Decision

**Decision owner:**

**Decision to be made:**

Examples: deploy/not deploy; choose model A vs B; increase or restrict authority; approve a post-training run; select a harness/tool configuration; determine whether a workflow needs human escalation.

**Decision deadline, if material:**

**What is currently uncertain?**

## 2. Target capability

**Capability name:**

**Operational objective:**

Describe what the agent must accomplish in the world, not merely what text it should produce.

**Start state:**

**Required terminal state:**

**Required process or ordering constraints:**

**Actions or side effects that are forbidden:**

**Conditions under which the correct behavior is clarify, abstain, escalate, decline, or no-op:**

## 3. Deployment threshold

Define the minimum evidence needed for the decision.

**Primary success metric:**

**Required threshold:**

**Reliability requirement:**

**Hard-invariant tolerance:**

**Unsafe-side-effect tolerance:**

**Recovery requirement:**

**Latency / cost / tool-budget constraints:**

A threshold that is not specified before evaluation must not be retrofitted after seeing results without being marked exploratory.

## 4. Evaluated system

**Model/provider:**

**Exact model revision:**

**Agent/harness:**

**Harness version/configuration:**

**System prompt/config identity:**

**Tool/API surface:**

**Permission/authority envelope:**

**Runtime constraints:**

**Expected stochasticity / repeated-run policy:**

## 5. Operational environment

**Relevant real systems or artifacts:**

Examples: CRM, billing, scheduling, workbook, database, casefile, Kubernetes state, GIS layers.

**Which state must be independently verifiable?**

**Which state must remain hidden from the evaluated agent?**

**Known operational invariants:**

**Known recovery procedures:**

**Important OOD conditions:**

**Important adversarial conditions:**

**Important partial-failure conditions:**

## 6. Data and privacy boundary

**Customer data required:**

**Can synthetic/private reconstructed data represent the decision adequately?**

**Prohibited data:**

**PII / confidential fields:**

**Retention constraints:**

**Redistribution/publication constraints:**

**Whether case-level debugging truth may be disclosed after evaluation:**

Private evaluator truth, hidden benchmark state, secrets, and customer-confidential data must remain outside buyer/public artifacts unless an explicit authorized disclosure boundary says otherwise.

## 7. Baseline and comparison

**Baseline system:**

**Comparison systems or interventions:**

**What must remain fixed across comparisons?**

Normally environment/task/verifier semantics should remain fixed when comparing models, harnesses, prompts, tools, or permissions.

**Held-out policy:**

**Regression panel:**

**Structural/OOD transfer requirement, if any:**

## 8. Failure priorities

Rank the consequences that matter to the buyer.

| Failure class | Business/safety consequence | Severity | Must block deployment? |
|---|---|---:|---|
| Wrong outcome |  |  |  |
| Wrong operational state |  |  |  |
| Authority/permission violation |  |  |  |
| Harmful side effect |  |  |  |
| Process/order violation |  |  |  |
| Evidence/provenance failure |  |  |  |
| Inefficiency/cost |  |  |  |
| Failure to recover |  |  |  |

## 9. Intervention scope

For a qualification-only pilot, leave this section as `NOT_APPLICABLE`.

Possible intervention classes:

- model change;
- prompt/system-policy change;
- harness change;
- tool/schema change;
- permission change;
- workflow change;
- parameter-efficient or other training intervention.

**Which interventions may Veritas evaluate?**

**Which intervention is owned by the customer?**

**Does the engagement require a causal/training-value claim, or only before/after measurement?**

A before/after improvement is not automatically attributed to Veritas-generated experience or training unless the relevant experimental controls support that claim.

## 10. Evidence authority

At intake, mark the strongest state actually required by the buyer:

- `EXECUTABLE`
- `VERIFIER_VALIDATED`
- `SCIENTIFICALLY_QUALIFIED`
- `FRONTIER_QUALIFIED`
- `TRAINING_VALIDATED`
- `COMMERCIAL_RELEASE`

**Required state:**

**Current known state:**

**Missing gates:**

Missing evidence remains `UNKNOWN`; scope or pricing must not silently convert it to PASS.

## 11. Pilot acceptance

A proposed engagement is ready to scope when all of the following are explicit:

- one decision;
- one operational capability;
- measurable terminal state and hard invariants;
- exact evaluated system identity;
- success/reliability threshold;
- unsafe-outcome policy;
- public/private boundary;
- frozen comparison semantics;
- held-out or regression policy where applicable;
- evidence state required for the decision.

If these cannot be specified, the first deliverable should be capability-definition work rather than a benchmark run.