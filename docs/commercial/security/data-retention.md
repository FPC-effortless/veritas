# Veritas Evaluation Data Retention Policy

Status: operational policy template for design-partner and pilot evaluations. Contract-specific obligations override this document.

## Data classes

1. **Benchmark private truth** — Veritas hidden world state, private seeds, oracles and verifier-only metadata.
2. **Customer configuration** — endpoint URLs, model/harness identifiers, budgets and non-secret run settings.
3. **Credentials** — API keys, access tokens and temporary customer secrets.
4. **Evaluation traces** — prompts/observations, tool calls, actions, results, state-transition metadata, costs and verifier components.
5. **Customer report artifacts** — manifests, scorecards, selected trajectories and recommendations.
6. **Operational logs** — infrastructure/security logs needed to diagnose delivery failures.

## Default retention

- Credentials: memory/environment-scoped for the active run only; do not write credentials to benchmark manifests or reports.
- Raw evaluation traces: 30 days after final pilot delivery unless the customer requests earlier deletion or a contract specifies otherwise.
- Customer reports and immutable run manifests: 90 days after final delivery for re-test/reproducibility, unless the customer requests earlier deletion.
- Operational logs: 30 days where technically configurable.
- Benchmark private truth: retained by Veritas as proprietary evaluator material; it is not customer data and is not exposed to evaluated agents.

## Minimization

Collect only data necessary to execute and verify the agreed evaluation. Do not ingest unrelated customer repositories, messages, documents, or production databases unless explicitly included in the pilot scope.

## Customer-controlled execution

Where customer data or model access cannot leave the customer boundary, prefer customer-controlled or isolated execution. Veritas may receive only the final manifest, verifier-safe result fields and agreed trace excerpts.

## Deletion

A deletion request should remove customer credentials, raw traces, customer-supplied artifacts and customer-specific reports from active storage and documented backups where technically feasible. Keep only accounting/legal records required by law and non-customer benchmark artifacts.

## Exceptions

Any longer retention, legal hold, production-data ingestion, or persistent credential storage requires an explicit written exception in the applicable SOW/DPA and a documented security review.
