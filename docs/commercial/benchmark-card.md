# Veritas — Commercial Benchmark Card

## What Veritas measures

Veritas evaluates AI models and agents in executable or evidence-grounded operational worlds with independent evaluator truth, reproducible versioning and explicit anti-gaming qualification.

The commercial system is designed to answer concrete model-development questions:

- which model or harness performs better on a defined operational capability;
- where an agent fails under incomplete evidence, permissions, state transitions or long-horizon constraints;
- whether a model/harness/training change produces a credible improvement on a matched private panel;
- whether a benchmark is itself feasible, discriminative, contaminated, imbalanced or exploitable before it is sold as an evaluation.

## Qualification status by environment family

### SRE Incident Response — qualified frozen v4

**Primary commercial SKU:** [Veritas SRE Evaluation Pack v1](sre-evaluation-pack-v1.md).

SRE v3 is not a current private benchmark. It is retained as historical/calibration material because:

- the current `private_stratum_coverage` gate rejects its 34-case private set as majority-transient;
- historical public Actions artifacts exposed raw v3 qualification material.

SRE v4 is the qualified replacement. The frozen candidate `SRE-CAND-92A84929AD1E82E24357` contains 87 scenarios and 30 private-test cases across 16 fresh providers. Private causal support is capacity 6, infrastructure 6, regression 10 and transient 8. All 18 qualification gates pass. The sealed private panel is `QPANEL-AFF065BA4C2FD75BE9BB3EBE`.

The evaluated system receives early incident evidence and predicts one of four causal classes. Later causal/resolution evidence is evaluator-side only. Balanced accuracy and macro F1 are the primary model metrics; raw accuracy is reported beside the majority-class baseline.

Commercial model evaluation consumes the exact sealed v4 `qualification.json` and checks candidate, evidence-manifest, qualification-report, panel and private-release-manifest identities. Reacquiring provider feeds or recomputing the split is not a valid commercial run.

### ProjectWorld v2 — qualified benchmark candidate

ProjectWorld v2 is a structurally generated full-project operational environment covering project type, delivery model, jurisdiction, systems, contracts, stakeholders, WBS, resources, approvals, risks, requirements and disturbance processes.

The latest 200-project qualification produced 40 private-test projects with zero failed gates. Policy means were:

- oracle 1.0000;
- competent 0.23144;
- myopic 0.14115;
- random 0.00143;
- exploit 0.0000.

ProjectWorld v2 is commercially promising but does not yet have the same buyer-facing integration/report pack as SRE.

### CompanyWorld / operational distribution — validated substrate, not current primary qualified SKU

CompanyWorld remains a broad synthetic enterprise environment spanning investigation, action, sequential control and portfolio operation. It has hardened evidence-grounded verification, matched-panel experimental integrity and replicated Training Value v3 evidence, but the commercial package distinguishes that engineering/training evidence from the generic 0.10 Benchmark Qualification status used for releaseable benchmark candidates.

## Generic Benchmark Qualification contract

A candidate is not releaseable merely because tasks execute or a workflow exits successfully. Qualification checks include:

- source-group separation;
- cross-split near-duplicate contamination;
- private leakage;
- provenance completeness;
- deterministic replay;
- programmatic verification;
- broken-case / feasibility rate;
- oracle feasibility;
- oracle > competent > myopic policy ordering;
- random-policy ceiling;
- exploit-policy ceiling;
- optional private-stratum coverage;
- immutable evidence and private-release manifests.

Domain qualification workflows must assert `benchmark_candidate`; a `not_qualified` result fails the release workflow rather than being interpreted as a passing benchmark. Once a candidate is sealed, public CI verifies the frozen release identity instead of rebuilding it from mutable upstream data.

## Private benchmark boundary

Public artifacts may include candidate IDs, panel IDs, evidence-manifest IDs, qualification-report IDs, private-release-manifest IDs, aggregate scores, class distributions, bundle hashes and gate outcomes. Raw private snapshots, private labels, per-scenario oracle outcomes, and per-case model/expected-label pairs remain outside the public repository under the [private benchmark handling policy](private-benchmark-handling.md).

## Model evaluation protocol

A procurement-grade run should:

- freeze benchmark candidate, panel, evidence-manifest, qualification-report and private-release-manifest IDs;
- keep evaluator truth inaccessible to the model/harness;
- record exact model and harness identities;
- use deterministic generation where supported or explicit stochastic replicate identities otherwise;
- retain structured-output reliability;
- report balanced accuracy, macro F1, raw accuracy, majority baseline and uncertainty;
- preserve matched panels for before/after or model-vs-model comparisons;
- publish only sanitized aggregate reports;
- retire cases whose private truth is disclosed for debugging.

## Current commercial claim

Veritas does **not** claim that one score is a universal proxy for production performance.

The current defensible platform claim is:

> Veritas can compile operational benchmark candidates with independent truth, contamination/leakage controls, calibrated policy baselines, stratum-coverage checks and immutable evidence identities; reject candidates that fail those gates; freeze qualified private panels; and evaluate real models or agents on the exact sealed panel through a buyer-safe reporting contract.

At least two real-model runs on the exact frozen v4 panel and an external paid design-partner use remain the next commercial validation layers.
