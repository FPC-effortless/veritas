# Veritas full product-roadmap coverage audit

Work ID: `ROADMAP-PROGRAM-001` / issue #239

Snapshot base at audit branch creation: `55956c852949024f5afa302e1442c2098ce820cc`.

## Purpose and authority boundary

This audit answers one question: **does every known remaining Veritas program requirement have a GitHub-native home that an agent can reconstruct without chat history?**

It does not claim that the mapped work is finished. `READY`, `BLOCKED`, `CLAIMED`, `REVIEW`, `DONE`, and `SUPERSEDED` are coordination states; scientific, Frontier, training-value, learning-efficiency, commercial, release, sealed/private-evidence, paid-compute, and external/manual authority remain separate.

Live trusted `veritas-agent-work-status:v1` records are execution authority. `work:*` labels are discovery metadata. `.github/agent-roadmap.yml` is a checked-in planning snapshot, not live authority; `python tools/roadmap/agent_roadmap.py sync` is the supported reconstruction path from live GitHub.

Primary source programs audited:

- #130 — High-Stakes Investigation / Gold flagship;
- #146 — Machine Experience / Learning Readiness;
- #148 — Learning Efficiency;
- #150 — repository coordination root;
- #209 — pre-roadmap existing-work audit;
- #239 — corrected Competitive Quality / full-coverage requirement;
- all current executable `agent-work` issues relevant to portability, trace, diagnostics, sandbox, harness, packaging/procurement, qualification, and commercial convergence.

## Classification legend

- **CANONICAL** — requirement has an executable Work ID/issue, regardless of whether it is presently blocked or ready.
- **DONE/HISTORICAL** — implementation already exists and must not be recreated as greenfield work.
- **SUPERSEDED** — older issue/PR is replaced by a named canonical lane or corrected evidence.
- **EXTERNAL/MANUAL** — completion requires authority or evidence that repository coding automation cannot fabricate.
- **NON-GOAL** — intentionally excluded from autonomous coding authority or from the product claim represented by the source program.

## Coverage result

**Missing executable backlog items: none.**

One genuine orphan was found during this audit: legacy #42, CompanyWorld no-work-anchor reconciliation. Earlier commit `508224847332f8e72acf48d83dc48b8955898a27` added empty/reference anchors and tests and `8dd87856e7a52eafe76e5ff40f686c460fcda292` added buyer-report anchor normalization, but #42 was opened after that work and its remaining acceptance criteria were not complete. The requirement is now canonicalized as **CAL-001 / #308**, automatically enrolled as trusted `READY`. #42 therefore maps to CAL-001 rather than being mislabeled DONE.

The statement “missing = none” means every known requirement is represented or explicitly classified. It does **not** mean the remaining roadmap is complete.

## Gold flagship program mapping

| Source requirement | Canonical work | Classification |
|---|---|---|
| Gold-10 executable flagship pilot | `ROADMAP-001 / GOLD-001-PILOT` #152 | CANONICAL |
| External independent red-team | `GOLD-002` #178 | CANONICAL |
| Buyer-safe Gold-10 quality case study | `GOLD-003` #179 | CANONICAL |
| Gold-25 expansion candidate | `GOLD-004` #180 | CANONICAL |
| Gold-50–100 release candidate | `GOLD-005` #181 | CANONICAL |
| Structured investigation corpus migration | `MIG-001` #184 | CANONICAL |
| Gold source/artifact acquisition receipts | `DATA-001` #185 | CANONICAL |
| Source-policy / coverage expansion | `DATA-002` #186 | CANONICAL |
| Legacy public-investigation Foundry disposition | `MIG-002` #187 | CANONICAL |
| Frozen Gold-10 case-selection manifest | `CASE-001` #188 | CANONICAL |
| Gold-10 scientific qualification | `QUAL-001` #201 | CANONICAL |
| Gold Frontier usefulness evaluation | `FRONTIER-GOLD-001` #202 | CANONICAL |
| Gold training-value experiment | `TRAIN-GOLD-001` #203 | CANONICAL |
| Gold matched-budget learning-efficiency experiment | `LE-GOLD-001` #204 | CANONICAL |
| Qualified Gold environment package | `GOLD-PKG-001` #205 | CANONICAL |
| Commercial-release qualification | `COMM-QUAL-001` #206 | CANONICAL |

