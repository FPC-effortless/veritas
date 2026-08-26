# Veritas funding and bounty application packets

Updated: 2026-08-26

This document is intentionally evidence-constrained. Do not claim independent reproduction, frontier-model validation, or training lift until those results exist.

## Canonical project description

Veritas is an open verifier-grounded evaluation and RL-environment framework for long-horizon operational agents. Its CompanyWorld environment presents synthetic enterprise worlds with public records, hidden structured ground truth, executable operational actions, and deterministic/mostly deterministic verification. The current evidence package includes six open-model calibration runs, retained GitHub Actions provenance, exploit/degenerate-policy checks, level-specific no-work anchors, baseline-adjusted scoring, and negative held-out SFT results.

Current evidence PR: https://github.com/FPC-effortless/veritas/pull/38
Independent reproduction request: https://github.com/FPC-effortless/veritas/issues/41

## Claims currently supported

- Six open language models have been run on a fixed CompanyWorld calibration slice with auditable external-CI artifacts.
- Qwen2.5-1.5B and Qwen2.5-3B produced parseable structured outputs on all 10 calibration episodes but remained close to no-work baselines, separating format compliance from operational capability.
- Existing held-out LoRA/SFT experiments did not improve verifier reward and are published as negative results.
- CompanyWorld includes public-reference solvers, hidden oracle state, and anti-exploit/degenerate-policy checks.
- Calibration reporting now supports raw, above-no-work, and normalized reward.
- A train-vs-heldout diagnostic v2 and a public-only noise/conflicting-projection ablation have been implemented.

## Claims not yet supported

- Veritas training improves held-out capability.
- CompanyWorld rankings generalize to frontier-model performance.
- CompanyWorld predicts real enterprise deployment performance.
- A third party has independently reproduced the benchmark.

---

# 1. Marius Hobbhahn / Manifund

## Ask

$5,000 compute/evaluation top-up for a 4-6 week CompanyWorld evidence sprint.

## One-paragraph pitch

Veritas is building verifier-grounded evaluations for long-horizon agents operating in noisy synthetic enterprise worlds. The current open evidence package already includes six real-model runs, hidden-ground-truth verification, exploit baselines, and negative training results. The proposed sprint will use the next $5k almost entirely for stronger/frontier-model inference, controlled noise/conflict, horizon and tool-budget ablations, independent reproduction, and a corrected train-vs-heldout experiment. The goal is not to prove a predetermined result; it is to produce an auditable open evaluation package that reveals where agent capability survives or fails under misleading evidence and long-horizon operational control.

## Budget

- $2,500 stronger/frontier model API and inference runs
- $1,000 repeated ablations / seeds / OOD evaluations
- $750 independent reproduction support and external compute reimbursement
- $500 training-value diagnostic runs
- $250 artifact hosting / contingency

## Milestones

1. >=1 substantially stronger model baseline using baseline-adjusted scoring.
2. Noise/conflicting-evidence ablation with preserved reference solvability.
3. Tool-budget/horizon or OOD ablation.
4. Training-value v2 result that distinguishes fitting from transfer.
5. At least one independent reproduction attempt with environment details and raw result.
6. Public report with negative findings retained.

## Status

Initial fit-check email sent to Marius on 2026-08-26.

---

# 2. BlueDot Rapid Grant

## Suggested ask

$3,000 initially, expandable only after stronger evidence.

## Form-ready description

I am already building an open technical AI-safety evaluation project for advanced agents. Veritas/CompanyWorld tests whether language-model agents can reconstruct and act on operational state from conflicting enterprise evidence while being scored against hidden structured ground truth. The work is already underway: six open models have been evaluated, results and provenance are public, and negative training results have been retained rather than reframed as success.

Funding would remove a specific experimental bottleneck: stronger-model/API access and repeated robustness runs. The funded phase would evaluate stronger agents under conflicting evidence, additional irrelevant context, longer horizons, and constrained tool budgets; run a corrected training-fit-vs-transfer experiment; and seek independent reproduction. The primary safety relevance is evaluation science for autonomous agents: measuring whether apparent competence survives adversarially misleading or noisy operational context rather than relying on surface task success.

## Requested costs

- $1,800 model API / hosted inference
- $600 repeated robustness/OOD runs
- $400 external reproduction compute reimbursement
- $200 artifact/storage contingency

## Concrete outputs

- open benchmark artifacts and hashes;
- baseline-adjusted model results;
- noise/conflict ablation;
- training diagnostic v2;
- replication record;
- short public write-up including failures/null results.

