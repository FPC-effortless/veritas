# Forge temporal data MVP (standalone incubation)

**Scope:** fail-closed, reproducible releases of user-supplied real operational events or decoded robot frame JSONL. This is a separate, installable package: no imports from Veritas, Woyengi, PNDS or TAC-OSM; no new authority granted to any model or agent.

Veritas already has rights-controlled acquisition, secure archive preparation, synthetic-world calibration and verified training-bundle infrastructure. Forge **does not replace** those functions. Woyengi already has authenticated ingestion, provenance, bitemporal reconstruction and authority. Forge must not treat arbitrary JSONL as Woyengi-authorized truth. TAC-OSM consumes prepared real events only after source and split contracts are approved.

## Features in v0.1

- Local-only JSONL release for `operations-jsonl` (offset-aware absolute timestamps) and `robot-jsonl` (explicit episode-relative seconds + frame index; decoded/exported from the source format).
- Strict input schema; explicit source, version, licensing, AI-use, redistribution and privacy-review declarations; no remote acquisition or guessed consent.
- Observed and available times remain distinct. Unknown outcomes stay unknown, unverified and without fabricated values. Action and outcome availability are separately represented.
- Deterministic subject-group-disjoint train/validation/test splits, stable salt, source/spec SHA-256 receipts and split-file checksums.
- Atomic all-or-nothing release; refuse malformed rows, duplicate source-record IDs, ambiguous identities, bad timestamps, NaN/Infinity, unauthorized rights or existing output. No dropped rows, silent repairs or retroactive split tuning.
- `point_in_time(record, cutoff)` removes unavailable future information. Downstream predictive model loaders **must call it** at each cutoff; stored full rows intentionally retain outcomes for supervised training.

## Install and run

```bash
cd integrations/forge
python -m pip install -e .
python -m unittest discover -s tests -v
forge-temporal release --input /local/path/events.jsonl --spec source.json --output /local/releases/v1
forge-temporal verify --release /local/releases/v1
```

Illustrative `source.json` (a claim from an operator, **not independent permission evidence**):

```json
{
  "dataset_id": "publisher-source-version",
  "source_id": "publisher/source",
  "source_version": "v1",
  "adapter": "robot-jsonl",
  "license_id": "source-specific-permission-id",
  "provenance_uri": "https://publisher.example/source",
  "ai_use_allowed": true,
  "redistribution_allowed": true,
  "privacy_reviewed": true,
  "split_salt": "frozen-public-research-protocol-v1"
}
```

Example `operations-jsonl` input (illustrative non-source test fixture):

```json
{"episode_id":"job-1","subject_id":"machine-1","record_id":"record-1","observed_at":"2026-01-01T12:00:00Z","available_at":"2026-01-01T12:00:02Z","observation":{"temperature_c":50.2},"action":{"performed_at":"2026-01-01T12:01:00Z","available_at":"2026-01-01T12:01:02Z","payload":{"type":"inspect"}},"outcome":{"status":"unknown","verified":false}}
```

Example `robot-jsonl` input (illustrative non-source test fixture):

```json
{"episode_id":"ep-001","subject_id":"robot-01","record_id":"ep-001/0","frame_index":0,"time_seconds":0.0,"available_seconds":0.0,"observation":{"state":[0.1,0.2]},"action":{"time_seconds":0.0,"available_seconds":0.0,"payload":{"joint_velocity":[0.1,-0.1]}},"outcome":null}
```

Without a real persistent robot/entity ID, subject-level holdout is unavailable until the adapter supplies defensible mappings. The robot converter explicitly requires availability time; it will not assume every sensor frame was immediately available. v0.1 does not directly parse LeRobot v3 Parquet/videos, DROID native files, ALOHA HDF5, arbitrary Woyengi envelopes or industrial CSV. Source-specific importers require separately reviewed timestamp and authority semantics.

## Ten-minute offline developer smoke demo (constructed data only)

From a fresh checkout of this branch, with Python 3.11+ and **no network or package installation required**:

```bash
cd integrations/forge
PYTHONPATH=src python examples/offline_quickstart.py
PYTHONPATH=src python -m unittest discover -s tests -v
```

The demo uses twelve **constructed** independent machine subjects, writes an ephemeral release, verifies its manifest and disjoint subject splits, and checks that point-in-time reads hide unavailable observations, actions and outcomes. Its JSON result explicitly reports `CONSTRUCTED_ONLY`, `NOT_PERFORMED` scientific qualification, and `NOT_RUN` physical inference. No remote acquisition, training, Woyengi authentication, model export or Veritas certification occurs. A successful demo is **developer contract evidence**, never a real-world capability result or independently verified source-rights claim.