The Gold source program’s distinctions between controlled/private truth, institutional findings, ambiguity/calibration, temporal cuts, public/private partitions, multimodal evidence, deterministic replay, verifier falsifiers, and separate scientific/Frontier/training/commercial gates are therefore not left as umbrella prose only: execution and qualification have named child lanes.

## Machine Experience / Learning Readiness mapping

| Source requirement | Canonical work | Classification |
|---|---|---|
| Machine Experience foundation | `EXP-001` / PR #149, integrated at historical main `6745c7313c13de9ea18d69f62b2585ff8b139f21` | DONE/HISTORICAL |
| Semantic failure/capability diagnostics | `EXP-002` #153 | CANONICAL |
| Semantic annotation / trace compiler | `TRACE-002` #154 | CANONICAL |
| Experience representation / trace schema integration | `TRACE-003` #155 | CANONICAL |
| Counterfactual experience | `EXP-003` #156 | CANONICAL |
| Capability curriculum graph | `CAP-001` #157 | CANONICAL |
| Procedure induction | `PROCIND-001` #158 | CANONICAL |
| Abstraction induction | `ABS-001` #159 | CANONICAL |
| Experience Foundry | `LEARN-001` #160 | CANONICAL |
| Continual-learning protocol | `CL-001` #161 | CANONICAL |
| Canonical training-value qualification | `TRAIN-001` #162 | CANONICAL |
| Historical trajectory metadata audit | `TRACE-001` #183 | CANONICAL |
| TRACE-003 stale-copy integrity correction | `TRACE-003-FIX-001` #250 | CANONICAL |
| Canonical trace graph | `TRACE-004` #268 | CANONICAL |
| First-class simulated actors | `ACTOR-001` #269 | CANONICAL |

Naming collision resolved: the Machine Experience source used “PROC-001” for procedure induction, but the executable child is deliberately `PROCIND-001` #158. Procurement/package work uses `PKG-*` / `ATTEST-*` IDs, so procedure induction and procurement packaging no longer share an ambiguous identifier.

## Learning Efficiency mapping

| Source requirement | Canonical work | Classification |
|---|---|---|
| Training usefulness / capability-gain qualification | `TRAIN-001` #162 | CANONICAL |
| LearningEfficiencyReport + resource accounting | `LE-002` #164 | CANONICAL |
| Equal-budget learning-efficiency experiment | `LE-003` #165 | CANONICAL |
| Minimum sufficient model analysis | `MODEL-001` #166 | CANONICAL |
| Selective teacher routing / targeted distillation | `TEACH-001` #167 | CANONICAL |
| Experience selection | `SEL-001` #189 | CANONICAL |
| Active curriculum | `CURR-001` #190 | CANONICAL |
| Capability-directed synthetic experience | `SYN-001` #191 | CANONICAL |
| Low-cost small-model regression suite | `TRAIN-002` #192 | CANONICAL |
| Model × harness × environment intervention diagnostics | `DIAG-002` #193 | CANONICAL |
| Advanced isolation/delegation experiment | `SANDBOX-003` #194 | CANONICAL |
| Compute-constrained specialized-model pilot | `AFRICA-001` #195 | CANONICAL |
| Gold training-value experiment | `TRAIN-GOLD-001` #203 | CANONICAL |
| Gold matched-budget learning-efficiency proof | `LE-GOLD-001` #204 | CANONICAL |

The source program’s data-, compute-, human-, teacher-, and monetary-efficiency dimensions remain separate denominators. No canonical ticket authorizes a universal scalar efficiency claim or fabricated cost data.

## Competitive quality / portability / diagnostics / runtime mapping

