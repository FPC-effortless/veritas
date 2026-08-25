# Build status

## Completed implementation
- Deterministic synthetic canonical world generation with typed IDs, temporal relationships, events, validation, and reproducibility.
- Pydantic schemas for entities, claims, sources, documents, budgets, findings, investigation state, actions, and verification results.
- Six typed evidence source families, deterministic claim projection, omission/staleness noise, citation links, and provenance DAG.
- SQLite FTS5 frozen search index with bounded query results.
- FastAPI agent-facing load/search/document/submit routes and configurable budget enforcement.
- Six procedural task families, answerability, difficulty vectors, split manifest generation.
- Baseline factorized verifier with false-merge penalties, support, abstention, calibration, and efficiency fields.
- Adversarial tests for false merges and unsupported claims.
- Trajectory recorder, JSONL/Parquet exporters, failure labels, CLI world/evidence/task/index commands.
- Docker/Makefile and reproducibility documentation.

## Validation
- Python compilation passes.
- Test suite passes: 10 tests.
- End-to-end world → evidence → FTS search → structured submission → verifier → JSONL/Parquet trajectory export passes; reference smoke world contains 382 relationships, 210 events, and 920 documents.

## Remaining limitations
- The implementation is a compact V0 foundation, not the complete commercial benchmark requested in the original specification.
- Default reference generation now produces 382 relationships and 210 events, meeting the requested minimum scale.
- Full independent verifier modules, robust temporal/evidence entailment scoring, leakage tests, all adversarial transformations, and complete end-to-end API tests remain.
- Renderer output is deterministic text rather than realistic HTML/XML source documents.
- Private benchmark storage, privileged trajectory exports, Harbor adapter, and production deployment hardening remain deferred.