The end-to-end product path remains: authorized real source → Woyengi permission-checked as-of export (where applicable) → independently qualified Forge release → TrainLab source/split/compute receipts → independently verified predictive capability → **fully local** user-device model SDK. The Woyengi candidate export currently needs its offline-only hardening in [draft PR #57](https://github.com/FPC-effortless/Woyengi/pull/57); this demo deliberately does not treat that draft or any operator-declared source rights as a qualified dataset. Customer preprocessing, embeddings, inference, state updates and optional speech must never depend on hosted inference or hidden cloud fallback.

## Scientific boundaries

The declared `privacy_reviewed` and rights fields are **not independently verified**. This MVP lacks automatic PII scans, rights adjudication, label verification, cross-source identity resolution, robust site/scene leakage grouping, large-data streaming, full model-safe loaders or curation efficacy results. A valid SHA-256 proves byte identity, not source authenticity. The reproducible unit fixtures are synthetic diagnostics: **zero real-world capability evidence**.

**Next gate:** ingest a pinned source-authorized authentic dataset; independently verify source timestamp/identity alignment and rights; hold out unseen subjects/sites/scenes; reproduce original releases; then run TAC versus properly matched GRU/Transformer baselines under equal data/parameter/training-compute budgets. Do not promote DEV outcomes into untouched TEST evidence. No trained model or commercial deployment is claimed.

Forge's `manifest.json` is a dataset release receipt, **not** a Veritas verifier oracle or Woyengi authorization receipt. Downstream evaluation and governed action retain independent authority boundaries. This package never writes to either system.

## Woyengi predictive-state export handoff (stacked integration candidate)

A separate, versioned Woyengi read-only export converter is implemented in `forge_data.woyengi.convert_export_candidate` in [draft PR #422](https://github.com/FPC-effortless/veritas/pull/422). This is a **constructed-data interop and point-in-time compatibility gate**, not a legal or operational dataset release and not independently authenticated source permission.

The only accepted input is Woyengi's `PREDICTIVE_READ_EXPORT` v1 contract produced by its [draft PR #56](https://github.com/FPC-effortless/Woyengi/pull/56) source-side module. A trusted, externally reviewed Woyengi host must establish real authorization, current-time access, source-specific AI-use rights and privacy/locality policy before real records reach Forge. JSON or SHA256 values alone cannot prove these properties.

**Release hard stop:** Forge `release` now rejects rows carrying `observation.kind=woyengi_bitemporal_claim_projection`, even if an operator declares all rights booleans `true`. The exporter and candidate converter cannot attest the legal original publisher, host permissions or source rights; a separately designed, independently authorized source adapter must qualify that before any dataset release. This avoids laundering constructed interoperability fixtures into a misleading training artifact.

The converter keeps `claim.validFrom` as **fact-validity time**, NOT an observed sensor event; it makes each derived projection record available to Forge **only at the complete snapshot prediction cutoff**, preventing historical `selected`/`conflicted` labels from being visible before they became known. No actions, outcomes, rewards or future truth are fabricated; each row explicitly carries unknown/unverified outcome semantics. `point_in_time` therefore returns `None` before the snapshot cutoff. Independently verify rights and fit/validation/test subject groups before any real `forge-temporal release` is authorized.

A real-code interop CI workflow, `.github/workflows/forge-woyengi-source-gate.yml`, executes Woyengi's pinned source exporter against constructed ClaimLedger + CapabilityEngine records, then executes the standalone Forge conversion, normalizer, and point-in-time checks. The workflow produces *software contract* evidence only, not a licensed dataset, scientific experiment, Veritas independent scorer or deployed product. One fixture subject is insufficient for a meaningful independent subject-held-out scientific comparison.

**Next gates:** external source consent/license audit, authenticated Woyengi host receipt, original publisher source and outcome evidence, multiple independent subjects and a frozen temporal split, a protected reference training runner, and an independent Veritas evaluation. The Forge security and reviewer prerequisites of PR #420 remain binding.

## TrainLab developer evidence receipt v0.1 — validation only

The local `validate-evidence` command checks an **untrusted** versioned receipt.
It is an engineering *claim checker*, not a Veritas attestor, original-data verifier,
qualified scientific scoring service, device benchmark or release authority.
The validator never produces `INDEPENDENTLY_QUALIFIED` or `DEVICE_READY`.

```bash
cd integrations/forge
PYTHONPATH=src python -m forge_data validate-evidence \
  --input examples/CONSTRUCTED_trainlab_evidence.json
PYTHONPATH=src python -m unittest discover -s tests -p 'test_evidence_receipt.py' -v
```

The example is **CONSTRUCTED**, has **NO TRAINING**, **NO DEVICE MEASUREMENT**,
and **NO VERITAS REVIEW**. It produces a redacted structural PASS while
retaining `scientific_qualification: NOT_QUALIFIED`,
`hardware_qualification: NOT_QUALIFIED` and `commercial_release: NOT_AUTHORIZED`.
A clean JSON structure or SHA never constitutes source authenticity or fitness.

Fields are version-locked and checked fail-closed:

- Source identity, publisher/original bytes (or explicit constructed fixture),
  point-in-time and split-check levels, and unverified rights status.
- Research track, original checkpoint and optimizer/RNG replay references,
  train tokens/updates and tuning budget, learned parameters, and matched
  baselines. For `TAC_100K`, the 95,000–105,000 rule applies, baseline
  parameter differences may not exceed 1% of TAC, and each baseline must
  have exactly the same data split, train tokens/updates and tuning budget.
  Historical `EXPLORATORY_500K` is separate and never promoted to 100K evidence.
- Named physical device + OS, ONNX/export operator report, numerical error,
  p50/p95, RAM, energy, artifact and network-trace hashes, airplane-mode and
  state replay, and local input/preprocessing/embeddings/inference/state/
  output/speech boundaries with `remote_fallback: false`.
- Independent review and protected TEST are **never** inferred from JSON fields.
  Separate Veritas permissions and external evidence remain mandatory.

`INTERNAL_MEASURED` training or `INTERNAL_PHYSICAL_MEASURED` device values are
accepted only as *self-reported candidates* with required fields; even those
remain explicitly **NOT QUALIFIED** by this tool. No actual 100K training,
physical Android test, valid original publisher permission, protected TEST
or independent Veritas qualification was run by this change.

This incubated module does not claim a separate TrainLab repository, a
shipping SDK, or commercial adoption. Business model: open models, fully
offline local SDKs and paid integration, optimization, verification tools and
support; never hosted per-inference customer model services.
