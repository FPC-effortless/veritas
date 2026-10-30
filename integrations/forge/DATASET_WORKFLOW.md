# Forge datasets, TrainLab runs, and comparison dashboard

This workflow joins the incubated Forge temporal release package to the existing
TrainLab runner and local dashboard. Both packages work without Veritas runtime
imports. Python 3.11+ is supported; the demonstration needs no network, package
installation, model download, secrets or paid compute.

From the repository root on this integration branch:

```bash
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python integrations/forge/examples/dataset_quickstart.py --output /tmp/forge-workbench --run
python -m trainlab serve --runs /tmp/forge-workbench/runs --experiments /tmp/forge-workbench
```

Open `http://127.0.0.1:8765`. The runs page shows two completed experiments.
Select both to compare their validation metrics, inspect logs, verify artifacts,
or download CSV/JSON. The Experiments page can launch either registered recipe
again. The dashboard uses the existing loopback, origin and session-token
boundaries. Keep it local; experiment commands are trusted operator code.

The example freezes 30 **constructed** subjects into 24 train, 3 validation,
and 3 local test subjects. Two tiny least-squares fits use the same declared
inputs, split identity, seed and two learned coefficients, with linear versus
squared input transforms. TEST examples are never used in fitting or metrics.
Original split bytes, including local TEST, remain in the trusted experiment
workspace and are hashed by TrainLab; this is an API guard, not process isolation
or authorization to access any protected evaluation panel. The values do not
measure real predictive skill. Source `verified: false` stays false.

The output directory persists the original JSONL/spec, immutable release,
registered recipes, run records, logs, model artifacts and `comparison.json`.
Existing output is refused. Use a new directory to regenerate the fixture.
Repeat a recipe to check replay using TrainLab's saved metrics/artifact digests.
Copied recipes require the two packages installed or absolute PYTHONPATH entries.

For installed packages:

```bash
python -m pip install ./integrations/forge ./integrations/trainlab
trainlab serve --runs /tmp/forge-workbench/runs --experiments /tmp/forge-workbench
```

## Reading an existing release

Record the manifest SHA256 in the frozen experiment protocol when releasing the
dataset. Supply that expected digest to `forge_data.dataset.Dataset`; deriving a
new pin from an untrusted or changed release defeats the identity check.

```python
from pathlib import Path
from forge_data.dataset import Dataset

dataset = Dataset(Path("release"), manifest_sha256=expected_manifest_sha256)
examples = dataset.examples(
    "train",
    cutoff="2026-01-01T10:00:01Z",
    feature_fields=["temperature"],
    target_cutoff="2026-01-02T10:00:00Z",
)
```

Only explicitly selected observation fields appear in `features`. Action payloads
are excluded. A separate `target` retains the original outcome and verification
flag only if known by `target_cutoff` (or by feature cutoff when omitted). Unknown
targets stay null. Feature availability never advances to the later label clock.
Robot releases use numeric relative-second cutoffs. TEST access requires
`allow_test=True`, an intentional local API opt-in with no external authority.

```bash
python -m forge_data.dataset inspect --release release --manifest-sha256 "$FORGE_MANIFEST_SHA256"
python -m forge_data.dataset export --release release --manifest-sha256 "$FORGE_MANIFEST_SHA256" \
  --split train --cutoff 2026-01-01T10:00:01Z --feature temperature
```

`inspect` prints aggregate counts without subject/source payloads. `export`
intentionally writes selected records to stdout; apply source privacy policy to
the destination. Inspection validates all split files before output. The reader
checks strict JSON, manifest identity, schema, source/episode/subject identity,
temporal normalization, split hashes and counts, and deterministic subject
assignment. It rejects symlink files and source candidates with unverified
Woyengi projection provenance. Each split is limited to 64 MiB, and the manifest
to 64 KiB. Reads use a verified in-memory snapshot, preventing a later file edit
from changing already-open examples. Larger sources need a streaming release
format; this reader does not claim large-data support.

An observation allowlist cannot establish semantic absence of leaked targets
inside a source feature. Source provenance, field visibility, consent/privacy,
split design, label verification and scientific qualification need independent
evidence. Hashes establish identity against the supplied pin, not authenticity.
Rights declarations and matching declared budgets are not attestation or proof
of equal actual training compute. Constructed runs remain `NOT_QUALIFIED`.

## Verification

```bash
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python -m unittest discover -s integrations/forge/tests -v
python -m unittest discover -s integrations/trainlab/tests -v
python integrations/trainlab/tests/browser_smoke.py
```

The browser check additionally requires Playwright and Chromium. Targeted CI
runs both package suites, the end-to-end demo and installed-package smoke. The
existing TrainLab browser workflow remains applicable. Missing/skipped checks
are not PASS. The package work remains stacked on unmerged Forge/TrainLab drafts;
it does not authorize their merge, scientific promotion, release or deployment.

Local implementation evidence on Python 3.12: 68 Forge checks and 18 TrainLab
checks passed without skips; the broader Veritas suite passed 1,251 tests with
2 existing skips. Chromium acceptance exercised recipe launch, replay, search,
comparison, CSV/JSON export, logs, artifact verification and mobile layout.
A separate browser check displayed the Forge-derived runs and their matched
declared-condition comparison. Both wheel/sdist builds, package metadata checks,
installed CLI smoke, new-file Ruff checks and dashboard JavaScript syntax passed.
These are local software checks; hosted exact-head CI, parent integration,
authentic-source qualification and physical-device evidence remain separate.
