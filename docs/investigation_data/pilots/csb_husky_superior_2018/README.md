# CSB Husky Superior Staged Evidence Pilot

This pilot adds U.S. Chemical Safety Board investigation `2018-02-I-WI`, the April 26, 2018 Husky Superior Refinery explosion and fires, as a staged investigation episode.

The target capability is reasoning during transient operations: a refinery unit is moving from normal operation toward a maintenance turnaround, safeguards and flow paths change, an explosion occurs, secondary consequences escalate, and later evidence changes the causal model.

## Evidence chronology

| Release date | Fragment | Role |
| --- | --- | --- |
| 2018-04-26 | CSB deployment announcement | context |
| 2018-08-02 | CSB factual update | ongoing institutional finding |
| 2018-08-02 | CSB interim animation | ongoing institutional reconstruction |
| 2022-12-29 | CSB final-report release | final institutional finding |
| 2023-06-09 | `Transient Hazards` safety video | post-final institutional reconstruction |

The August 2018 factual update states that the explosion occurred while the fluid catalytic cracking unit was being shut down for planned maintenance and inspection. It documents the explosion, debris impact on a nearby asphalt tank, release of hot asphalt, subsequent fire, injuries, and evacuation while explicitly stating that the investigation was ongoing.

The final December 2022 release explains that the accident occurred during shutdown of the FCC unit for a turnaround and reports the completed investigation. The June 2023 video is deliberately treated as post-final communication rather than historical evidence available to an investigator in 2018.

## Staged reasoning objective

At the first cutoff, the agent knows only that CSB deployed to a refinery explosion during shutdown preparations and that injuries and community evacuation were reported. This is context, not a causal conclusion.

At the August 2018 cutoff, the agent receives both a factual investigative update and an interim animation. The correct behavior is to update hypotheses about transient operations and event escalation while recognizing that both artifacts came from an ongoing investigation.

At the December 2022 cutoff, final institutional findings become available. A later evaluator can compare the agent's earlier evidence-grounded hypotheses with those final findings without treating them as omniscient truth.

At the June 2023 cutoff, the post-final `Transient Hazards` reconstruction becomes available. It is useful for training or explanation only when the simulated time permits post-final material.

## Conservative temporal policy

Date-only publications become available at **12:00Z on the following calendar day**. The regression suite checks both sides of each release gate:

1. `2018-04-27T11:59:59Z`: no evidence;
2. `2018-04-27T12:00:00Z`: deployment context only;
3. `2018-08-03T11:59:59Z`: deployment context only;
4. `2018-08-03T12:00:00Z`: factual update and interim animation added;
5. `2022-12-30T11:59:59Z`: 2018 evidence only;
6. `2022-12-30T12:00:00Z`: final institutional release added;
7. `2023-06-10T11:59:59Z`: final release visible but post-final video withheld;
8. `2023-06-10T12:00:00Z`: post-final safety video added.

## Precision and epistemic treatment

The April deployment release describes the explosion as occurring **around** 10 a.m. CDT. That is not encoded as an exact private timestamp. `actual_timeline` therefore remains empty in this metadata-level pilot.

The deployment release is `context`. The August factual update and animation are `official_finding` evidence because they are institutional analysis produced during an ongoing investigation. The December 2022 release and June 2023 safety video are also `official_finding`, but their later availability is preserved by temporal gating.

`ground_truth_claims` remains empty. Final CSB conclusions are stored only as private institutional findings.

## Media and privacy policy

The repository stores only CSB-hosted landing-page metadata. It does not copy factual-update PDFs, final-report PDFs, appendices, video bytes, captions, transcripts, frames, photographs, or named-person records.

The review record covers link-only use. Any media acquisition or derived artifact requires a separate artifact-level review.

## Falsifiers

The pilot fails if:

- August 2018 factual analysis appears at the April deployment stage;
- December 2022 final findings appear in a 2018 state;
- the June 2023 post-final reconstruction appears before its release gate;
- the deployment announcement is mislabeled as a completed finding;
- an ongoing factual update is silently treated as final ground truth;
- an approximate event time is converted into an exact private timestamp;
- any fragment lacks the checked-in review identifier;
- source PDFs or media bytes are introduced without artifact-level review;
- the executable pilot drifts from the Gold-10 Husky identity, capability tags, or August 2 interim-animation date.

## Scientific status

This is an implementation/provenance pilot. It does not establish scientific qualification, frontier discrimination, or training readiness.

The next research layer should score whether an agent can reason correctly across transient operating modes, distinguish safeguards from assumptions, and revise hypotheses without using future final-report knowledge.
