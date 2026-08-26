# Veritas SRE Evaluation Pack v1

## Product

**Veritas SRE Evaluation Pack v1** is a private, source-disjoint evaluation package for measuring whether an AI model or agent can infer the likely causal class of active service incidents from incomplete early evidence without access to later resolution notes.

It is the first Veritas benchmark SKU to pass the generic Benchmark Qualification protocol on a fresh empirical source family.

## Qualified benchmark evidence

The qualified SRE v3 candidate was compiled from structured incident histories from CircleCI, Discord, Dropbox, MongoDB and npm.

Qualification result:

- candidate: `SRE-CAND-24057DDECB32893163ED`;
- qualification report: `QREPORT-B6933216BEC640C258AF10D5`;
- total scenarios: 173;
- private-test scenarios: 34;
- failed qualification gates: 0;
- oracle mean: 1.0000;
- competent public-evidence baseline: 0.88235;
- myopic baseline: 0.82353;
- seeded-random baseline: 0.17647;
- exploit baseline: 0.0000.

The private candidate is frozen separately from the public repository. Public artifacts may contain candidate IDs, panel IDs, evidence-manifest IDs, aggregate policy means and qualification gates, but not raw resolution snapshots, per-scenario oracle predictions or private causal labels.

## Customer question answered

The standard pilot answers:

> Given the evidence available while an incident is still unfolding, how reliably does this model or agent identify the most likely causal class, and where does it fail relative to calibrated benchmark anchors?

Current causal classes are:

- regression;
- infrastructure;
- capacity;
- transient.

## Evaluation boundary

The evaluated system receives:

- incident title;
- the first configured public incident updates;
- the four allowed output classes;
- a strict structured-output instruction.

It does **not** receive:

- later resolution notes;
- root-cause analysis text reserved for evaluator construction;
- the private causal label;
- oracle policy outputs;
- private per-case evaluation metadata.

## Standard deliverables

A completed evaluation produces:

1. immutable benchmark candidate and panel identifiers;
2. model/harness/version identity;
3. overall accuracy;
4. 95% Wilson uncertainty interval;
5. structured-output parse reliability;
6. per-causal-class accuracy and uncertainty;
7. confusion diagnostics;
8. benchmark calibration anchors;
9. a buyer-safe evaluation report;
10. optional confidential failure analysis under a case-retirement policy.

## Supported integration modes

### OpenAI-compatible endpoint

```bash
python tools/run_sre_endpoint_evaluation.py \
  --snapshot-dir <private-snapshot-dir> \
  --endpoint https://customer.example/v1/chat/completions \
  --model customer-agent \
  --providers circleci discord dropbox mongodb npm \
  --version sre-v3 \
  --expected-candidate-id SRE-CAND-24057DDECB32893163ED \
  --output customer-sre-evaluation.json
```

Authentication is read from `VERITAS_MODEL_API_KEY` by default. The private benchmark remains on the evaluator side.

### Local/open checkpoint

```bash
python tools/run_sre_open_model_evaluation.py \
  --snapshot-dir <private-snapshot-dir> \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --providers circleci discord dropbox mongodb npm \
  --version sre-v3 \
  --expected-candidate-id SRE-CAND-24057DDECB32893163ED \
  --output model-evaluation.json
```

## Buyer-facing report

```bash
python tools/build_sre_customer_evaluation_report.py \
  customer-sre-evaluation.json \
  --customer-name "Example Co" \
  --qualification public-qualification-summary.json \
  --output example-co-sre-report.md
```

The standard buyer report intentionally omits private per-scenario oracle labels. If case-level truth is disclosed for debugging, those cases should be treated as consumed and retired from future private scoring.

## Commercial validity boundaries

This pack is suitable for paid design-partner evaluation once the seller has completed contracting/payment details and the target model or harness can be invoked reliably. It is not represented as a universal proxy for all production SRE work.

The strongest current claim is narrower and testable:

> Veritas can construct a source-disjoint SRE incident benchmark that passes feasibility, contamination, leakage, replay, provenance, discrimination and exploit-resistance qualification gates, and can evaluate real model/harness behavior on a frozen hidden panel with immutable evidence identifiers.

The next commercial evidence requirement is external use: a third party must run a real model or agent through this pack and confirm that the resulting capability report is useful for a concrete model-selection, regression, post-training or harness decision.
