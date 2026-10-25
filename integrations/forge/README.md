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
{"episode_id":"job-1","subject_id":"machine-1","record_id":"record-1","observed_at":"2026-01-01T12:00:00Z","available_at":"2026-01-01T12:00:02Z","observation":{"temperature_c":50.2},"action":{"performed_at":"2026-01-01T12:01:00Z","payload":{"type":"inspect"}},"outcome":{"status":"unknown","verified":false}}
```

Example `robot-jsonl` input (illustrative non-source test fixture):

```json
{"episode_id":"ep-001","subject_id":"robot-01","record_id":"ep-001/0","frame_index":0,"time_seconds":0.0,"available_seconds":0.0,"observation":{"state":[0.1,0.2]},"action":{"time_seconds":0.0,"payload":{"joint_velocity":[0.1,-0.1]}},"outcome":null}
```

Without a real persistent robot/entity ID, subject-level holdout is unavailable until the adapter supplies defensible mappings. The robot converter explicitly requires availability time; it will not assume every sensor frame was immediately available. v0.1 does not directly parse LeRobot v3 Parquet/videos, DROID native files, ALOHA HDF5, arbitrary Woyengi envelopes or industrial CSV. Source-specific importers require separately reviewed timestamp and authority semantics.

## Scientific boundaries

The declared `privacy_reviewed` and rights fields are **not independently verified**. This MVP lacks automatic PII scans, rights adjudication, label verification, cross-source identity resolution, robust site/scene leakage grouping, large-data streaming, full model-safe loaders or curation efficacy results. A valid SHA-256 proves byte identity, not source authenticity. The reproducible unit fixtures are synthetic diagnostics: **zero real-world capability evidence**.

**Next gate:** ingest a pinned source-authorized authentic dataset; independently verify source timestamp/identity alignment and rights; hold out unseen subjects/sites/scenes; reproduce original releases; then run TAC versus properly matched GRU/Transformer baselines under equal data/parameter/training-compute budgets. Do not promote DEV outcomes into untouched TEST evidence. No trained model or commercial deployment is claimed.

Forge's `manifest.json` is a dataset release receipt, **not** a Veritas verifier oracle or Woyengi authorization receipt. Downstream evaluation and governed action retain independent authority boundaries. This package never writes to either system.
