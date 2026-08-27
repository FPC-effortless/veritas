# Build status

## Version

Current release candidate: **0.10.0**.

Veritas 0.10 is the benchmark-qualification release built on the 0.9 native-artifact runtime and the 0.9.1 experimental-integrity hardening.

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
- private-panel stratum coverage gates that reject majority-class benchmark artifacts.

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

SRE v3 previously passed the older qualification protocol but is now **retired as a private benchmark** for two reasons:

1. the stronger 0.10 `private_stratum_coverage` gate correctly rejects its 34-case private panel because it is dominated by the transient class;
2. historical Actions artifacts exposed raw v3 qualification material, so the suite can no longer be treated as secret private test data.

SRE v4 is now a **qualified and frozen benchmark candidate**. The frozen release uses 16 fresh Statuspage providers: Airtable, Claude, Elastic, Figma, Grafana, Hedera, HubSpot, IBM Cloud Security, Instructure, New Relic, Postman, Reddit, Render, Snowflake, Supabase and Webflow.

The sealed v4 release contains **87 scenarios** and exactly **30 private-test cases**. Private causal support is balanced enough to pass the release contract: capacity 6, infrastructure 6, regression 10, transient 8. Its exact private-panel policy means are:

`oracle 1.0000 > competent 0.4000 > myopic 0.3000 > random 0.2333`, with exploit `0.0000`.

All 18 qualification gates pass. Canonical public identities are recorded in `results/sre-v4/RELEASE.json`; the source snapshots, exact split, private causal evidence and private release manifest are retained only in the sealed private bundle. The private bundle SHA-256 is also pinned in the public release record.

The one-time sealing run encrypted the private bundle before artifact transport. Public CI no longer downloads live provider feeds or reconstructs/splits SRE v4. It now verifies only the immutable release identities, frozen hash, aggregate qualification evidence and public-artifact secrecy contract.

## Release gate

0.10 may merge only when the exact candidate head passes:

- Python 3.12 and 3.13 tests;
- package build;
- environment/product smoke tests;
- native artifact fidelity;
- full 4,480-case operational distribution validation;
- ProjectWorld distribution and ProjectWorld v2 qualification;
- frozen SRE v4 release-identity verification with no failed qualification gates;
- frontend build;
- container/API health;
- aggregate `Required` check;
- Security.

`main` repository protection is an external repository-administration requirement and must require the aggregate `Required` and `Security` checks before 0.10 is considered operationally released.

## Next release: 0.11

0.11 is reserved for industrial sandbox fidelity, not another benchmark-integrity rewrite. Candidate integrations include live Kubernetes/container/network execution, Terraform/cloud control planes, broader Excel calculation semantics, deeper enterprise replicas, browser/OCR investigation surfaces, raster/PostGIS GIS execution, and deeper cross-domain causal propagation.

0.11 work should begin only after 0.10 is merged with the frozen qualified SRE v4 release and the commercial evaluation pack is rebased onto that release with exact sealed-panel model evidence.
