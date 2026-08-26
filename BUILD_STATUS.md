# Build status

## Version

Current benchmark/runtime version: **0.6.0**.

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

### Unified Operational Worlds v1

- One canonical `Veritas` product facade and capability catalog spanning Unified Operational Worlds, CompanyWorld, External Investigation, Selective Agency, Capability Foundry, Continuous Capability Observatory, Reality Calibration, and Verified Training Products.
- Five first-class operational domains under one contract:
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
- Executable reference environments for:
  - DCF spreadsheet formula repair and recalculation;
  - CRM/ERP discount approval and authority control;
  - Kubernetes/API incident recovery and blast-radius control;
  - OSINT identity resolution and false-merge prevention;
  - GIS projection/topology repair and source preservation.
- Separate public-bundle/private-oracle packaging for the unified operational suite.
- Dedicated `veritas` CLI for capability discovery, domain discovery, single-world builds, five-world suite builds, and persistent company builds while retaining the legacy `iworld` CLI.
- CI configuration includes direct smoke paths for the unified CLI and company build.
- README and unified-operational-world architecture documentation updated to the v0.6 product model.

## Regression coverage

The test suite now covers, among other existing behaviors:

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
- unified CLI smoke paths in CI configuration.

## CI status note

The pull request's initial unified-world head passed the repository CI and Security workflows. Subsequent connector-authored commits do not automatically instantiate GitHub Actions runs in this integration, so the final persistent-substrate/entity-graph/CLI head does **not** have a fresh GitHub Actions result yet.

The current final PR is mergeable at the Git level. Its reported commit failure is Vercel's external deployment rate limit (`Deployment rate limited — retry in 24 hours`), not a repository test result.

A fresh human/GitHub-triggered `workflow_dispatch`, push, or eligible PR event should run the configured Python 3.12/3.13 tests, package build, legacy environment smoke, unified Veritas smoke, Next.js build, and container-health gates before merge.

## Remaining scale work

The five domains are implemented as executable reference environments on the common substrate; they are **not yet production-scale task distributions**. The main remaining scale work is:

- procedural train/IID/OOD/adversarial generators producing hundreds to thousands of tasks per operational domain;
- deepen the current shared entity graph into a causal operational graph so the same customers, employees, suppliers, facilities, applications, assets, accounts, and parcels propagate consequences across domains;
- domain-native artifact engines for real workbook files/formula DAGs, containerized infrastructure, enterprise database/application state, evidence corpora, and GIS artifacts;
- long-horizon cross-domain task compiler over persistent histories rather than one reference episode per domain;
- native domain verifier plugins for spreadsheet calculation graphs, infrastructure health, enterprise consistency, OSINT evidence entailment, and geospatial geometry/output files while retaining the shared score contract;
- private benchmark split/oracle registry and commercial artifact storage;
- concrete trainer runners/adapters for SFT, preference learning, RL and VOPSD;
- expert-trajectory generation policies, counterfactual execution and demonstration-set curation pipelines;
- calibration-aware procedural generators and automated calibration report scoring against generated worlds;
- larger adversarial transformation library and difficulty calibration;
- production orchestration persistence and multi-process/distributed episode storage;
- frontend benchmark/operator console for the unified operational suite.
