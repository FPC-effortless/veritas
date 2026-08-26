# Veritas Unified Operational Worlds

Veritas is a unified operational-world capability foundry for training and evaluating agents on economically valuable, long-horizon work with independently verifiable outcomes.

The product is not a collection of unrelated benchmarks. Every operational domain runs on the same substrate:

```text
Persistent Operational Substrate
  -> shared entity / relation graph
  -> public TaskContract
  -> system records + public tools
  -> agent actions
  -> deterministic hidden state transitions
  -> append-only state/event journal
  -> private evaluator oracle
  -> independent multi-layer verifier
  -> reward + diagnostics
  -> replay / fork / counterfactual
  -> trajectory / benchmark / training product
```

## Product surface

`investigation_world.veritas.Veritas` is the canonical Python entry point. The operational suite currently contains five first-class domains:

1. `financial_spreadsheet`
2. `enterprise_operations`
3. `devops_incident_response`
4. `investigation_osint`
5. `gis_operations`

`Veritas.build_company()` mounts all five domains into one `PersistentOperationalSubstrate`. The resulting `VeritasCompany` has a shared organization identity, persistent state, a cross-domain entity/relation graph, append-only event history, deterministic snapshots, and counterfactual forks.

The same `Veritas` facade exposes a capability catalog covering the wider product rather than treating older modules as separate products:

- Unified Operational Worlds
- CompanyWorld
- External Investigation
- Selective Agency
- Capability Foundry
- Continuous Capability Observatory
- Reality Calibration
- Verified Training Products

Existing capability-family implementations remain intact and are unified at the product layer rather than duplicated.

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

Episode construction rejects malformed contracts, including duplicate public actions or records, actions on non-permitted systems, required/forbidden contradictions, oracle effects referencing unknown actions or undeclared parameters, missing required evidence records, and duplicate invariant IDs.

`OperationalEpisode.public_payload()` explicitly omits the oracle. Evaluated agents must never receive evaluator targets, hidden effects, forbidden-action labels, consequence severity, or private ground truth.

## Persistent operational substrate

`PersistentOperationalSubstrate` is the shared truth authority for multi-domain Veritas worlds. It provides:

- organization-scoped persistent state;
- mounting of multiple domain episodes without resetting state;
- append-only `OperationalStateEvent` transitions;
- shared record inventory with episode-based domain isolation;
- persistent `OperationalEntity` and `OperationalRelation` graph;
- domain- and entity-filtered graph traversal;
- domain- and world-filtered event history;
- deterministic `state_at(sequence)` reconstruction;
- point-in-time snapshots;
- `fork_at(sequence)` for replay and counterfactual branches;
- integrity validation over event ordering, reconstructed state, relation endpoints, world IDs, and domain ownership.

When a `VeritasCompany` is built, its agent-visible records are aggregated into persistent operational entities. Each entity preserves the domains, record types, systems, and source record IDs that describe it. Record relationships become typed graph edges, and the organization is linked to every operational object through the shared company scope.

This is the basis for long-horizon tasks in which earlier finance, enterprise, infrastructure, investigation, or GIS actions change the state encountered by later tasks.

## Public tool boundary

`OperationalRuntime` provides the shared executable interface:

- `search(system, query)`
- `search_all(query)`
- `open_record(record_id)`
- `act(action_name, **parameters)`
- `state_snapshot()` — harness-facing, not an evaluated-agent tool
- `budget_snapshot()`
- `trace()` — harness/verifier-facing
- `submit(submission)`

A runtime can operate as an isolated episode or attach to a persistent company substrate. Attached runtimes commit realized state changes and side effects into the shared event journal.

The tool boundary is intentionally asymmetric. `act()` returns only system-observable response data. Verifier-only information remains in the harness trace:

```text
agent sees:
  action name
  public system
  submitted/system-observable result

harness/verifier sees:
  hidden state changes
  hidden side effects
  forbidden-action status
  consequence severity
  action parameters and cost
```

This prevents reward-oracle leakage while still allowing the simulated system to return legitimate observable action results.

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

Domain-native verifiers can add richer checks, but they should emit into this shared contract rather than replacing it.

## Financial / Spreadsheet Operational World

The initial executable scenario is a DCF repair task. It models workbook formulas, dependency trees, audit checks, recalculation, formula-lineage invariants, and destructive hard-code failure modes.

The scale expansion should add:

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

The intended expansion covers CRM, ERP, HRIS, ITSM, email, documents, approvals, accounting, procurement, inventory, and analytics within one persistent synthetic company.

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

The implementation can mount all five worlds into one persistent synthetic organization:

```text
Company identity
  + typed operational entity graph
  + CRM / ERP operational state
  + workbook and financial-model state
  + cloud infrastructure and incident state
  + public-record / investigation state
  + parcel and geospatial state
  + hidden causal ground truth per task
  + append-only cross-domain event history
  + deterministic reconstruction and forks
```

The current entity graph gives the common substrate a stable identity layer. The next depth layer is stronger semantic and causal linking so the same customer, supplier, employee, facility, account, application, asset, parcel, and incident can participate in multiple domains and propagate consequences between them.

## Foundry integration

The shared substrate feeds the existing Veritas foundry lifecycle:

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

## CLI

The package retains `iworld` for backward compatibility and adds the canonical Veritas product CLI:

```bash
veritas capabilities
veritas domains
veritas build-world financial_spreadsheet --seed 42 --output finance.json
veritas build-suite --seed 42 --output suite.json --oracle-output private_oracles.json
veritas build-company --organization-id ORG-DEMO-001 --seed 42 --output company.json
```

Public episode bundles and evaluator-only oracle bundles are written separately. A company build also includes its public entity/relation graph, world payloads, snapshot, and event history.

## Immediate engineering sequence

The current implementation establishes the persistent state substrate, entity graph, shared runtime/verifier contract, capability catalog, and one executable reference scenario per domain. The next scaling layers should be built in this order:

1. procedural generators that create hundreds to thousands of tasks per domain with train/IID/OOD/adversarial partitions;
2. deepen the shared entity graph into a cross-domain causal graph with consequence propagation;
3. domain-native artifact engines for real workbook files, containerized infrastructure, enterprise database state, evidence corpora, and GIS files;
4. cross-domain task compiler using one persistent company and multi-episode temporal histories;
5. domain-specific verifier plugins that add native checks while emitting the shared seven-part score;
6. private split/oracle packaging and registry for commercial benchmarks;
7. rollout adapters and verified training-product exporters;
8. observatory cells spanning world x model x harness x seed x snapshot.

This makes the five environments one Veritas product rather than five codebases.
