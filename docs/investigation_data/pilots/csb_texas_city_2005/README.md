# CSB Texas City Temporal Fusion Pilot

This pilot exercises the investigation evidence-fusion contract against one real, high-consequence industrial accident: U.S. Chemical Safety Board report `2005-04-I-TX`, the March 23, 2005 BP Texas City refinery explosion and fire.

The pilot is deliberately narrow. It validates provenance, multimodal linkage, information-release timing, source-policy review, and public/private separation. It does **not** claim that the episode is scientifically qualified, frontier-useful, or ready for training distribution.

## Evidence chronology

The manifest contains four CSB-published evidence fragments:

| Release date | Fragment | Modality | Locator |
| --- | --- | --- | --- |
| 2005-10-27 | Preliminary findings | document | https://www.csb.gov/csb-issues-preliminary-findings-in-bp-texas-city-refinery-accident-investigators-present-data-in-public-meeting/ |
| 2006-10-30 | Organizational preliminary findings | document | https://www.csb.gov/csb-investigation-of-bp-texas-city-refinery-disaster-continues-as-organizational-issues-are-probed/ |
| 2007-03-20 | Final findings release / Board approval | document | https://www.csb.gov/u-s-chemical-safety-board-concludes-organizational-and-safety-deficiencies-at-all-levels-of-the-bp-corporation-caused-march-2005-texas-city-disaster-that-killed-15-injured-180/ |
| 2008-03-21 | `Anatomy of a Disaster` | video | https://www.youtube.com/watch?v=XuJtdQOU_Z4 |

The CSB video page identifies `Anatomy of a Disaster` as published March 21, 2008 and embeds the YouTube video above:

https://www.csb.gov/videos/anatomy-of-a-disaster/

The final investigation report itself is dated March 20, 2007, but the dated CSB release also says the full report text would be posted within the following week. Because the exact first-public timestamp of the PDF is not established by this pilot's evidence, the PDF is **not** used as an agent-visible time-gated fragment. The March 20 final-findings release is used instead.

## Conservative temporal policy

These historical CSB pages establish publication dates but do not provide a trustworthy machine-readable public-release timestamp for every artifact. The pilot therefore makes each dated artifact available at `00:00:00Z` on the **following calendar day**.

This intentionally biases against premature disclosure. A task evaluated at the end of the publication day may temporarily withhold evidence that was already public, but it cannot expose evidence before the documented release date.

The regression test evaluates four cutoffs:

1. `2005-10-28T00:00:00Z`: preliminary findings only;
2. `2006-10-31T00:00:00Z`: preliminary + organizational findings;
3. `2007-03-21T00:00:00Z`: preliminary + organizational + dated final findings;
4. `2008-03-22T00:00:00Z`: all dated documents + the official CSB video.

## Epistemic treatment

CSB findings are represented as `official_finding`, not `private_truth`.

The private oracle records what the CSB officially concluded so an evaluator can distinguish institutional-conclusion agreement from independent causal truth. `ground_truth_claims` is intentionally empty in this first pilot.

This prevents an important category error: a high-quality government investigation is strong evidence, but its final conclusion is not automatically promoted into philosophical or omniscient ground truth.

## Media policy

The video is linked, not copied. The pilot does not download YouTube media, captions, frames, or transcripts.

`review_record.json` scopes `review-csb-texas-city-link-only-v1` to public, link-only use and excludes named individuals from the normalized task state. Any later report acquisition, local media acquisition, transcript extraction, frame extraction, redistribution, or training use requires a separate artifact-level review.

## Falsifiers

The pilot fails if:

- the 2006 findings appear at the 2005 cutoff;
- the final findings release appears before its documented 2007 release;
- the final-report PDF is treated as temporally available without separately establishing its first-public posting time;
- the 2008 video appears at any earlier cutoff;
- the external-host video enters without the recorded review identifier;
- the review identifier does not match the checked-in review record;
- the final CSB conclusion is serialized into the public episode before its dated evidence is available;
- the source catalog rejects the CSB source under its current policy.

## Intended next step

After this pilot passes repository CI, expand the same construction to the remaining `csb-gold-10` investigation set, selecting cases with rich public timelines and multiple causal contributors while preserving case-level train/dev/eval separation.
