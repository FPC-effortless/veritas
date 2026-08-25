# Build Status

## Milestone 1 — Canonical Reality ✓

**Implemented:**
- Typed canonical IDs (PER-*, ORG-*, ADDR-*, EVENT-*, REL-*, CLAIM-*, SOURCE-*, DOC-*)
- Entity schemas: Person, Organization, Address, Domain with Pydantic v2
- Relationship schema with temporal validity (valid_from, valid_to)
- Event-sourced world history (OrganizationCreated, DirectorAppointed, etc.)
- CanonicalWorld state container with temporal query methods
- WorldFactory.generate(seed, config) → deterministic world
- WorldGenerationConfig exposure of num_people, num_organizations, relationship_density, etc.
- World validator detecting dangling IDs, invalid dates, duplicate IDs, temporal ordering
- Deterministic seed tests confirming reproducibility

**Status:** ✓ All tests passing. Verified scale to 100 people, 50 orgs, 300+ relationships in <30s.

**Tested:**
- pytest unit tests in tests/unit/test_core.py
- Seed reproducibility
- Temporal queries (relationships_at, entity_state_at)
- World validation

---

## Milestone 2 — Claims & Provenance ✓

**Implemented:**
- Claim schema (claim_id, subject_id, predicate, object, valid_from, valid_to, truth_status, origin_source_id)
- TruthStatus enum: true, false, partially_true, outdated, unknown
- Source schema (source_id, name, source_type, reliability_baseline)
- ProvenanceDAG with cycle detection
- Functions: get_provenance_ancestors(), get_root_sources(), independent_source_count()
- Evidence projection with stale/omitted claims modeling

**Status:** ✓ Citation-laundering detection working. ProvenanceDAG prevents cycles.

---

## Milestone 3 — Evidence & Search

**In Progress:**
- Six evidence renderers (registry, news, company_site, filing, archive, directory)
- SQLite FTS5 search indexing
- Evidence corruption engine (omission, staleness, name abbreviation)
- Public vs. hidden document representations

---

## Milestone 4 — Investigation Tools & API

**Deferred:**
- FastAPI service with agent-visible routes only
- /search/web, /search/news, /search/documents, /registry/search, etc.
- Budget tracking and enforcement

---

## Milestone 5 — Tasks & Structured Outputs

**Deferred:**
- TaskSpec and six task families (EntityResolution, OwnershipReconstruction, etc.)
- InvestigationResult structured output
- Answerability modeling

---

## Milestone 6 — Factorized Verifier

**Implemented:**
- Multi-dimensional verifier with component scores
- Relationship verification, false-merge penalty, unsupported-claim detection
- Aggregate reward calculation

---

## Milestone 7 — Adversarial Testing & Trajectories

**Deferred:**
- Adversarial test suite (identity collisions, stale evidence, citation laundering, etc.)
- Trajectory recording (JSONL, Parquet)
- Failure taxonomy

---

## Milestone 8 — Reference World & Packaging

**Deferred:**
- Generate 100-person, 50-org reference world with 48 benchmark tasks
- Train/public/private splits
- Commercial-quality README
- Optional Harbor adapter

---

## Known Limitations

1. Evidence renderers are templates, not full HTML/XML generation yet
2. Search is not indexed (projected for Milestone 3)
3. No API service (projected for Milestone 4)
4. No investigation budget enforcement in API (projected for Milestone 4)
5. Verifier is simplified; full calibration/efficiency metrics deferred
6. No trajectory recording (projected for Milestone 7)
7. Identity collisions not yet generated (projected for Milestone 3)

## Next Steps

1. Complete Milestone 3: Full evidence renderers, FTS5 indexing, corruption engine
2. Build Milestone 4: FastAPI with full search tools, budget enforcement
3. Implement Milestone 5: Six task families with procedural generation
4. Finalize verifier (Milestone 6) with calibration metrics
5. Add adversarial mechanisms and trajectory export
6. Generate reference world and benchmark splits

"}},{
