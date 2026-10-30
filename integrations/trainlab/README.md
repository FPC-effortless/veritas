# TrainLab local workbench

Run declared experiments, keep a reproducible record, and compare saved results in a web dashboard. The Python 3.11+ local runner has no runtime dependencies or telemetry. Optional authenticated production hosting adds Waitress. The package is incubated beside Forge in Veritas; it is not a new Veritas release or a scientific qualification service.

## Production deployment

See [PRODUCTION.md](PRODUCTION.md) for the exact support contract, authenticated
server, portable container/Compose deployment, TLS setup, bounded execution,
health monitoring, crash recovery, backup/restore and deployment acceptance.
Production hosting serves one shared workspace for trusted operators and approved
recipes; it does not provide untrusted-job or tenant isolation. Public access
requires HTTPS, operator authentication and a configured origin. A merge or a
constructed demo alone does not qualify an installed production deployment.

## Start in under ten minutes

From `integrations/trainlab`:

```bash
python -m pip install -e .
trainlab run examples/linear.json
trainlab run examples/mean.json
trainlab serve --experiments examples
```

Open the printed **http://127.0.0.1:8765** URL in a browser on the **same machine**. The dashboard shows persistent runs, metrics, status, elapsed time, source identities, artifacts, and logs. Search/filter/sort the run list, select runs to compare, export comparison CSV or individual JSON records, and verify stored file hashes. The Experiments view can launch the trusted recipes registered with `--experiments`; only one dashboard job executes at a time. Without that flag the dashboard is read-only. Existing records survive restarts; keep `.trainlab/runs` to retain them.

Without installing anything, prepend `PYTHONPATH=src` to `python -m trainlab` instead:

```bash
PYTHONPATH=src python -m trainlab run examples/linear.json
PYTHONPATH=src python -m trainlab run examples/mean.json
PYTHONPATH=src python -m trainlab serve --experiments examples
PYTHONPATH=src python -m unittest discover -s tests -v
```

PowerShell: set `$env:PYTHONPATH = 'src'` once, then use `python -m trainlab`.

**The two examples use a tiny constructed regression fixture.** They exercise actual local training, fixed train/validation partitions, checkpoints, predictions, metrics, replay, failure handling, and reporting. Their parameter counts differ (two learned parameters versus one), so they are not a matched scientific model comparison. Neither example accesses protected TEST or establishes authentic-data capability, source rights, device performance, or independent Veritas qualification.

## Your first real experiment

Copy an example JSON recipe next to your code and input files. Its schema is `trainlab.experiment.v1`:

- `name`, `description`: bounded human-readable labels;
- `command`: an argv array, executed **without a shell**, with the recipe directory as working directory;
- `seed`: unsigned 32-bit seed; `timeout_seconds`: positive timeout, up to one day;
- `source_kind`: `CONSTRUCTED` or `AUTHENTIC_CANDIDATE` (never an authenticity attestation);
- `split_identity`: your frozen train/validation split identity;
- `inputs`: every code/data file required for the run, relative to the recipe directory;
- `artifacts`: required output files, relative to the per-run output directory;
- `metrics`: exact output metric names mapped to `min` or `max`;
- `budget`: one or more declared integer counters such as updates, exposures, parameters, or tuning trials.

TrainLab supplies `TRAINLAB_OUTPUT_DIR`, `TRAINLAB_SEED`, and `PYTHONHASHSEED`. Your command **must** use the seed to initialize its framework, then write a finite numeric `metrics.json` and every declared artifact into that output directory. It must wait for its workers and exit. Declare checkpoints, optimizer/RNG state, and evaluation outputs as artifacts when they are needed for actual replay. Framework determinism and equivalent kernels are the experiment author's responsibility.

```python
import json, os, random
from pathlib import Path

random.seed(int(os.environ["TRAINLAB_SEED"]))
output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
# Train and evaluate your model here.
(output / "metrics.json").write_text(json.dumps({"validation_loss": 0.25}))
(output / "checkpoint.json").write_text(json.dumps({"weights": [0.1, 0.2]}))
```

