# CSB Gold-10 Investigation Fusion Corpus

`csb-gold-10` is the first case-level expansion of Veritas high-stakes investigation data beyond the BP Texas City pilot.

It is a **reviewed executable fusion corpus**, not yet a ten-case scientific benchmark. The corpus records completed U.S. Chemical Safety Board investigations, dated evidence surfaces, causal-capability coverage, hindsight-controlled `FusionManifest` pilots, and the conservative date policy that every case preserves.

## Current executable status

All ten selected cases now have reviewed executable pilots under `docs/investigation_data/pilots/`.

`pilot_coverage.json` maps the canonical `index.json` case set to exactly one pilot per case. CI fails if coverage drops below 10/10, a mapping is duplicated, a pilot loses its review binding, private truth is introduced into a link-only public fragment, or source artifact bytes are checked into the pilot directories.

All ten official CSB final reports have also been acquired byte-for-byte on a GitHub-hosted runner, SHA-256 verified, and registered in `docs/investigation_data/verified_artifacts.json`. Raw report bytes were deleted before workflow artifact publication and are not committed to Git.

This is implementation/provenance and artifact-verification coverage only. It does not establish scientific qualification, frontier discrimination, exploit resistance, or training readiness.

## Selected cases

| Case | Accident | Final report | Distinctive investigation capability |
| --- | --- | --- | --- |
| BP Texas City | 2005-03-23 | 2007-03-20 | startup, process safety, organizational causality |
| T2 Laboratories | 2007-12-19 | 2009-09-15 | reactive chemistry and thermal runaway |
| Imperial Sugar | 2008-02-07 | 2009-09-24 | combustible dust and secondary propagation |
| Tesoro Anacortes | 2010-04-02 | 2014-05-01 | metallurgy and high-temperature hydrogen attack |
| Chevron Richmond | 2012-08-06 | 2015-01-28 | corrosion, material selection, leak response |
| West Fertilizer | 2013-04-17 | 2016-01-28 | emergency response, community risk, land use |
| Williams Olefins | 2013-06-13 | 2016-10-19 | isolation, overpressure, non-routine operations |
| Arkema Crosby | 2017-08-29 | 2018-05-24 | flooding, extreme weather, safeguard degradation |
| Husky Superior | 2018-04-26 | 2022-12-29 | turnaround and transient operating states |
| Philadelphia Energy Solutions | 2019-06-21 | 2022-10-11 | HF risk, corrosion, safeguards, offsite consequence |

## Why these ten

The goal is causal and procedural diversity rather than incident count. A model that performs well across these cases must reason over different mechanisms: chemistry, dust propagation, metallurgy, corrosion, overpressure, emergency response, land-use consequences, natural-hazard coupling, transient plant states, and toxic-material safeguards.

Several cases also contain **pre-final visual releases**. Chevron Richmond, West Fertilizer, Arkema Crosby, Husky Superior, and Philadelphia Energy Solutions therefore support staged investigations in which an agent must update hypotheses as evidence accumulates before the CSB publishes its final conclusions.

Other cases primarily contain post-final explanatory videos. Those are still useful as sealed evaluator references, late-stage evidence, process-verification material, or augmentation sources after artifact-level review; they must not leak into earlier simulated cutoffs.

## Temporal policy

The corpus declares `date_only_availability_policy = next_day_12z`.

If an official source establishes only a calendar release date, downstream manifests must not invent a precise release time. The default conservative gate is 12:00 UTC on the following calendar day. A more precise earlier timestamp may be used only when the original source establishes it reliably.

This is a default anti-hindsight rule, not a claim about when each artifact was actually first visible.

## Source and media boundary

Every URL in `index.json` is on `csb.gov`, the source host already present in the Veritas source catalog. The index deliberately points to CSB video pages rather than directly embedding YouTube URLs.

That distinction matters:

- a CSB page can establish publisher identity, investigation linkage, and a dated media surface;
- resolving or acquiring an externally hosted video is a separate artifact-level operation;
- external media, transcripts, frames, captions, and downloaded files remain subject to the fusion source/review policy;
- no source bytes are stored in this corpus index.

The typed validator rejects URLs outside the cataloged source host boundary.

## Epistemic boundary

A CSB final report date is metadata about the investigation lifecycle. It does not automatically turn every statement in the report into omniscient private truth.

Downstream episode construction must continue to distinguish:

1. directly established evidence;
2. CSB preliminary findings;
3. CSB final institutional findings;
4. derived reconstructions;
5. genuinely supportable private truth claims;
6. unknown or contested propositions.

The executable pilots preserve this separation. Institutional conclusions remain `OfficialFinding`-class evidence unless a stronger independent basis justifies a private truth claim.

## Validation

Run:

```bash
veritas-data validate-fusion-corpus docs/investigation_data/corpora/csb_gold_10/index.json
```

Validation checks:

- exactly ten cases;
- unique case IDs and slugs;
- valid accident/final-report chronology;
- internally consistent pre-final/post-final release dates;
- unique release IDs inside each case;
- valid HTTPS URLs;
- source-catalog acquisition/AI-use policy;
- every URL remains under the source's allowed hosts;
- the corpus contains both pre-final and post-final evidence.

Repository CI additionally validates `pilot_coverage.json` against every executable pilot and `report_acquisition.json` against the corpus, coverage registry, source policy, and verified-artifact registry.

## Final-report acquisition status

`report_acquisition.json` is the machine-readable registry for the ten official CSB final reports. It distinguishes **official URL resolution**, **byte verification**, and **artifact-level use review** as separate states.

All ten report rows are now `verified`. Each is bound to a central verification record containing:

- source and resolved URLs;
- retrieval timestamp;
- exact byte count;
- report SHA-256;
- provenance-receipt SHA-256;
- source-catalog SHA-256.

Some historical CSB report locators are dispatcher URLs while stable static PDF URLs are used for byte re-acquisition. Queue receipts therefore retain both identities: `canonical_source_url` preserves the checked-in official locator and `acquisition_url` records the bounded transport URL actually fetched. Each receipt also carries the queue digest and an `acquisition_spec_sha256` over the source ID, case ID, artifact ID, canonical source URL, acquisition URL, and expected SHA-256, so changing either URL changes the retained acquisition authority.

The `CSB Gold-10 Report Acquisition` GitHub workflow performs networked re-acquisition with read-only repository permissions. Because the verified report SHA-256 values are fed back into the downloader as expected checksums, any future byte change behind the same CSB URL fails closed. Raw PDFs are deleted before workflow artifacts are uploaded; only receipt metadata is retained. Cleanup is scoped to the exact raw artifact path owned by the current invocation, and acquisition refuses to overwrite a pre-existing raw or provenance target rather than recursively deleting caller-owned files under the output root.

Artifact verification is **not** artifact-use approval. Every report remains `pending_artifact_level_review` for redistribution or derived training artifacts. Report-derived facts and CSB conclusions must remain epistemically distinct.

The next substantive construction step is safe text/layout extraction from the verified reports with page-level provenance, deterministic extraction manifests, and no raw PDFs committed to Git. Videos remain downstream multimodal augmentation rather than the primary report-grounded evidence layer.

Do not mass-scrape current CSB pages and pretend current page text existed at historical cutoffs. Each historical release surface must remain individually dated and reviewed before it becomes time-gated agent evidence.
