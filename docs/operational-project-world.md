# Operational Project World

`investigation_world.projectworld` is Veritas' long-horizon project-delivery environment substrate. It models a project as a persistent causal world rather than a collection of independent prompts.

The first domain adapter is a construction project that spans design decisions, approvals, procurement, physical execution, inspection, rework, commissioning, and handover.

## Design goals

The implementation is built around six requirements:

1. **Persistent state** — actions mutate project state across the full episode.
2. **Role and authority boundaries** — agents act as named project roles with explicit permissions, management scope, visibility, and approval limits.
3. **Causal downstream effects** — design choices alter later cost, duration, and resource requirements.
4. **Event-driven time** — work completion, procurement arrivals, delays, and rework occur on a deterministic event queue.
5. **Private ground truth** — hidden delays and latent defects are held in a verifier-only oracle and never returned in the public payload.
6. **State-based verification** — success is scored from completion, requirements, cost, schedule, quality, and authority outcomes rather than an LLM judge.

## Package

```text
investigation_world/projectworld/
├── models.py        # canonical project, role, work, resource, decision, oracle and state schemas
├── runtime.py       # OperationalProjectWorld event-driven simulator
├── verifier.py      # deterministic project outcome verifier
├── construction.py  # flagship construction reference world
└── __init__.py      # public API
```

## Core model

A scenario is split into a public project specification and a private oracle:

```text
ProjectScenario
├── OperationalProjectWorldSpec       # agent-visible contract
│   ├── roles
│   ├── resources
│   ├── work_packages
│   ├── requirements
│   └── decisions
└── ProjectOracle                     # evaluator-only truth
    ├── work_package_delay_days
    ├── resource_delay_days
    └── latent_defects
```

`ProjectScenario.public_payload()` intentionally excludes the oracle and generator seed.

## Action surface

The runtime currently supports:

- `start_work`
- `advance_time`
- `procure`
- `choose_option`
- `inspect`
- `resolve_issue`
- `approve`

Invalid or unauthorized actions do not crash the episode. They produce a rejected transition, a small negative reward, and an authority/precondition violation in the harness journal.

## Event semantics

Work and resource transitions are scheduled on a deterministic queue ordered by `(due_day, event_id)`.

For a work package:

```text
BLOCKED
  ↓ dependencies + decisions satisfied
READY
  ↓ start_work
IN_PROGRESS
  ↓ scheduled completion
AWAITING_INSPECTION ── defect ──> REWORK_REQUIRED
  │                                  ↓ resolve_issue
  │                              IN_PROGRESS
  │                                  ↓ rework completion
  └──────── pass <──────────── AWAITING_INSPECTION
  ↓ optional approval
AWAITING_APPROVAL
  ↓ approve
COMPLETE
```

A deliverable is not accepted into `completed_deliverables` until the work package reaches `COMPLETE`. Execution finishing by itself is therefore insufficient when inspection or approval gates exist.

## Causal design decisions

`ProjectDecisionOption` can mutate downstream:

- direct work-package cost;
- work-package duration;
- resource requirements.

This lets an early design choice reshape the project that the agent later has to deliver.

The construction reference world includes a structural-system decision where choosing structural steel changes foundation/superstructure durations, cost, and material requirements.

## Construction reference world

`build_construction_project_world(seed=42)` creates a 12-storey mixed-use development with a $38M budget and a 420-day target.

Roles include:

- project director;
- project manager;
- architect;
- structural engineer;
- MEP engineer;
- procurement manager;
- site manager;
- quality inspector;
- commissioning manager;
- owner representative.

The work graph covers:

```text
concept design
  → structural + MEP design
  → design coordination
  → permit release
  → foundations
  → superstructure
  → envelope + MEP rough-in
  → interiors
  → commissioning
  → handover
```

Resources include labor, concrete, rebar, structural steel, facade units, and MEP equipment with explicit costs and procurement lead times.

The private construction oracle injects deterministic seed-dependent permit delay, long-lead MEP delivery delay, and a latent quality defect that requires inspection and rework to discover and clear.

## Role observations

Agents should receive `world.observe(role_id)`, not `state_snapshot()`.

Observations are filtered by role visibility and management relationships. The harness can use `state_snapshot()` and `trace()` for evaluation and debugging. Hidden oracle fields are not present in either agent-facing scenario payloads or observations.

## Verification

`verify_project_world()` and `OperationalProjectWorld.verify()` score six dimensions:

| Dimension | Weight |
| --- | ---: |
| Completion | 0.30 |
| Requirements | 0.25 |
| Cost | 0.15 |
| Schedule | 0.15 |
| Quality | 0.10 |
| Authority | 0.05 |

A passing project currently requires:

- all work packages complete;
- all hard requirements satisfied;
- no open quality issues;
- cost at or below budget;
- completion at or before the deadline.

The dimensional scores remain available even for failed projects, which makes the environment suitable for dense RL reward, curriculum construction, failure mining, and capability evaluation.

## Example

```python
from investigation_world.projectworld import (
    OperationalProjectWorld,
    ProjectAction,
    ProjectActionKind,
    build_construction_project_world,
)

scenario = build_construction_project_world(seed=42)
world = OperationalProjectWorld(scenario)

observation = world.observe("architect")
world.step(
    ProjectAction(
        actor_role_id="architect",
        kind=ProjectActionKind.CHOOSE_OPTION,
        target_id="structural_system",
        parameters={"option_id": "structural_steel"},
    )
)

report = world.verify()
```

## Current boundary

This first implementation establishes the reusable project state machine and the construction reference world. It deliberately does **not** add construction to the legacy `WorldDomain` enum yet. That enum currently determines the existing five-domain production distribution and its 4,480-case compatibility contract. ProjectWorld is introduced as a separate long-horizon environment family so the existing Veritas 0.7 operational distribution remains stable.

The next integration layer should add ProjectWorld-specific procedural scenario generation, Foundry trajectory/reward adapters, Observatory cells, and an adapter that projects project state/events into the shared persistent operational substrate where cross-environment composition is required.
