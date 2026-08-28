# Public investigation datasets

This directory defines provenance-first public operational records for Veritas External Investigation worlds.

The committed manifests do **not** redistribute remote source documents. They identify official public artifacts by URL, role, source, and case. A materialized dataset release should fetch approved artifacts, freeze their bytes, record SHA-256 digests, and retain the source provenance needed for audit and re-verification.

## Files

- `source_registry.json` — acquisition registry for public organizations with usable operational records.
- `seeds/seed_v1.json` — four reference/training cases from NTSB and the U.S. Chemical Safety Board.

The seed cases are deliberately marked `train_reference`. They are known public cases and must not be reused as sealed evaluation holdouts.

## Public/private boundary

Each case has two independent artifact collections:

- `public_evidence` — evidence that may be exposed to the evaluated agent.
- `verifier_references` — official findings/final reports for operator-side scoring and audit only.

`PublicInvestigationCase` rejects overlap between those collections. Public projections strip verifier references, omit operator notes, and deny truth-bearing metadata keys such as `probable_cause`, `root_cause`, `official_findings`, and `recommendations`, including inside artifact metadata.

## Prepare projections

```bash
veritas-foundry prepare-public-investigations \
  datasets/public_investigations/seeds/seed_v1.json \
  --public-output build/public-investigations.json \
  --verifier-output /secure/veritas/public-investigations-verifier.json
```

The verifier output should be written outside an agent-visible package and outside any training corpus. Omit `--verifier-output` when only the public projection is required.

## Materialize source artifacts

```bash
veritas-foundry materialize-public-investigations \
  datasets/public_investigations/seeds/seed_v1.json \
  --registry datasets/public_investigations/source_registry.json \
  --public-root /datasets/veritas/public
```

This downloads approved document/web artifacts, records byte counts and SHA-256 hashes, and writes a public `materialization.json` inventory. YouTube artifacts are retained as reference-only links rather than being misidentified as downloaded video bytes.

Verifier material is **not downloaded by default**. When an operator explicitly supplies a separate verifier root, verifier bytes and their inventory are written only there:

```bash
veritas-foundry materialize-public-investigations \
  datasets/public_investigations/seeds/seed_v1.json \
  --public-root /datasets/veritas/public \
  --verifier-root /secure/veritas/verifier
```

The materializer validates the dataset against the source registry and rejects ordinary downloads from unregistered hosts. Redirects are checked again after resolution.

## Release discipline

A reference manifest is not a qualified benchmark. Before using a case in a sealed evaluation release:

1. freeze source bytes and SHA-256 hashes;
2. verify licensing/redistribution constraints for every artifact;
3. freeze train/calibration/holdout membership before model exposure;
4. keep holdout evidence and verifier material outside public training surfaces;
5. record acquisition time, source version, transformation lineage, and parser version;
6. run leakage and answerability audits;
7. qualify verifier behavior separately from ingestion success.
