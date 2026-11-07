# Veritas Capability Development Program

## Product

Veritas helps a team answer one operational question:

> Can this agent perform the capability we need reliably enough to deploy, and what must change if it cannot?

The customer provides a concrete capability, model or agent configuration, and deployment decision. Veritas builds or selects an executable operational environment, evaluates the agent against hidden independently verified state, identifies consequential failure modes, and measures whether subsequent model, harness, tool, permission, prompt, or training changes improve held-out capability without unacceptable regressions.

The buyer does not need to understand Veritas's internal world, trajectory, qualification, or portability architecture to use the program.

## What the customer buys

A Veritas engagement is organized around a **Capability Contract**, not around access to a benchmark.

The contract states:

- the operational capability to be measured;
- the concrete deployment or model-development decision;
- required success and reliability thresholds;
- unsafe outcomes and hard invariants;
- allowed tools, permissions, budgets, and latency constraints;
- exact model, agent, harness, and runtime identities;
- the evaluation distribution and held-out policy;
- which evidence states Veritas can legitimately claim.

Veritas then executes the following loop:

`capability contract -> executable environment -> frozen baseline -> failure diagnosis -> intervention -> held-out reevaluation -> deployment/training decision`

## Standard engagement

### 1. Capability contract

Define one capability narrowly enough that success, failure, side effects, authority, and useful deployment thresholds can be measured.

Examples:

- issue or refuse a refund under authentication, eligibility, and idempotency constraints;
- recover an incident without harming dependencies or violating the SLO recovery procedure;
- investigate conflicting evidence while preserving justified uncertainty;
- repair a financial workbook while preserving formula lineage and controls;
- complete a long-horizon operational workflow while respecting role authority and irreversible actions.

### 2. Executable environment

Use an existing Veritas environment where it matches the decision, or construct a scoped private environment using the same public/private, hidden-state, verifier, trajectory, and native-artifact boundaries.

The environment is not considered qualified merely because it runs. Its evidence state is reported explicitly.

### 3. Frozen baseline evaluation

Evaluate pinned model/agent/harness revisions on a frozen private panel. Record outcome correctness separately from state correctness, hard constraints, side effects, process, efficiency, and evidence.

Where repeated runs are material, report reliability rather than a single favorable trajectory.

### 4. Failure diagnosis

Identify failure mechanisms and capability gaps from verifier-backed execution evidence. Distinguish at least:

- incorrect outcome;
- wrong operational state;
- constraint or authority violation;
- harmful side effect;
- process failure;
- evidence failure;
- recoverable execution failure;
- harness/tool/interface failure where evidence permits attribution.

Unknown attribution remains unknown.

### 5. Intervention

The customer may change the model, prompt, harness, tools, permissions, system design, or training procedure. Veritas can provide evaluation and verified experience artifacts at the maturity permitted by the evidence.

Training assets are not described as training-qualified until the relevant training-value gates are satisfied.

### 6. Held-out reevaluation

Repeat measurement on an undisclosed or otherwise policy-valid held-out panel using the same evaluation semantics. The comparison must bind exact environment, task, verifier, model, harness, and intervention identities.

### 7. Decision report

The final buyer-safe report answers:

- Did the system meet the defined capability threshold?
- Which failure modes remain?
- Which failures are unsafe versus inefficient or recoverable?
- Did the intervention improve held-out capability?
- Did unrelated capabilities regress?
- What authority envelope is justified by the evidence?
- What remains unknown?
- What is the highest-value next experiment?

## Commercial SKU ladder

### Qualification Pilot

A fixed-scope evaluation of one consequential workflow. This is the default entry product.

**Current preferred wedge:** Veritas Independent Agent Qualification — Voice Operations, once its exact release candidate is merged and qualified. Voice workflows create a direct buyer problem because an apparently successful conversation can still leave CRM, billing, scheduling, authentication, or escalation state wrong.

SRE remains an available frozen evaluation asset when incident-analysis capability is the customer's actual decision.

### Capability Improvement Cycle

Baseline evaluation, failure diagnosis, customer intervention, and held-out reevaluation. This product can establish whether a specific intervention improved a specific capability. It does not by itself establish that Veritas-generated training data caused the improvement.

### Verified Training-Value Program

Available only when the relevant environment and experiment satisfy the canonical training-value qualification contract. The required evidence includes train/held-out separation, pinned semantics, replicated effects where required, exploit monitoring, structural/OOD transfer classification, and regression evidence.

### Learning-Efficiency Program

Available only when resource-accounting and matched-budget evidence are present. The claim is not lower training loss. It is greater **verified held-out capability gain per observed scarce resource** relative to an appropriate control.

Resource denominators remain separate: data, compute, teacher inference, human expertise, elapsed time, and money are not collapsed into a universal efficiency score.

## Evidence ladder

Veritas keeps product maturity states distinct:

| State | What it establishes |
|---|---|
| `EXECUTABLE` | The environment can run under its declared contract. |
| `VERIFIER_VALIDATED` | The verifier has passed the required correctness/exploit checks. |
| `SCIENTIFICALLY_QUALIFIED` | The benchmark/environment satisfies the applicable validity, leakage, ambiguity, diversity, and reproducibility gates. |
| `FRONTIER_QUALIFIED` | Evidence shows the environment is useful for differentiating current strong agents under the applicable policy. |
| `TRAINING_VALIDATED` | A qualified training experiment demonstrates held-out capability improvement under the required controls. |
| `COMMERCIAL_RELEASE` | The package is suitable for its declared buyer/deployment channel. |

No state silently implies a later state. Missing evidence is reported as `UNKNOWN` or not qualified.

## What Veritas should lead with

Lead with:

> We independently test whether an AI agent can perform a consequential operational capability, show where it fails, and measure whether changes actually improve held-out performance.

Use native artifacts, persistent state, independent verification, private worlds, adversarial cases, machine experience, and portability as evidence for why the result is trustworthy—not as concepts the buyer must learn before understanding the offer.

## What Veritas should not lead with

Do not lead with:

- number of generated episodes;
- number of world families;
- internal ontology or architecture diagrams;
- marketplace integrations;
- a generic claim that Veritas is an RL environment framework;
- training-value or learning-efficiency claims that have not passed their dedicated evidence gates.

## Product success

Engineering completeness is not the success criterion for this product.

Commercial evidence progresses through these externally grounded stages:

1. a buyer understands and accepts the capability framing;
2. the buyer provides a real workflow and decision to evaluate;
3. a scoped proposal or SOW is sent;
4. a paid design partner begins;
5. Veritas resolves a materially uncertain deployment or model-development decision;
6. a customer intervention produces a verified held-out improvement, if applicable;
7. stronger learning-efficiency evidence shows a Veritas-directed treatment beating a matched control, if applicable.

Only the evidence actually obtained may be claimed.