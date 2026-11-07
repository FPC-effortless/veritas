# Competitive overlap regression review — 2026-08-28, refreshed 2026-11-07

**Work ID:** COMP-001 / issue #182
**Original review:** 2026-08-28; intermediate source update: 2026-10-12
**Current public-source check:** 2026-11-07 UTC
**Veritas comparison baseline:** `34f86edf9fbc091245df44ecba2c0b4de6e6a389`

## Evidence policy and changes since the previous review

This refresh replaces stale product descriptions and execution recommendations, rather than making an archive-only disposition of COMP-001. Earlier versions remain in Git history. Public primary sources below were read on the check date; some browser results were cached from the preceding six days. Mutable upstream `main` documentation is not a pinned installed release or a verified runtime result. No competitor software, model, provider, account, private panel, or hosted workflow was executed.

Documentation establishes what a project documents, not that its performance, security, interoperability, or qualification claims have been independently reproduced. Vendor product claims are identified as such. `ADOPT`, `INTEGRATE`, `IGNORE`, and `EXCEED` below are engineering dispositions, not comparative scientific rankings or execution permission.

Material corrections:

- NeMo's current environment concept includes an agent harness; the previous assertion that the harness is external to its environment was too strong.
- Prime's old `docs/v1/tasksets.md` and `docs/v1/harnesses.md` URLs return 404. Replacement top-level docs retain task/trace, multi-agent, and capability semantics. Current runtime docs list subprocess, Docker, Prime, and custom runtimes; the old built-in Modal claim is not retained.
- OpenEnv now documents reward rubrics, Inspect AI evaluation, and Harbor-based training traces. Describing trajectory scoring only as evolving understated the documented surface.
- TRAIN-001 is implementation-DONE, not still dependency-blocked. That does not establish training usefulness. Generic packaging has merged, while its trusted coordination record still needs reconciliation. These are separate facts.

## 1. NeMo Gym

