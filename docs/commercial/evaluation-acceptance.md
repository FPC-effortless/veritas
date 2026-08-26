# Veritas Pilot Evaluation Acceptance Criteria

A paid pilot is considered technically complete only when the following conditions are satisfied.

## Integration acceptance

- The agreed customer model/agent is uniquely identified by model, endpoint/container/harness version, and configuration.
- Authentication works without recording reusable secrets in the report or repository.
- Test prompts/tasks can be sent and parsed successfully.
- Tool calls and structured final outputs follow the agreed schema.
- Token/tool/time/retry limits are recorded before the private run starts.

## Dry-run acceptance

- At least one non-private development task completes end to end.
- Tool usage, costs/budgets, failures, and final submission appear in the trajectory.
- The independent verifier produces a score without accessing customer-hidden internals.
- A failed/invalid model output is classified rather than silently coerced into a passing result.

## Private-run acceptance

- The run uses the frozen benchmark version and private-suite hash stated in the manifest.
- Private oracle data is not sent to the evaluated agent.
- Every attempted task has a terminal status: scored, model error, harness error, timeout, or operator-cancelled.
- Any operator retry is recorded and follows the agreed retry policy.
- No benchmark methodology change occurs after the first scored private task without invalidating/restarting the affected run.

## Report acceptance

The final readout contains:

- run/benchmark/model/harness identifiers;
- per-level and per-family outcome metrics available for the agreed suite;
- parse/format reliability;
- authority/policy failures where applicable;
- budget/tool/cost statistics where available;
- representative successful and failed trajectories with sensitive information redacted;
- limitations and any invalidated tasks;
- prioritized capability gaps and recommended next experiments.

## Non-acceptance conditions

A run must not be presented as a valid private evaluation if:

- private answer/oracle information leaked into the agent context;
- the benchmark version/hash cannot be established;
- the verifier or task semantics changed mid-run;
- systematic harness failures make the evaluated sample unrepresentative;
- outputs were manually edited before scoring;
- unsupported retries were selectively applied to improve the result.

## Customer sign-off

Commercial acceptance is based on delivery of the agreed evaluation artifacts and readout, not on the customer achieving a particular score. A poor model score is a valid evaluation outcome when the run itself satisfies these criteria.
