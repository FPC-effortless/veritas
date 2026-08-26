# Build status

## Version

Current benchmark/runtime candidate: **0.8.0**.

## Implemented

### Veritas capability-foundry stack

- Deterministic hidden canonical world generation with typed entities and event-sourced temporal relationship intervals.
- Leakage-safe evidence projection and strict public/private task/oracle separation.
- Source-aware search surfaces, isolated executable episode runtimes, budgets, trace storage, replay, counterfactuals and failure mining.
- CompanyWorld, External Investigation, Selective Agency, Continuous Capability Observatory, Reality Calibration and Verified Training Product primitives remain first-class capabilities under one Veritas product facade.
- Persistent operational substrate with organization-scoped state, append-only event history, deterministic reconstruction, snapshots, counterfactual forks and persistent entity/relation graph.

### Unified Operational Worlds Production v2

Five operational domains share one runtime and the same seven-dimensional verification contract:

1. Financial / Spreadsheet
2. Enterprise Operations
3. DevOps / Incident Response
4. Investigation / OSINT
5. GIS Operations

The shared verifier dimensions remain **outcome, state, constraints, side effects, process, efficiency and evidence**. v0.8 deepens how those dimensions are earned; it does not introduce incompatible domain-specific reward surfaces.

### Stateful operational semantics

v0.8 adds:

- hidden state preconditions on action effects;
- hidden required-prior-action conditions;
- realistic blocked system responses when prerequisites are not met;
- blocked actions do not mutate truth and do not satisfy required process steps;
- ordered required procedures inside the existing process score;
- repeated required action counts;
- richer assertion comparisons, including threshold checks;
- final-state and trajectory-wide (`always`) invariants;
- transient invariant violations remain detectable even when later repaired;
- temporal/provenance-rich public records with validity interval, observation time, freshness, source authority, confidence and provenance roots.

### Deep financial / spreadsheet cases

Production cases now include workbook manifests, formula-lineage/dependency graphs, calculation chains, authoritative ledger reconciliation, model-governance policy and review context.

Representative workflow:

`inspect lineage -> reconcile source -> repair formula -> recalculate -> validate controls`

Artifact contract: `xlsx_formula_dependency_graph_v2`.

### Deep enterprise-operations cases

Production cases now span CRM, CPQ, ERP, IAM and finance-control evidence. They include role/authority assignments, credit profiles, quote versions, order state, customer/account context and immutable audit events.

Representative workflow:

`verify authority -> validate credit -> request approval -> hold order -> update stage -> reconcile systems`

Artifact contract: `crm_cpq_erp_control_graph_v2`.

### Deep DevOps / incident-response cases

Production cases now include change-management evidence, deployment state, distributed dependency graphs, log signatures, SLI windows, SLO policy and Kubernetes deployment specifications.

Representative workflow:

`correlate change -> inspect dependencies -> recover service -> verify health -> validate SLO`

Artifact contract: `incident_telemetry_dependency_graph_v2`.

### Deep investigation / OSINT cases

Production cases now include explicit hypothesis state, repeated evidence linking, source provenance, independence metadata, identifier crosswalks, negative evidence, archived reporting and chain-of-custody invariants.

Representative workflow:

`record hypothesis -> resolve identity -> link independent evidence -> corroborate -> close case`

Artifact contract: `multi_source_provenance_casefile_v2`.

### Deep GIS cases

Production cases now include catalog metadata, CRS definitions, datum/axis-order context, spatial extent, topology rules, schema profiles, lineage and output contracts.

Representative workflow:

`inspect metadata -> reproject -> repair geometry -> validate topology -> execute overlay`

Artifact contract: `vector_crs_topology_lineage_v2`.

## Production-scale distribution

The default `OperationalDistributionConfig` remains **4,480 executable episodes**:

- train: 512 per domain / 2,560 total;
- IID test: 128 per domain / 640 total;
- OOD: 128 per domain / 640 total;
- adversarial: 128 per domain / 640 total;
- 896 cases per domain across all five domains.

The v2 compiler preserves the v0.7 scale/integrity guarantees and adds deep-realism validation:

- deterministic generation and fingerprints;
- opaque public world/task/record identifiers;
- hash-mixed public ordering;
- split, seed, scenario-family, surface-profile, difficulty and oracle remain evaluator-only;
- generator-only scenario fields are stripped before public packaging;
- literal private scenario labels are rejected if leaked publicly;
- difficulty vectors are recomputed after domain-depth expansion;
- every deep case must satisfy minimum system heterogeneity, action-surface depth, ordered procedure depth, temporal/provenance evidence, stateful preconditions and trajectory invariants;
- OOD/adversarial pressure and train/held-out isolation remain intact.

See `docs/operational-production-scale.md` and `docs/domain-realism-v08.md`.

## Regression coverage

The test suite covers the existing Veritas contract plus:

- state-gated actions and blocked transitions;
- blocked required actions not satisfying process credit;
- ordered process verification;
- repeated required actions;
- transient trajectory-invariant detection;
- threshold/tolerance assertions;
- deep-domain record/action/system minimums;
- opaque realism-layer record IDs;
- deep public/private leakage checks;
- preservation of all five domains and all four distribution partitions.

## CI release gate

The required workflow continues to gate merge on:

- Python 3.12 tests;
- Python 3.13 tests;
- package build;
- environment/unified-product smoke tests;
- Next.js build;
- container build and API health;
- the dedicated `Production-scale operational distribution` job, which compiles and validates all **4,480** default episodes;
- aggregate `Required` status;
- Security workflow checks.

v0.8 must pass this gate on the exact PR head before merge.

## Remaining fidelity work

v0.8 is materially deeper at the operational state, evidence, procedure, control and verification layers. It does **not** claim that every domain already runs a native industrial engine. The main remaining fidelity layer is:

- real XLSX files and formula-evaluation/dependency engines;
- containerized Kubernetes/Terraform/cloud sandboxes;
- richer enterprise application/database replicas;
- large rendered evidence/document corpora for investigation work;
- native vector/raster GIS execution and output-file verification;
- deeper cross-domain causal propagation and long-horizon multi-episode task compilation;
- empirical calibration against real operational distributions and failure rates.

Those engines should attach behind the existing `TaskContract -> Runtime -> HiddenOracle -> seven-dimensional verifier` boundary rather than fragmenting Veritas into incompatible products.
