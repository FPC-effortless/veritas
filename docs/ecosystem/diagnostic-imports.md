# Import existing diagnostic records

TrainLab reads pinned local JSON exports from MLflow and the PyTorch profiler.
Use the SHA256 received with the original archive or logged at export. Each
report links normalized rows back to their source indices. The importer never
opens tracker connections or executes imported content.

## MLflow metric history

Save one response from
[MLflow Get Metric History](https://mlflow.org/docs/latest/api_reference/rest-api.html#get-metric-history)
as a local JSON file. Pass the run ID and metric key used to request it.

```bash
python -m trainlab.diagnostic_imports mlflow \
  --input history.json --sha256 SHA --run-id RUN --metric-key validation_loss --initial-page
```

Metric values must be finite. Timestamps are integer milliseconds, and both
timestamps and steps accept int64 integers and decimal string encodings.
Source order and repeated steps are preserved. Dataset name, dataset digest
and logged model form separate scopes. An explicit foreign run ID or metric
key is rejected. If the response omits run IDs, association comes from the
import declaration. Declare `--initial-page` only when the request started
without a page token. Both unknown origin and later pages stay incomplete.
A continuation token also marks the result incomplete.
Token contents are omitted, and the importer does not fetch later pages.

## PyTorch Chrome trace

Save output from
[`torch.profiler.profile.export_chrome_trace`](https://docs.pytorch.org/docs/stable/profiler.html)
and pass a capture identity.

```bash
python -m trainlab.diagnostic_imports pytorch \
  --input trace.json --sha256 SHA --capture-id CPU_CAPTURE
```

Version 1 complete-event CPU operator spans are normalized with process,
thread, timestamp and duration. Chrome trace event timestamps/durations are
microseconds. The top-level display unit is a UI preference. Operator
summaries add inclusive durations. Nested and concurrent calls can overlap,
so these sums are not exclusive runtime, GPU time or end-to-end cost.
Metadata and other phases/categories are counted separately. Uncovered
event types, no usable rows, and omitted events leave the result incomplete.

Both importers validate a bounded finite JSON document, then process the first
`--max-events` rows in source order. Omitted rows and the source-byte SHA
remain explicit. Retain the original artifact beside the normalized report.
There is no global cache, provider discovery, merged cross-run metadata, or
live tracker session. The acceptance capture used an MLflow 3.5.1 local run with three logged
observations. Its metric-history response retained both observations at
step one. PyTorch 2.5.1+cpu exported a matrix multiplication trace with eight
CPU operator spans across 19 events. The import retained all eight. Its
other event types remain visible as uncovered.
