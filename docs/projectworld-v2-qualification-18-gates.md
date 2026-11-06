# ProjectWorld v2 — 18-Gate Qualification Contract

## Purpose

This document separates the executable benchmark-candidate checks from the stronger ProjectWorld
release evidence. A successful generator, test suite or generic qualification report does not
establish HUD compatibility, operational readiness or release authorization.

## Executable benchmark-candidate gate set

`tools/build_projectworld_v2_qualification_candidate.py` uses the existing generic qualification
protocol with private-stratum coverage enabled. Its report must contain each of these exact names
once, with no missing, duplicated or additional gate:

1. `source_groups`
2. `train_source_groups`
3. `dev_source_groups`
4. `private_test_source_groups`
5. `private_test_scenarios`
6. `source_disjoint`
7. `cross_split_contamination`
8. `private_leakage`
9. `provenance`
10. `deterministic_replay`
11. `programmatic_criteria`
12. `feasibility`
13. `policy_ordering`
14. `competent_ceiling`
15. `oracle_competent_gap`
16. `random_ceiling`
17. `exploit_resistance`
18. `private_stratum_coverage`

The generic thresholds remain unchanged. ProjectWorld additionally requires `project_type`
metadata, at least five private strata, at least one case in every stratum and no stratum above
30% of the private panel. The report's `releaseable` flag and all 18 gate results must agree before
the tool can issue a private release manifest. A failed gate produces `not_qualified` and a failing
process exit; an invalid gate set is an error. No threshold is relaxed to make a candidate pass.

The restored workflow compiles 200 structural projects and runs five policy classes. It keeps the
full candidate, per-case evaluations and private release manifest in ephemeral evaluator storage.
Only an allowlisted aggregate summary is uploaded. `--output` is operator-private;
`--public-output` contains counts, gate names/pass flags and aggregate policy means, not rows,
hidden labels, panel identifiers or arbitrary gate observations.

## Separate higher-level release evidence

The following PW2-01 through PW2-18 checklist is **not** the generic report's gate-name set.
It retains the stronger intended release requirements. Each assertion needs separate exact-candidate
evidence before making the corresponding release/HUD claim; counting 18 generic gates does not
implement or satisfy this checklist.

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

An exact-candidate generic report may support the narrowly labelled claim **18/18 generic
benchmark-candidate checks passed**. It cannot support **PW2-01 through PW2-18 release evidence
passed**, HUD conformance, Frontier qualification or marketplace-release readiness without the
separate evidence above. This document and the repaired workflow are implementation, not a
completed scientific or hosted qualification run.
