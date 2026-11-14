# CSPT002 — corrected synthetic diagnostic (2026-11-06)

**Result:** NO POSITIVE DIAGNOSTIC SIGNAL; no capability claim; no GPU usage.

## Frozen design and provenance

- `PREREGISTRATION_002.json` and `cspt002.py` frozen by SHA256 before first CSPT002 fit, see `FROZEN_002.sha256`.
- 4 arms × 3 seeds 11/23/37 × 120 steps × 32 examples = 3,840 sampled generated worlds per fit. Online parameter count **65,100**, identical in all arms. EMA target encoder is nontrainable and only used by the causal latent arm.
- Target data is constructed with complete oracle state knowledge; the learner receives only initial state facts, a transfer, and an item query at inference. The `target_post` text is supplied exclusively to the loss's no-gradient EMA branch.
- Worlds are SHA256-partitioned by underlying owner/object/action state, independently of textual paraphrase and which object is queried. A receiver-swapped counterfactual is tested only when its state stays in the heldout partition.
- 12 checkpoints retained; reloaded checkpoint weights were independently re-evaluated in separate Python processes against exact DEV and exploratory TEST fixtures. **12/12 metric replays passed.** This is not an external independent scientific review.

## Results on development scenarios (mean over three seeds)

| Arm | Exact owner ↑ | Affected item ↑ | Unaffected item ↑ | Both item queries ↑ | State-triplet exact ↑ | Mean train seconds ↓ |
|---|---:|---:|---:|---:|---:|---:|
| Answer-only | 48.70% | 84.80% | 9.80% | 0.43% | 0.28% | 1.79 |
| Good views | 45.92% | 75.19% | 13.99% | 0.17% | 0.00% | 3.22 |
| Completion | 44.53% | 71.96% | 14.50% | 0.17% | 0.00% | 4.79 |
| Causal latent | 45.92% | 74.54% | 14.82% | 0.09% | 0.00% | 5.54 |

> All training-time values are CPU one-thread `time.perf_counter()` observations for the fit loop only, excluding evaluation. They are not hardware-independent FLOPs measurements.

`state_triplet_exact` jointly requires correct transferred-owner and untouched-owner queries, plus a correct changed-receiver counterfactual in the same heldout split. Counterfactual eligibility was 60.9–63.8% across the three DEV seeds. A recipient-only heuristic cannot satisfy this metric even though it can pass the old CSPT001 intervention score.

**Pre-registered decision:** the causal latent arm did not exceed the answer-only arm by ≥5 percentage points on DEV state-triplet correctness in any seed. The diagnostic signal is rejected. The floor-level endpoint does not distinguish fine-grained architectural contributions.

## Invalid preceding experiment

CSPT001 used alternate queries of an identical world in different data splits and an exploitable primary metric. Its results are retained as preliminary engineering observations but must NOT be cited as held-out structural generalization or scientific evidence of JEPA superiority/inferiority. CSPT002 is a new registration; none of the old receipts have been overwritten.

## Research interpretation

The model can exploit the transfer recipient but has not learned a stable exact mapping for multiple simultaneously mentioned object identities at this budget. Although the additional good-view, completion and latent-prediction objectives are implemented and differentiable, the experiment **does not** prove they help, nor show that JEPA generally fails. The answer-only baseline is a supervised answer-token control, NOT a genuine pretrained next-token language-model baseline. Extra objectives have different FLOPs and supervision, so parameter parity alone does not confer fair-compute qualification.

## Next scientifically discriminating work

1. Build a *structure-complete* benchmark whose required facts are updated through multiple chronological events, with disjoint source/time splits, pairwise role reversals, unchanged facts, exact-value binding, and a genuine independent target evaluator. Make a no-fit oracle/shortcut audit a gate before another training run.
2. Determine representation adequacy and optimization separately; measure binding error vs training budget without retroactively changing this protocol. If necessary preregister new follow-up studies with dedicated data and objective controls.
3. Port the proved objective to appropriately sized language-model backbones on legally sourced real text/trajectories. Compare with credible Transformer/GRU/SSM controls at ≥3 seeds and matched parameter, data and training-compute budgets. Observe real language perplexity, structural composition, delayed memory edits and inference cost.
4. Require the existing source, anti-cheat, reward-verifier, sealed-TEST, PNDS and independent-review gates before any TAC-OSM model admission, GPU allocation, scientific promotion or merging into the production intelligence architecture.
