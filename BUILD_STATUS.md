# Build status

## Version

Current software version: **0.11.0**.

Canonical release tag: **v0.11.0**.

Veritas 0.11 is the commercial-portability release. It is built on the 0.9 native-artifact runtime, the 0.9.1 experimental-integrity hardening, and the 0.10 benchmark-qualification release. The merged portability implementation is the software release identity; 0.11 is no longer reserved for a future industrial-sandbox rewrite.

Development `main` may contain post-`v0.11.0` integration work while package metadata remains `0.11.0`; that does **not** create or authorize a new 0.11 release artifact. Portable operational convergence is one such post-release integration candidate and remains subject to the release authority described below.

## Release identity

The buyer-facing 0.11 release must agree across all public surfaces:

- Python package version: `0.11.0`;
- README software version: `0.11.0`;
- portability manifest schema: `0.11.0`;
- generated HUD package version: `0.11.0`;
- generated Prime package version: `0.11.0`;
- Git tag / GitHub release: `v0.11.0`;
- licensing: root Apache-2.0 public grant plus explicit commercial restrictions for private evaluation assets and separately delivered generated data.

Release automation verifies these identities before publishing artifacts.

## Canonical capability stack

Veritas currently includes:

- deterministic hidden operational worlds with strict public/private task and oracle separation;
- source-aware tools, budgets, traces, replay, counterfactuals and failure mining;
- persistent operational state and append-only reconstruction;
- CompanyWorld, Operational Worlds, ProjectWorld, Reality Calibration and Continuous Agent Capability Observatory;
- grounded reward verification that separates oracle correctness from admissible-evidence support;
- matched longitudinal panels, paired model × intervention effects, generation replicates and recovery/cadence integrity;
- native artifact mutation behind the existing seven-dimensional verifier;
- generic benchmark qualification with source-disjoint splitting, near-duplicate clustering, provenance, replay, leakage, contamination, feasibility, policy-ordering and exploit-resistance gates;
- private-panel stratum coverage gates that reject majority-class benchmark artifacts;
- vendor-neutral portable environment/task/release/capability/reset/verifier/artifact/metering contracts;
- standalone HUD v6 and Prime Verifiers v1 packaging for the qualified SRE v4 release;
- a generic `PortableOperationalContract` / `PortableRuntimeProtocol` program with MCP compilation, Woyengi schema consumption, trajectory/reverification, NeMo/OpenEnv/Harbor/Prime/HUD operational exporters, sandbox boundaries, and cross-runtime conformance machinery on the post-release development line.

## 0.11 commercial portability

The portability layer preserves a vendor-neutral internal contract. HUD and Prime are adapters over that contract rather than dependencies of Veritas core.

The exact sealed SRE v4 proof establishes:

- deterministic task and run identity;
- deterministic reset for identical environment version + task + seed;
- exact reward parity with the canonical SRE verifier;
- no canonical private scenario IDs in buyer-safe material;
- no canonical private scenario IDs in generated operator task records;
- clean HUD installation and image build;
- live HUD task start and grade;
- Prime Verifiers v1 taskset loading plus the legacy compatibility bridge;
- deterministic HUD and Prime package identities.

The validated buyer-safe identities are pinned in `release/0.11.0/PORTABILITY_IDENTITIES.json` and are carried into the GitHub release provenance record.

## Portable operational convergence candidate

The generic operational program is integrated through shared package surfaces without superseding the frozen SRE HUD/Prime compatibility paths. `PortableEnvironmentManifest` can reference generic operational semantics by `PortableOperationalContract` schema version plus `PortablePublicContract.public_id`; the full contract ID is intentionally excluded because it commits to evaluator-private semantics. Unbound legacy manifests omit the new reference field entirely so their serialized shape and content-derived identity remain compatible.

The installed generic command is `veritas-portable`; `tools/world_portability.py` remains a compatibility launcher. Exact interface versions, runtime mapping status, and unsupported external-runtime semantics are recorded in `docs/portability/portable-operational-convergence.md`.

This integration is **not** scientific qualification, Frontier Qualification, commercial qualification, or release authorization.

## Operational Worlds Production v3

The five operational domains retain exactly **4,480 executable episodes**:

- train: 2,560 total;
- IID test: 640 total;
- OOD: 640 total;
- adversarial: 640 total.

Native engines remain:

- spreadsheet: `openpyxl-workbook-v1`;
- enterprise: `sqlite-enterprise-replica-v1`;
- DevOps: `declarative-kubernetes-sandbox-v1`;
- investigation: `rendered-evidence-corpus-v1`;
- GIS: `shapely-pyproj-vector-v1`.

The native fidelity release gate executes all 20 domain × split cells and requires the mutated artifact plus ordinary state/outcome verification to agree.

## Training Value v3

The completed replicated CompanyWorld transfer matrix uses a fixed 24-example training panel, a fixed 100-episode held-out panel, and training seeds 7, 17 and 29.

- Qwen2.5-0.5B-Instruct: mean held-out paired improvement **+0.5628**, seed-level Student-t 95% interval **[0.4220, 0.7036]**, 87% of held-out episodes improved in each replicate.
- Qwen2.5-1.5B-Instruct: mean held-out paired improvement **+0.7562**, seed-level Student-t 95% interval **[0.7182, 0.7941]**, 100% of held-out episodes improved across all three replicates.

