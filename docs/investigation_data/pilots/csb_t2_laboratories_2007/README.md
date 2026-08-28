# CSB T2 Laboratories staged evidence pilot

This pilot models the U.S. Chemical Safety and Hazard Investigation Board investigation of the December 19, 2007 T2 Laboratories explosion and fire in Jacksonville, Florida.

## Purpose

The case adds reactive-chemistry, cooling-system, thermal-runaway, overpressure, hazard-recognition, and offsite-consequence reasoning. It is particularly useful because CSB published a preliminary runaway-reaction hypothesis in January 2008, long before the September 2009 final report.

It is an implementation/provenance pilot only. It is not scientifically qualified, frontier qualified, or training-ready merely because it is executable.

## Evidence stages

All date-only publication surfaces use the repository `next_day_12z` policy.

1. **December 19, 2007 — deployment announcement**
   - role: `context`
   - available from: `2007-12-20T12:00:00Z`
   - source: https://www.csb.gov/csb-deploys-to-fatal-jacksonville-florida-explosion/

2. **January 3, 2008 — investigation update**
   - role: `context`
   - available from: `2008-01-04T12:00:00Z`
   - source: https://www.csb.gov/statement-by-csb-investigator-in-charge-robert-hall-updating-the-public-on-the-investigation-of-the-t2-laboratories-explosion-and-fire/

3. **January 25, 2008 — field-phase preliminary findings**
   - role: preliminary institutional `official_finding`
   - available from: `2008-01-26T12:00:00Z`
   - source: https://www.csb.gov/csb-concludes-field-phase-of-t2-blast-investigation-in-jacksonville-fl-higher-number-of-offsite-injuries-found/
   - CSB publicly stated that preliminary findings indicated a runaway chemical reaction while explicitly saying further laboratory work would continue.

4. **September 15, 2009 — final findings**
   - role: final institutional `official_finding`
   - available from: `2009-09-16T12:00:00Z`
   - source: https://www.csb.gov/csb-finds-t2-laboratories-explosion-caused-by-failure-of-cooling-system-resulting-in-runaway-chemical-reaction-report-notes-company-did-not-recognize-hazards-of-chemical-process/

5. **September 22, 2009 — Runaway safety video**
   - role: post-final institutional communication
   - available from: `2009-09-23T12:00:00Z`
   - source: https://www.csb.gov/videos/runaway-explosion-at-t2-laboratories/

## Hypothesis-revision rule

The January 25 release is unusually valuable because it supports a specific early causal hypothesis without completing the investigation. A compliant agent may use it as evidence but must still:

- retain uncertainty about the exact initiating failure;
- distinguish preliminary runaway-reaction evidence from the later cooling-system conclusion;
- update when the final report adds hazard-recognition and process-design conclusions;
- avoid treating a preliminary institutional statement as private causal truth.

## Epistemic boundary

The final report and related CSB material contain precise event times and detailed causal analysis. At this metadata level:

- `ground_truth_claims` remains empty;
- `actual_timeline` remains empty;
- preliminary and final CSB conclusions remain institutional findings;
- precise public timestamps are not promoted automatically into private truth.

## Rights and privacy boundary

This pilot is link-only. It does not check in final-report PDFs, transcripts, downloaded update documents, source article text, embedded video bytes, captions, frames, photographs, or named worker/owner/investigator/injured-person records.

Any artifact acquisition, extraction, redistribution, or training use requires a separate review.

## Falsifiers

The pilot fails if:

- January 2008 preliminary findings leak into the December deployment state;
- September 2009 final findings leak into a January 2008 state;
- the post-final Runaway video appears before its release gate;
- the January 3 update is treated as a completed finding;
- the January 25 preliminary hypothesis is silently treated as final/private truth;
- public exact timestamps are automatically promoted into the private timeline;
- report/document/media bytes enter the checked-in pilot;
- the executable pilot drifts from Gold-10 T2 identity, capability tags, or Runaway release date.

## Scientific status

Implementation/provenance pilot only. No scientific qualification, frontier qualification, or training-readiness claim.
