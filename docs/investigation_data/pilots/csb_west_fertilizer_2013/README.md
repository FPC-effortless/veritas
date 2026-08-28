# CSB West Fertilizer Staged Evidence Pilot

This pilot adds U.S. Chemical Safety Board investigation `2013-02-I-TX`, the April 17, 2013 West Fertilizer Company fire and ammonium-nitrate explosion, as a staged high-consequence investigation episode.

It is designed to test a different reasoning profile from the refinery pilots: community blast consequences, emergency-responder risk, hazardous-material awareness, regulatory coverage, and land-use planning.

## Provenance chronology

A source-level timing discrepancy is preserved rather than normalized away:

- CSB published a **news release on May 3, 2013** saying it released a three-minute video documenting the blast damage.
- The dedicated CSB **video landing page is dated May 10, 2013** and says the footage was taken May 3.

The manifest therefore creates two evidence fragments. The May 3 publisher announcement is timed context; the May 10 landing page is the video/primary-evidence surface. This keeps the Gold-10 index's `west-blast-damage-2013` May 10 date intact while also retaining evidence that CSB publicized the footage earlier.

Later stages are:

| Release date | Fragment | Role |
| --- | --- | --- |
| 2013-05-03 | CSB video-release news | context |
| 2013-05-10 | dedicated blast-damage video page | primary evidence |
| 2014-04-22 | preliminary findings | official finding |
| 2016-01-29 | final-report approval news | official finding |
| 2016-01-29 | `Dangerously Close` safety video | official reconstruction/finding |

The CSB investigation page records the final report as released January 28, 2016 and the investigation as unanimously approved at the January 28 public meeting. The pilot uses the dated January 29 approval-news surface for final institutional conclusions rather than copying or assigning an inferred timestamp to the report PDF.

## Staged reasoning objective

At the May 2013 stages, the agent can reason about observable damage and the scale of offsite consequences but must not borrow later conclusions about regulatory failures, responder preparation, or land-use policy.

At the April 2014 stage, preliminary CSB analysis becomes available. The agent should update hypotheses about ammonium-nitrate hazards and community protection while still recognizing that the investigation was ongoing.

At the January 2016 stage, the final institutional findings and post-final reconstruction become visible. Final-answer agreement can then be evaluated separately from whether earlier reasoning was justified at its historical cutoff.

## Conservative temporal policy

Date-only evidence becomes available at **12:00Z on the following calendar day**. Tests assert the state immediately before and at each gate.

This yields:

1. `2013-05-04T11:59:59Z`: no evidence;
2. `2013-05-04T12:00:00Z`: May 3 publisher announcement only;
3. `2013-05-11T11:59:59Z`: announcement only;
4. `2013-05-11T12:00:00Z`: announcement + damage video page;
5. `2014-04-23T12:00:00Z`: preliminary findings added;
6. `2016-01-30T12:00:00Z`: final approval and `Dangerously Close` added.

## Epistemic treatment

The damage video is `primary_evidence`. The publisher announcement is `context`. CSB preliminary and final analyses and the later narrated reconstruction are `official_finding` evidence.

`ground_truth_claims` remains empty. Final CSB conclusions stay in the private oracle as institutional findings so the environment does not equate a government investigation's conclusion with omniscient truth.

## Privacy and media policy

The repository stores only metadata and external CSB locators. It does not store report PDFs, video bytes, embedded YouTube content, captions, transcripts, audio, frames, photographs, or named-person records.

The checked-in review record covers only this link-only construction. Any artifact acquisition or derivative creation requires a separate artifact-level review.

## Falsifiers

The pilot fails if:

- the May 10 video page is backdated to the May 3 news-release date;
- the May 3 publisher announcement is mislabeled as raw video evidence;
- April 2014 preliminary findings appear in a May 2013 state;
- final January 2016 conclusions or reconstruction appear at a pre-final cutoff;
- damage footage is treated as an institutional conclusion rather than primary evidence;
- any fragment lacks the checked-in review identifier;
- a report PDF is introduced as time-gated evidence without an explicit reviewed publication decision;
- final institutional findings leak into the public episode before their source release;
- the executable pilot drifts from the Gold-10 West case identity or capability selection.

## Scientific status

This is an implementation/provenance pilot. It does not establish scientific qualification, frontier discrimination, or training readiness.

The next research layer should score hypothesis checkpoints and responder/community-risk judgments at each historical stage, not only final-answer similarity.
