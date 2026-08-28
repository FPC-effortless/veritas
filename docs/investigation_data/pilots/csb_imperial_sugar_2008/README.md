# CSB Imperial Sugar staged evidence pilot

This pilot models the U.S. Chemical Safety and Hazard Investigation Board investigation of the February 7, 2008 Imperial Sugar refinery explosion and fire in Port Wentworth, Georgia.

## Purpose

The case adds combustible-dust, housekeeping, equipment-design, primary-event uncertainty, and secondary-explosion propagation reasoning. It is especially useful because CSB published preliminary findings in March 2008 that supported a multi-stage propagation mechanism while explicitly leaving the initiating primary event unresolved.

## Evidence stages

- **Feb. 8, 2008:** deployment context; available `2008-02-09T12:00:00Z`.
- **Feb. 17, 2008:** investigation update/context; available `2008-02-18T12:00:00Z`.
- **Mar. 12, 2008:** preliminary propagation findings; available `2008-03-13T12:00:00Z`.
- **Sep. 24, 2009:** final institutional findings; available `2009-09-25T12:00:00Z`.
- **Oct. 6, 2009:** `Inferno` post-final reconstruction; available `2009-10-07T12:00:00Z`.

The pilot uses CSB public landing pages only and applies the repository `next_day_12z` rule to date-only publication surfaces.

## Primary-event uncertainty

The March 12 testimony stated that the investigation remained ongoing. It described the catastrophe as a multi-stage event and supported the proposition that a primary event dislodged accumulated sugar dust, fueling additional explosions, while saying the nature of the primary event was still unknown.

A compliant agent must therefore distinguish:

- strong evidence for secondary propagation;
- uncertainty about the initiating event;
- later final findings about dust accumulation, housekeeping, equipment design, and the likely primary explosion location.

## Epistemic and rights boundary

`ground_truth_claims` and `actual_timeline` remain empty. CSB preliminary and final conclusions remain institutional findings, not omniscient truth.

The pilot is link-only: no report PDFs, testimony downloads, source text, transcripts, media bytes, captions, frames, photographs, or named-person records are checked in. Artifact acquisition or training use requires a separate review.

## Falsifiers

The pilot fails if preliminary findings leak into February states; final findings leak into 2008 states; the `Inferno` video leaks before its release; the March preliminary evidence is represented as resolving the primary event; institutional findings become private truth automatically; source artifact bytes are checked in; or the executable case drifts from Gold-10 identity, capability tags, or the `Inferno` release date.

## Scientific status

Implementation/provenance pilot only. No scientific, frontier, or training-readiness qualification is claimed.
