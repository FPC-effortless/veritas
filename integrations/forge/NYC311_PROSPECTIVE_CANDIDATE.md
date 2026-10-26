# NYC311 fixed-ID public-source cohort candidate — 2026-10-27

**STATUS: REAL PUBLIC SOURCE ACQUIRED / NO SCIENTIFIC TRAINING QUALIFICATION.**

This is a small, separate, source-faithful companion to Forge's existing public-source snapshot module and to the TAC-OSM Enterprise [blocked study protocol](https://github.com/FPC-effortless/TAC-OSM/blob/research/ecosystem-first-class-boundaries-2026-10-26/research/enterprise-forecast-source-preflight-2026-10-26/PROTOCOL.md). It does not approve the future experiment, establish historical as-of features, train any model, open REPORT/TEST, perform outcomes verification, or authorize any real-world action.

## Real source milestone

**First immutable candidate capture (anchor to preserve):**
- [GitHub Actions run #40419202170](https://github.com/FPC-effortless/veritas/actions/runs/40419202170), real NYC Open Data `erm2-nwe9`, 2026-10-26T23:21:54.161638Z.
- 100 publisher-reported `Open` cases selected in an acquisition-time bounded public API query. Only `unique_key,created_date,agency,complaint_type,status` requested; no raw address, free text, location or closure labels.
- Original publisher-response SHA256: `751a0e826e29067f59935491f82a0378a45c15f9d4e76e3e72fb2ac432d7f568`.
- Frozen case ID list SHA256: `b2f3c8e8a65e9672a146560eb4f152b948bad84782355c31927347eb7f794831`. **Do not replace membership with any later "latest 100" public query.** IDs are retained in a restricted artifact, not written individually into public CI logs.
- Original bytes, original case IDs, acquisition clock, hash and explicit no-FIT authorization live in [artifact #12697711013](https://github.com/FPC-effortless/veritas/actions/runs/40419202170/artifacts/12697711013) (90-day retention under the repository's Actions policy, not permanent Git storage).
- Later source-code pushes may have generated **other candidate cohorts** during the initial implementation. They are distinct, **not** the named study anchor above. The latest workflow explicitly disables new enrollments on ordinary branch pushes or PR validation; further captures require manual dispatch. No schedule, automated future label lookup or costly training exists.

The prior metadata recovery identified an actual NYC archive `187190` and a large publisher-defined compressed/materialized size. The official NYC Open Data 101 guide states that archive downloads are **whole-file only**; do not download the multi-GB archive or its unfiltered sensitive columns merely to satisfy a research checkbox. Use only a rights-reviewed isolated publisher export or a safe prospective capture protocol. An archive's publisher version is not evidence of the exact historical availability of any field without independent release/timestamp confirmation.

## Executable source guards

`integrations/forge/src/forge_data/nyc311_prospective.py` provides source-only commands:

```sh
PYTHONPATH=integrations/forge/src python -m forge_data.nyc311_prospective inspect-candidate --candidate /secure/first-capture
# Explicitly operator-initiated future captures only:
PYTHONPATH=integrations/forge/src python -m forge_data.nyc311_prospective candidate --output /secure/new-candidate --limit 100
# Never attempt followup before seven elapsed days, and only from original membership:
PYTHONPATH=integrations/forge/src python -m forge_data.nyc311_prospective followup --candidate /secure/first-capture --output /secure/7-day-source-observation
PYTHONPATH=integrations/forge/src python -m forge_data.nyc311_prospective inspect-followup --candidate /secure/first-capture --followup /secure/7-day-source-observation
```

The first capture's hard seven-day minimum ends **2026-11-02T23:21:54.161638Z**. This is an earliest technical source-access constraint, **not** an activated scheduled task or validated seven-day outcome observation tolerance. An actual followup may occur later, producing unknown/missing counts that cannot be treated as publisher-closed or complete negative labels. New/unknown case IDs are forbidden: query the exact original 100 using text-numeric SQL-safe IDs. A missing case is **unknown**, never closed. Reopenings are also possible and need version-specific interpretation.

`inspect_candidate` and `inspect_followup` recheck saved raw bytes, source query membership, all ID digests, timestamps, missingness and unqualified status. They do **not** cryptographically prove real publisher truth, legal AI-use rights or independent Veritas verification. The original snapshot includes only `status='Open'` **as observed at acquisition**. Neither case creation time nor a latest-row source label proves historical availability.

## What remains blocked

1. A rights/privacy/retention review for any **future training release**, including observed source fields and evidence storage; no asserted boolean is adequate as independent attestation.
2. Freeze an experiment activation addendum: exact enrolled-group disposition, fixed seven-day horizon tolerance/completeness, monitoring/followup cadence, independent label/source auditor, real cohort selection and embargo/splits, protected REPORT/TEST, model/runner/PNDS hashes, seed and compute budgets, proper scores and meaningful effect threshold. This candidate does **not** constitute that addendum.
3. Observe publisher statuses of the *same* original case IDs after elapsed time, preserving actual source bytes/clock. Missing cases, corrections, late statuses, reopenings and target ambiguity remain explicit. Do not secretly use later future status as a prior model input.
4. Independent Veritas evaluation against actual original permitted outcome records, then only separately preregistered FIT. Publisher-reported closed status is **not** independently verified physical problem resolution.
5. Independent exact-head security/code review and merge decisions for stacked Forge PRs remain separate from software test PASS.

**Research status:** `SOURCE_COHORT_CANDIDATE_ONLY`; `FIT=BLOCKED`; `REPORT=BLOCKED`; `REPO_REPLAY=BLOCKED`; `QUALIFIED_LIVE_DEVICE=NO`.