| Program requirement | Canonical work | Classification |
|---|---|---|
| Environment maturity / qualification integration | `VQ-007` #163 | CANONICAL |
| Generic Qualified Environment Package | `PKG-001` #168 | CANONICAL |
| Content-bound attestation integrity | `ATTEST-001` #169 | CANONICAL |
| Capability/environment catalog | `CAT-001` #170 | CANONICAL |
| Environment fidelity / realism disclosure | `ENV-001` #171 | CANONICAL |
| Qualified templates/examples | `DX-003` #172 | CANONICAL |
| Portability convergence / conformance coverage | `PORT-004` #173 | CANONICAL; consumes earlier merged portability/exporter substrate rather than recreating it |
| First-party Local/Docker sandbox providers | `SANDBOX-001` #174 | CANONICAL |
| Remote sandbox provider | `SANDBOX-002` #175 | CANONICAL |
| Harness conformance contract | `HARNESS-001` #176 | CANONICAL |
| Reference harness adapters | `HARNESS-002` #177 | CANONICAL |
| Competitive overlap review | `COMP-001` #182 | CANONICAL |
| Trajectory metadata audit | `TRACE-001` #183 | CANONICAL |
| Model/harness/environment diagnostics | `DIAG-002` #193 | CANONICAL |
| Advanced isolation/delegation | `SANDBOX-003` #194 | CANONICAL |
| Qualified-package shared-surface convergence | `CONV-001` #199 | CANONICAL |
| Frontier qualification integration | `FRONTIER-INT-001` #200 | CANONICAL |
| Commercial-release qualification | `COMM-QUAL-001` #206 | CANONICAL |
| CompanyWorld baseline-normalized calibration/reporting | `CAL-001` #308 | CANONICAL; discovered by this audit |

Earlier generic exporter, portable runtime, conformance, evidence, attestation, and public/private-boundary implementations that are already merged are prerequisites/evidence for these convergence tickets. They are not to be respawned as generic “portability v1” greenfield lanes merely because older Work IDs are absent from the current strategic child list.

## CompanyWorld calibration reconciliation discovered by the audit

Legacy #42 was the only known open executable requirement that remained `LEGACY_NONROADMAP_BLOCKED` after #209.

Historical evidence is deliberately split:

1. `508224847332f8e72acf48d83dc48b8955898a27` created fixed diagnostic/interactive/sequential/dynamic calibration fixtures, `empty_anchors`, `reference_anchors`, and tests that show diagnostic empty reward is zero while higher-level empty anchors may be positive.
2. `8dd87856e7a52eafe76e5ff40f686c460fcda292` created buyer-facing CompanyWorld reporting and a `normalize_capability_score(score, empty, reference)` path.
3. #42 was opened later and requires explicit non-zero-anchor rationale, level-specific above-baseline calibration fields, fail-closed invalid-anchor handling, regression-locked semantics, and a regenerated public report without an unresolved baseline-validity warning.
4. Therefore historical work is **partial evidence**, not completion. `CAL-001` #308 is the canonical remaining lane and preserves the requirement without widening other CompanyWorld scoring ownership.

## Pre-roadmap reconciliation

The #209 existing-work audit remains the canonical historical ledger. This audit carries forward its dispositions rather than reopening them:

| Legacy item | Disposition |
|---|---|
| #32 seller/payment/legal/platform work | EXTERNAL/MANUAL |
| #41 independent reproduction | EXTERNAL/MANUAL |
| #42 CompanyWorld no-work anchors | SUPERSEDED AS A ROADMAP HOME by `CAL-001` #308; implementation still pending |
| #43 older training-value item | SUPERSEDED by `TRAIN-001` #162 |
| #63 / draft PR #65 Frontier qualification | canonical Frontier lane; manual/authority boundaries remain protected |
| #71 external commercial distribution | EXTERNAL/MANUAL |
| #106 service-control item | historical/non-roadmap disposition retained from #209; not duplicated as a new product lane |
| legacy PR #118 public-investigation stack | SUPERSEDED/migration source; useful corpus handled by `MIG-001` #184 and disposition by `MIG-002` #187 |
| PR #134 | canonical structured-corpus migration implementation/evidence; do not recreate |
| PR #147 | canonical Gold acquisition implementation/evidence; do not recreate |
| PR #149 | Machine Experience foundation DONE/HISTORICAL |
| PR #107 | experimentally superseded by corrected PR #109; evidence only |
| PR #28 / #25 | historical evidence only |
| Dependabot PRs #2–#6 | automated dependency maintenance, not strategic roadmap work |

## Duplicate and supersession register

- `PROC-001` source shorthand for procedure induction is normalized to `PROCIND-001` #158.
- Procurement/package work uses `PKG-001` #168, `ATTEST-001` #169, `GOLD-PKG-001` #205, and related qualification IDs; it must not reuse `PROC-001`.
- `ROADMAP-001` and `GOLD-001-PILOT` are aliases for the same #152 lane, not two implementations.
- legacy #43 is replaced by `TRAIN-001` #162.
- legacy #42 is now mapped to `CAL-001` #308.
- legacy PR #118 is migration/supersession input, not a fresh implementation lane.
- PR #107 is experimentally superseded by corrected PR #109.
- TRACE-003 follow-up integrity work is explicitly separated as `TRACE-003-FIX-001` #250 rather than silently rewriting historical completion evidence.

