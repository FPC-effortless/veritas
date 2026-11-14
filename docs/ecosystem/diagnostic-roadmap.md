# Research diagnostics roadmap

This tracks the requested architecture-agnostic workbench, beginning with
DIAGNOSTICS-001 (#519), tracked in [program #525](https://github.com/FPC-effortless/veritas/issues/525). A foundation is not a complete feature. The intended
product answers what failed, which explanations survive, which bounded experiment
can distinguish them, and whether a repair survives fresh evaluation. No finite
catalog promises complete diagnosis of arbitrary models or datasets.

| # | Feature | Current boundary and next acceptance milestone |
| --- | --- | --- |
| 1 | Capability adapter SDK | Initial callable SDK; fixed-weight sklearn/PyTorch, CLI and store acceptance. Bound JSON row schemas and deterministic replay/batch probes added in DIAGNOSTICS-002 (#521). Native learned persistent-model acceptance remains outstanding. |
| 2 | Coverage/evidence report | Version/scope/status and missing capabilities implemented. Next: reusable slices, uncertainty and finding-to-example navigation. |
| 3 | Budget-aware execution | Cooperative call/time limits, partial journal, outer TrainLab timeout. RAM/GPU/API hard caps and cost estimates remain unimplemented. |
| 4 | Reusable computations | [Bound prediction reuse](prediction-artifacts.md), exact request/hash checks and independent consumer reads implemented. Embedding/distributed caches remain future work. |
| 5 | Dataset audit | [Dataset pack](dataset-diagnostics.md) adds missing/null selected-feature findings and bounded row coverage. Semantic units, modalities and annotation alignment remain proposed. |
| 6 | Label investigation | Exact-feature label disagreements now produce review findings with row witnesses; no automatic correction. Adjudication and fresh-evaluation repair comparison remain proposed. |
| 7 | Leakage/split investigation | Exact selected-feature and declared entity/generator overlap now inspected across train/validation. Near duplicates, preprocessing and true mechanism independence remain unresolved. |
| 8 | Coverage/drift/rare cases | Proposed general slice/distribution analysis; no claim that existing identifiers prove independent causal coverage. |
| 9 | Training sanity | Existing optional PyTorch foundations plus actual scalar tiny-fit/frozen-update acceptance in [experiment packs](experiment-diagnostics.md). General shape/shift/mask checks remain incomplete. |
| 10 | Numerical/optimizer forensics | Ordered event pack localizes first observed nonfinite/gradient/update violations. Scaler/operator/context instrumentation remains incomplete. |
| 11 | Learning dynamics | Declared loss/diversity/acquisition/retention event checks implemented; missing coverage stays explicit. Causal forgetting and representation analysis remain unimplemented. |
| 12 | Resume/equivalence | Existing bounded CPU checkpoint/export checks; deterministic adapter replay/batch/order probes added. Precision/stochastic/distributed equivalence remains unverified. |
| 13 | Benchmark validity | Paired reference/expected-change/sensitive-group/deficient-control pack added. Actual general intervention execution and independence attestation remain incomplete. |
| 14 | Baseline/supervision qualification | Machine-readable supervision/budget/seed/selection ledger added, including failed and missing seeds. Competence evidence references remain caller-supplied, not verified. |
| 15 | Statistical design | Complete declared unit-by-seed paired bootstrap, effects and comparison-family adjustment added. Seed uncertainty, stopping/selection correction and experimental design remain incomplete. |
| 16 | Behavioral packs | Single-label classification, slice/confusion/error/calibration pack added. Other task packs and deployment acceptance remain incomplete. |
| 17 | State lifecycle debugger | Bounded lifecycle diagnostic plus store clear/repopulate control; native semantic debugger and conditional collateral-damage metrics remain future work. |
| 18 | State/component interventions | Existing bounded interventions; no general frozen-model/retraining intervention comparison SDK yet. |
| 19 | Whole-session cost | Initial direct host interval, phase ledger, failures/retries and explicit missing measurements. Memory, energy, billing, distributed timing and overhead calibration remain future work. |
| 20 | Quality/cost scaling | Context-checked descriptive quality/session-cost Pareto analysis added. Actual scaling sweeps, uncertainty and matched-reliability inference remain incomplete. |
| 21 | Failure browser/reproducer | Inspectable JSON artifacts/graph; no general UI browser, grouping or automatic minimization yet. |
| 22 | Hypothesis/repair verification | Research Lab supplies continuity; hypothesis ranking, experiment selection and fresh repair/regression orchestration remain proposed. |
| 23 | Diagnostic qualification | Injected data/artifact/reset faults plus training/benchmark/ledger/statistics/classification/cost clean-fault-unknown controls. No population-level sensitivity, false-alarm or overhead claim. |
| 24 | Portable collaboration/packs | Versioned six-pack API catalog and portable reports added; signed community loading and exact-version collaborative review UI remain incomplete. |

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