## Why now

The infrastructure and initial evidence already exist. The marginal bottleneck is experimental compute rather than project formation.

---

# 3. Snorkel Open Benchmarks Grant

## Project to submit

**CompanyWorld Open: Verifier-Grounded Long-Horizon Operational Agent Benchmark**

## Proposed public scope

Release a deliberately public subset of CompanyWorld while retaining any future commercial/private generator or held-out distributions outside the grant project. The grant output would include:

- public benchmark specification;
- reproducible task generator or fixed open task corpus;
- structured evidence records;
- hidden-answer build pipeline with release-safe evaluation package;
- verifier implementation;
- degenerate/exploit baselines;
- stronger-model calibration and robustness ablations;
- documentation and an academic-style benchmark report.

## Application description

Current agent evaluations often conflate output formatting, retrieval, reasoning, and operational control. CompanyWorld separates these by representing a latent operational world, rendering heterogeneous records and misleading projections, asking an agent to reconstruct claims and/or execute actions, and verifying the result against private structured state. Initial open-model experiments demonstrate that models can satisfy output format requirements while remaining near no-work operational baselines, motivating a larger open benchmark focused on evidence-grounded long-horizon autonomy.

The proposed collaboration would expand CompanyWorld Open into a high-quality public benchmark with expert data/evaluation support, stronger calibration, adversarial evidence variants, and independently reproducible artifacts. Existing Veritas IP outside the grant remains separate; all agreed Program outputs would be released under the required permissive licenses.

## Important program constraint

Snorkel support is in-kind, not cash. Do not use this route for personal compensation. The public grant artifact must be kept cleanly separable from private Veritas generators and future commercial holdouts.

---

# 4. Prime Intellect Application-Only Bounties

## Qualification statement

I have built Veritas, an independent open project for verifier-grounded LLM agent evaluation and RL environments. The project includes executable synthetic operational worlds, private ground truth, deterministic verifiers, task distributions, anti-exploit policies, calibration runners, held-out training experiments, and reproducibility artifacts. A current empirical evidence PR is available at https://github.com/FPC-effortless/veritas/pull/38.

## Preferred targets

Apply only to a task where prior library experience can be represented truthfully. Do not claim extensive use of a software library without evidence.

### Best conceptual fits

1. Xbench-DeepSearch / search-and-tool-use benchmark implementation.
2. AppWorld benchmark implementation.
3. FutureX full pipeline.
4. `verifiers` library evals only if sufficient direct library experience can be demonstrated.

## Relevant experience

- Designed hidden-ground-truth operational benchmarks.
- Built public-only deterministic reference solvers.
- Implemented model runners and structured-output parsing.
- Built interactive, sequential and dynamic execution surfaces.
- Added reward integrity tests against empty, abstention, citation-only, projection-trust and field-stuffing policies.
- Ran real-model calibration and held-out LoRA/SFT experiments on public CI.
- Added baseline-normalized evaluation and robustness-ablation infrastructure.

## Proposed implementation approach for a benchmark bounty

1. Faithfully reproduce source task semantics before extending them.
2. Build a deterministic/replayable harness and explicit verifier contract.
3. Separate public observations from answer/evaluator state.
4. Add degenerate-policy and leakage tests.
5. Reproduce reported/source scores on appropriate models where feasible.
6. Add training integration only after evaluation validity passes.
7. Publish raw artifacts and reproducibility metadata.

---

# 5. Technical AI-safety funding route

Do not reuse the earlier unsupported statement that a specific "TAIF" program is presently open at $10k-$150k unless an official current application page is verified. Current application strategy should instead prioritize verified-open routes such as BlueDot Rapid Grants and Marius/Manifund, while monitoring larger technical AI-safety RFPs.

## Safety framing for future larger grants

The most defensible theory of change is evaluation science for increasingly autonomous agents:

1. advanced agents increasingly act across tools and long-horizon workflows;
2. conventional point-answer benchmarks can miss failures caused by stale, conflicting or strategically misleading evidence;
3. verifier-grounded operational worlds can expose false state reconstruction, unjustified certainty, reward hacking, authority violations and execution errors;
4. reliable measurements make it easier for labs and safety evaluators to identify dangerous capability/reliability gaps before deployment or increased autonomy.

Do not frame CompanyWorld as catastrophic-risk work merely because it involves agents. The safety application becomes stronger only when stronger models, adversarial evidence, autonomy/horizon scaling and independent reproduction demonstrate that the benchmark captures meaningful failure modes.
