# Research diagnostics roadmap

This tracks the requested architecture-agnostic workbench, beginning with
DIAGNOSTICS-001 (#519). A foundation is not a complete feature. The intended
product answers what failed, which explanations survive, which bounded experiment
can distinguish them, and whether a repair survives fresh evaluation. No finite
catalog promises complete diagnosis of arbitrary models or datasets.

| # | Feature | Current boundary and next acceptance milestone |
| --- | --- | --- |
| 1 | Capability adapter SDK | Initial callable SDK; fixed-weight sklearn/PyTorch, CLI and store acceptance. Next: native persistent-model conformance and schema/batching checks. |
| 2 | Coverage/evidence report | Version/scope/status and missing capabilities implemented. Next: reusable slices, uncertainty and finding-to-example navigation. |
| 3 | Budget-aware execution | Cooperative call/time limits, partial journal, outer TrainLab timeout. RAM/GPU/API hard caps and cost estimates remain unimplemented. |
| 4 | Reusable computations | Existing artifact hashing/receipt import; no general prediction/embedding cache or stale-cache qualification yet. |
| 5 | Dataset audit | Forge temporal/schema foundations; semantic units, modalities and annotation-alignment packs remain proposed. |
| 6 | Label investigation | Proposed: adjudication with versioned evidence and fresh-evaluation comparison; disagreement must not auto-change labels. |
| 7 | Leakage/split investigation | Forge grouped/temporal integrity; general near-duplicate, preprocessing and generator-mechanism analysis remain proposed. |
| 8 | Coverage/drift/rare cases | Proposed general slice/distribution analysis; no claim that existing identifiers prove independent causal coverage. |
| 9 | Training sanity | Existing optional PyTorch foundations; generalized shape/shift/mask/tiny-fit diagnostic packs remain incomplete. |
| 10 | Numerical/optimizer forensics | Existing finiteness checks; earliest-fault localization, scaler/update/optimizer context remain future work. |
| 11 | Learning dynamics | Proposed: slice learning, collapse and acquisition-versus-forgetting analysis. |
| 12 | Resume/equivalence | Existing bounded CPU checkpoint/export checks; broader cache/batch/precision/distributed equivalence remains unverified. |
| 13 | Benchmark validity | Bounded deletion intervention and explicit preflight review exist; general intervention SDK and qualified shortcut packs remain future work. |
| 14 | Baseline/supervision qualification | Lifecycle reviews require explicit judgments; general machine-readable supervision/tuning ledgers and baseline competence tests remain future work. |
| 15 | Statistical design | Proposed: paired/group-aware uncertainty, stopping and selection accounting; bootstrap cannot create independence. |
| 16 | Behavioral packs | Constructed scalar agreement and store-reset checks only in this slice; calibration, retrieval/generation/forecasting/agent packs are not implemented here. |
| 17 | State lifecycle debugger | Bounded lifecycle diagnostic plus store clear/repopulate control; native semantic debugger and conditional collateral-damage metrics remain future work. |
| 18 | State/component interventions | Existing bounded interventions; no general frozen-model/retraining intervention comparison SDK yet. |
| 19 | Whole-session cost | Initial direct host interval, phase ledger, failures/retries and explicit missing measurements. Memory, energy, billing, distributed timing and overhead calibration remain future work. |
| 20 | Quality/cost scaling | Proposed: qualified workload sweeps and uncertainty; tiny adapter timings must not be used as architecture rankings. |
| 21 | Failure browser/reproducer | Inspectable JSON artifacts/graph; no general UI browser, grouping or automatic minimization yet. |
| 22 | Hypothesis/repair verification | Research Lab supplies continuity; hypothesis ranking, experiment selection and fresh repair/regression orchestration remain proposed. |
| 23 | Diagnostic qualification | Initial injected-fault and clean software controls; no population-level detection sensitivity, false-alarm or overhead claims. |
| 24 | Portable collaboration/packs | Existing receipts, graph and exportable files; a community pack API and review-comment workflow remain future work. |

## Delivery order

1. Establish inspectable SDK contracts, coverage and timing with injected faults
   and real-library acceptance. That is the scope of the initial workbench PR.
2. Connect one native persistent-state adapter and a reusable prediction artifact
   contract. Verify reset/batching/order and fresh-versus-cached equivalence before
   claiming architecture breadth or reusable computation savings.
3. Add general dataset/benchmark validity packs and explicit supervision/tuning
   ledgers, with independent controls and conservative unresolved statuses.
4. Add measured resource counters and qualified quality/cost workload sweeps.
   Keep complete-call inference central to Woyengi's inference-heavy objective;
   do not substitute arithmetic counts or process training time for inference cost.
5. Add minimal reproductions and repair/regression workflows, then user-facing
   failure exploration and community packs once evidence contracts are stable.

Every phase needs executed clean/fault controls, bounded false-claim behavior,
independent review and exact-source reproduction. Scientific effectiveness and
research output per hour need separate measurements; merged infrastructure is
not proof of a better model or a frontier-performing research platform.
