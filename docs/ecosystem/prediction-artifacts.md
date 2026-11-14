# Reusing predictions and checking adapters

DIAGNOSTICS-002 (#521) adds a bounded prediction contract and deterministic adapter
probes to the [research workbench](diagnostic-workbench.md). This is implementation
verification, not scientific or frontier qualification.

## One pass, multiple consumers

`trainlab.prediction_artifacts` accepts ordinary finite JSON. `make_request` freezes:

- Exact model, dataset, code and configuration SHA256 identities.
- Task name and the supported `finite-json-v1` output contract.
- Ordered, unique row IDs and canonical input-content hashes.
- Stateless/sequential execution mode, query mutation, persistence/reset semantics
  and the SHA256 identity of the initial state (including a declared empty state).

Include seeds, precision, tokenizer, preprocessing, output interpretation, runtime
and other prediction-affecting settings in the pinned configuration. Bind actual
weights/state bytes where available; a recipe hash is a recipe declaration, not
proof of the weights actually executed. A state identity must cover the complete
relevant state, including RNG for a seeded run. The helper cannot infer omissions.

```python
from trainlab.prediction_artifacts import make_request, write_predictions, read_predictions

request = make_request(identities, input_rows, task=task, state=state)
# input_rows: [{"id": "row-1", "input": <JSON>}, ...]
# predictions: [{"id": "row-1", "output": <JSON>}, ...] in exactly the same order
pin = write_predictions(new_path, request, predictions)
# Preserve pin in an independently retained TrainLab receipt/protocol.
first_consumer = read_predictions(new_path, pin, request)
second_consumer = read_predictions(new_path, pin, request)
```

Every read requires both the external byte hash and the expected request. A file's
self-description or filename is insufficient. Recompute the expected request from
the currently intended model/data/config/state before reuse. Duplicate, missing,
extra or reordered prediction IDs, changed bindings, malformed/duplicate-key JSON,
nonfinite values and unsupported schemas are rejected. Each read parses a fresh
copy; mutations by one consumer cannot change another consumer's values.

Publication uses a flushed temporary file and an exclusive atomic hard link; an
existing destination is never replaced. The parent directory must already exist.
Unsupported filesystems fail instead of falling back to partial overwrite. A crash
before publication can leave a temporary file; a crash after publication can leave
a complete file without its external receipt. Neither is automatically reusable.

Limits: 10,000 rows, 16 MiB serialized document, 32 JSON nesting levels, local
trusted execution. These are format limits, not a hard memory quota. The reader
hashes and parses the same bounded byte buffer. No distributed caching, automatic
eviction, embeddings, pickle loading, or prediction-equivalence inference is added.
Row IDs and outputs may contain sensitive information: only use data authorized
for the chosen artifact boundary. Hashing is not anonymization or a privacy review.

## Adapter conformance

`conformance_checks(probe_rows, mode="stateless" | "sequential")` returns ordinary
Workbench diagnostics. The adapter exposes `predict_rows`, accepting/returning the
row structures above. Use 2–128 representative deterministic probe rows. The
Workbench records every prediction/reset operation and enforces its normal budget.

| Probe | Stateless | Sequential |
| --- | --- | --- |
| Fresh replay | Repeat the full input | Reset to the declared initial state before each full input |
| Batch equivalence | Full batch versus first row + remaining rows | Reset before each run; preserve state between split batches |
| Reverse order | Reverse inputs and restore output order before comparison | Not applicable; input order can change state and answers |

Sequential adapters must expose `reset` restoring the **same initial state**, which
may be empty or populated; it is not universally equivalent to clearing memory.
An absent capability reports `UNSUPPORTED`. Broken row/output structure or unequal
predictions reports `FAILED`; interrupted/budget-exhausted probes stay inconclusive
under Workbench rules. Unhandled execution errors are also inconclusive. These
probes may leave adapter state changed; restore it before subsequent research.

Comparisons are exact canonical JSON, including numeric representation. Stochastic
and tolerance-based precision equivalence require separate protocols. Runtime
exceptions expressed as `LabError` are treated as contract failures; other errors
remain inconclusive. No automatic retries or fallback to cached results occurs.

The probe rows must actually distinguish the suspected failure. Constant outputs
can pass conformance even when every answer is wrong. Correct IDs with consistently
mislabelled values can also escape these structural checks. Use a separate reference
or label oracle for answer semantics; conformance never replaces it. A finite clean
probe cannot establish that all batches, inputs, resets or hidden state are sound.

## Executed integration and falsifiers

The existing composed example now persists a bound prediction artifact and runs
reference agreement plus diversity from two independent reads of that same pass:

```bash
python integrations/trainlab/examples/diagnose_models.py \
  --root /tmp/new-diagnostic-run --backends cli store sklearn torch wrong
```

Install the four ecosystem packages as described in the workbench quickstart;
sklearn and PyTorch are optional installed backends. Forge selects public
constructed validation rows. Actual TrainLab runs retain the artifact/report, and
Research Lab links their receipts to the dataset. The reference/diversity consumers
make zero prediction calls; adapter conformance and store reset make **additional,
separately metered calls**. The example does not claim all diagnosis takes one pass.

The store's conformance reset restores its populated initial fixture; its separate
clear/repopulate probe checks absence explicitly. It is an explicit dictionary
control, not native CSM/DPSL. The deliberately wrong `y=3x` adapter can satisfy
conformance/diversity while failing the `y=2x` reference check. This separation is
intentional. No model fits or architecture cost ranking are performed.

The test suite includes stale identity/content/order, corrupted bytes, duplicate
keys, nonfinite/overflowing JSON, swapped IDs, positional output mapping, batch-size
dependence, broken reset, missing capability, publication failure and budget
exhaustion, alongside clean stateless and order-dependent sequential controls.
Native learned-state adapter acceptance remains outstanding.
