# Build status

## Version

Current benchmark/runtime candidate: **0.9.0**.

## Implemented

### Veritas capability-foundry stack

- Deterministic hidden canonical world generation with typed entities and event-sourced temporal relationship intervals.
- Leakage-safe evidence projection and strict public/private task/oracle separation.
- Source-aware search surfaces, isolated executable episode runtimes, budgets, trace storage, replay, counterfactuals and failure mining.
- CompanyWorld, External Investigation, Selective Agency, Continuous Capability Observatory, Reality Calibration, ProjectWorld and Verified Training Product primitives remain first-class capabilities under one Veritas product facade.
- Persistent operational substrate with organization-scoped state, append-only event history, deterministic reconstruction, snapshots, counterfactual forks and persistent entity/relation graph.

### Unified Operational Worlds Production v3

Five operational domains still share one runtime and the same seven-dimensional verification contract:

1. Financial / Spreadsheet
2. Enterprise Operations
3. DevOps / Incident Response
4. Investigation / OSINT
5. GIS Operations

The verifier dimensions remain **outcome, state, constraints, side effects, process, efficiency and evidence**. v0.9 adds native artifact execution behind that contract rather than adding a new reward surface.

### Native artifact execution

Every generated operational episode carries a deterministic, opaque, lazy `NativeArtifactDescriptor`. Artifacts are materialized only when a rollout needs them, keeping the 4,480-case distribution lightweight.

Current engines:

- Financial / Spreadsheet: `openpyxl-workbook-v1` — real XLSX workbook mutation and checks.
- Enterprise Operations: `sqlite-enterprise-replica-v1` — CRM/CPQ/ERP/IAM/credit/audit relational replica.
- DevOps / Incident Response: `declarative-kubernetes-sandbox-v1` — Kubernetes-style manifests plus executable cluster/telemetry state.
- Investigation / OSINT: `rendered-evidence-corpus-v1` — registry JSON, archive HTML, directory CSV and mutable casefile.
- GIS Operations: `shapely-pyproj-vector-v1` — real GeoJSON reprojection, geometry repair and overlay execution.

`NativeOperationalRuntime` mirrors only successful, unblocked operational transitions into the artifact. Native checks are injected into hidden target state before the ordinary verifier runs, so an agent cannot receive full outcome/state credit while leaving the actual artifact incorrect.

### Parameterized native fidelity

`ParameterizedNativeArtifactWorkspace` derives materialized bytes and validation targets from each procedurally generated episode rather than reference-case constants.

This currently covers generated variation in:

- spreadsheet formula ranges, sheet/cell targets and enterprise value;
- enterprise deal/order/account/control state;
- DevOps service identity and recovered error-rate target;
- OSINT identities, companies and supported resolution;
- GIS source/target layers and CRS pair.

A regression test executes a non-reference generated training case from every domain and requires both native artifact validity and 1.0 shared state/outcome scores.

### Stateful operational semantics retained

v0.9 preserves the v0.8 deep semantics:

- hidden state preconditions on action effects;
- hidden required-prior-action conditions;
- blocked system responses when prerequisites are not met;
- blocked actions do not mutate truth or satisfy required process steps;
- ordered and repeated required procedures;
- threshold/tolerance assertions;
- final-state and trajectory-wide (`always`) invariants;
- temporal/provenance-rich public records.

### Production-scale distributions retained

Operational distribution remains exactly **4,480 executable episodes**:

- train: 512 per domain / 2,560 total;
- IID test: 128 per domain / 640 total;
- OOD: 128 per domain / 640 total;
- adversarial: 128 per domain / 640 total;
- 896 cases per domain across all five domains.

The v3 operational compiler retains opaque IDs, split/oracle isolation, deterministic fingerprints, deep-realism constraints and anti-leakage checks, and additionally validates native engine assignment, opaque artifact IDs and source-record lineage for every episode.

ProjectWorld remains a separate long-horizon environment family with a default **896-project** construction distribution and its own versioned runtime/verifier contract.

See:

- `docs/operational-production-scale.md`
- `docs/domain-realism-v08.md`
- `docs/native-artifact-fidelity-v09.md`
- `docs/projectworld-procedural-distribution.md`

## Native fidelity release gate

CI now has a dedicated `Native artifact fidelity` job:

```bash
veritas validate-native-fidelity --seed 42 --cases-per-split 8
```

It deterministically selects and executes one case from every operational **domain × split** cell:

- 5 domains;
- train, IID, OOD and adversarial;
- **20 native artifact executions** total.

For each sampled case the evaluator procedure must execute without blocked/missing transitions, the actual artifact must pass every native check, and submission through the ordinary verifier must achieve state=1.0 and outcome=1.0.

This complements, rather than replaces, exhaustive descriptor/integrity validation over all 4,480 cases.

## Regression coverage

The test suite covers the existing Veritas contract plus:

- real XLSX creation/mutation and formula-state validation;
- SQLite enterprise state transitions and audit history;
- declarative infrastructure recovery state;
- heterogeneous OSINT corpus/casefile mutation;
- pyproj reprojection, Shapely geometry repair and overlay creation;
- native artifact tampering reducing ordinary verifier state/outcome scores;
- generated-case parameter propagation into native artifacts;
- state-gated actions and blocked transitions;
- ordered/repeated process verification;
- transient trajectory-invariant detection;
- deep public/private leakage checks;
- preservation of all operational and ProjectWorld distribution gates.

## CI release gate

Merge is gated on the exact candidate head passing:

- Python 3.12 tests;
- Python 3.13 tests;
- package build;
- environment/unified-product smoke tests;
- native artifact fidelity across all 20 domain × split cells;
- full **4,480-case** operational distribution validation;
- full **896-project** ProjectWorld distribution validation;
- Next.js build;
- container build and API health;
- aggregate `Required` status;
- Security source and dependency checks.

## Remaining fidelity work

v0.9 is **native artifact fidelity**, not universal industrial simulation.

Remaining high-value integrations include:

- a broader Excel-compatible calculation engine for arbitrary formulas, macros, Power Query and external links;
- live Kubernetes/container/network sandboxes plus Terraform/cloud-provider control planes;
- vendor-deeper enterprise application replicas and richer transactional failure modes;
- browser-scale rendered web, OCR/image-heavy investigation corpora and larger search surfaces;
- raster GIS, GDAL/PostGIS-scale execution and rendered map products;
- deeper cross-domain causal propagation and long-horizon multi-episode operational tasks;
- empirical calibration of artifact/state distributions and failure rates against real operational data.

These should plug behind the existing `TaskContract -> Runtime -> HiddenOracle -> seven-dimensional verifier` boundary rather than fragmenting Veritas into incompatible products.