**Observed:** Its [environment concepts](https://docs.nvidia.com/nemo/gym/main/about/concepts/environments/) describe dataset, agent harness, verifier, and state, with the model external. Runtimes host that composition; a sandbox adds isolation. This is a logical decomposition, not proof that a particular runtime safely isolates arbitrary workloads.

The [authoring guide](https://docs.nvidia.com/nemo/gym/main/contribute/environments/new-environment/) documents manifest-backed scaffolding, validation, verifier fixtures, and `gym env publish`. Importantly, that publish command is a **local readiness check**, not hosted publication. Supported fixtures cover reward endpoints, malformed inputs, and reseeded determinism when declared. The guide explicitly lists deferred automation, including capability checks and certificate-backed validation; it does not promise that static validation proves grading quality.

The [evaluation guide](https://docs.nvidia.com/nemo/gym/evaluation/) documents aggregation, profiling, comparison, BLADE diagnosis, and offline reward recomputation. It warns that changing several experimental factors together cannot identify the cause of a score change.

**Disposition:** **ADOPT** concrete authoring falsifiers through DX-003 (#172) and controlled diagnostic practices through DIAG-002 (#193), subject to their live scope. **INTEGRATE** execution interfaces rather than reproduce infrastructure. **EXCEED** is the target for Veritas's content-bound/private-safe evidence assurance, not a claim of measured superiority. Do not copy a CLI's “publish” label into release authority.

## 2. Prime Intellect Verifiers

**Observed:** The [overview](https://raw.githubusercontent.com/PrimeIntellect-ai/verifiers/main/docs/overview.md) distinguishes tasksets, harnesses, agents, environments, and traces. An environment owns episode control flow across agents; traces carry messages, rewards, metrics, errors, and model-call records. The [taskset guide](https://raw.githubusercontent.com/PrimeIntellect-ai/verifiers/main/docs/tasksets.md) describes immutable task data and task-owned lifecycle/reward functions receiving the trace. This supports trace-oriented interoperability, not an inference that every reward uses all trace information.

The [environment guide](https://raw.githubusercontent.com/PrimeIntellect-ai/verifiers/main/docs/env.md) explicitly documents user simulation as a second agent, plus multi-attempt/judge compositions. The [harness guide](https://raw.githubusercontent.com/PrimeIntellect-ai/verifiers/main/docs/harnesses.md) declares optional capabilities including MCP, resume, skills, system-prompt handling, and tool interception. Resume does not by itself imply live steering. The [runtime guide](https://raw.githubusercontent.com/PrimeIntellect-ai/verifiers/main/docs/runtimes.md) separates runtime from harness capabilities and documents pre-provision refusal of unsupported runtime requirements. It warns that subprocess execution has host access and Python task hooks run in the evaluator process.

The [README](https://raw.githubusercontent.com/PrimeIntellect-ai/verifiers/main/README.md) connects Verifiers with the Environments Hub, prime-rl, and Hosted Training. Account-native behavior and compatibility with Veritas's pinned adapter are not tested by this review.

**Disposition:** **ADOPT** explicit task/harness/runtime compatibility declarations through HARNESS-001/#176, HARNESS-002/#177, and ACTOR-001/#269; **ADOPT** environment-owned simulated actors through the existing actor contract, not a new parity ticket. **INTEGRATE** external training/distribution through #71 and existing adapters. **IGNORE** first-party trainer parity. Preserve Veritas evaluator privacy rather than assuming another project's task references are safe for public export.

## 3. OpenEnv

**Observed:** The [current README](https://raw.githubusercontent.com/openenv/OpenEnv/main/README.md) documents synchronous/asynchronous `reset`, `step`, and `state` over WebSocket; Docker/local/cloud/Spaces deployment; MCP production tool exposure; rubric rewards; Inspect AI evaluation; and Harbor harness integration with framework-neutral training traces. It also documents scaffold/validate/push commands and distinguishes host-bound local serving from isolated deployment. The old Hugging Face GitHub URL redirects to `openenv/OpenEnv`.

**Disposition:** **INTEGRATE** useful protocol/harness surfaces under existing portability and HARNESS-002/#177 ownership. **ADOPT** concise validation ergonomics through DX-003/#172. **IGNORE** catalog-count parity and a speculative new UI/trainer project. The earlier claim that its scoring surface was merely evolving is withdrawn; so is reliance on an older experimental-status warning as the present reason to avoid integration. Versioned compatibility and semantic-loss checks, not a label, should govern adoption. No live OpenEnv deployment or token-capture correctness was tested.

## 4. Harbor

**Observed:** The [README](https://raw.githubusercontent.com/harbor-framework/harbor/main/README.md) documents agent evaluation, benchmark sharing, local Docker and remote providers, and rollout generation. Its scale claims are project-reported, not reproduced here. The [RL documentation](https://www.harborframework.com/docs/training-workflows/rl) describes an external rollout interface and SkyRL integration; the fetched page resolved to a commit-pinned documentation page, not an executed training run.

The [Harbor Index repository](https://github.com/harbor-framework/harbor-index) describes 80 tasks selected from over 6,000 candidates with repeated runs, broken-task detection, human audits, and reward-hacking supervision. Those counts and process claims are the maintainers' report; this review does not independently audit their selection or leaderboard.

**Disposition:** **INTEGRATE** runtime/harness breadth only through existing owner-scoped lanes such as HARNESS-002/#177 and SANDBOX-002/#175 when eligible. **ADOPT** retained negative findings and repeated task checks through GOLD-002/#178 and verifier QA. **IGNORE** provider-count parity and first-party RL framework implementation. This recommendation does not lift the hold on #263 or authorize any sandbox implementation or execution.

## 5. HUD

**Observed:** The [SDK README](https://raw.githubusercontent.com/hud-evals/hud-python/main/README.md) documents a manifest/start/grade envelope, capability-driven interaction, template-based tasks, image deployment, taskset synchronization, and trace recording. Its capabilities include shell, MCP, browser, GUI, and beta robotics. These are documented interfaces, not evidence that any Veritas package has successfully deployed on the current upstream version.

The [coding-template README](https://raw.githubusercontent.com/hud-evals/01-coding-template/main/README.md) requires its golden integration path to receive full reward before shipping. It uses scenario-oriented examples, so it must not be assumed interchangeable with every current SDK template API without version-specific checks.

The [product page](https://www.hud.ai/) advertises automated grader/reward-hack QA, failure analysis, collaborative task review, and DataVendor monetization. These remain **vendor claims**, not independently established detection accuracy, revenue, account access, legal eligibility, or buyer demand.

**Disposition:** **INTEGRATE** distribution through external/manual #71 and existing portability contracts; **ADOPT** golden-path plus negative/exploit falsifiers through authoring and verifier-QA lanes. **EXCEED** is an assurance goal requiring evidence, not an achieved competitive ranking. **IGNORE** marketplace/platform cloning. Hosted access, NDA/tier behavior, publication, pricing, and payment remain unverified and separately authorized.

## Cross-cutting regression assessment

| Required dimension | Current evidence and disposition |
| --- | --- |
| Environment semantics | NeMo composition, Prime task/agent control flow, OpenEnv step API and HUD capability envelope are distinct abstractions. **INTEGRATE** adapters; retain canonical Veritas semantics. |
| Verifier QA | NeMo fixtures, HUD golden paths and Harbor's reported audit process provide concrete patterns. **ADOPT** falsifiers without substituting them for independent verifier QA. |
| Scientific / Frontier / training qualification | Interface docs and successful rollouts do not establish these states. **EXCEED** as an assurance objective; no head-to-head scientific result is claimed. |
| Realism | Containers and browser/native-artifact access do not by themselves prove fidelity. **EXCEED** through disclosed Veritas fidelity contracts and claim-specific evidence, not unsupported comparative adjectives. |
| Trajectories / reverification | Prime records traces, OpenEnv documents training captures, and NeMo documents offline rescoring. **INTEGRATE** while preserving identity, visibility and replay boundaries. |
| Diagnostics | NeMo documents controlled comparisons; HUD advertises diagnosis. **ADOPT** useful presentation, retain intervention/evidence limits. |
| Developer experience | Documented scaffold/validate loops are actionable patterns. **ADOPT** within DX ownership; do not start duplicate authoring frameworks. |
| Sandbox / harness breadth | Multiple projects document external harnesses/providers. **INTEGRATE** where demand and authorization justify it; **IGNORE** provider-count parity. |
| Portability / conformance | Similar envelopes do not establish semantic equivalence. **EXCEED** on explicit semantic-loss and conformance evidence, as a design goal. |
| Expert task QA | Harbor reports human audit and retained attack checks. **ADOPT** through GOLD-002; do not infer an independent Veritas red-team occurred. |
| Procurement / release packaging | Prime/HUD offer distribution surfaces; Veritas's package must preserve private/public and UNKNOWN boundaries. **INTEGRATE** distribution, never equate package installation with commercial completion. |

## Internal baseline and executable sequence

At the exact Veritas baseline above, [BUILD_STATUS.md](../../BUILD_STATUS.md) records software release 0.11.0, the frozen SRE portability proof, and post-release generic operational integration. That document, the scientific overlay and individual evidence contracts remain authoritative. This comparative review reran none of their scientific or release evidence. It does not promote a release or infer broad qualification from a narrow SRE result.

The following trusted bot status snapshots were read on 2026-11-07. Links identify the records; these are mutable live snapshots, not permanent permission grants. Labels, issue-body State fields, strategic rank and this table cannot override them.

| Lane | Observed coordination / repository state | Consequence for this review |
| --- | --- | --- |
| HARNESS-001 #176 | [DONE, transition 11](https://github.com/FPC-effortless/veritas/issues/176#issuecomment-5454878595), linked #259 | Reuse the merged contract, not a duplicate foundation. |
| DX-003 #172 | [REVIEW, transition 8](https://github.com/FPC-effortless/veritas/issues/172#issuecomment-5455031182), linked #261; #261 merge `f6ebcf7` is in baseline history | Code presence is not permission to overwrite or silently complete stale coordination. Reconcile through the owning authorized workflow. |
| TRAIN-001 #162 | [DONE, transition 3](https://github.com/FPC-effortless/veritas/issues/162#issuecomment-5461181957), linked #461; implementation merge `6e2911a` present | Reuse the offline policy engine. [Its contract](../training_qualification/README.md) is not a trainer, execution attestor, or real training-value PASS. |
| PKG-001 #168 | [BLOCKED, transition 3](https://github.com/FPC-effortless/veritas/issues/168#issuecomment-5461181154), old limitation-privacy finding; #299 merge `b4c0b11` present | Report the code/status mismatch, not a new claim or automatic DONE. Authorized reconciliation must verify the actual fix. |
| HARNESS-002 #177, SANDBOX-002 #175 | [#177 BLOCKED](https://github.com/FPC-effortless/veritas/issues/177#issuecomment-5461180710), [#175 BLOCKED](https://github.com/FPC-effortless/veritas/issues/175#issuecomment-5461180936), each transition 0 | Integration targets only; neither is advertised as claim-ready. |
| GOLD-002 #178, DIAG-002 #193 | [#178 BLOCKED](https://github.com/FPC-effortless/veritas/issues/178#issuecomment-5461180616), [#193 BLOCKED](https://github.com/FPC-effortless/veritas/issues/193#issuecomment-5461178584), each transition 0 | QA/diagnostic dispositions map to existing owners but do not authorize execution. |
| ACTOR-001 #269, CONV-001 #199 | [#269 BLOCKED](https://github.com/FPC-effortless/veritas/issues/269#issuecomment-5461171254), [#199 BLOCKED](https://github.com/FPC-effortless/veritas/issues/199#issuecomment-5461177839), each transition 0 | Capability negotiation and package convergence remain scope/dependency-gated. |
| SANDBOX-001 #174 / PR #263 | [BLOCKED, transition 12](https://github.com/FPC-effortless/veritas/issues/174#issuecomment-5454980376); unresolved security review restriction | Do not recommend integration, inspect its implementation, or execute its artifacts under this review. Only its public status/reference was read. |

Strategic priority remains trustworthy evidence, retained attacks, controlled diagnostics, usable packaging and selective ecosystem interoperability. **Executable order is not a ranked feature list**:

1. Reuse already-integrated contracts and implementation; do not recreate completed work from this old review.
2. Before any future implementation, verify trusted state, frozen ownership, actual dependencies and exact-head gates. A BLOCKED lane remains blocked even if a provider appears merged. Any required reconciliation belongs to the authorized coordinator, not this document.
3. Preserve [existing-work classifications](../roadmap/existing-work-audit.md): #28 is EVIDENCE_ONLY, and #25's accidental integration was reverted by #501 (`7dcf1b0`, present in baseline history). Neither is an execution or merge recommendation. Existing scope holds, including #263, remain intact.
4. External distribution #71 and seller/payment #32 remain separate manual-authority work under that same audit. No current account-native access, listing, payment or private-evidence completion was established here.
5. Any future training usefulness claim must satisfy the canonical training evidence contract. The old instruction to keep TRAIN-001 implementation blocked is withdrawn; implementation-DONE is not empirical capability gain.

## Source ledger and unavailable evidence

All primary pages linked in sections 1–5 were checked on **2026-11-07 UTC**. This is a read date, not their publication date. The material available through those pages supports the narrowed descriptions above. The browser reported cached ages from today to six days old; upstream pages can change after this check.

- NeMo: environment concepts, new-environment guide and evaluation guide retrieved successfully. A guessed `NVIDIA/NeMo-Gym` GitHub URL returned 404; it is not used as evidence of product absence. Official NVIDIA documentation provides the supported facts.
- Prime: README, overview, top-level tasksets/harnesses/env/runtimes guides retrieved. Old `docs/v1/tasksets.md` and `docs/v1/harnesses.md` returned 404; current linked replacements were used. No claim of current Modal support is retained.
- OpenEnv: old GitHub repository URL redirected; current `openenv/OpenEnv` README retrieved. No stale experimental-status or delayed-reward-RFC claim is needed for the current disposition.
- Harbor: README, Harbor Index and RL guide retrieved. The RL guide resolved to `26106c6d9c66848a1440faf5724d336affac52aa` documentation. Provider throughput, leaderboard integrity and task-selection quality were not reproduced.
- HUD: SDK README, coding-template README and public product page retrieved. Hosted training effectiveness, QA accuracy, buyer demand, pricing/tier/NDA behavior and account-native compatibility remain unverified.
- Veritas: baseline AGENTS, BUILD_STATUS, training qualification contract, existing-work audit and the linked trusted status records were read. No private benchmark rows, held-out artifacts, secret-bearing exports, models or external runs were accessed.

## Duplicate / supersession disposition and falsifiers

No new roadmap item or expanded trainer/model-serving/cloud/marketplace program is warranted by this review. Recommendations map to the named existing contracts. No duplicate was identified that this document can legitimately mark superseded; no issue/PR was closed or status changed. A future duplicate disposition must use its owning coordination process rather than silently treating old status as current.

This review fails if a dated/unavailable source is treated as current verified capability, marketing becomes scientific evidence, blocked work is advertised as READY, a merge is called qualification, private evidence is exposed, or feature counts alone justify scope expansion. The refresh explicitly corrects the first and third risks while retaining separate implementation, scientific, Frontier, training, commercial and release authorities.
