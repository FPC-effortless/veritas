# Veritas Paid Design-Partner Pilot

## Objective

Evaluate a customer's real AI agent against a private CompanyWorld benchmark and produce an evidence-backed capability report showing where the system succeeds, fails, over-spends, violates authority, or breaks under long-horizon operational complexity.

## Standard pilot scope

A standard design-partner pilot includes:

1. **Integration** — connect the customer's model or agent harness through an adapter without exposing Veritas private oracles.
2. **Dry run** — validate tool schemas, structured outputs, budgets, deterministic replay and trajectory capture on public/development tasks.
3. **Private evaluation** — run a frozen private stratified task suite across investigation, action, sequential control and dynamic portfolio levels.
4. **Failure analysis** — classify errors by evidence, planning, authority, recovery, tool selection, budget use, structured-output reliability and state management.
5. **Readout** — deliver a versioned scorecard, trajectories for representative failures, benchmark metadata and recommended next experiments.

## Pilot deliverables

- evaluation manifest with model/harness/version metadata;
- private benchmark run identifier and benchmark hash;
- per-level and per-family capability scores;
- no-work and public-reference anchors;
- tool/token/cost statistics where available;
- parse/format reliability;
- authority and policy-compliance rates;
- recovery and deadline behavior;
- representative successful and failed trajectories;
- prioritized capability gaps;
- optional re-evaluation after a customer model or harness change.

## Success criteria

The pilot is successful if the customer can answer at least one concrete decision question, such as:

- Which model/harness should we deploy for this class of work?
- Where does our agent fail when work becomes multi-step or concurrent?
- Does extra test-time compute improve outcomes enough to justify its cost?
- Which tool or permission changes improve success without increasing unsafe actions?
- Did a new model, prompt, training run or agent architecture produce a statistically credible improvement?

## Customer inputs

The customer supplies one of:

- an OpenAI-compatible model endpoint;
- an agent endpoint that accepts tasks and exposes tool calls;
- a container/CLI that can be run in an isolated environment;
- a model checkpoint that can be evaluated in the agreed compute environment.

The customer also specifies evaluation constraints such as token budget, tool budget, maximum wall-clock time, allowed systems and retry policy.

## Private evaluation boundary

Private task seeds, evaluator oracles and hidden ground truth are not sent to the customer agent. Customer outputs are scored by Veritas independently of the evaluated model.

## Optional training-value extension

A pilot can be extended into a capability-development experiment:

1. establish a pre-training held-out score;
2. train or adapt the system using Veritas train-world trajectories;
3. evaluate on fresh private worlds and unseen object identities;
4. report absolute and normalized improvement, confidence intervals and any capability regressions.

## Commercial model

Commercial terms are quoted separately based on evaluation volume, model-inference cost, integration complexity, private-world generation requirements and whether the customer needs a one-time evaluation, repeated regression testing, or a training environment.
