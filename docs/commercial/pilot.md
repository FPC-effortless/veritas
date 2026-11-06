# Veritas Paid Design-Partner Pilot

## Objective

Evaluate a customer's real AI model or agent against a frozen Veritas private benchmark and produce an evidence-backed capability report that can support a concrete model-selection, regression, harness, training or deployment decision.

The default first pilot uses the qualified and frozen **Veritas SRE Evaluation Pack v1 / SRE v4** release. SRE v3 is retired from unseen private scoring and must not be used as the paid-pilot panel.

## Standard pilot scope

1. **Integration** — connect the customer's model or agent harness through an OpenAI-compatible endpoint, local checkpoint, container or agreed adapter without exposing evaluator truth.
2. **Dry run** — validate prompt/tool schemas, structured outputs, deterministic or replicate semantics, budgets and trajectory capture on non-private cases.
3. **Private evaluation** — run the exact frozen private panel while retaining candidate, evidence-manifest, qualification-report, panel and private-release-manifest IDs.
4. **Failure analysis** — classify capability gaps without automatically disclosing private case truth.
5. **Readout** — deliver a versioned scorecard, uncertainty, benchmark anchors and recommended next experiment.
6. **Optional re-evaluation** — repeat on the same undisclosed panel for strict regression testing or on a newly qualified panel after private case disclosure.

## Default SRE deliverables

- benchmark version and all five sealed release identities;
- model/harness/version metadata;
- balanced accuracy;
- macro F1;
- raw private-panel accuracy and 95% Wilson interval;
- majority-class baseline and raw-accuracy lift over that baseline;
- structured-output parse reliability;
- per-causal-class precision, recall, F1 and recall uncertainty;
- aggregate confusion diagnostics;
- oracle / competent / myopic / random / exploit benchmark anchors;
- buyer-safe written evaluation report;
- optional confidential case-level debugging report under the benchmark-retirement policy.

## Success criteria

The pilot is commercially successful if the customer can answer at least one decision question that was materially uncertain before the evaluation, for example:

- Which model should handle this incident-analysis workload?
- Did our new prompt, tool layer or harness improve performance?
- Does a larger model improve enough to justify inference cost?
- Which causal classes remain failure modes?
- Did a post-training run improve held-out capability without increasing regressions?
- Should this system advance to a more realistic operational or long-horizon environment?

The pilot does **not** require the evaluated model to achieve a predetermined score. A negative or null result is valid commercial output if it resolves a real decision with credible evidence.

## Customer inputs

The customer supplies one of:

- an OpenAI-compatible model endpoint;
- an agent endpoint or harness;
- a container/CLI runnable in an isolated environment;
- a model checkpoint evaluated in the agreed compute environment.

The customer also supplies the exact model/harness identifier and any relevant inference constraints.

## Private evaluation boundary

Private benchmark snapshots, later resolution evidence, labels and oracle outcomes remain evaluator-side. See [Private Benchmark Handling](private-benchmark-handling.md).

Detailed operator reports containing per-case expected labels remain in controlled private storage. Buyer/public reports are produced through the explicit sanitization contract and omit scenario IDs and per-case prediction/truth pairs.

Commercial execution consumes the sealed SRE v4 release directly; it must not reacquire provider feeds or regenerate the private split. Before inference, the evaluator verifies candidate, evidence-manifest, qualification-report, panel and private-release-manifest identities.

If private truth is disclosed for debugging, those cases are treated as consumed and are not subsequently described as unseen private-test cases.

## Expansion options

After the first SRE pilot, a customer can expand into:

- ProjectWorld v2 for long-horizon project orchestration and recovery;
- CompanyWorld for enterprise investigation/action/control;
- Observatory matched-panel regression tracking across model or harness versions;
- training-value experiments using train-world data and fresh held-out evaluation;
- 0.11 industrial sandboxes when live-system fidelity is required by the customer's decision.

## Training-value extension

A training experiment must separate training and held-out panels, run multiple training RNG seeds where practical, preserve exact panel hashes, and report paired per-episode effects, uncertainty and seed variance. Broad transfer claims require source/grammar-disjoint evaluation rather than only different episode IDs from the same generated family.

## Commercial terms

Commercial terms are quoted separately based on evaluation volume, inference cost, integration complexity, private-world generation requirements, confidentiality requirements and whether the customer needs a one-time evaluation, repeated regression testing or a training environment.
