# 084: Randomized probing after a synthetic causal shift

**The registered directional gate passed on all three paired simulation seeds; the result remains NOT_QUALIFIED.** In this deliberately confounded world, allocating a checked randomized probe produced the correct post-shift effect sign; observing the same number of opportunities passively, or retaining the original estimate, did not.

## Frozen design and result

Each seed used 160 acquisition opportunities before and 160 after a change. The probe branch used a host-prescribed randomized setting balanced within nuisance strata; the learner saw realized settings and consequences but not the stratum. Passive settings were nuisance-correlated. The frozen control kept its pre-change passive estimate. Each arm used a smoothed count estimator. The reference was the empirical paired potential-outcome contrast on a separate 160-world constructed panel per phase and seed, not an external task. It reached the scorer only after the prediction artifact was closed.

The prespecified post-shift rule required adequate support (at least 20 observations per setting), the correct nonzero sign and at least 0.10 less absolute error than the better passive or frozen control in **every** paired seed.

| Paired seed | Reference | Randomized probe | Passive | Frozen | Probe absolute-error advantage vs better control |
|---|---:|---:|---:|---:|---:|
| 1 | −0.2000 | −0.1358 | +0.2264 | +0.5730 | 0.3622 |
| 2 | −0.1813 | −0.2716 | +0.3273 | +0.7182 | 0.4182 |
| 3 | −0.1375 | −0.2469 | +0.1819 | +0.6818 | 0.2100 |

Per seed, active and passive each saw 320 acquisition opportunities and made 320 count updates. The active arm used 320 checked probes (160 post-shift); passive used no probes. Frozen had 320 opportunities but made only the 160 pre-shift updates. This is an equal-opportunity contrast, **not** equal acquisition cost. The TrainLab-recorded fit, prediction and verification elapsed times were 0.062458 s, 0.056098 s and 0.035950 s, respectively, for all arms/seeds together. Those bounded stage times are not a comparison of arm costs and exclude upstream world/data construction and review. No end-to-end cost, cost-optimal probe policy or 12:1 efficiency claim follows.

## Source and retained evidence

- Preregistered design: [PROTOCOL_082_086.md](PROTOCOL_082_086.md), 084 section. An unused prospective draft was held before fit after review identified a visible order cue for hidden strata and a sign predicate which could count a zero as negative. The executed R1 shuffled balanced strata, required a strictly correct sign, and was independently readmitted before any fit or scoring.
- Exact worker: [stage_084_086_worker.py](stage_084_086_worker.py), SHA-256 `8185926f087cc247f292bd09e72e5d385b48f173e9957177e86a3daaad1dde2b`; exact staged estimator: [life_study_082_086.py](../../src/research_lab/life_study_082_086.py), `596e59decbb39522d5fe97f3660805a031682e83a35d7c5df5cd60c99d362c33`. Frozen role protocol `70a9945f0aee9ff3a41164a7e522b7a6260ef67e85e1f55a7f12c790c23bfa23` and world specification `3970989681b108ec0ab50fc5e8d1540a7684271b88077e814eff0b06f527be47`.
- Reviewed recipe SHA-256: fit `c839da02f58ad6167ab6dd1c8075922a32f9bc5e8bb72c045a6343a5e90f6f3f`, predict `fd635f951ed2c5f95bf54ed4b435a8dccc9e4965165607cb1a791c7e9d8ebe94`, verify `0afa4f4bd1fb78b15d0827cd900129532cdd316acaa80081a4f43c6f4642ca66`.
- Canonical 081 world gate stage digest `25c71b275e128ee8dd534d6cd6adcfbcf077c942a564f121ef27f1e91721fd94`. 084 native verified stage digests: fit `74c22f23bc4d82778591d2804047f96a9de1da56a3f9b8dc18c0b6d08b829e7c`, predict `59022e00fd1345e81dd7fecf2a7767bb3e7c4ab018476732d02f82dc1ec27c38`, verify `72c126a7898c08a5d5f7d3caea97d59e12c8db423736149808590595bc4ebf20`. Verified private aggregate `c2f6ef468d892ace07681515547282e731b05c95b3dfc75083d82be7c9b0818b`; typed private Veritas evidence artifact `57b1a633df14c5362ef3ec702222942d863b6ef96daecb8d5764666bbad8a309`. Digest references do not provide access to the artifacts.
- Separately authorized stages passed TrainLab execution adequacy for their declared conditions. Research Lab retained their lineage. Independent post-audit verified receipts, recalculated smoothed estimates and reference contrasts from the retained artifacts, and reproduced the gate arithmetic. **No separate same-seed executable replay was done.**

## Resume without weakening the boundary

Start with the [four-gate protocol](FOUR_GATE_PROTOCOL.md), [bundle builder](stage_084_086_bundle.py) and [conductor](conductor.py). For an audit of the completed study, use the authorized private native receipts and evidence, verifying file digests and prior-stage bindings. Keep split identities, raw histories, outcomes, predictions, private review records and checkpoint data out of the public repository. The public checkpoint contains only aggregate results and digest references.

For a newly approved replication, begin with a distinct execution root and a newly reviewed 081 native-world prerequisite. Prepare a new frozen data/adequacy plan before observing scores, then build and obtain independent exact review for fit, predict and verify separately; each launch must pass conductor preflight with pinned roles and a native receipt from the previous stage. Do not relaunch a completed stage, use any historic GO token, or promote the result based on directional gating alone. Improve the science with controlled probe budgets and mechanism/structure changes, exact independent replay and complete resource accounting. This pilot does not establish autonomous experiment design, transfer to unfamiliar causal systems, superiority to original COG systems, general intelligence or efficiency.
