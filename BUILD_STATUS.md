# Build status

## Version

Current benchmark/runtime version: **0.4.0**.

## Implemented

- Deterministic hidden canonical world generation with typed entities and event-sourced temporal relationship intervals.
- Temporal ownership transfers, residence changes, organization renames, dissolutions, and historical state queries.
- Leakage-safe evidence projection using public names/aliases rather than canonical entity IDs.
- Six source families with source-conditioned omission, staleness, partial truth, false claims, and citation dependence.
- Citation provenance DAG and independent-root reasoning.
- Source-aware SQLite FTS5 search surfaces for web, registry, filing, archive, and general document search.
- Isolated FastAPI episode sessions with per-episode hidden world/oracle, search index, budget, and public task.
- Concrete public `TaskSpec` objects plus separate privileged `TaskOracle` objects.
- Six task families: entity resolution, ownership reconstruction, temporal reconstruction, provenance, conflict resolution, and due diligence.
- Task-scoped verifier with precision/recall/F1, hidden identity resolution, temporal scoring, private claim-backed evidence support, provenance scoring, calibration, abstention, efficiency, and explicit false-merge/unsupported-claim penalties.
- Reward integrity guards: empty and conclusion-only submissions cannot earn answerable-task reward; answer stuffing reduces score.
- Trajectory recorder plus JSONL/Parquet export and failure labels.
- Docker/Makefile packaging and reproducibility tooling.
- GitHub Actions CI, security scanning, dependency maintenance, release validation, GitHub Releases, and GHCR publishing.

## Regression coverage

The suite now covers:

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

## Known external CI condition

GitHub Actions workflows are accepted and triggered, but the observed private-repository runs have failed before any workflow step receives a runner (`runner_id: 0`, empty step lists across unrelated jobs). This is consistent with an account/repository GitHub-hosted runner, Actions policy, minutes, or billing condition rather than an application-test failure. The PR should remain unmerged until a runner executes the gates successfully.

## Remaining product work

- richer realistic HTML/XML/PDF-style synthetic renderers
- larger adversarial transformation library and difficulty calibration
- stronger semantic evidence-entailment scoring beyond structured hidden claim links
- benchmark manifest/version registry and private-evaluation artifact storage
- external RL harness adapters and production orchestration persistence
- multi-process/distributed episode storage instead of in-process session state
- frontend benchmark/operator console
