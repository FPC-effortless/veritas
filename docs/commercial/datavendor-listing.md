# DataVendor Tier 1 Listing — Copy-Ready Draft

This file is the seller-side draft for the first formal DataVendor marketplace listing. It reflects DataVendor's current supply-first listing model: attach assets, set per-asset-type pricing, describe the offer, pass HUD review, and publish to the catalog.

## Listing strategy

List the qualified commercial SKU as **one managed RL/evaluation environment**, not as 30 individually saleable private tasks.

Reason: the fixed SRE v4 private panel is a measurement asset. Listing it as a positive-price 30-task taskset can make the tasks eligible for marketplace sampling and consume holdout secrecy. Keeping the panel evaluator-side inside the managed environment preserves the commercial/private boundary while still selling a runnable evaluation asset.

A separate public/synthetic taskset can be listed later if sampling/discovery is useful; do not use the frozen private panel for that purpose.

## Intent

**Publish a listing**

Use a Data Proposal instead only if HUD review blocks the formal listing or the platform requests demand validation first.

## Domain

Choose the closest current DataVendor tags to:

- AI / machine learning evaluation
- software engineering / DevOps / SRE
- agents / tool use
- incident response / operational reasoning

Do not choose regulated-domain tags unless the listing actually contains that domain's data.

## Asset

**Type:** RL environment / agent evaluation environment  
**Quantity:** 1  
**Delivery:** managed HUD runtime  
**Version:** Veritas SRE Evaluation Pack v1 / Veritas 0.11.0  
**Repository/release reference:** `https://github.com/FPC-effortless/veritas/releases/tag/v0.11.0`

Do not attach a raw zip of the private panel, private source snapshots, hidden causal labels, canonical private scenario IDs, or decryption material.

## Title

**Veritas SRE v1 — Private Incident-Cause Agent Evaluation**

## Executive summary

Veritas SRE Evaluation Pack v1 is a verifier-grounded private evaluation environment for testing whether AI models and agents can infer the likely causal class of an active service incident from incomplete early evidence, without access to later resolution notes. The frozen SRE v4 release contains 87 qualified scenarios and a sealed 30-case private panel across regression, infrastructure, capacity, and transient causal classes. All 18 scientific qualification gates pass. The exact panel has been exercised against two real open-model families and through a customer-equivalent authenticated OpenAI-compatible endpoint rehearsal. Veritas 0.11.0 adds standalone HUD compatibility with deterministic reset, canonical reward parity, opaque private task identity, and buyer-safe metering. Buyers receive managed evaluation access and buyer-safe aggregate results; the private evaluator truth remains evaluator-side.

## Buyer use cases

- compare candidate models or agent harnesses;
- pre/post-training regression evaluation;
- assess structured-output reliability and incident-cause classification;
- identify failure modes before production deployment;
- establish a repeatable private holdout for an internal model-development cycle.

## Evidence / quality notes

- 87 frozen SRE v4 scenarios;
- exactly 30 private evaluation cases;
- four causal classes with material private support;
- 18/18 scientific qualification gates passed;
- exact candidate/evidence/report/panel/private-release identities pinned;
- two real model families executed on the exact sealed panel;
- authenticated OpenAI-compatible endpoint dress rehearsal completed 30/30 cases with zero retries and zero operator interventions;
- HUD adapter clean-install, Docker build, task-start/task-grade, deterministic reset and reward-parity validation completed in Veritas portability CI;
- private task rows and hidden causal labels are excluded from buyer-safe manifests and public artifacts.

## Limitations / claim boundary

- SRE v4 is scientifically qualified; it is **not yet claimed as Frontier Qualified**.
- Current commercial evidence proves executable private evaluation and model differentiation, not correlation with every real-world SRE workflow.
- The fixed private panel should not be published or repeatedly exposed as public training data.
- Customer-specific production-readiness claims require customer-specific deployment evidence.

## Rights / provenance

Public project-authored Veritas code is Apache-2.0. The frozen private benchmark, evaluator oracles and other restricted commercial assets remain governed by `LICENSING.md` and transaction-specific terms. Third-party materials are not relicensed by Veritas merely because Veritas can reference or transform them. Delivery of the commercial environment must preserve the evaluator-side private boundary.

## Pricing

### Initial listing anchor

**$10,000 per environment**

Treat this as an initial commercial anchor, not market evidence. Before submitting the final price, run DataVendor's asset estimator and inspect any platform-provided price guidance. Adjust if the platform produces a credible demand/price signal.

Do not lower the price merely to make the first catalog entry look inexpensive: the listing represents a qualified private evaluation asset, not 30 commodity prompts. If a buyer needs a lower-friction trial, scope a limited paid evaluation or buyer-safe public/synthetic demo rather than exposing part of the frozen private panel.

## Delivery/setup instructions

1. Buyer/environment execution remains on managed HUD infrastructure or an agreed customer-controlled evaluation boundary.
2. Buyer supplies the model endpoint/harness/checkpoint through the agreed private integration channel.
3. Veritas runs the fixed qualified evaluator and returns buyer-safe aggregate metrics and failure analysis.
4. Credentials, raw private task rows, hidden labels and evaluator secrets are never placed in public marketplace metadata.
5. Re-evaluations must record the exact Veritas/SRE release identity so historical scores remain comparable.

## Public preview material

Safe to show in the listing:

- Veritas `v0.11.0` release link;
- `docs/commercial/sre-evaluation-pack-v1.md`;
- `docs/commercial/marketplace-release.md`;
- `docs/portability/README.md`;
- buyer-safe qualification summary / aggregate evidence;
- public synthetic `veritas-sre-open` material once merged.

Do not preview:

- `private_tasks.json` or equivalent private rows;
- expected labels for the frozen panel;
- private snapshots/later-evidence fields;
- private release ciphertext/decryption material;
- customer traces or credentials.

## Vendor-access sequence

1. Create the vendor organization and complete organization setup.
2. Complete HUD review and sign the HUD vendor NDA to obtain Tier 1 listing capability.
3. Choose **Publish a listing** in Add supply.
4. Select domain tags.
5. Attach the managed HUD environment asset and set the per-environment price.
6. Paste the title and executive summary above.
7. Review delivery/private-data details and submit for marketplace review.
8. After the listing is live, request Tier 2+ if you also want access to buyer Project briefs.
9. For briefs, submit a priced offer only when the requested capability genuinely matches Veritas or a custom environment you can build.

## Definition of done

DataVendor commercial submission is complete only when the seller account shows one of the following external states:

- listing submitted for review;
- listing approved/live; or
- platform-requested remediation with a concrete review record.

A sent email or a repository-compatible HUD package alone does not count as marketplace submission.
