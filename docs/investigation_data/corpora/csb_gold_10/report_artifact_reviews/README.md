# Gold-10 report artifact review

RIGHTS-001 records the exact repository authority boundary for using the ten byte-verified CSB final reports as **internal task/verifier evidence**.

This is a repository provenance/policy decision, not a legal opinion or a blanket rights grant. The canonical `uscsb` source policy permits acquisition and AI use with conditions, requires attribution, keeps redistribution review-required, and requires embedded third-party media to be reviewed separately. The ten authority records therefore permit only internal extraction/normalization needed to construct and verify Gold-10 tasks, subject to the restrictions encoded in `task_use_authority_v1.json`.

The authority does **not** permit committing raw PDFs, redistributing raw reports in public/exported packages, treating photographs/video/attachments as implicitly cleared, using institutional findings as private ground truth, bypassing temporal cuts or personal-data/redaction review, or inferring commercial, scientific, Frontier, training-value, or model-training authorization.

## Fail-closed identity binding

Every record binds the exact current case ID, artifact ID, report SHA-256, provenance receipt SHA-256, source-catalog authority SHA-256, canonical URL, and acquisition URL from the merged Gold-10 registry. `validate_task_use_authority.py` rejects authority when any bound identity or the canonical `uscsb` policy drifts, when coverage is not exactly ten reports, or when an approval loses a required restriction.

The helper `is_eligible_for_internal_task_evidence()` returns true only after the entire authority manifest validates and the caller supplies the exact artifact ID, report hash, and receipt hash. A mutable `artifact_review_status` string is never consumed as authority.

Targeted falsifiers live beside the records because trusted RIGHTS-001 ownership is restricted to this directory:

```text
python docs/investigation_data/corpora/csb_gold_10/report_artifact_reviews/validate_task_use_authority.py
python docs/investigation_data/corpora/csb_gold_10/report_artifact_reviews/test_task_use_authority.py
```

The tests cover missing artifact identity, report-hash drift, receipt-hash drift, source-catalog authority drift, invalid decisions, missing restrictions, source-policy drift, and canonical registry drift.
