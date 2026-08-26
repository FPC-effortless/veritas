# Veritas Unified Operational Worlds

Veritas is a unified operational-world capability foundry for training and evaluating agents on economically valuable work with independently verifiable outcomes.

The product is not a collection of unrelated benchmarks. Every operational domain runs on the same architecture:

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
  -> train / IID / OOD / adversarial distributions
  -> trajectory / benchmark / training product
```

## Product surface

`investigation_world.veritas.Veritas` is the canonical Python entry point. Five first-class domains share the substrate/runtime/verifier contract:

1. `financial_spreadsheet`
2. `enterprise_operations`
3. `devops_incident_response`
4. `investigation_osint`
5. `gis_operations`

The same facade inventories the wider Veritas product: CompanyWorld, External Investigation, Selective Agency, Capability Foundry, Continuous Capability Observatory, Reality Calibration and Verified Training Products.

## Shared episode contract

Each `OperationalEpisode` contains a public `TaskContract`, agent-visible records and public action specifications, while evaluator-only truth lives in `HiddenOracle`.

The private oracle contains target state, invariants, hidden action effects, required/forbidden actions, evidence requirements and resource bounds. Episode construction rejects malformed contracts, including duplicate records/actions, actions on non-permitted systems, required/forbidden contradictions, missing evidence and oracle effects that reference unknown actions or undeclared parameters.

`OperationalEpisode.public_payload()` excludes oracle state. `OperationalRuntime.act()` likewise returns only system-observable action information; hidden state changes, consequence severity, forbidden-action status and hidden side effects remain harness/verifier data.

## Persistent operational substrate

`PersistentOperationalSubstrate` is the truth authority for multi-domain Veritas worlds. It provides:

- organization-scoped persistent state;
- multi-domain episode mounting without state reset;
- append-only state events;
- episode-owned record isolation;
- persistent `OperationalEntity` and `OperationalRelation` graph;
- domain/entity-filtered graph traversal;
- deterministic `state_at(sequence)` reconstruction;
- snapshots and event history;
- `fork_at(sequence)` for replay and counterfactual branches;
- integrity checks over state, event ordering, relation endpoints and world/domain ownership.

`Veritas.build_company()` mounts all five domains into one `VeritasCompany` and populates its shared entity graph from domain records. That gives later work a persistent company state rather than forcing every task to begin from an unrelated toy environment.

## Verification contract

All operational worlds emit the same seven dimensions:

1. **Outcome** — was the objective achieved?
2. **State** — do independently checked target assertions hold?
3. **Constraints** — were invariants and authority boundaries preserved?
4. **Side effects** — did execution create unnecessary or harmful consequences?
5. **Process** — were required operational steps completed?
6. **Efficiency** — was resource use proportionate?
7. **Evidence** — is the required evidence supplied?

The aggregate reward currently uses:

```text
0.30 outcome
+ 0.20 state
+ 0.15 constraints
+ 0.10 side effects
+ 0.10 process
+ 0.05 efficiency
+ 0.10 evidence
```

Domain-native verifiers may add richer checks but should emit into this common contract rather than redefining success.

## Production-scale distribution

Veritas 0.7 adds `OperationalDistributionConfig` and a deterministic compiler for the five-domain operational suite.

Default scale:

| Split | Per domain | Total |
|---|---:|---:|
| Train | 512 | 2,560 |
| IID test | 128 | 640 |
| OOD | 128 | 640 |
| Adversarial | 128 | 640 |
| **Total** | **896** | **4,480** |

Every case remains an executable `OperationalEpisode`; the scale layer does not reduce the environment to prompt/label rows.

Current domain parameterizers vary operational state and identifiers:

- **Financial / Spreadsheet:** sheet/cell locations, formula windows, valuation outcomes and units.
- **Enterprise Operations:** deal/order IDs, accounts, discounts and transaction amounts.
- **DevOps / Incident Response:** services, deployments, databases, error rates, latency and pod state.
- **Investigation / OSINT:** companies, abbreviated/true/decoy identities, addresses, registry numbers and historical dates.
- **GIS Operations:** layer identities, target overlays, CRS pairs, feature counts and geometry defects.

The evaluator bundle also tracks scenario-family, surface-profile and `DifficultyVector` metadata. OOD cases increase unfamiliarity/noise. Adversarial cases introduce conflicting context, tighter resource budgets and high adversarial pressure.

## Split and oracle privacy

Per-case split assignment is private. Public IDs are opaque stable-hash identifiers rather than containing split or generator-seed text. Public cases are deterministically hash-mixed rather than emitted in split blocks.

The public bundle excludes:

- split;
- generator seed;
- scenario-family label;
- surface-profile label;
- difficulty vector;
- hidden target state;
- hidden action effects;
- forbidden-action labels;
- evaluator oracle.

The private evaluator bundle retains those values. The compiler produces separate public and private fingerprints, and distribution validation checks count integrity, task/world uniqueness, train/held-out disjointness, leakage and adversarial conditions.

See [`operational-production-scale.md`](operational-production-scale.md) for the full scale/integrity specification.

## Domain coverage

### Financial / Spreadsheet

The reference execution contract covers formula repair, recalculation, dependency evidence, model invariants and destructive hard-code failure. The production generator varies workbook/formula state over thousands of possible cases. Native XLSX/formula-DAG execution is a separate fidelity extension.

### Enterprise Operations

The reference execution contract spans CRM + ERP approval state, authority routing, order holds and segregation-of-duties controls. The production generator varies customer/deal/order/discount/value state. Broader ERP/CRM/HRIS/ITSM replicas are a fidelity extension.

### DevOps / Incident Response

The reference execution contract covers observability, service recovery, dependency health, blast-radius control and recovery verification. The production generator varies services, databases, deployments, latency, errors and replica health. Native Kubernetes/Terraform sandboxes are a fidelity extension.

### Investigation / OSINT

The reference execution contract covers evidence-backed identity resolution, provenance and false-merge prevention and interoperates conceptually with Veritas External Investigation. The production generator varies entities, decoys, addresses, filings and historical evidence. Larger evidence corpora and richer semantic entailment are fidelity extensions.

### GIS Operations

The reference execution contract covers CRS alignment, geometry repair, topology validity and source preservation. The production generator varies layers, overlays, CRS combinations, feature counts and defects. Native vector/raster artifact execution is a fidelity extension.

## CLI

```bash
veritas capabilities
veritas domains
veritas build-world financial_spreadsheet --seed 42 --output finance.json
veritas build-suite --seed 42 --output suite.json --oracle-output reference_oracles.json
veritas build-distribution --seed 42 --output public.json --oracle-output private.json
veritas validate-production-scale --seed 42
veritas build-company --organization-id ORG-DEMO-001 --seed 42 --output company.json
```

The legacy `iworld` CLI remains available for backwards compatibility.

## CI production gate

The required CI workflow contains a dedicated `Production-scale operational distribution` job. It installs the package and runs the default 4,480-case compiler/validator. This job is included in the `Required` aggregate gate alongside Python 3.12/3.13 tests, package build, environment smoke tests, frontend build and container health.

## Foundry integration

The production distribution remains part of the existing Veritas learning/evaluation lifecycle:

```text
reality calibration
-> deterministic world generation
-> train / IID / OOD / adversarial distribution
-> executable runtime
-> trace capture
-> independent verification
-> failure mining
-> challenge mutation
-> verified demonstration / preference / RL / VOPSD products
-> held-out observatory re-evaluation
```

Training algorithms remain outside environment truth. SFT, preference learning, RL and VOPSD consume verifier-qualified outputs; none is allowed to define the hidden target or verifier.

## Remaining depth work

The procedural synthetic distribution is now production-scale in volume, split integrity, reproducibility, adversarial pressure and CI validation. Further work is primarily depth/fidelity:

1. deepen scenario-family semantics instead of relying primarily on domain parameterization;
2. link the shared entity graph into a richer causal graph with consequences propagating between domains;
3. add native XLSX, enterprise-app/database, Kubernetes/Terraform, evidence-corpus and GIS artifact engines;
4. compile long-horizon cross-domain tasks over persistent multi-episode histories;
5. add native verifier plugins while preserving the common seven-dimensional score contract;
6. empirically calibrate difficulty and realism against public data, telemetry and expert procedures;
7. add distributed runtime persistence and private commercial benchmark/oracle registries.

Those improvements strengthen fidelity without fragmenting Veritas into separate domain products.
