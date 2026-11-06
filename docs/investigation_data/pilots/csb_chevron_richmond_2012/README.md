# CSB Chevron Richmond Staged Evidence Pilot

This pilot extends the investigation evidence-fusion system with a case that has meaningful **pre-final** evidence: U.S. Chemical Safety Board investigation `2012-03-I-CA`, the August 6, 2012 Chevron Richmond refinery pipe rupture and fire.

The purpose is not to train a model to repeat the final CSB report. It is to test whether an agent can revise a causal hypothesis as evidence quality and institutional interpretation change over time.

## Evidence chronology

The manifest uses four dated CSB publication surfaces:

| Release date | Fragment | Role | Modality |
| --- | --- | --- | --- |
| 2012-09-11 | Surveillance video from the accident | primary evidence | video |
| 2013-04-19 | Board-approved interim investigation findings | official finding | document |
| 2013-04-19 | CSB narrated accident animation | official reconstruction/finding | video |
| 2015-01-30 | CSB release recording approval of the final report | final institutional finding | document |

The CSB investigation page records the accident on August 6, 2012, the final report release on January 28, 2015, and identifies an Interim Report, Regulatory Report, and Final Report. The pilot uses the separately dated January 30 final-approval release rather than assuming an exact first-public timestamp for the report PDF.

## Staged reasoning objective

At the first cutoff, the agent sees only surveillance evidence. It can infer event sequence and visible conditions but must not borrow corrosion, management-system, or emergency-response conclusions from later CSB analysis.

At the April 2013 cutoff, the agent gains the Board-approved interim findings and a CSB reconstruction. The correct behavior is not merely to add facts: the agent should update confidence, distinguish direct observation from CSB interpretation, and record which earlier hypotheses were strengthened, weakened, or remain unresolved.

At the 2015 cutoff, final institutional findings become available. Agreement with the final CSB conclusion can then be evaluated separately from whether earlier reasoning was justified by evidence available at the time.

## Conservative temporal policy

Historical publication pages frequently provide a calendar date without a trustworthy release timestamp. As in the Texas City pilot, date-only evidence becomes available at **12:00Z on the following calendar day**.

This is deliberately conservative for U.S. publication dates and prevents UTC conversion from exposing material during the prior local evening.

The regression test checks both sides of each release boundary:

1. `2012-09-12T11:59:59Z`: no evidence;
2. `2012-09-12T12:00:00Z`: surveillance only;
3. `2013-04-20T11:59:59Z`: surveillance only;
4. `2013-04-20T12:00:00Z`: surveillance + interim findings + reconstruction;
5. `2015-01-31T11:59:59Z`: pre-final evidence only;
6. `2015-01-31T12:00:00Z`: final institutional release also visible.

## Epistemic treatment

The pilot deliberately uses different evidence roles:

- surveillance footage: `primary_evidence`;
- CSB interim report approval: `official_finding`;
- CSB narrated animation: `official_finding` because it is an institutional reconstruction, not raw observation;
- final approval release: `official_finding`.

`ground_truth_claims` remains empty. The private oracle stores the CSB final institutional conclusion separately so a later evaluator can compare evidence-grounded reasoning with the agency's conclusion without silently declaring that conclusion omniscient truth.

## Media and privacy policy

All four artifacts are referenced through CSB-hosted landing pages. No source text, report PDF, embedded video bytes, captions, audio, or frames are checked into the repository.

`review_record.json` approves only this link-only, metadata-level use. Embedded media resolution or local derivative creation requires a separate artifact-level rights review.

The normalized actors identify only the CSB and the facility operator. Individual worker, resident, investigator, and other personal names are excluded from the task state.

## Falsifiers

The pilot fails if:

- surveillance becomes visible before its release gate;
- April 2013 institutional analysis leaks into the September 2012 state;
- final 2015 findings leak into either pre-final state;
- surveillance is mislabeled as an institutional finding;
- the CSB reconstruction is treated as raw primary evidence;
- the checked-in review identifier does not match every fragment;
- a final-report PDF is introduced as time-gated evidence without an explicit, reviewed publication-time decision;
- the CSB conclusion is serialized into the public episode before its source release is available;
- official findings are promoted automatically to private ground truth.

## Scientific status

This is an implementation/provenance pilot for staged evidence and hypothesis revision. It is **not** scientific qualification, frontier qualification, or training-readiness evidence.

The next useful step after this pilot is to add claim-level hypothesis checkpoints so a trajectory can be scored on whether each revision was justified at the exact evidence stage, not only on the final answer.
