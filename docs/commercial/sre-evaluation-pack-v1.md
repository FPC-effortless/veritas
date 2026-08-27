# Veritas SRE Evaluation Pack v1

## Product

**Veritas SRE Evaluation Pack v1** is a private, source-disjoint evaluation package for measuring whether an AI model or agent can infer the likely causal class of active service incidents from incomplete early evidence without access to later resolution notes.

The product is built on the Veritas 0.10 Benchmark Qualification protocol. A commercial evaluation is valid only against a frozen candidate whose current qualification report is `benchmark_candidate` and whose private panel has never been published.

## Frozen benchmark

SRE v3 is **retired from private commercial scoring**. It passed an earlier qualification gate set, but the stronger 0.10 stratum-coverage rule rejects its 34-case private panel because it is overwhelmingly transient, and historical public Actions artifacts exposed raw v3 qualification material.

The commercial benchmark is the frozen SRE v4 release:

- candidate: `SRE-CAND-92A84929AD1E82E24357`;
- evidence manifest: `EVID-2C69B48DCDD5F2232EABDC9B`;
- qualification report: `QREPORT-C585121E94D91766BB6664E3`;
- private panel: `QPANEL-AFF065BA4C2FD75BE9BB3EBE`;
- private release manifest: `PRIVREL-036192DA63716D331C929C0C`;
- 87 total scenarios and 30 private-test cases;
- private causal support: capacity 6, infrastructure 6, regression 10, transient 8;
- 18/18 qualification gates passed.

The source family contains Airtable, Claude, Elastic, Figma, Grafana, Hedera, HubSpot, IBM Cloud Security, Instructure, New Relic, Postman, Reddit, Render, Snowflake, Supabase and Webflow.

The private source snapshots, exact split and later-evidence causal material are sealed in one private release bundle. Commercial evaluators **consume that sealed candidate directly**. They do not reacquire provider feeds, reconstruct scenarios or rerun the split.

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
- the configured early public incident updates;
- the four allowed output classes;
- a strict structured-output instruction.

It does **not** receive:

- later resolution notes;
- root-cause analysis text reserved for evaluator construction;
- the private causal label;
- oracle policy outputs;
- private per-case evaluation metadata.

## Standard metrics

Balanced accuracy and macro F1 are the primary headline metrics. Raw accuracy is secondary and is always reported beside the majority-class baseline so an imbalanced panel cannot make a trivial constant classifier look strong.

A completed evaluation produces:

1. immutable benchmark candidate, evidence-manifest, qualification-report, panel and private-release-manifest identities;
2. model/harness/version identity;
3. balanced accuracy;
4. macro F1;
5. raw accuracy and 95% Wilson interval;
6. majority-class baseline and raw-accuracy lift over that baseline;
7. structured-output parse reliability;
8. per-causal-class precision, recall, F1 and recall uncertainty;
9. aggregate confusion diagnostics;
10. benchmark calibration anchors;
11. a buyer-safe evaluation report;
12. optional confidential failure analysis under a case-retirement policy.

## Supported integration modes

### OpenAI-compatible endpoint

```bash
python tools/run_sre_endpoint_evaluation.py \
  --qualification <private-v4-bundle>/results/sre-v4/qualification.json \
  --endpoint https://customer.example/v1/chat/completions \
  --model customer-agent \
  --expected-candidate-id SRE-CAND-92A84929AD1E82E24357 \
  --expected-evidence-manifest-id EVID-2C69B48DCDD5F2232EABDC9B \
  --expected-report-id QREPORT-C585121E94D91766BB6664E3 \
  --expected-panel-id QPANEL-AFF065BA4C2FD75BE9BB3EBE \
  --expected-private-release-manifest-id PRIVREL-036192DA63716D331C929C0C \
  --output <private-operator-report.json> \
  --public-output customer-sre-evaluation.json
```

Authentication is read from `VERITAS_MODEL_API_KEY` by default. The detailed operator report remains private; `--public-output` omits scenario IDs, per-case predictions and per-case expected labels.

### Local/open checkpoint

```bash
python tools/run_sre_open_model_evaluation.py \
  --qualification <private-v4-bundle>/results/sre-v4/qualification.json \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --expected-candidate-id SRE-CAND-92A84929AD1E82E24357 \
  --expected-evidence-manifest-id EVID-2C69B48DCDD5F2232EABDC9B \
  --expected-report-id QREPORT-C585121E94D91766BB6664E3 \
  --expected-panel-id QPANEL-AFF065BA4C2FD75BE9BB3EBE \
  --expected-private-release-manifest-id PRIVREL-036192DA63716D331C929C0C \
  --output <private-operator-report.json> \
  --public-output model-evaluation.json
```

## Buyer-facing report

```bash
python tools/build_sre_customer_evaluation_report.py \
  customer-sre-evaluation.json \
  --customer-name "Example Co" \
  --qualification public-qualification-summary.json \
  --output example-co-sre-report.md
```

The standard buyer report intentionally omits the private per-scenario oracle. If case-level truth is disclosed for debugging, those cases are consumed and must be retired from future unseen private scoring.

## Private execution contract

Private source snapshots, split manifests and oracle labels must not be committed to the public repository or uploaded raw to public-repository Actions artifacts, even with short retention. The optional manual model-evidence workflow consumes one checksum-pinned sealed private bundle in an ephemeral runner and uploads only sanitized aggregate outputs.

Every model report is rejected unless candidate, evidence-manifest, qualification-report, panel and private-release-manifest identities all match the sealed release. This prevents a provider-list mismatch or accidental re-split from producing commercially invalid evidence under a familiar candidate label.

## Commercial validity boundaries

This pack is suitable for paid design-partner evaluation after the seller has completed the required contracting/payment controls and at least two real-model runs have been recorded against the exact frozen v4 panel. It is not represented as a universal proxy for all production SRE work.

The strongest intended claim is:

> Veritas can construct a source-disjoint, contamination-audited SRE incident benchmark with material support across its causal classes, freeze its hidden panel evaluator-side, and evaluate real model/harness behavior with imbalance-aware metrics and immutable release identities.

The next commercial validation layer is external use: a third party must confirm that the resulting capability report is useful for a concrete model-selection, regression, post-training or harness decision.
