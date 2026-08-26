# Veritas Commercial Evaluation Package

This directory contains the buyer-facing material for turning Veritas from a research benchmark into a repeatable enterprise-agent evaluation product.

- [Benchmark card](benchmark-card.md) — what is measured, validation boundaries and caveats.
- [Paid design-partner pilot](pilot.md) — standard pilot scope, deliverables and success criteria.
- [Security and delivery](security-and-delivery.md) — deployment modes, data boundaries and procurement evidence.
- [Procurement readiness](procurement-readiness.md) — checklist for repeatable enterprise delivery.

Supporting tools:

```bash
# Evaluate an OpenAI-compatible endpoint.
python tools/run_endpoint_calibration.py \
  --endpoint https://example.internal/v1/chat/completions \
  --model customer-agent \
  --output run.json

# Create a versioned run manifest.
python tools/create_evaluation_manifest.py \
  --benchmark-version companyworld-v1 \
  --benchmark-hash <hash> \
  --model customer-agent \
  --harness customer-harness-v2 \
  --attempts-per-task 3 \
  --output manifest.json

# Render calibration JSON into a buyer-facing report.
python tools/build_customer_evaluation_report.py \
  run.json \
  --customer-name "Example Co" \
  --benchmark-version companyworld-v1 \
  --output evaluation-report.md
```

The commercial package intentionally does not publish private benchmark seeds, evaluator oracles, customer-specific sales strategy, customer secrets or design-partner pricing.
