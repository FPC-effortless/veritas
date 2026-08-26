# Veritas CompanyWorld — Commercial Benchmark Card

## What Veritas measures

Veritas evaluates whether an AI agent can operate in a synthetic enterprise with private ground truth, heterogeneous systems, conflicting evidence, permissions, delayed effects and resource constraints.

The benchmark has four capability levels that share the same operational world:

1. **Investigation** — reconstruct facts from evidence and cite support.
2. **Operational Action** — choose and execute the correct authorized action.
3. **Sequential Control** — satisfy prerequisites, approvals, delayed effects, reconciliation and closure.
4. **Dynamic Portfolio Control** — manage concurrent cases under stochastic approvals, outages, deadlines, shared resources and global budgets.

## Current validated benchmark substrate

The default CompanyWorld task distribution contains 1,920 cases across 11 operational families. The dynamic layer composes those cases into 640 three-case portfolios.

Current task families include:

- shipment discrepancy investigation;
- duplicate supplier invoice investigation;
- authority-limit investigation;
- order-to-cash fulfillment timing;
- procure-to-pay reconciliation;
- customer settlement reconstruction;
- payment-block recovery;
- incident SLA investigation;
- safety corrective-action follow-up;
- cross-system order-to-cash reconstruction;
- ledger posting reconstruction.

## Ground truth and verifier design

CompanyWorld separates public observations from evaluator-only truth. Public episodes contain task instructions and system projections; private oracles contain the expected operational facts, evidence requirements and outcome conditions.

The verifier scores factual correctness, evidence support, calibration, authority compliance, action/outcome correctness and efficiency. Long-horizon layers additionally score prerequisite compliance, state transitions, deadlines, resource conflicts and recovery behavior.

The benchmark has explicit regression tests for common reward-hacking strategies, including empty answers, conclusion-only output, citation-only output, field stuffing, blind trust in divergent projections, authority bypass, out-of-order execution, incorrect compensation and evidence mutation.

## Calibration anchors

Every evaluation can report two anchors:

- **No-work anchor** — the reward obtained by submitting no meaningful work.
- **Public-reference anchor** — a deterministic oracle-blind policy that solves tasks using only the public evidence and published operational rules.

Customer/model capability can therefore be normalized between these anchors without exposing private ground truth.

## Evaluation modes

### Full-context planning

The model receives the public episode payload and returns a structured answer or plan. This isolates reasoning and instruction following from tool-discovery behavior.

### Agent/harness evaluation

The customer agent interacts with Veritas system surfaces and budgets through the runtime. This is the preferred commercial evaluation because it measures the customer's actual tool-use policy, state management and recovery behavior.

## Recommended commercial protocol

For a procurement-grade evaluation:

- use a private stratified test set;
- freeze benchmark and harness versions;
- run at least 3 attempts per task for stochastic agents;
- record model/harness versions, tool/token budgets and costs;
- retain complete trajectories;
- report per-family results and confidence intervals;
- keep evaluator oracles and private seeds inaccessible to the evaluated system.

## What Veritas does not currently claim

Veritas does not yet claim that its score is a validated proxy for every real enterprise deployment. External customer validation and stronger-model calibration are ongoing. The benchmark is best described today as a rigorously instrumented synthetic enterprise capability environment with independent ground truth and explicit anti-gaming validation.
