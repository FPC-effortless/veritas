# Research diagnostics roadmap

This tracks the requested architecture-agnostic workbench, beginning with
DIAGNOSTICS-001 (#519), tracked in [program #525](https://github.com/FPC-effortless/veritas/issues/525). A foundation is not a complete feature. The intended
product answers what failed, which explanations survive, which bounded experiment
can distinguish them, and whether a repair survives fresh evaluation. No finite
catalog promises complete diagnosis of arbitrary models or datasets.

| # | Feature | Demonstrated boundary | Remaining acceptance |
| --- | --- | --- | --- |
| 1 | Capability adapters | Callable SDK, pinned prediction replays, and [learned SlotStore lifecycle conformance](native-memory-adapter.md) on a SET-only panel (#547). | Exercise the same adapter contract on native COPY/LINK/DELETE, other model families, and independent CLI/API implementations. |
| 2 | Coverage and evidence reports | [Offline evidence browser](diagnostic-bundles.md) inspected on desktop and at 320 px with raw sources, filters and coverage status (#535). | Inspect reusable interactive slices and uncertainty on large real reports, with keyboard and mobile acceptance. |
| 3 | Budget-aware execution | Cooperative call and time limits plus [Linux command supervision](resource-diagnostics.md) with inherited per-process limits and partial receipts. | Enforce API request/rate and supported aggregate/GPU budgets. Test hard termination, restart recovery and quota-denial paths. |
| 4 | Reusable computations | [Pinned prediction reuse](prediction-artifacts.md) and [imports](diagnostic-imports.md) replay live MLflow metrics and PyTorch trace captures (#553). | Verify embedding and distributed reuse, complete paginated import, cache isolation and equivalent outputs across supported producers. |
| 5 | Dataset audit | [Forge semantic audit](semantic-audit.md) checks bounded types, ranges, enums, units and declared UTF-8/JSON/CSV/PNG/PCM WAV profiles (#543). | Detect annotation-to-content misalignment and exercise more media profiles on representative fixtures with independently known validity. |
| 6 | Label investigation | Versioned reviewed corrections retain originals. A [public Wine repair pilot](dataset-repair.md) compared three fits on the same held-out evaluation rows (#551). | Verify real reviewer adjudication and replicable repair benefit across multiple naturally occurring label problems. |
| 7 | Leakage and splits | Exact/group overlap, declared transform-fit provenance and bounded lexical near-duplicates are [auditable](data-quality-diagnostics.md). | Verify observed transform fitting and generator independence. Test semantic near duplicates against independent ground truth. |
| 8 | Coverage, drift and rare cases | [Distribution checks](data-quality-diagnostics.md) include missingness, KS, total variation and rarity. One [labeled drift pilot](dataset-repair.md) records per-slice outcome differences (#551). | Detect semantic slices and distinguish effects of drift from ordinary sampling variation on independent projects. |
| 9 | Training sanity | [Tiny-fit controls](experiment-diagnostics.md) and [native PyTorch observation](training-observer.md) exercise dense CPU updates, classification and next-token input contracts (#559). | Exercise production-framework variants, accelerators and longer representative supervised and next-token loops. |
| 10 | Numerical and optimizer forensics | [Ordered trace checks](experiment-diagnostics.md) and [native CPU hooks](training-observer.md) localize observed activation, parameter gradient and update anomalies (#559). | Cover intermediate gradients, optimizer context, scaler behavior and distributed instrumentation. |
| 11 | Learning dynamics | [Declared trajectories](experiment-diagnostics.md) check loss and diversity. [Pinned slice panels](training-observer.md) track observed acquisition and regression (#559). | Verify fixed-panel dynamics on saved checkpoints with causal retention controls and model representation evidence. |
| 12 | Resume and equivalence | [Pinned resume comparison](resume-equivalence.md) checks exact and toleranced CPU state. The observed Torch control localizes omitted optimizer, RNG and sampler state (#549). | Exercise mixed precision, device and distributed resume on saved real-project checkpoints and compare supported state beyond the current CPU trace. |
| 13 | Benchmark validity | [Paired benchmark checks](experiment-diagnostics.md) score supplied oracle parity, sensitivity and deficient controls. [Lifecycle preflight](lifecycle-preflight.md) adds a concrete lifecycle panel. | Run independent oracle and shortcut controls in the general evaluator. Verify reference provenance and generator independence. |
| 14 | Baselines and supervision | [Comparison ledger](experiment-diagnostics.md) tracks supervision, tuning, seeds and budgets. [Competence screens](competence-panels.md) independently rescore bound predictions and complete maps (#539). | Calibrate diverse baselines on primitive tasks and verify supervision, tuning and budget provenance from actual runs. |
| 15 | Statistics and design | [Paired resampling](experiment-diagnostics.md) and [crossed uncertainty](comparison-design.md) report unit, seed and combined intervals for declared complete designs (#557). | Cover prospective sample design and stopping, and validate inference after adaptive selection on independent studies. |
| 16 | Behavioral packs | [Classification diagnostics](experiment-diagnostics.md) report confusion, calibration, error slices and unavailable labels. | Complete deployable regression, sequence and retrieval coverage with real-project acceptance, plus application-specific metrics. |
| 17 | State lifecycle | [State packs](state-diagnostics.md) execute declared histories and collateral-damage checks. [Native learned SET acceptance](native-memory-adapter.md) exercises updates and source/peer isolation (#547). | Run equivalent native acceptance for deletion, alias/reference and restoration semantics on multiple stateful architectures. |
| 18 | State and component interventions | [State probes](state-diagnostics.md) pair omitted-write replay and source/peer restore isolation. | Bind frozen weights and intervention histories to a general replay path, and verify retraining interventions and collateral outcomes. |
| 19 | Whole-session cost | [CPU receipts](resource-diagnostics.md) retain wall time, wait4 user/system CPU, peak process RSS and failed attempts. [Imports](diagnostic-imports.md) retain bounded profiler spans (#553). | Measure aggregate RAM, synchronized GPU/distributed work, energy and API billing within declared boundaries. |
| 20 | Quality and cost scaling | [Replayable matched CPU sessions](reliability-cost.md) link exact complete-map quality, failures and costs (#541). [Assessment checks](assessment-diagnostics.md) compare declared workloads. | Run native learned-state sweeps on matched quality and cost workloads with independent repeats and declared uncertainty. |
| 21 | Failure browser and reproducer | [Bounded reducer](state-diagnostics.md) preserves observed failures. [Offline browser](diagnostic-bundles.md) inspects verified reports and raw evidence (#535). | Minimize configurations and data as well as events. Execute portable reproducer commands in a clean environment. |
| 22 | Hypothesis and repair | [State repair checks](state-diagnostics.md) track fresh/regression outcomes. A [Wine repair pilot](dataset-repair.md) verifies one controlled label perturbation (#551). | Select and execute discriminating experiments across multiple plausible causes. Verify generalized repair and regression coverage on independent problems. |
| 23 | Diagnostic qualification | A [pinned scorer and native Wine pilot](diagnostic-qualification.md) retain detections, false alarms, localization gaps and timing pairs (#545). The pilot is inconclusive. | Qualify representative independent projects with calibrated overhead, annotated positives/negatives and complete exact localization evidence. |
| 24 | Portable packs and collaboration | [Verified bundles](diagnostic-bundles.md) and [OpenSSH reviews](signed-bundle-reviews.md) bind offline verdicts to an exact bundle. Verification uses a separately pinned recipient trust list (#555). | Establish authenticated team workflows and safe executable pack distribution, verification and portable replay. |

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
