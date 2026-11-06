# CSB Williams Olefins staged evidence pilot

This pilot models the U.S. Chemical Safety and Hazard Investigation Board investigation of the June 13, 2013 Williams Olefins plant explosion and fire in Geismar, Louisiana.

## Purpose

The case adds reasoning about non-routine operations, isolated equipment, overpressure, pressure-relief protection, management of change, process hazard analysis, and process safety management.

It also tests a less convenient but important data condition: the reviewed CSB case record does not expose a separate public pre-final factual update or preliminary animation between deployment and the 2016 final case study. Veritas must preserve that sparse history instead of manufacturing a richer chronology.

## Evidence stages

1. **June 14, 2013 — deployment announcement**
   - role: `context`
   - available from: `2013-06-15T12:00:00Z`
   - source: https://www.csb.gov/chemical-safety-board-deploying-to-accident-at-williams-olefins-plant-in-geismar-louisiana/

2. **October 19, 2016 — final case-study release**
   - role: final institutional `official_finding`
   - available from: `2016-10-20T12:00:00Z`
   - source: https://www.csb.gov/csb-releases-final-case-study-into-2013-explosion-and-fire-at-williams-olefins-plant-in-geismar-louisiana/

3. **January 25, 2017 — Blocked In safety video**
   - role: post-final institutional communication
   - available from: `2017-01-26T12:00:00Z`
   - source: https://www.csb.gov/videos/blocked-in/

## Identifier reconciliation

Gold-10 stores the case as `2013-03-I-LA`, while the current CSB recommendation series displays identifiers such as `2013-3-I-LA-4` without the leading zero in the middle field.

The pilot preserves both `CSB-2013-03-I-LA` and `CSB-2013-3-I-LA` as source aliases. It does not rewrite the Gold-10 case identity to match the recommendation-number formatting.

## Sparse-history rule

The absence of a reviewed pre-final factual release is treated as evidence about the public record, not as a missing field to fill with generated material.

Accordingly:

- no synthetic 2013–2016 evidence fragment is introduced;
- the deployment-only state remains deployment-only until the final release gate;
- `ground_truth_claims` remains empty;
- `actual_timeline` remains empty;
- the final CSB conclusion remains an institutional finding, not omniscient truth.

## Rights and privacy boundary

This pilot is link-only. It does not check in final-report PDFs, appendices, source article text, embedded video bytes, captions, transcripts, frames, photographs, or named worker/contractor/investigator records.

Any artifact acquisition, extraction, redistribution, or training use requires a separate review.

## Falsifiers

The pilot fails if:

- final findings appear before October 20, 2016 at 12:00Z;
- the post-final video appears before January 26, 2017 at 12:00Z;
- a generated pre-final factual or animation fragment is inserted to make the case look more complete;
- deployment context is treated as a completed causal finding;
- final findings are promoted automatically into private truth;
- either CSB identifier form is silently discarded or used to rewrite Gold-10;
- report/media bytes enter the checked-in pilot;
- the executable pilot drifts from the Gold-10 Williams case or its `Blocked In` release.

## Scientific status

Implementation/provenance pilot only. No scientific qualification, frontier qualification, or training-readiness claim.
