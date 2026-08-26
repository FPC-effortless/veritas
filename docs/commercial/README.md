# Veritas Commercial Evaluation Package

This directory is the customer- and procurement-facing operating package for Veritas evaluations.

## Primary commercial SKU

The first benchmark SKU with empirical Benchmark Qualification evidence is **[Veritas SRE Evaluation Pack v1](sre-evaluation-pack-v1.md)**.

Current qualified SRE evidence:

- candidate `SRE-CAND-24057DDECB32893163ED`;
- 173 empirical incident scenarios;
- 34 private-test cases;
- zero failed qualification gates;
- calibrated oracle / competent / myopic / random / exploit policy separation;
- frozen private benchmark stored outside the public repository;
- OpenAI-compatible endpoint and local-checkpoint evaluation surfaces;
- buyer-safe report generation that does not expose per-case private truth.

ProjectWorld v2 is the second qualified environment family and is the next candidate for a separate commercial pack. The older CompanyWorld pilot material remains useful for enterprise-workflow evaluation but should not be presented as the primary qualified SKU.

## Buyer-facing material

- [SRE Evaluation Pack v1](sre-evaluation-pack-v1.md) — current primary SKU and execution contract.
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
- [Launch checklist](launch-checklist.md) — minimum conditions before accepting payment.
- [Procurement readiness](procurement-readiness.md) — current and deferred enterprise-readiness items.

Customer-specific pricing, private benchmark seeds, raw frozen private suites, evaluator oracles, internal sales strategy, customer secrets, and private adversarial suites must **not** be committed to this public repository or uploaded as long-lived public-repository Actions artifacts.

## Standard SRE evaluation flow

```bash
# 1. Evaluate an OpenAI-compatible endpoint while the private panel remains evaluator-side.
python tools/run_sre_endpoint_evaluation.py \
  --snapshot-dir <private-snapshot-dir> \
  --endpoint https://example.internal/v1/chat/completions \
  --model customer-agent \
  --providers circleci discord dropbox mongodb npm \
  --version sre-v3 \
  --expected-candidate-id SRE-CAND-24057DDECB32893163ED \
  --output run.json

# 2. Render the buyer-facing report.
python tools/build_sre_customer_evaluation_report.py \
  run.json \
  --customer-name "Example Co" \
  --qualification public-qualification-summary.json \
  --output evaluation-report.md
```

Customer-controlled inference is preferred where the buyer cannot send model inputs or outputs to a third-party hosted service.
