# Build status

## Version

Current benchmark/runtime version: **0.7.0**.

## Implemented

### Existing Veritas capability-foundry stack

- Deterministic hidden canonical world generation with typed entities and event-sourced temporal relationship intervals.
- Temporal ownership transfers, residence changes, organization renames, dissolutions, and historical state queries.
- Leakage-safe evidence projection using public names/aliases rather than canonical entity IDs.
- Six source families with source-conditioned omission, staleness, partial truth, false claims, and citation dependence.
- Citation provenance DAG and independent-root reasoning.
- Source-aware SQLite FTS5 search surfaces for web, registry, filing, archive, and general document search.
- Isolated FastAPI episode sessions with per-episode hidden world/oracle, search index, budget, and public task.
- External Investigation capability family: entity resolution, ownership reconstruction, temporal reconstruction, provenance, conflict resolution, and due diligence.
- CompanyWorld enterprise-control capability family with investigation, action, sequential control and dynamic work.
- Selective Agency capability family with execute/clarify/reframe/decline/no-op judgment and procedural train/IID/OOD/adversarial cases.
- Trace-first foundry runtime, trace storage, replay descriptors, counterfactual branches, failure-to-challenge mapping, task-distribution control and moving learnability frontier.
- Continuous Capability Observatory infrastructure for longitudinal world/model/harness/seed/snapshot evaluation.
- Expert-trajectory primitives for verifier-qualified demonstrations, recovery/counterfactual roles and preference pairs.
- Reality-calibration primitives for provenance-backed calibration sources, distribution targets, dependency targets, procedure priors and calibration reports.
- Trainer-product boundary for SFT, preference learning, RL and VOPSD with verifier thresholds, invariant gates, split isolation and trace provenance.
- Trajectory recorder plus JSONL/Parquet export and failure labels.

### Unified Operational Worlds Production v1

- One canonical `Veritas` product facade and capability catalog spanning Unified Operational Worlds, CompanyWorld, External Investigation, Selective Agency, Capability Foundry, Continuous Capability Observatory, Reality Calibration, and Verified Training Products.
- Five first-class operational domains under one runtime/verifier contract:
  - Financial / Spreadsheet
  - Enterprise Operations
  - DevOps / Incident Response
  - Investigation / OSINT
  - GIS Operations
- `PersistentOperationalSubstrate` with organization-scoped state, append-only cross-domain event history, deterministic state reconstruction, snapshots, and counterfactual forks.
- Persistent `OperationalEntity` / `OperationalRelation` graph generated from domain records and shared organization scope.
- Episode-owned record isolation so domains do not mix records merely because they use the same underlying system family.
- `VeritasCompany` for mounting all five domains into one persistent synthetic organization.
- Shared public `TaskContract`, agent-visible `OperationalRecord`, public actions, private `HiddenOracle`, hidden action effects, target-state assertions, invariants, evidence requirements, and budgets.
- Construction-time world integrity checks for action uniqueness, permitted systems, oracle action references, required/forbidden contradictions, evidence existence, parameter declarations, record IDs, and invariant IDs.
- Oracle-safe action boundary: public action results do not expose forbidden-action status, hidden state changes, hidden side effects, or consequence severity; those remain in harness/verifier traces.
- Shared seven-dimensional operational verifier: outcome, state, constraints, side effects, process, efficiency, and evidence.

### Production-scale distribution

The default `OperationalDistributionConfig` compiles **4,480 executable episodes**:

- train: 512 per domain / 2,560 total;
- IID test: 128 per domain / 640 total;
- OOD: 128 per domain / 640 total;
- adversarial: 128 per domain / 640 total;
- 896 cases per domain across five domains.

Production-distribution features implemented:

- deterministic case generation from a versioned seed;
- domain-specific state/data parameterization rather than prompt-only duplication;
- multiple evaluator scenario-family labels per domain;
- split-specific distractor, OOD and adversarial pressure;
- tighter adversarial budgets and conflicting-context records;
- `DifficultyVector` metadata in the evaluator package;
- opaque public world/task/record identifiers rather than split/seed-bearing IDs;
- deterministic hash-mixed public ordering rather than split-grouped output;
- strict public/private packaging: split, generator seed, scenario-family label, surface profile, difficulty vector and oracle remain evaluator-only;
- public and private distribution fingerprints;
- exact count, uniqueness, split isolation, leakage and adversarial-integrity validation;
- `veritas build-distribution` and `veritas validate-production-scale` CLI commands;
- scale can be raised parametrically without changing the runtime contract.

See `docs/operational-production-scale.md` for the exact production-scale contract.

## Regression coverage

The test suite covers, among other existing behaviors:

- deterministic world/evidence generation;
- public/canonical leakage boundaries;
- public-task/private-oracle separation;
- train/public/private split disjointness;
- reward-hacking regressions;
- source-aware tool surfaces and per-episode budget isolation;
- held-out trajectory exclusion from training bundles;
- all five operational-domain registrations;
- unified operational public/private oracle isolation;
- oracle-safe action response behavior;
- deterministic operational target-state verification;
- forbidden-action and invariant-violation penalties;
- persistent company organization scoping;
- episode-owned domain record isolation;
- shared entity/relation graph construction;
- cross-domain substrate mounting and event sequencing;
- point-in-time state reconstruction and counterfactual fork behavior;
- unified capability catalog membership;
- production-distribution domain/split coverage;
- deterministic production hashes and IDs;
- procedural parameter diversity;
- public split/seed/family/oracle leakage prevention;
- adversarial conflict and pressure requirements;
- unified CLI smoke paths.

## CI status

The original concern that GitHub Actions was not running was a timing/observation issue rather than a disabled Actions configuration. GitHub created the pull-request CI and Security runs after a short event/indexing delay. The exact v0.6 final head subsequently completed both CI and Security successfully.

The v0.7 production-scale changes add a required `Production-scale operational distribution` CI job. That job compiles and validates the full **4,480-case** default distribution, and it has completed successfully on the production-scale branch head. Python 3.12/3.13 tests, package build, unified-product smoke paths, frontend build, container-health checks and Security checks are also required before merge.

An external Vercel deployment status may still report account-level build-rate limiting. That is separate from the repository CI/security gates and does not indicate a Veritas application-test failure.

## Remaining fidelity and infrastructure work

The procedural benchmark/runtime distribution is production-scale in case volume, split management, reproducibility, adversarial pressure and CI validation. Remaining work is primarily **fidelity and deployment depth**, not the absence of a scale layer:

- deepen scenario-family semantics beyond the current parameterized base contracts;
- deepen the shared entity graph into a causal operational graph so customers, employees, suppliers, facilities, applications, assets, accounts and parcels propagate consequences across domains;
- domain-native artifact engines for real XLSX/formula DAG execution, containerized Kubernetes/Terraform infrastructure, enterprise database/application replicas, large evidence corpora and native vector/raster GIS artifacts;
- long-horizon cross-domain task compilation over persistent multi-episode histories;
- native verifier plugins for spreadsheet dependency graphs, infrastructure health, enterprise consistency, OSINT evidence entailment and geospatial output artifacts while retaining the shared score contract;
- private benchmark registry and commercial oracle storage;
- concrete trainer runners/adapters for SFT, preference learning, RL and VOPSD;
- calibration-aware procedural generators and automated calibration-report gates;
- larger adversarial transformation library and empirical difficulty calibration;
- production orchestration persistence and multi-process/distributed episode storage;
- frontend benchmark/operator console for the unified operational suite.
