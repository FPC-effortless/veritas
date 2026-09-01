# Gold-10 case-selection freeze

CASE-001 freezes the first ten CSB investigation cases before Gold-10 task implementation or model-result inspection. It does not create a new source, acquisition, rights, or truth authority.

## Canonical inputs

The freeze is reconstructed from existing canonical repository inputs:

- `docs/investigation_data/corpora/csb_gold_10/index.json` — exact ten-case selection and release policy;
- `docs/investigation_data/corpora/csb_gold_10/pilot_coverage.json` — one reviewed executable pilot per selected case;
- `docs/investigation_data/corpora/csb_gold_10/report_acquisition.json` — byte-verified report identities and provenance receipts;
- `src/investigation_world/investigation_data/source_catalog.json` — canonical CSB source rights, AI-use, privacy/redaction, and truth semantics;
- each pilot's `manifest.json` and `review_record.json` — temporal cut, evidence modalities, link-only review, and non-oracular truth boundary;
- `data/gold10/case_selection_v1.json` — the pre-model split, calibration designation, and future #152 owner paths.

`build_gold10_manifest()` content-hashes these inputs and emits a deterministic aggregate `manifest_sha256`. A material change to selection metadata, pilot content, report provenance, source policy, temporal cut, truth regime, split, or ownership therefore changes the reconstructed manifest identity.

## Frozen split

The case-disjoint split is fixed before model results:

- train: `2005-04-I-TX`, `2008-03-I-FL`, `2008-05-I-GA`, `2010-08-I-WA`, `2013-03-I-LA`, `2017-08-I-TX`;
- dev: `2012-03-I-CA`, `2013-02-I-TX`;
- eval: `2018-02-I-WI`, `2019-04-I-PA`.

Chevron Richmond (`2012-03-I-CA`) is explicitly designated for calibration/uncertainty behavior because the canonical case has useful pre-final public evidence. This designation is part of the frozen identity rather than a post-result choice.

## Truth and contamination

All ten cases are public historical CSB investigations. They are classified as high-contamination, non-sealed evidence. Current pilot manifests contain no private ground-truth claims. CSB findings remain institutional findings/evidence and are never promoted to omniscient truth by CASE-001.

Controlled/private truth is explicitly unavailable for this historical ten-case set. Gold-10 must not manufacture it.

## Report-byte authority

All ten final reports have byte-level acquisition verification and provenance receipts, but the current report registry marks every report `pending_artifact_level_review`. Verification of bytes is not authorization for redistribution, extraction, training, or task evidence.

CASE-001 therefore binds each report's artifact ID, URLs, byte count, report SHA-256, receipt SHA-256, and catalog identity while setting `eligible_for_task_evidence` to false unless a future authority record changes the exact review state to `approved_for_task_use`.

The existing `approved_for_link_only_pilot` review records authorize the current external-link pilot only. They do not authorize report-byte use.

## Ownership boundary

CASE-001 records future #152 task and verifier paths under:

- `src/investigation_world/gold10/tasks/**`;
- `src/investigation_world/gold10/verifiers/**`.

Those files are not implemented by CASE-001. Task/verifier implementation remains blocked until the case-selection freeze is merged, and any task that consumes final-report bytes additionally requires exact artifact-level use authority.

## Evidence ceiling

A successful freeze establishes deterministic case composition, provenance binding, temporal ownership, and fail-closed report eligibility. It is not verifier qualification, scientific qualification, Frontier qualification, training-value evidence, or commercial release authorization.
