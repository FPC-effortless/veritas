# OperationalProjectWorld

`OperationalProjectWorld` is Veritas's generic executable environment for long-horizon project delivery. The first domain pack is construction, while the runtime remains project-generic: role-scoped observations, authority, task dependencies, shared resources, delayed effects, external events, evidence, budget state and independent outcome verification are first-class.

## Why this is a world rather than a workflow benchmark

A project episode contains public operating state and private ground truth. Agents take actions that mutate state, consume money and resources, create delayed consequences, cross role/authority boundaries, and encounter hidden exogenous events. Verification scores accepted outcomes and process invariants from the resulting state; it does not require an agent to reproduce one reference trajectory.

```text
requirements / site / design
        ↓
quantities + work packages
        ↓
procurement + resources
        ↓
schedule + dependencies
        ↓
execution + RFIs + quality + safety
        ↓
commissioning + handover
        ↓
independent verification
```

## Package layout

```text
src/investigation_world/projectworld/
├── models.py        # generic project state/action/oracle schema
├── runtime.py       # event-driven multi-role simulator
├── verifier.py      # independent multi-dimensional verifier
├── sources.py       # source manifest, transcript registry, field-level fusion
├── adapters.py      # IFC/OSHA/USAspending/NOAA normalization adapters
├── construction.py  # construction roles, policies and reference project
└── foundry.py       # train/IID/OOD/adversarial distribution generation
```

## Core environment semantics

### Partial observability and authority

Every role has explicit readable/writable namespaces, direct financial authority and approval/delegation capabilities. Observations are projections of one underlying project state, so an architect, quantity surveyor, site manager and owner can see different slices without creating inconsistent copies of reality.

### Actions

Actions are checked against current phase, role permission, target scope, state prerequisites, required evidence, activity dependencies, elapsed duration, shared-resource capacity, direct financial authority and remaining budget. Accepted actions update state immediately and/or schedule future effects. Reversible actions can be compensated while irreversible actions remain in the trace.

### Event-driven time

`advance(ticks)` applies delayed consequences, releases hidden exogenous events, accrues active-resource cost and changes subsequent observations. The reference construction episode includes weather disruption, a long-lead procurement delay and a safety hold. These remain private oracle events until they occur.

### Construction domain pack

The role roster includes owner, owner's representative, project director, project manager, architect, structural engineer, MEP engineer, quantity surveyor, BIM coordinator, procurement manager, contract administrator, site manager, superintendent, safety manager, QA/QC inspector, subcontractor and commissioning manager.

The action surface includes design review/approval, RFIs, submittals, work-package creation/release, procurement and expediting, activity execution, schedule/progress updates, risk mitigation, stop-work, inspection/acceptance/rework, change orders, payment certification, commissioning, handoff and project acceptance.

## Verification

The private verifier evaluates requirements, quality, schedule, cost, safety, coordination, authority, process discipline, evidence discipline and handover. It separately counts unauthorized attempts, prerequisite violations, resource conflicts, missing evidence, rework and irreversible errors. Critical outcome failures impose direct penalties.

This supports multiple successful trajectories while rejecting superficially plausible but operationally invalid ones.

## Source fusion

`construction_source_manifest()` registers the following source families for calibration and scenario generation:

| Source | Primary use |
| --- | --- |
| GNI BIM Dataset (2026) | IFC geometry/semantics, elements and quantity priors |
| buildingSMART official sample/test files | IFC conformance and verifier fixtures |
| buildingSMART community sample/test files | broader examples plus edge/invalid cases |
| IFC-Bench | held-out BIM reasoning and sequencing tasks |
| OSHA Severe Injury Reports | construction hazard/event priors |
| OSHA enforcement/data downloads | inspection/citation/violation distributions |
| USAspending contract awards | supplier, work-package, contract and cost priors |
| NOAA GHCNh | hourly weather and weather-delay priors |
| USGS 3DEP | terrain, grade, drainage and earthwork context |
| OpenStreetMap | road/access/logistics and site context |

Every normalized fact has a canonical object, field, source, confidence, authority rank, observation time and provenance. `fuse_records()` resolves a winning value by authority/confidence/freshness while retaining conflicting alternatives, so disagreement remains available for adversarial and epistemic-state tasks.

The first adapters cover parsed IFC rows, OSHA incidents, USAspending awards, NOAA hourly observations and site/geospatial records. They accept ordinary mappings rather than binding the runtime to a storage backend, allowing large datasets to remain on external storage and stream through normalization jobs.

## YouTube / procedural corpus

The manifest seeds a construction procedural-video registry covering construction project management, Primavera P6 scheduling, BIM coordination, preconstruction, procurement/cost control and quantity surveying. Sources with verified duration in the initial registry total about 5.7 hours.

The repository does **not** bundle copyrighted transcript text. `chunk_transcript()` accepts an authorized transcript export or local transcript file and produces overlapping provenance-preserving chunks. `transcript_chunks_to_evidence()` exposes those chunks as searchable project evidence. This lets the procedural corpus scale independently of the environment schema.

## Foundry distributions

`generate_construction_distribution()` uses Veritas's existing `DistributionSplit` abstraction:

- `train`: calibrated baseline variation;
- `iid_test`: held-out seeds under comparable priors;
- `ood`: longer durations, higher costs, resource pressure and changed event distributions;
- `adversarial`: tighter budgets, earlier hidden disruptions, constrained resources and plausible non-authoritative distractor evidence.

Every generated episode receives a stable hash, generator parameters and difficulty vector. This makes the task distributions suitable for RL training, benchmark releases, model-to-model comparisons and longitudinal capability evaluation.

## Example

```python
from investigation_world.projectworld import (
    OperationalProjectWorldRuntime,
    ProjectAction,
    ProjectActionType,
    ProjectRole,
    construction_episode,
)

episode = construction_episode()
runtime = OperationalProjectWorldRuntime(episode)

observation = runtime.observation_for(ProjectRole.PROJECT_MANAGER)

runtime.act(
    ProjectRole.PROJECT_MANAGER,
    ProjectAction(
        action_type=ProjectActionType.APPROVE_DESIGN,
        target_object_type="design",
        target_object_id="D-001",
        evidence_ids=["EV-DESIGN-REVIEW"],
    ),
)

runtime.advance(1)
score = runtime.verify()
```

## Deliberate v1 boundaries

This implementation establishes the executable state/control substrate and data-fusion contracts. It does not claim to embed a complete structural solver, CFD engine, BIM authoring application, Primavera clone or construction economics package. Those should attach as tool-backed domain capabilities while `OperationalProjectWorld` remains the authoritative project-state, causal-event and verification layer.

High-value extensions are native IFC parsing via an optional `ifcopenshell` extra; CPM/PERT and resource leveling; location-aware NOAA/USGS/OSM ingestion; quantity-to-cost assemblies; richer contract/RFI/submittal state machines; BIM clash/IDS verification; and trajectory calibration against larger authorized project-management corpora.
