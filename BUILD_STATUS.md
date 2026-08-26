# Build status

## Version

Current benchmark/runtime version: **0.6.0**.

## Implemented

- Deterministic hidden canonical world generation with typed entities and event-sourced temporal relationship intervals.
- Temporal ownership transfers, residence changes, organization renames, dissolutions, and historical state queries.
- Leakage-safe evidence projection using public names/aliases rather than canonical entity IDs.
- Six source families with source-conditioned omission, staleness, partial truth, false claims, and citation dependence.
- Citation provenance DAG and independent-root reasoning.
- Source-aware SQLite FTS5 search surfaces for web, registry, filing, archive, and general document search.
- Isolated FastAPI episode sessions with per-episode hidden world/oracle, search index, budget, and public task.
- Concrete public `TaskSpec` objects plus separate privileged `TaskOracle` objects.
- External Investigation capability family: entity resolution, ownership reconstruction, temporal reconstruction, provenance, conflict resolution, and due diligence.
- CompanyWorld enterprise-control capability family with investigation, action, sequential control and dynamic work.
- Selective Agency capability family with execute/clarify/reframe/decline/no-op judgment and procedural train/IID/OOD/adversarial cases.
- Unified Operational Worlds covering financial/spreadsheet, enterprise operations, DevOps/incident response, investigation/OSINT, and GIS under one task/runtime/verifier contract.
- `PersistentOperationalSubstrate` for organization-scoped state, cross-domain event history, deterministic reconstruction, snapshots, and counterfactual forks.
- `VeritasCompany` facade for mounting all five operational worlds into one persistent synthetic organization.
- Shared public `TaskContract`, agent-visible `OperationalRecord`, public actions, private `HiddenOracle`, hidden action effects, state assertions, invariants, evidence requirements and budgets.
- Shared seven-dimensional operational verifier: outcome, state, constraints, side effects, process, efficiency, and evidence.
- Executable reference environments for DCF spreadsheet repair, CRM/ERP approval control, Kubernetes incident recovery, OSINT identity resolution, and GIS projection/topology repair.
- Separate public-bundle/private-oracle packaging for the unified operational suite.
- Dedicated `veritas` CLI for domain discovery, single-world builds, five-world suite builds, and persistent company builds while retaining the legacy `iworld` CLI.
- Task-scoped investigation verifier with precision/recall/F1, hidden identity resolution, temporal scoring, private claim-backed evidence support, provenance scoring, calibration, abstention, efficiency, and explicit false-merge/unsupported-claim penalties.
- Reward integrity guards: empty and conclusion-only submissions cannot earn answerable-task reward; answer stuffing reduces score.
- Trace-first foundry runtime, trace storage, replay descriptors, counterfactual branches, failure-to-challenge mapping, task-distribution control and moving learnability frontier.
- Expert-trajectory primitives for verifier-qualified demonstrations, recovery/counterfactual roles and preference pairs.
- Reality-calibration primitives for provenance-backed calibration sources, distribution targets, dependency targets, procedure priors and calibration reports.
- Trainer-product boundary for SFT, preference learning, RL and VOPSD with verifier thresholds, invariant gates, split isolation and trace provenance.
- Trajectory recorder plus JSONL/Parquet export and failure labels.
- Docker/Makefile packaging and reproducibility tooling.
- GitHub Actions CI, security scanning, dependency maintenance, release validation, GitHub Releases, and GHCR publishing.

## Regression coverage

The suite covers:

- deterministic world/evidence generation
- temporal ownership state transitions
- public/canonical leakage boundaries
- public-task/private-oracle separation
- train/public/private split disjointness
- empty-answer reward hacking
- false-positive answer stuffing
- false entity merges
- source-aware tool surfaces
- per-episode budget isolation
- provenance cycle/laundering behavior
- tool cost exhaustion
- held-out trajectory exclusion from training bundles
- external-investigation capability-family separation
- world-calibration fingerprinting and quality gates
- all five operational-world domain registrations
- unified operational public/private oracle isolation
- deterministic operational target-state verification
- forbidden-action and invariant-violation penalties
- persistent company organization scoping
- cross-domain substrate mounting and event sequencing
- point-in-time state reconstruction and counterfactual fork behavior
- unified CLI smoke paths in CI configuration

## CI status note

The pull request's initial unified-world head passed the repository CI and Security workflows. Subsequent connector-authored commits do not automatically trigger GitHub Actions in this integration, so the latest persistent-substrate/CLI additions require a fresh GitHub-triggered run before merge. The CI configuration now includes direct smoke coverage for the `veritas` CLI and unified company build.

An external Vercel status may fail because of account build-rate limits; that is separate from the Python/Next.js repository CI gates.

## Remaining product work

The five domains are implemented as executable reference environments on the common substrate; they are **not yet production-scale task distributions**. The main remaining scale work is:

- procedural train/IID/OOD/adversarial generators producing hundreds to thousands of tasks per operational domain
- shared cross-domain entity and causal graph so the same customers, employees, suppliers, facilities, applications, assets, accounts and parcels participate across multiple worlds
- domain-native artifact engines for real workbook files/formula DAGs, containerized infrastructure, enterprise database/application state, evidence corpora, and GIS artifacts
- long-horizon cross-domain task compiler over persistent histories rather than one reference episode per domain
- native domain verifier plugins for spreadsheet calculation graphs, infrastructure health, enterprise consistency, OSINT evidence entailment, and geospatial geometry/output files while retaining the shared score contract
- private benchmark split/oracle registry and commercial artifact storage
- concrete trainer runners/adapters for SFT, preference learning, RL and VOPSD
- expert-trajectory generation policies, counterfactual execution and demonstration-set curation pipelines
- ingestion/normalization adapters that turn real datasets and domain corpora into `WorldCalibrationSpec` targets
- calibration-aware procedural generators and automated calibration report scoring against generated worlds
- richer realistic HTML/XML/PDF-style synthetic renderers
- larger adversarial transformation library and difficulty calibration
- production orchestration persistence and multi-process/distributed episode storage
- frontend benchmark/operator console for the unified operational suite
