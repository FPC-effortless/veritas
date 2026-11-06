# CSB Tesoro Anacortes staged evidence pilot

This pilot models the U.S. Chemical Safety and Hazard Investigation Board investigation of the April 2, 2010 Tesoro refinery explosion and fire in Anacortes, Washington.

## Purpose

The case adds metallurgy, high-temperature hydrogen attack (HTHA), inspection strategy, preventive maintenance, startup, hazard-analysis, and inherently-safer-material reasoning. It also provides a useful draft-to-final investigation interval in early 2014.

## Evidence stages

- **Apr. 2, 2010:** deployment context; available `2010-04-03T12:00:00Z`.
- **Apr. 1, 2011:** anniversary safety message during the ongoing investigation; available `2011-04-02T12:00:00Z`.
- **Jan. 29, 2014:** draft HTHA findings; available `2014-01-30T12:00:00Z`.
- **Jan. 30, 2014:** animation release; available `2014-01-31T12:00:00Z`.
- **May 1, 2014:** final report approval; available `2014-05-02T12:00:00Z`.
- **Oct. 28, 2014:** `Behind the Curve` post-final video; available `2014-10-29T12:00:00Z`.

## Animation publication-date reconciliation

Two CSB surfaces disagree on the animation date:

- the animation landing page displays **January 28, 2014**;
- CSB's contemporaneous news release says the agency released the animation on **January 30, 2014**.

For historical availability, the pilot uses the explicit publisher release announcement and therefore exposes the animation from `2014-01-31T12:00:00Z` under the repository's date-only policy. It does not alter the landing-page metadata or pretend the discrepancy does not exist.

## Draft-versus-final rule

The January 29 CSB release describes a draft report open for public comment. The May 1 release records final Board approval. Agents may use the draft HTHA theory as strong institutional evidence, but must preserve its draft status and remain able to revise conclusions before final approval.

## Epistemic and rights boundary

`ground_truth_claims` and `actual_timeline` remain empty. Precise public times and CSB institutional findings are not automatically promoted into private truth.

The pilot is link-only: no draft/final report PDFs, appendices, source text, media bytes, captions, transcripts, frames, photographs, or named-person records are checked in. Artifact acquisition or training use requires a separate review.

## Falsifiers

The pilot fails if draft findings leak into the 2010/2011 states; the animation is backdated to January 28 despite the explicit January 30 release announcement; May final approval leaks into the January draft state; `Behind the Curve` leaks before October 29; draft/final findings become private truth automatically; source artifact bytes are checked in; or the executable case drifts from Gold-10 identity, capability tags, or `Behind the Curve` date.

## Scientific status

Implementation/provenance pilot only. No scientific, frontier, or training-readiness qualification is claimed.
