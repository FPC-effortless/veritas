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

## Offline candidate audit quickstart (stacked company integration draft)

The read-only `audit-candidate` command validates a **constructed** Woyengi
export, checks point-in-time visibility, and prints **only counts and nonqualification markers**.
It neither writes a Forge release nor invokes a model, Veritas verifier or remote service.

From the repository root, using Python 3.11+:

```bash
PYTHONPATH=integrations/forge/src python -m unittest discover -s integrations/forge/tests -p 'test_candidate_audit.py' -v
PYTHONPATH=integrations/forge/src python -m forge_data audit-candidate \
  --input integrations/forge/examples/CONSTRUCTED_woyengi_candidate.json \
  --as-of 2026-02-14T23:59:59Z
PYTHONPATH=integrations/forge/src python -m forge_data audit-candidate \
  --input integrations/forge/examples/CONSTRUCTED_woyengi_candidate.json \
  --as-of 2026-02-15T00:00:00Z
```

The first as-of instant must show **0 of 2** records visible; the second must show
**2 of 2**. Both outputs must remain `STRUCTURAL_ONLY`, with
`model_training_release: PROHIBITED`, `model_inference: NOT_PERFORMED`, and
`device_offline_qualification: NOT_RUN`. These are fixture expectations, not
measured model performance. Invalid/oversize JSON, duplicate keys and nonfinite
numbers are rejected. No source identities or feature values are printed.

The sample uses deliberately constructed identities and placeholder feature hashes,
not genuine publisher provenance. This audit proves no Woyengi authentication,
source licensing, independent outcome correctness, TrainLab scientific result,
Veritas qualification, customer product or deployable model.

**Required future workflow:** authorized source -> independently qualified Forge release
-> reproducible TrainLab experiment -> Veritas independent qualification -> Woyengi
local SDK. The source rights, operator approvals and model evidence gates remain separate.

**Customer inference rule:** inputs, preprocessing, embeddings, state updates, inference,
outputs and any speech processing stay entirely on the customer-controlled device,
without a cloud call or hidden fallback. Cloud training, CI and signed delivery
are permitted; hosted per-inference services are not a company offering.

**First proposed device:** Samsung Galaxy A07 (SM-A075F, Android 16).
Real ONNX operator support, numerical agreement, physical p50/p95 latency, peak RAM,
energy and airplane-mode behavior remain **NOT RUN/BLOCKED**; Python fixture
checks cannot qualify hardware. The commercial pathway is open models and local
SDKs with paid integration, optimization, verification tooling and support.
