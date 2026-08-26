# CompanyWorld Sequential Control

CompanyWorld sequential control extends the validated investigation and single-action environments into long-horizon operational episodes.

The capability ladder is intentionally additive:

1. **Diagnostic CompanyWorld** — investigate and reconstruct operational truth.
2. **Interactive CompanyWorld** — investigate, take one operational action, and verify the resulting state.
3. **Sequential CompanyWorld** — investigate, respect workflow prerequisites, obtain authority, execute remediation, wait for delayed system effects, reconcile downstream state, verify invariants, and close or recover the case.

The existing diagnostic and interactive episode formats are unchanged.

## Control protocol

A normal successful trajectory is:

```text
Evidence-backed investigation
        ↓
OPEN_CONTROL_CASE
        ↓
[REQUEST_OPERATIONAL_APPROVAL]
        ↓
[advance → approval event]
        ↓
Domain remediation
        ↓
RECONCILE_SYSTEM_STATE
        ↓
advance → downstream reconciliation event
        ↓
VERIFY_CONTROL_INVARIANTS
        ↓
CLOSE_CONTROL_CASE
        ↓
Private outcome verification
```

The approval stage is conditional. Actors with direct authority can execute the evidence-supported remediation immediately after opening the control case. Lower-authority actors must request approval scoped to a specific remediation action. Approval arrives as a delayed simulated system event and only delegates that action.

## Evidence and state separation

Public evidence remains immutable throughout the episode. Sequential actions mutate only an isolated operational state overlay. This preserves the evidence snapshot used by the investigation verifier and prevents an agent from rewriting the records that justify its answer.

Action execution validates only public structural rules:

- action availability;
- target scope;
- role or delegated authority;
- required public parameters;
- public workflow prerequisites.

Execution does **not** compare action parameters with private ground truth. Correctness is evaluated only by the final verifier, preventing repeated action attempts from becoming an oracle side channel.

## Delayed effects

Some actions schedule effects rather than applying them immediately.

`REQUEST_OPERATIONAL_APPROVAL` creates a pending approval and schedules an `APPROVED` state for the next tick. `RECONCILE_SYSTEM_STATE` creates a pending reconciliation and schedules `COMPLETE` for the next tick.

Agents must call `advance()` to observe those external-system transitions. This creates a minimal temporal control problem rather than a purely synchronous action API.

## Recovery

`COMPENSATE_LAST_ACTION` restores the state values that existed immediately before the most recent remediation. It also resets remediation, reconciliation, and verification progress so a corrected action can be attempted.

`ESCALATE_CONTROL_FAILURE` is available when safe local recovery cannot be completed.

Compensation is tested as a state-restoration invariant, not merely represented as a status label.

## Reward

Sequential reward jointly evaluates:

- private domain outcome;
- completed control-state invariants;
- investigation fact correctness;
- evidence support;
- authority discipline;
- sequence efficiency.

A correct investigation with no remediation is capped at `0.25`. A blind state-changing action with no correct investigation/evidence is capped at `0.20`. Full reward requires the correct operational outcome and a completed control protocol.

The verifier does not require one exact action trace. Alternative trajectories may score fully if they satisfy the same domain and control outcomes without authority or prerequisite violations.

## Benchmark validity checks

The sequential benchmark harness validates:

- zero private-oracle leakage;
- public reference policy reaches full reward;
- investigation-only reward remains bounded;
- one-shot remediation cannot bypass the workflow;
- prerequisites block out-of-order actions;
- scoped approval cannot be bypassed;
- compensation restores pre-remediation state;
- evidence remains immutable;
- deterministic episode compilation.

## CLI

Compile public sequential episodes and an optional private oracle bundle:

```bash
iworld compile-companyworld-sequential /path/to/companyworld_v0_1 \
  --output companyworld_sequential.json \
  --oracle-output companyworld_sequential_oracles.json
```

Run the sequential benchmark validity suite:

```bash
iworld benchmark-companyworld-sequential /path/to/companyworld_v0_1 \
  --output companyworld_sequential_benchmark.json
```

The default distribution inherits all 1,920 CompanyWorld episodes across the existing 11 task families.
