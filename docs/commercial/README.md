# Veritas Commercial Evaluation Package

This directory is the customer-, marketplace-, and procurement-facing operating package for Veritas evaluations.

## Current commercial release

The canonical software release is **Veritas 0.11.0** / tag **`v0.11.0`**. It contains the 0.10 benchmark-qualification substrate plus the 0.11 vendor-neutral portability contract and standalone HUD/Prime packaging. The immutable GitHub release includes Python distributions, checksums, SBOM, provenance, portability identities, the root license and the commercial licensing policy.

## Primary commercial SKU

The first buyer-facing benchmark SKU is **[Veritas SRE Evaluation Pack v1](sre-evaluation-pack-v1.md)**.

SRE v3 is retired from private commercial scoring: the stronger current stratum-coverage gate rejects its majority-transient private set, and historical Actions artifacts exposed raw v3 qualification material.

SRE v4 is the qualified frozen commercial benchmark. Its sealed release contains 87 scenarios and a 30-case private panel across 16 fresh Statuspage providers. All 18 scientific qualification gates pass; exact release identities are pinned and every commercial evaluator consumes the sealed `qualification.json` rather than rebuilding the candidate from provider feeds.

The exact sealed panel has passed real-model execution on two model families and a customer-equivalent authenticated OpenAI-compatible endpoint dress rehearsal. Veritas 0.11 also exports the SKU through validated HUD v6 and Prime Verifiers v1 adapters without putting the private evaluator truth into buyer-safe manifests.

ProjectWorld v2 remains a qualified second environment family and is the next candidate for a separate commercial pack. CompanyWorld remains useful for enterprise-workflow evaluation and training experiments but is not presented as the primary generic-qualification SKU.

## Buyer-facing material

- [Marketplace release packet](marketplace-release.md) — canonical 0.11 release, public/private boundary, offer structure, and external-distribution status.
- [HUD / DataVendor submission](hud-submission.md) — HUD-safe asset description, current Tier 1 listing/Tier 2 briefs path, and seller-account acceptance run.
- [Copy-ready DataVendor listing](datavendor-listing.md) — title, executive summary, managed-environment asset choice, initial pricing anchor, evidence, rights and preview/private boundaries.
- [Prime Intellect submission](prime-submission.md) — private proof, sanitized Hub publication strategy and Hosted Evaluation acceptance criteria.
- [SRE Evaluation Pack v1](sre-evaluation-pack-v1.md) — primary SKU and execution contract.
- [Benchmark card](benchmark-card.md) — broader Veritas measurement substrate, validity boundaries, and caveats.
- [Paid design-partner pilot](pilot.md) — standard pilot scope, deliverables, and success criteria.
- [Security and delivery](security-and-delivery.md) — deployment modes, data boundaries, and current security posture.
- [Private benchmark handling](private-benchmark-handling.md) — oracle, snapshot, disclosure and retirement rules.
- [Evaluation acceptance criteria](evaluation-acceptance.md) — when a pilot run is considered valid and complete.
- [Customer onboarding](onboarding.md) — information needed to connect and run a pilot.
- [Statement of Work template](sow-template.md) — editable pilot scope for contracting.
- [Invoice template](invoice-template.md) — neutral invoice structure; legal entity/payment fields must be completed by the seller.
- [Release and score-compatibility policy](release-policy.md) — how benchmark versions and historical scores are governed.

## Operator material

- [Pilot dress rehearsal](pilot-dress-rehearsal.md) — end-to-end pre-sale execution gate.
- [Launch checklist](launch-checklist.md) — minimum conditions before accepting payment and current HUD/Prime external-distribution gates.
- [Procurement readiness](procurement-readiness.md) — current and deferred enterprise-readiness items.

Customer-specific pricing, private benchmark seeds, raw frozen private suites, evaluator oracles, internal sales strategy, customer secrets, and private adversarial suites must **not** be committed to this public repository or uploaded raw to public-repository Actions artifacts at any retention period.

## Public commercial inquiry route

Use the repository's **Commercial evaluation inquiry** issue template for buyer-safe first contact. Do not place credentials, private benchmark content, customer-confidential data or private endpoint details in a public issue; move those to an agreed private channel during onboarding.

## Standard SRE evaluation flow

```bash
# 1. Evaluate an OpenAI-compatible endpoint against the exact sealed v4 panel.
python tools/run_sre_endpoint_evaluation.py \
  --qualification <private-v4-bundle>/results/sre-v4/qualification.json \
  --endpoint https://example.internal/v1/chat/completions \
  --model customer-agent \
  --expected-candidate-id SRE-CAND-92A84929AD1E82E24357 \
  --expected-evidence-manifest-id EVID-2C69B48DCDD5F2232EABDC9B \
  --expected-report-id QREPORT-C585121E94D91766BB6664E3 \
  --expected-panel-id QPANEL-AFF065BA4C2FD75BE9BB3EBE \
  --expected-private-release-manifest-id PRIVREL-036192DA63716D331C929C0C \
  --output <private-operator-report.json> \
  --public-output run.json

# 2. Render the buyer-facing report from the sanitized aggregate report.
python tools/build_sre_customer_evaluation_report.py \
  run.json \
  --customer-name "Example Co" \
  --qualification public-qualification-summary.json \
  --output evaluation-report.md
```

Balanced accuracy and macro F1 are primary SRE metrics. Raw accuracy is always reported beside the majority-class baseline.

Customer-controlled inference is preferred where the buyer cannot send model inputs or outputs to a third-party hosted service.
