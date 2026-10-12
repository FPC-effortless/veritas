# Gold-10 case-selection freeze

CASE-001 freezes the first ten CSB investigation cases before Gold-10 task implementation or model-result inspection. It does not create a new source, acquisition, rights, truth, release, training, scientific, Frontier, or commercial authority.

## Canonical inputs

The freeze is reconstructed from existing canonical repository inputs:

- `docs/investigation_data/corpora/csb_gold_10/index.json` — exact ten-case selection and release policy;
- `docs/investigation_data/corpora/csb_gold_10/pilot_coverage.json` — one reviewed executable pilot per selected case;
- `docs/investigation_data/corpora/csb_gold_10/report_acquisition.json` — byte-verified report identities and provenance receipts;
- `docs/investigation_data/corpora/csb_gold_10/report_artifact_reviews/task_use_authority_v1.json` — exact content-bound internal task/verifier evidence authority and restrictions;
- `src/investigation_world/investigation_data/source_catalog.json` — canonical CSB source rights, AI-use, privacy/redaction, and truth semantics;
- each pilot's `manifest.json` and `review_record.json` — temporal cut, evidence modalities, link-only review, and non-oracular truth boundary;
- `data/gold10/case_selection_v1.json` — the pre-model split, calibration designation, report-use authority policy, and future #152 owner paths.

`build_gold10_manifest()` content-hashes these inputs and emits a deterministic aggregate `manifest_sha256`. A material change to selection metadata, pilot content, report provenance, task-use authority, source policy, temporal cut, truth regime, split, or ownership therefore changes the reconstructed manifest identity.

## Frozen split

The case-disjoint split is fixed before model results:

- train: `2005-04-I-TX`, `2008-03-I-FL`, `2008-05-I-GA`, `2010-08-I-WA`, `2013-03-I-LA`, `2017-08-I-TX`;
- dev: `2012-03-I-CA`, `2013-02-I-TX`;
- eval: `2018-02-I-WI`, `2019-04-I-PA`.

Chevron Richmond (`2012-03-I-CA`) is explicitly designated for calibration/uncertainty behavior because the canonical case has useful pre-final public evidence. This designation is part of the frozen identity rather than a post-result choice.

## Truth, temporal availability, and contamination

All ten cases are public historical CSB investigations. They are classified as high-contamination, non-sealed evidence. Current pilot manifests contain no private ground-truth claims. CSB findings remain institutional findings/evidence and are never promoted to omniscient truth by CASE-001.

Controlled/private truth is explicitly unavailable for this historical ten-case set. Gold-10 must not manufacture it.

The reconstructed manifest distinguishes all modalities declared anywhere in a pilot from modalities that are actually public at that pilot's frozen `simulation_as_of` cut. Evidence released after the cut cannot become available merely because it exists in the same pilot manifest.

## Report task-use authority

All ten final reports have byte-level acquisition verification and provenance receipts. The report registry's mutable `artifact_review_status` remains observational only and is never an authorization token.

RIGHTS-001 now supplies a separate, independently reviewed, content-bound authority at `report_artifact_reviews/task_use_authority_v1.json`. CASE-001 permits `eligible_for_task_evidence=true` only after that authority is validated against the exact canonical ten-case set and, for every report, the exact `case_id`, `artifact_id`, report SHA-256, receipt SHA-256, catalog SHA-256, canonical URL, and acquisition URL.

The accepted decision is exactly `approved_for_internal_task_evidence_with_conditions`. Every approved record must preserve all of the following restrictions:

- internal extraction and normalization only;
- no raw-PDF Git commit;
- no raw-PDF public or exported redistribution;
- embedded third-party media must be excluded or separately reviewed;
- CSB attribution and source-locator provenance must be retained;
- institutional findings are not private ground truth;
- the frozen temporal cut must be respected;
- personal-data and redaction review must occur before content becomes agent-visible;
- verbatim reproduction must be minimized;
- the authority grants no commercial, Frontier, scientific, or training-value claim.

The authority also explicitly does **not** authorize raw-PDF redistribution, public-package redistribution, model-training rights, commercial release, scientific qualification, or Frontier qualification. Missing, malformed, incomplete, stale, identity-drifted, or restriction-weakened authority fails closed.

The existing `approved_for_link_only_pilot` review records remain a separate boundary for the current external-link pilots. They are not used as report-byte authorization.

## Ownership boundary

CASE-001 records future #152 task and verifier paths under:

- `src/investigation_world/gold10/tasks/**`;
- `src/investigation_world/gold10/verifiers/**`.

Those files are not implemented by CASE-001. Task/verifier implementation remains blocked until the case-selection freeze is merged. #152 may use report evidence only through the exact validated internal task-use authority and must continue to enforce its redaction, temporal, provenance, third-party-media, non-private-truth, and redistribution ceilings.

## Evidence ceiling

A successful freeze establishes deterministic case composition, provenance binding, content-bound internal report-use eligibility, temporal ownership, and fail-closed authority reconstruction. It is not verifier qualification, scientific qualification, Frontier qualification, training-value evidence, public redistribution authority, or commercial release authorization.
