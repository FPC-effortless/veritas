# DataVendor Registration — Veritas

## What we provide

Veritas builds verifier-grounded environments for training and evaluating AI agents in
persistent, executable, partially observable operational worlds.

## Flagship sample

**Veritas SRE Evaluation Pack v1**

The flagship environment gives an agent a realistic incident-response objective and requires
it to investigate evidence, perform stateful operational actions, modify the underlying native
artifact correctly, preserve safety/process invariants, and reach a verified terminal state.

The reward is not based on whether the final response sounds correct. The verifier independently
checks outcome, state, constraints, side effects, process, efficiency and evidence.

## Why it is differentiated

Most benchmark examples can be solved by producing the right answer or action label. Veritas
makes the operational world authoritative. Unsafe or out-of-order actions can be blocked; harmful
intermediate states remain detectable; and native-artifact correctness is checked separately from
the agent's report.

## Validation

The SRE v4 release is the first qualified Veritas portability proof. The 0.11 portability layer
provides a vendor-neutral manifest and a HUD adapter while keeping private task rows, hidden
oracles and evaluator-only artifacts outside buyer-safe distribution.

Hosted HUD identifiers and performance numbers will be added only after the exact exported
package has completed a real HUD evaluation.

## Commercial use

The public sample is intended to demonstrate the environment/verifier architecture. Private
benchmarks, customer data and operator-only evaluation material remain separately controlled.

## Links to provide after deployment

- Veritas repository: https://github.com/FPC-effortless/veritas
- HUD environment: PENDING
- HUD taskset: PENDING
- Successful HUD trace: PENDING
- Adversarial failed trace: PENDING