These are reproducible within-family transfer results, not yet a claim of broad source/grammar-disjoint capability transfer.

## ProjectWorld v2

ProjectWorld v2 is structurally generated rather than a scalar reparameterization of one skeleton. It includes:

- project grammar across project type, delivery model, jurisdiction, systems, stakeholders, contracts, WBS, resources, suppliers, approvals, risks and disturbances;
- identity-bound actions;
- supplier capacity, MOQ, storage and persistent purchase-order lifecycle;
- expediting, substitution, crew/overtime and resequencing recovery;
- resource-consuming rework;
- role-scoped observations;
- independent completion, technical, quality, safety, authority, schedule and cost verification.

The latest 200-project qualification remains a **benchmark candidate** with a 40-project private panel and policy ordering:

`oracle > competent > myopic > random > exploit`.

## SRE qualification state

SRE v1 and v2 remain historical `not_qualified` candidates.

SRE v3 is retired as a private benchmark because the stronger private-stratum coverage gate rejects its imbalanced private panel and historical Actions artifacts exposed raw qualification material.

SRE v4 is the qualified, frozen commercial benchmark candidate. The sealed release uses 16 fresh Statuspage providers and contains **87 scenarios** with exactly **30 private-test cases**. Private causal support is capacity 6, infrastructure 6, regression 10, transient 8.

Its exact private-panel policy means are:

`oracle 1.0000 > competent 0.4000 > myopic 0.3000 > random 0.2333`, with exploit `0.0000`.

All 18 qualification gates pass. Canonical public identities are recorded in `results/sre-v4/RELEASE.json`; source snapshots, exact split, private causal evidence and the private release manifest remain in the sealed private bundle. Public CI verifies immutable identities, frozen hash, aggregate qualification evidence and secrecy boundaries rather than rebuilding the private benchmark from live feeds.

## Release gate

Veritas 0.11.0 is publishable only when the exact release commit passes:

- Python 3.12 and 3.13 tests;
- package build and metadata validation;
- environment/product smoke tests;
- native artifact fidelity;
- full 4,480-case operational distribution validation;
- ProjectWorld distribution and ProjectWorld v2 qualification;
- frozen SRE v4 release-identity verification;
- portability tests and external HUD/Prime adapter gates;
- frontend build;
- container/API health;
- aggregate `Required` check;
- Security;
- release-identity consistency tests;
- root-license and commercial-licensing policy checks.

The release workflow then emits an immutable procurement object containing Python distribution hashes, GHCR image digest, pinned HUD/Prime/qualification identities, SBOM and provenance.

### Portable operational convergence release gate

Any release that promotes the generic portable operational program must additionally have fresh evidence for all of the following on the exact candidate/merge ref:

- deterministic `PortableOperationalContract` fixture and canonical bytes;
- public/private leakage suite;
- deterministic reset;
- native operational verifier/reward parity;
- cross-runtime semantic conformance with no semantic loss promoted over missing evidence;
- full OpenEnv and Prime `AdapterConformanceReport` replay from evaluator/operator-side evidence,
  without widening either agent-facing contract;
- clean external wheel/package installation;
- existing SRE HUD smoke;
- existing SRE Prime smoke;
- Woyengi pinned-fixture parity;
- deterministic trajectory conversion;
- offline reverification;
- explicit documentation of unsupported external-runtime semantics.

The `Portable Operational Convergence` workflow supplies the generic implementation/package gates. Existing `Portability Validation` supplies the frozen SRE HUD/Prime compatibility gates. Ordinary repository `CI` remains required for the full repository verification ladder. A missing, skipped, unavailable, or stale gate is **UNVERIFIED**, not PASS.

Repository-wide Python quality uses pinned Ruff/Mypy versions and a fail-closed ratcheted baseline.
The ratchet prevents new diagnostic fingerprints while package owners remove pre-existing debt; it
does not convert outstanding lint/type debt into a clean full-repository PASS.

## Next release: 0.12

0.12 is the next industrial-fidelity and procurement-hardening line. Candidate integrations include live Kubernetes/container/network execution, Terraform/cloud control planes, broader Excel calculation semantics, deeper enterprise replicas, browser/OCR investigation surfaces, raster/PostGIS GIS execution, deeper cross-domain causal propagation, stronger supply-chain attestations, and additional commercially qualified environment SKUs.

### Post-0.11 quality foundation

The development line now includes the v1 Veritas Environment Maturity Model. Its canonical states
are `DRAFT`, `EXECUTABLE`, `VERIFIER_VALIDATED`, `SCIENTIFICALLY_QUALIFIED`,
`FRONTIER_QUALIFIED`, `TRAINING_VALIDATED`, and `COMMERCIAL_RELEASE`. Promotion is sequential,
content/version bound, and fail-closed: missing evidence remains `UNKNOWN`. Deterministic
qualification identities are distinct from timestamped historical records, so requalification does
not erase prior status.

This implements the maturity substrate, not the later verifier, frontier, training-value, or
procurement qualification programs that provide transition evidence.

The repository also adopts a “Do Not Build” architecture policy. Full trainers, model serving,
hyperscale sandbox clouds, generic expert marketplaces, benchmark aggregation, broad harness
catalogs, generic agent frameworks, and target-runtime replacement remain presumptive non-goals.
Proposals entering those areas must document why integration is insufficient and how the smallest
owned boundary strengthens Veritas assurance.
