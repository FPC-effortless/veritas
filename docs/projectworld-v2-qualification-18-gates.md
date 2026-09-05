# ProjectWorld v2 — 18-Gate Qualification Contract

## Purpose

This document defines the release gate contract for ProjectWorld v2. It is intentionally evidence-oriented: a release is not described as qualified merely because the generator or runtime executes successfully. Every gate must emit a machine-checkable result, and the release is eligible only when all 18 gates pass.

## Gates

| ID | Gate | Required assertion |
|---|---|---|
| PW2-01 | Deterministic generation | Same distribution seed/config produces byte-equivalent public project specifications. |
| PW2-02 | Split integrity | Train, IID, OOD and adversarial membership is deterministic and mutually exclusive. |
| PW2-03 | Scale | Production distribution contains 896 projects: 512 train, 128 IID, 128 OOD, 128 adversarial. |
| PW2-04 | Public/private boundary | Agent-facing bundles contain no seed, split identity, oracle, latent defect, hidden-delay or disruption truth. |
| PW2-05 | Hash integrity | Public and evaluator bundles have independently reproducible content hashes. |
| PW2-06 | Grammar validity | Every generated project compiles from the validated ProjectWorld construction grammar. |
| PW2-07 | Runtime reachability | Every sampled project can initialize and execute through the HUD-compatible runtime contract. |
| PW2-08 | Action validity | Identity-bound actions reject malformed, unauthorized or otherwise invalid transitions. |
| PW2-09 | Persistent state | Resource, procurement, schedule, authority, inspection and project state persist correctly across action sequences. |
| PW2-10 | Procurement lifecycle | Procurement supports lead time, capacity/MOQ, delay, expediting and substitution semantics without state corruption. |
| PW2-11 | Recovery/rework | Delays, latent defects and rework consume the correct resources/time and permit valid recovery strategies. |
| PW2-12 | Role authority | Role-scoped observations and authority constraints prevent unauthorized state transitions. |
| PW2-13 | Outcome verifier | Completion is determined from authoritative project state, not self-reported agent output. |
| PW2-14 | Policy calibration | Oracle/competent policies outperform myopic/random baselines on the intended objective. |
| PW2-15 | Exploit resistance | Exploit/shortcut policies cannot obtain competent-level success by bypassing intended constraints. |
| PW2-16 | OOD generalization | OOD projects exercise project/site regimes outside the training support. |
| PW2-17 | Adversarial stress | Adversarial projects combine budget, schedule, market, site, delay and latent-defect pressure as specified. |
| PW2-18 | HUD/export conformance | The release package, taskset and environment satisfy the pinned HUD contract and reproduce the recorded qualification result. |

## Release rule

A ProjectWorld v2 release is **QUALIFIED** only if `PW2-01` through `PW2-18` all return `PASS` from the same immutable release candidate. Any missing, skipped, non-deterministic, or failed gate makes the release **NOT QUALIFIED**.

The qualification report must record the release commit, distribution configuration, generator/runtime versions, gate results, artifact hashes, and evaluator-private identifiers. Private oracle material must remain outside buyer-facing artifacts.

## Marketplace claim rule

The marketplace listing may claim **18/18 qualification gates passed** only when a generated qualification report for the exact release candidate records 18/18 PASS. This document is the contract, not itself evidence of a completed qualification run.
