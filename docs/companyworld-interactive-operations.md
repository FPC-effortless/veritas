# CompanyWorld Interactive Operations

CompanyWorld interactive episodes extend the validated investigation distribution into an `investigate → act → verify` environment. Evidence remains an immutable historical snapshot; operational actions mutate only an isolated simulated state overlay.

## Episode contract

Each interactive episode contains:

- the public investigation task and projected enterprise records;
- an actor role;
- costed, typed operational actions;
- public authorization/effect policies for those actions;
- public initial operational state;
- a private expected action and outcome contract used only by the verifier.

The public payload never includes the private action oracle, expected parameters, or outcome conditions.

## Authority

Action policies enumerate the roles permitted to execute them. Some episodes deterministically assign a manager/controller role with direct write authority; others assign an analyst role that must escalate instead of performing the privileged write. Unauthorized attempts are rejected, consume budget, are journaled, and cannot mutate state.

## State semantics

Enterprise evidence does not change when the agent acts. The runtime keeps a separate state overlay keyed by `(object_type, object_id, field_name)`. This avoids a common benchmark failure mode where an agent can modify the same evidence later used to verify its answer.

Action execution validates only public structure and authorization. It does **not** compare supplied parameters with private ground truth. Parameter correctness is checked only by final outcome verification, preventing iterative action calls from becoming an oracle side channel.

## Interactive coverage

The compiler maps all 11 CompanyWorld task families into operational decisions:

- shipment shortfall remediation;
- duplicate supplier invoice blocking/escalation;
- authority-limit repair/escalation;
- order fulfillment confirmation/expediting;
- procure-to-pay approval/review routing;
- receivables closure/collections follow-up;
- payment-block recovery closure/escalation;
- incident SLA closure/escalation;
- safety corrective-action closure/escalation;
- order-to-cash certification/escalation;
- ledger posting certification/escalation.

## Reward

Interactive reward requires both epistemic correctness and operational success. The verifier combines:

- final outcome state;
- investigation fact correctness;
- evidence support;
- action precision;
- authority compliance;
- budget efficiency.

Outcome credit is multiplicatively gated by investigation quality. A correct investigation with no action is capped at `0.35`; a lucky action with no investigation/evidence is capped at `0.20`. A fully correct evidence-backed investigation followed by the authorized state transition can score `1.0`.

## CLI

Compile public episodes with optional private oracles:

```bash
iworld compile-companyworld-interactive /path/to/companyworld \
  --output interactive.json \
  --oracle-output interactive-oracles.json
```

Run the interactive benchmark-validity harness:

```bash
iworld benchmark-companyworld-interactive /path/to/companyworld \
  --output interactive-validation.json
```

The validity harness checks public/private separation, public-only solvability, investigation-only reward bounds, blind-action reward bounds, unauthorized-write rejection, evidence immutability, and deterministic compilation.
