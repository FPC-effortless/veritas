# CSB PES Philadelphia staged evidence pilot

This pilot models the U.S. Chemical Safety and Hazard Investigation Board investigation of the June 21, 2019 Philadelphia Energy Solutions refinery fire and explosions as a hindsight-controlled investigation episode.

## Purpose

The case adds a high-consequence refinery investigation with hydrofluoric-acid exposure, corrosion, safeguard reliability, offsite projectile risk, emergency isolation, and inherently-safer-design reasoning.

It is an implementation/provenance pilot only. It is not scientifically qualified, frontier qualified, or training-ready by virtue of being checked into the repository.

## Evidence stages

The pilot exposes only dated CSB publication surfaces and applies the repository `next_day_12z` policy to date-only releases:

1. **June 21, 2019 — deployment announcement**
   - role: `context`
   - available from: `2019-06-22T12:00:00Z`
   - source: https://www.csb.gov/chemical-safety-board-deploying-to-site-of-refinery-explosion-and-fire-outside-philadelphia-pa/

2. **October 16, 2019 — factual update**
   - role: ongoing institutional `official_finding`
   - available from: `2019-10-17T12:00:00Z`
   - source: https://www.csb.gov/chemical-safety-board-releases-factual-update-and-new-animation-detailing-the-events-of-the-massive-explosion-and-fire-at-the-pes-refinery-in-philadelphia-pa/

3. **October 16, 2019 — preliminary animation**
   - role: ongoing institutional reconstruction / `official_finding`
   - available from: `2019-10-17T12:00:00Z`
   - source: https://www.csb.gov/videos/preliminary-animation-of-philadelphia-energy-solutions-refinery-fire-and-explosions/

4. **October 11, 2022 — final-report release**
   - role: final institutional `official_finding`
   - available from: `2022-10-12T12:00:00Z`
   - source: https://www.csb.gov/csb-releases-final-report-into-2019-pes-fire-and-explosion-in-philadelphia/

5. **October 27, 2022 — Wake Up Call safety video**
   - role: post-final institutional communication
   - available from: `2022-10-28T12:00:00Z`
   - source: https://www.csb.gov/videos/wake-up-call-refinery-disaster-in-philadelphia/

## Identifier reconciliation

The public CSB surfaces do not use one identifier consistently.

- The investigation/recommendation series uses `2019-04-I-PA`.
- The October 2019 factual-update document is labeled `No. 2019-06-I-PA`.

The pilot preserves both as source aliases. It does not silently rewrite the factual-update identifier or mutate the Gold-10 case identity. The executable case remains bound to the Gold-10 `2019-04-I-PA` selection while retaining `2019-06-I-PA` as source provenance.

## Epistemic boundary

The factual update contains precise event timestamps, but precision is not the same as omniscient truth. At this metadata level:

- `ground_truth_claims` remains empty;
- `actual_timeline` remains empty;
- the final CSB causal conclusions remain `official_findings` in the private oracle;
- exact public factual-update timestamps are not promoted automatically into private truth.

A future artifact-level ingestion may construct a reviewed timeline, but only after source-by-source provenance and truth-status decisions.

## Rights and privacy boundary

This pilot is link-only. It does not check in:

- factual-update or final-report PDFs;
- appendices;
- source article text;
- embedded video bytes;
- captions or transcripts;
- frames or photographs;
- named worker, firefighter, or investigator records.

Any acquisition, extraction, redistribution, or training use of those artifacts requires a separate review.

## Falsifiers

The pilot fails if:

- October 2019 analysis appears in the June deployment state;
- October 2022 final findings appear in a 2019 state;
- the post-final Wake Up Call video appears before its release gate;
- the deployment announcement is treated as a completed causal finding;
- the factual update or preliminary animation is treated as private ground truth;
- either public CSB identifier is silently discarded or rewritten;
- exact public timestamps are automatically promoted into the private timeline;
- report PDFs or media bytes become part of the checked-in pilot;
- the executable pilot drifts from the Gold-10 PES case and its selected evidence releases.
