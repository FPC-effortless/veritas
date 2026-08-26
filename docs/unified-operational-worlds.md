# Veritas Unified Operational Worlds

Veritas is a unified operational-world capability foundry for training and evaluating agents on economically valuable, long-horizon work with independently verifiable outcomes.

The product is not a collection of unrelated benchmarks. Every domain runs on the same substrate:

```text
Operational World
  -> public TaskContract
  -> system records + tools
  -> agent actions
  -> deterministic state transitions
  -> append-only action journal
  -> hidden evaluator oracle
  -> independent multi-layer verifier
  -> reward + diagnostics
  -> trajectory / benchmark / training product
```

## Product surface

`investigation_world.veritas.Veritas` is the canonical entry point for the operational suite. It builds episodes and runtimes for five first-class domains:

1. `financial_spreadsheet`
2. `enterprise_operations`
3. `devops_incident_response`
4. `investigation_osint`
5. `gis_operations`

Existing CompanyWorld, External Investigation, Selective Agency, calibration, observatory, tracing, and training-product modules remain capability layers of Veritas. The unified substrate is the common execution and verification contract beneath new domain worlds.

## Shared episode contract

Each `OperationalEpisode` contains:

- a public `TaskContract`;
- agent-visible `OperationalRecord` objects;
- public action specifications;
- evaluator-only `HiddenOracle` state;
- deterministic hidden action effects;
- target state assertions;
- invariants;
- required and forbidden actions;
- evidence requirements;
- tool-call and cost budgets.

`OperationalEpisode.public_payload()` explicitly omits the oracle. Evaluated agents must never receive evaluator targets, hidden effects, forbidden-action labels, or private ground truth.

## Runtime

`OperationalRuntime` provides the shared executable interface:

- `search(system, query)`
- `search_all(query)`
- `open_record(record_id)`
- `act(action_name, **parameters)`
- `budget_snapshot()`
- `trace()`
- `submit(submission)`

Every action is journaled with system, kind, parameters, cost, realized state changes, side effects, forbidden-action status, and consequence severity. The harness owns this trace; the evaluated agent cannot self-report its way to a higher score.

## Verification contract

All operational worlds are scored on the same seven dimensions:

1. **Outcome** — was the objective actually achieved?
2. **State** — do verified target state assertions hold?
3. **Constraints** — were invariants and authority boundaries preserved?
4. **Side effects** — did the agent cause harmful or unnecessary changes?
5. **Process** — were required operational steps completed?
6. **Efficiency** — was work completed within reasonable action/tool budgets?
7. **Evidence** — are required supporting records present?

The aggregate reward is currently:

```text
0.30 outcome
+ 0.20 state
+ 0.15 constraints
+ 0.10 side effects
+ 0.10 process
+ 0.05 efficiency
+ 0.10 evidence
```

Domain-specific verifiers can later add richer metrics, but they should emit into this shared contract rather than replacing it.

## Financial / Spreadsheet Operational World

The initial executable scenario is a DCF repair task. It models workbook formulas, dependency trees, audit checks, recalculation, formula-lineage invariants, and destructive hard-code failure modes.

The next expansion should add:

- multi-sheet three-statement models;
- circular-reference and broken-link faults;
- scenario tables and sensitivities;
- pivot/table/chart operations;
- formula provenance and dependency DAGs;
- accounting reconciliation;
- valuation and covenant checks;
- train/IID/OOD/adversarial workbook generators.

## Enterprise Operations World

The initial scenario spans CRM + ERP state for a high-value discount approval. It verifies cross-system consistency, authority routing, order holds, and segregation-of-duties constraints.

The intended world expands to CRM, ERP, HRIS, ITSM, email, documents, approvals, accounting, procurement, inventory, and analytics within one persistent synthetic company.

## DevOps / Incident-Response World

The initial scenario models an API outage with observability, Kubernetes, and database surfaces. The correct solution restores the failing service, verifies recovery, and leaves a healthy database untouched.

The intended expansion includes:

- Kubernetes clusters;
- Terraform/IaC state;
- deployment and rollback workflows;
- logs, metrics, traces, alerts, and SLOs;
- network and DNS failures;
- security incidents;
- dependency graphs and blast-radius constraints;
- multi-stage incident timelines.

## Investigation / OSINT World

The initial operational episode bridges Veritas's existing investigation capability into the shared substrate through identity resolution, evidence linking, provenance requirements, and false-merge penalties.

The mature domain should continue to use the existing richer investigation generator and verifier while exposing compatible operational task/runtime metadata for cross-domain evaluation and training.

## GIS Operational World

The initial scenario verifies CRS alignment, geometry repair, topology validity, and source preservation for a parcel/flood-zone workflow.

The intended expansion includes:

- vector and raster workflows;
- spatial joins and overlays;
- network/routing operations;
- projection correctness;
- topology and geometry checks;
- geoprocessing pipelines;
- exact/tolerance-aware output-file verification.

## Unified company substrate

The strategic end state is a persistent synthetic organization rather than five isolated environments:

```text
Company identity and actors
  + CRM / ERP / HRIS / finance
  + workbooks and models
  + cloud infrastructure and incidents
  + documents / messages / approvals
  + public records and external evidence
  + sites, parcels, routes, and geospatial assets
  + hidden causal ground truth
  + event history
  + authority and policy graph
```

A single generated organization can therefore emit finance, enterprise operations, DevOps, investigation, GIS, selective-agency, cross-application, and long-horizon tasks while preserving shared identities and causal history.

## Foundry integration

The shared substrate is designed to feed the existing Veritas foundry lifecycle:

```text
world generation
-> task distribution
-> executable runtime
-> trace capture
-> independent verification
-> failure mining
-> adversarial mutation
-> held-out benchmark
-> verified demonstrations / preferences / RL trajectories / VOPSD inputs
-> observatory re-evaluation
```

Training algorithms remain outside environment truth. SFT, RL, preference learning, and VOPSD may consume verified trajectories, but none is allowed to define success.

## Immediate engineering sequence

The current implementation establishes the common substrate and one executable reference scenario per domain. The next implementation layers should be built in this order:

1. persistent cross-domain entity/state/event store;
2. procedural generators that create hundreds to thousands of tasks per domain;
3. domain-native artifact engines (workbooks, containers, GIS files, enterprise DB state);
4. cross-domain task compiler using one persistent company;
5. domain-specific verifier plugins that emit the shared seven-part score;
6. private split/oracle packaging for commercial benchmarks;
7. rollout adapters and verified training-product exporters;
8. observatory cells spanning world x model x harness x seed x snapshot.

This makes the five environments one Veritas product rather than five codebases.
