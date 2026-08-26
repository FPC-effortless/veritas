# Build status

## Version

Current benchmark/runtime version: **0.5.0**.

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
- Task-scoped verifier with precision/recall/F1, hidden identity resolution, temporal scoring, private claim-backed evidence support, provenance scoring, calibration, abstention, efficiency, and explicit false-merge/unsupported-claim penalties.
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

## Known external CI condition

GitHub Actions workflows are accepted and triggered, but prior observed private-repository runs failed before any workflow step received a runner (`runner_id: 0`, empty step lists across unrelated jobs). This is consistent with an account/repository GitHub-hosted runner, Actions policy, minutes, or billing condition rather than an application-test failure. Changes should not be merged on the assumption that CI passed unless a runner actually executes the gates.

## Remaining product work

- concrete trainer runners/adapters for SFT, preference learning, RL and VOPSD
- expert-trajectory generation policies, counterfactual execution and demonstration-set curation pipelines
- ingestion/normalization adapters that turn real datasets and domain corpora into `WorldCalibrationSpec` targets
- calibration-aware world generators and automated calibration report scoring against generated worlds
- full executable External Investigation world distributions distinct from CompanyWorld
- richer realistic HTML/XML/PDF-style synthetic renderers
- larger adversarial transformation library and difficulty calibration
- stronger semantic evidence-entailment scoring beyond structured hidden claim links
- benchmark manifest/version registry and private-evaluation artifact storage
- production orchestration persistence and multi-process/distributed episode storage
- frontend benchmark/operator console
