# Veritas Commercial Evaluation Package

This directory is the customer- and procurement-facing operating package for **Veritas CompanyWorld Pilot v1**.

## Buyer-facing material

- [Benchmark card](benchmark-card.md) — what Veritas measures, validity boundaries, and caveats.
- [Paid design-partner pilot](pilot.md) — standard pilot scope, deliverables, and success criteria.
- [Security and delivery](security-and-delivery.md) — deployment modes, data boundaries, and current security posture.
- [Evaluation acceptance criteria](evaluation-acceptance.md) — when a pilot run is considered valid and complete.
- [Customer onboarding](onboarding.md) — information needed to connect and run a pilot.
- [Statement of Work template](sow-template.md) — editable pilot scope for contracting.
- [Invoice template](invoice-template.md) — neutral invoice structure; legal entity/payment fields must be completed by the seller.
- [Release and score-compatibility policy](release-policy.md) — how benchmark versions and historical scores are governed.

## Operator material

- [Pilot dress rehearsal](pilot-dress-rehearsal.md) — end-to-end pre-sale execution gate.
- [Launch checklist](launch-checklist.md) — minimum conditions before accepting payment.
- [Procurement readiness](procurement-readiness.md) — current and deferred enterprise-readiness items.

Customer-specific pricing, private benchmark seeds, evaluator oracles, internal sales strategy, customer secrets, and private adversarial suites must **not** be committed to this public repository.

## Standard evaluation flow

```bash
# 1. Evaluate an OpenAI-compatible endpoint.
python tools/run_endpoint_calibration.py \
  --endpoint https://example.internal/v1/chat/completions \
  --model customer-agent \
  --output run.json

# 2. Create immutable run metadata.
python tools/create_evaluation_manifest.py \
  --benchmark-version companyworld-pilot-v1 \
  --benchmark-hash <private-suite-hash> \
  --model customer-agent \
  --harness customer-harness-v1 \
  --attempts-per-task 3 \
  --output manifest.json

# 3. Render a buyer-facing report.
python tools/build_customer_evaluation_report.py \
  run.json \
  --customer-name "Example Co" \
  --benchmark-version companyworld-pilot-v1 \
  --output evaluation-report.md
```

The standard initial pilot uses synthetic CompanyWorld tasks and does not require production customer data. Customer-controlled inference is preferred where the buyer cannot send model inputs or outputs to a third-party hosted service.
