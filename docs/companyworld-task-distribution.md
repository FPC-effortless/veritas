# CompanyWorld expanded task distribution

CompanyWorld v2 expands Veritas from 320 injected-anomaly investigations into a broader operational capability environment. The original anomaly tasks remain intact; the expanded compiler adds deterministic tasks derived from the linked enterprise state without exposing evaluator-only answers.

## Default distribution

`iworld compile-companyworld-distribution DATASET` keeps the 320 legacy anomaly episodes and adds up to 200 episodes from each expanded family. On CompanyWorld v0.1 this produces 1,920 episodes across 11 task families.

| Family | Operational capability | Systems | Default v0.1 count |
| --- | --- | --- | ---: |
| `O2C_FULFILLMENT_TIMING` | Reconcile requested vs actual fulfillment timing | ERP, WMS | 200 |
| `P2P_RECONCILIATION` | Apply three-way match policy across PO, receipt and invoice | ERP, WMS, AP workflow | 200 |
| `CUSTOMER_SETTLEMENT_RECONSTRUCTION` | Reconstruct invoice settlement from receivables and cash application | AR workflow, Treasury | 200 |
| `PAYMENT_BLOCK_RECOVERY` | Recover a blocked P2P process and calculate time-to-unblock | Process | 200 |
| `INCIDENT_SLA_INVESTIGATION` | Reconstruct incident resolution and apply severity-specific SLA | ITSM, Process | 200 |
| `SAFETY_CORRECTIVE_FOLLOWUP` | Combine incident severity, corrective-action state and escalation policy | Safety, Compliance | 200 |
| `CROSS_SYSTEM_CASH_CYCLE` | Reconstruct order → shipment → invoice → settlement timeline | ERP, WMS, AR, Treasury | 200 |
| `LEDGER_POSTING_RECONSTRUCTION` | Reconcile source invoice to AR debit and revenue credit | AR workflow, Ledger | 200 |

The legacy families remain:

- `INVESTIGATE_MISSING_SHIPMENT` — 200
- `INVESTIGATE_DUPLICATE_INVOICE` — 80
- `INVESTIGATE_AUTHORITY_BREACH` — 40

## Deterministic stratified sampling

Expanded task candidates are ranked with a stable hash of `world_id`, task family and object ID. Sampling is round-robin across outcome strata so common classes cannot dominate merely because they are more frequent in the source company.

Examples:

- O2C: late vs on-time ship commitment.
- P2P: automatic match vs review under the published tolerance.
- Settlement: paid vs partial vs open.
- Incident: SLA met vs breach.
- Safety: escalation vs no escalation.

No stratum label is written to the public episode.

## Multi-record evidence contracts

Some operational conclusions cannot be verified from one record. `OperationalFactTarget` therefore supports two evidence modes:

- `semantic_any`: the original mode; one semantically entailing record is sufficient.
- `listed_count`: derived facts require a minimum number of oracle-listed public records.

For example, an O2C fulfillment-delay conclusion requires both the ERP ship commitment and the WMS shipment timeline. Citing only one source can receive fact credit but only partial evidence credit.

The evidence requirement itself is evaluator-only and never appears in `episode.public_payload()`.

## Compile

```bash
iworld compile-companyworld-distribution /path/to/companyworld_v0_1 \
  --output companyworld_distribution.json \
  --oracle-output companyworld_distribution_oracles.json \
  --per-family 200
```

The public bundle uses format `veritas-companyworld-distribution-v2` and receives family-stratified 60/20/20 train/public-eval/private-eval splits.

To omit the original 320 anomaly tasks:

```bash
iworld compile-companyworld-distribution /path/to/companyworld_v0_1 \
  --no-include-legacy
```

## Validate

```bash
iworld benchmark-companyworld-distribution /path/to/companyworld_v0_1 \
  --output companyworld_distribution_benchmark.json \
  --per-family 200
```

The expanded benchmark runs the same anti-gaming policy suite as the original CompanyWorld benchmark. The public reference policy contains deterministic solvers for every expanded family and receives only public episode payloads.

The distribution is considered valid only when:

- source integrity passes;
- no private oracle fields leak;
- every fact has enough direct evidence for its declared evidence contract;
- empty, conclusion-only, abstention-only and citation-only policies score zero;
- blind divergent-projection trust scores zero;
- field stuffing remains bounded;
- the public evidence solver reaches full reward on every task;
- the privileged oracle reaches full reward;
- correct answers without evidence score below evidence-backed answers;
- repeated compilation is byte-stable at the public-payload level.

## Operational policy encoded by v2

The first expanded distribution includes explicit derived policy records so policy-dependent decisions remain publicly solvable rather than hidden in evaluator code:

- P2P three-way match: amount tolerance = 0.2% of PO value with a $10 minimum, quantity tolerance = 0 units.
- Incident SLA: P1 = 4h, P2 = 12h, P3 = 72h, P4 = 168h.
- Safety escalation: overdue corrective actions escalate; open corrective actions on `SERIOUS` or `DAYS_AWAY` incidents escalate.

These policy records are synthetic CompanyWorld operational configuration, not claims about any real company's policy.
