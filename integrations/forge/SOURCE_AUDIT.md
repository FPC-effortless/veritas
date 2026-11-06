# Forge source-level integration audit — 2026-10-25

## Evidence boundary

All findings are from existing code and contracts; neither training nor authentic-source dataset import occurred in this change. The separate Forge package ships no generated-world state, source data, credentials or hidden benchmark labels. All synthetic fixtures are unit diagnostics.

## Veritas: reuse, don't copy

- `src/investigation_world/investigation_data/acquisition.py` and `models.py`: rights-aware acquisition and source provenance receipts. Retain as authority for Veritas's investigation sources; Forge v0.1 requires independent source-policy declarations and must not treat those as verified by itself.
- `src/investigation_world/investigation_data/preparation.py`: safe archive extraction, content hashing and deterministic selection. Future Forge publisher adapters can call a separately versioned common library instead of duplicating archive and acquisition logic.
- `src/investigation_world/foundry/calibration_ingestion.py`: actual-source data calibrates synthetic world generators; **not** a real sequence dataset/ground truth substitute.
- `src/investigation_world/foundry/training_product.py`, `training_corpus.py`: training uses TRAIN-only independently verified trajectories. Forge must never promote full source rows or held-out labels into a model-visible evaluator context.
- `src/investigation_world/integrations/woyengi/adapter.py`: existing integration contract. New Forge import/export must preserve separate authority identity and never infer privileged governance from a content hash.
- `docs/operational-world-dataset-fusion.md`: existing source-specific normalization and source-quality cautions; Forge temporal source converters must not erase their original evidence semantics.

## Woyengi: state is not a dataset

- `packages/ingestion/src/index.ts` creates provisional, source-identified ingestion envelopes with content hashes and locality policy.
- `docs/architecture.md` separates observation/claim/evidence from authoritative state, maintains identity and bitemporal reconstruction, and distinguishes platform authority from compute.
- An eventual Woyengi adapter must export only explicitly authorized observations, preserve both clocks, redact or deny restricted records, and keep Woyengi acceptance/reconciliation out of the Forge data processor.

## TAC-OSM and PNDS: model and mathematical boundaries

- `TAC-OSM/src/tac_osm/leakage.py` blocks forbidden gold/oracle/target attributes at the routing interface. Forge's `point_in_time` is complementary, not a substitute for downstream model input audits.
- TAC's authentic physical model fits and long-history failures are research outcomes; a new dataset export does **not** change any existing gate.
- `pnds-lean/foundation/v1/README.md` requires source-verified original data, matched active parameters, data and training compute, untouched tests and preservation of negative results. No Lean proof is claimed for this Python data utility.

## Why standalone under integrations/forge/

No repository-creation route is authorized through the current connector. The `integrations/forge` subtree in Veritas incubates a separately buildable, dependency-free Python package; it is not part of Veritas's `src/investigation_world` namespace. Veritas's existing test runner gets one narrow smoke hook; no existing scientific gate is weakened.

## Next source-authorized milestone

1. Verify an exact pinned real publisher artifact, license/AI-use/redistribution and personal-data decision in an independent acquisition process.
2. Add reviewed concrete importers for one authentic operational source and one robot dataset (for example, decoded LeRobot/ALOHA data). Never invent `available_at`, intervention times or verified outcomes.
3. Validate source/entity/time continuity and longitudinal group/site holdout; freeze source and cleaned manifests before model selection.
4. Compare TAC with strong matched baselines using **identical genuine training data, parameter budget and training compute**, with untouched evaluation splits. Measure predictive and decision outcomes separately.
5. Require independent source-level review, GitHub CI and release qualification before merge or distribution.

Status: MVP structural gates tested on fixtures locally; authentic-source run, broader Veritas CI, independent review, commercial qualification and native HDF5/Parquet adapters remain OPEN.