Run IDs are unique; runs never overwrite each other. `run.json` captures the config, command, seed, input SHA-256s, Git commit and dirty state, host runtime, declared budget, UTC start/end, elapsed time, status, exit code, metrics, and artifact hashes. Config snapshots and logs stay beside the outputs. Inputs changed during execution invalidate success. Missing/invalid metrics or artifacts fail the run, and timeouts retain an explicit `timed_out` record. CLI non-success returns a nonzero exit code. A host crash can leave a `running` record; it is not proof that a job is still alive, and verification rejects unfinished records.

```bash
trainlab list
trainlab compare <run-id-1> <run-id-2>
trainlab verify .trainlab/runs/<run-id>
trainlab run examples/linear.json --runs /private/local/run-store
trainlab serve --runs /private/local/run-store --experiments examples --port 8765
```

To replay, use a clean checkout of the recorded commit, restore the exact declared input bytes and runtime, and rerun the saved `experiment.json` **from the original recipe directory**. The snapshot does not copy source data or recreate your environment. Compare metric/artifact hashes explicitly; a matching seed alone does not guarantee reproducibility.

## Evidence and comparison boundaries

TrainLab reports observed process execution and **self-reported** metrics. Comparisons show all values without declaring a winner. Differences in source/input hashes, split identity, metric directions, seed, declared budgets, or successful completion are flagged. Matching declarations do not independently measure or equalize actual compute, number of learned parameters, labels, or tuning exposure. Include those counters in the budget when relevant. Failed/incomplete runs are retained, never silently treated as successful measurements.

The existing [Forge TrainLab evidence validator](../forge/README.md#trainlab-developer-evidence-receipt-v01--validation-only) remains the separate claim-checking boundary for authentic-source training/device receipts. This workbench's execution record does not replace that receipt or independent Veritas review. All runs and comparisons retain `qualification: NOT_QUALIFIED`. Authentic source permissions and untouched TEST access must be established independently before using real records. Physical-device qualification requires measurements on the named device; host wall time is not model latency or a phone benchmark.

## Browser acceptance checks

The Python suite exercises execution, timeout/failure, replay, changed inputs, output tampering, path boundaries, registered launch, same-origin controls, and malformed records. The optional browser check exercises the actual CLI-to-dashboard flow, run launch, filters, comparison, CSV/JSON downloads, logs, artifact verification, keyboard dialog dismissal, and mobile layout:

```bash
python -m pip install playwright
python -m playwright install chromium
PYTHONPATH=src python tests/browser_smoke.py
```

Browser tooling is a development-only dependency. Neither install nor browser access is needed by the runner. Automated screenshots are written to `/tmp/trainlab-browser-qa` on Linux. The targeted `TrainLab local workbench` GitHub workflow checks Python 3.11 and 3.13, package installation, examples, and browser acceptance on constructed fixtures.

## Local execution and privacy

Run recipes only if you trust their code. The runner is **not a sandbox**: a recipe can access the local account's files, environment, and network. This tool adds no training service, network access, or credentials. Do not put tokens or secrets in command arguments, recipe files, output artifacts, or logs. These are deliberately retained locally. The dashboard does not scan the filesystem: it reads the specified run store and explicitly registered config directory. It binds only to `127.0.0.1`, rejects unexpected Host/Origin values, requires a per-session same-origin token for launching recipes, and accepts no browser-supplied commands or file paths. Do not expose it through public forwarding.

POSIX timeouts terminate the process group; on Windows only the immediate process can be terminated with the standard library. Experiments must not detach workers. Each stdout/stderr stream is capped at 16 MiB; exceeding it fails the run. Artifact/dataset space still requires a host filesystem quota. Active stores support 1,000 runs and 8 MiB of aggregate metadata; archive/rotate stores before that limit. Input/record files have bounded JSON sizes. Artifact checksums prove byte identity against the saved record, not signed authenticity; editing both a file and its local record is outside this integrity check.

The initial commercial hypothesis remains open models/local SDKs with paid integration, optimization, evidence tooling, and support. No customer adoption, revenue, hardware qualification, or commercial release is claimed.