## Coordination-system coverage needed to execute the product roadmap

The product roadmap is also reconstructible through its coordination Work IDs. Key lanes include:

- `ROADMAP-002` #196 — manifest/DAG synchronizer — DONE;
- `ROADMAP-AUDIT-001` #209 — existing-work audit — DONE;
- `ROADMAP-NOTIFY-001` #211 — dependency-ready reconciliation — DONE after PR #307 and live #239 BLOCKED→READY acceptance;
- `AGENT-DISCOVERY-001` #208 — work-discovery protocol;
- `ROADMAP-CLAIM-BOOTSTRAP` #216 — bootstrap labels/enrollment support;
- `ROADMAP-PROGRAM-001` #239 — this coverage audit;
- `ROADMAP-BOOTSTRAP-VERIFY-001` #243 — fresh-agent GitHub-only cold-start verification;
- `ROADMAP-COMPLETE-001` #244 — final coordination operational declaration.

#243 and #244 remain proof gates. This audit does not pre-authorize their completion.

## External/manual authority register

The following classes must stay outside autonomous implementation completion unless their own explicit authority is granted:

- seller/payment/payout/account setup;
- legal/licensing/rights decisions requiring human authority;
- independent external red-team or reproduction evidence;
- external model/provider accounts and paid compute;
- sealed/private benchmark operations outside the authorized evaluator boundary;
- Frontier runs where separate Frontier authority is required;
- commercial release/publication/distribution actions requiring human or platform authority;
- customer secrets, private evidence, or buyer data that repository automation cannot self-authorize.

A code PR can create tooling for these surfaces but cannot fabricate the external evidence needed to mark the authority-bound outcome complete.

## Intentionally out of scope / non-goals

- “DONE” coordination state is not scientific, Frontier, training, learning-efficiency, or commercial PASS.
- Strategic rank is not execution permission. Dependencies, trusted state, collision checks, and frozen ownership determine claimability.
- The roadmap does not require Veritas to own every model harness, remote sandbox, trainer, cloud runtime, or marketplace implementation. It owns contracts, conformance, evidence, and selected reference adapters/providers where tickets explicitly say so.
- The roadmap does not turn institutional findings into omniscient hidden truth for real investigations.
- The roadmap does not authorize LLM judges as sole reward authority where deterministic/private verification is required.
- The roadmap does not infer missing resource/cost denominators or convert UNKNOWN evidence to PASS.
- The roadmap does not treat the checked-in manifest snapshot as stronger authority than live trusted GitHub coordination state.

## Reconstruction procedure for future agents

A fresh agent can reconstruct the remaining program from GitHub alone by:

1. reading `AGENTS.md`, `.agents/universal/CONTRACT.md`, and `.agents/veritas/OVERLAY.md`;
2. reading coordination root #150 and program roots #130, #146, and #148;
3. reading this audit plus `docs/roadmap/existing-work-audit.md`;
4. querying open `agent-work` issues and their latest trusted status records;
5. running `python tools/roadmap/agent_roadmap.py sync` when a current machine-readable planning view is required;
6. treating `.github/agent-roadmap.yml` as a snapshot, not live execution authority;
7. claiming only a trusted READY lane and waiting for accepted CLAIMED state before editing;
8. preserving separate qualification/manual authority boundaries.

`CAL-001` #308 is intentionally discoverable by this procedure even if the checked-in manifest predates its creation, because the supported synchronizer discovers live enrolled `agent-work` issues.

## Final audit conclusion

At snapshot base `55956c852949024f5afa302e1442c2098ce820cc`, supplemented by live GitHub coordination through creation/enrollment of `CAL-001` #308, every known requirement in the audited Gold, Machine Experience/Learning Readiness, Learning Efficiency, Competitive Quality, portability/trace/diagnostics/sandbox/harness/procurement, coordination, and pre-roadmap source sets is one of:

- mapped to a canonical executable Work ID;
- retained as DONE/historical evidence;
- explicitly superseded with a replacement;
- classified external/manual authority work; or
- explicitly non-goal/out-of-scope.

**Missing-item list: NONE.**

This is a roadmap-coverage result only. The many mapped BLOCKED/READY/active implementation, qualification, experiment, Gold-scaling, and external/manual lanes still have to be executed under their own contracts.