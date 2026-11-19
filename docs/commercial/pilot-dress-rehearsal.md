# Veritas Pilot Dress Rehearsal

Run this procedure on the exact commercial release candidate before accepting payment for the first pilot.

## Goal

Prove that an operator can run a model locally on the same user-controlled device as the evaluator and produce a complete evaluation package without manual score editing, private-answer leakage, remote inference or ad hoc methodology changes.

## Rehearsal setup

Use:

- a non-customer model served on the same device at `http://127.0.0.1:8765/v1/chat/completions`;
- the intended commercial software release candidate;
- a frozen non-production private test suite distinct from any customer suite;
- the same manifest/report tools intended for customers;
- the same local credential handling process intended for the first pilot, with airplane mode enabled and outbound network tracing retained.

## Procedure

### 1. Freeze run metadata

Record:

- software commit/tag;
- benchmark version;
- test-suite content hash;
- model and harness identifiers;
- attempts per task;
- token/tool/time/retry budgets;
- operator name/date.

Create the evaluation manifest before the scored run.

### 2. Integration smoke test

- confirm local endpoint authentication and loopback-only binding;
- run one development task in airplane mode;
- verify the evaluator does not use environment proxies or follow redirects;
- verify structured output parsing;
- verify failures/timeouts are explicit;
- confirm API credentials do not appear in generated artifacts.

### 3. Private execution

Run the frozen rehearsal suite without exposing oracle/private-ground-truth fields to the model. Do not change prompts, retry policy, verifier weights, task semantics, or benchmark data after scoring begins.

### 4. Integrity checks

Confirm:

- no private oracle fields appear in agent-visible payloads or trajectories;
- no network request or hosted fallback occurs during model inference;
- every task has a terminal status;
- retries match the frozen policy;
- verifier outputs are reproducible for the saved submissions;
- benchmark/test-suite hash is unchanged;
- operator intervention is logged;
- invalid tasks are quarantined rather than manually fixed post hoc.

### 5. Produce customer-equivalent package

Generate and retain:

- evaluation manifest;
- machine-readable raw results;
- aggregate scorecard;
- representative success/failure trajectories;
- buyer-facing report;
- limitations/caveats;
- recommended next experiments.

### 6. Operator readout test

Conduct a simulated 30-minute buyer readout. The first five minutes must answer a decision question directly rather than narrating the architecture.

A valid structure is:

1. decision/recommendation;
2. strongest supporting result;
3. highest-risk failure mode;
4. representative trajectory;
5. next experiment/change to test.

## Pass criteria

The commercial release candidate passes rehearsal only if:

- the entire workflow completes using documented commands/processes;
- no reusable credential or private-answer leakage occurs;
- the model remains functional in airplane mode and all observed network activity is absent;
- all expected artifacts are generated;
- aggregate results can be reproduced from retained raw outputs;
- the report clearly distinguishes measured facts, interpretation, and limitations;
- the operator can explain what changed between any two compared runs;
- a second operator could repeat the procedure from the documentation.

If any integrity criterion fails, do not accept a paid private evaluation on that release candidate until the issue is fixed and the rehearsal is rerun.
