# CompanyWorld backend

CompanyWorld is Veritas's operational-enterprise backend. It converts a linked synthetic company dataset into isolated investigation episodes with separate public system observations and evaluator-only truth.

## Data boundary

The adapter expects the CompanyWorld layout:

```text
companyworld_v0_1/
├── canonical/       # operational/system records
├── ground_truth/    # evaluator-only anomalies and answers
├── metadata/        # manifests and data dictionary
└── validation/      # source integrity report
```

`ground_truth/` must never be made available to an operating agent. The adapter may use evaluator truth to render observable evidence projections, but public episode payloads do not contain `true_value`, hidden causes, answer classes, expected resolutions, or hidden-error identifiers.

## Supported anomaly families

The first adapter version compiles the three CompanyWorld v0.1 hidden-error families:

- shipment short-pick / delivery reconciliation;
- duplicate supplier-invoice investigation;
- approval-authority misconfiguration.

Each episode contains records projected into independent enterprise systems:

- `ERP`
- `WMS`
- `AP_WORKFLOW`
- `AUTH_SERVICE`
- `EMAIL`
- `LEDGER`
- `PROCESS`

A false or stale projected state remains observable but is marked only by its system provenance, not by evaluator truth metadata.

## Validate the dataset

```bash
iworld validate-companyworld /path/to/companyworld_v0_1
```

Validation requires the original CompanyWorld integrity report to pass ledger balance, tested foreign-key, and non-negative-inventory checks, and verifies that hidden anomaly objects match private task-answer objects.

## Compile episodes

```bash
iworld compile-companyworld \
  /path/to/companyworld_v0_1 \
  --output runs/companyworld/public.json \
  --oracle-output runs/companyworld/oracles.json
```

The public file contains tasks, system records, and train/public/private split manifests. The oracle file is privileged and contains the expected operational facts and evaluator annotations.

Use `--limit N` for small smoke runs.

## Agent output contract

CompanyWorld uses the existing `InvestigationResult` object. Operational conclusions are placed in `claims`:

```json
{
  "claims": [
    {
      "object_type": "SHIPMENT",
      "object_id": "SHP-00000001",
      "field_name": "delivered_quantity",
      "value": 37
    }
  ],
  "evidence": [
    {"record_id": "CWR-..."}
  ],
  "overall_confidence": 0.94
}
```

The operational verifier scores fact precision/recall/F1, evidence support, calibration, abstention, and budget efficiency. Empty or zero-correctness answers receive zero reward on answerable tasks, and false-fact stuffing reduces reward.

## In-process runtime

```python
from investigation_world.companyworld import CompanySystem, CompanyWorldAdapter, CompanyWorldRuntime

adapter = CompanyWorldAdapter("/path/to/companyworld_v0_1")
episode = adapter.compile_episodes(limit=1)[0]
runtime = CompanyWorldRuntime(episode)

records = runtime.search_system(CompanySystem.WMS, episode.task.target_object_id)
```

System lookups have distinct costs. This lets evaluation measure not only correctness but information gathering and tool-budget management.

## Next expansion

The next CompanyWorld milestone should compile additional enterprise task families directly from the existing canonical tables and process event log:

- order-to-cash root-cause analysis;
- procure-to-pay reconciliation;
- financial/ledger investigations;
- process conformance and recovery;
- incident and safety investigations;
- contract/obligation analysis;
- cross-system temporal reconstruction.

Those task families should retain the same public-projection/private-oracle boundary and receive adversarial validation before inclusion in a benchmark release.
