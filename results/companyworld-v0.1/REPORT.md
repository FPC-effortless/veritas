# CompanyWorld v0.1 calibration anchor report

## Scope

This report resolves the no-work baseline semantics for the deterministic public calibration fixtures. It reports calibration anchors only; it contains no model evaluation and makes no customer performance claim.

## Calibration anchors

| Capability level | Empty-anchor mean | Public-reference mean | Interpretation |
| --- | ---: | ---: | --- |
| Diagnostic investigation | 0.000 | 1.000 | No-work gets no factual or evidence credit. |
| Interactive action | 0.100 | 1.000 | 0.050 authority compliance + 0.050 budget efficiency are always-on with no unauthorized actions and no budget spent. |
| Sequential control | 0.150 | 1.000 | 0.080 authority + 0.070 sequence efficiency remain with no actions, ticks, violations, or unauthorized attempts. |
| Dynamic portfolio control | 0.250 | 1.000 | No-op raw subtotal is 0.400; the zero-success ceiling caps it at 0.250. |

The higher-level nonzero values are intentional verifier semantics. They reflect compliance/efficiency terms which can be satisfied without task progress; they are not evidence of capability. The dynamic 0.250 is additionally enforced by the no-success reward ceiling. For the seed-7 dynamic fixture, all approval outcomes are `APPROVED`, so the no-denial uncertainty-recovery default contributes 0.100. No verifier or runtime scoring behavior is changed by this calibration correction.

## Buyer comparison rule

For each level, define:

```text
net_reward = model_mean - empty_anchor_mean
normalized_reward = clamp(net_reward / (reference_anchor_mean - empty_anchor_mean), 0, 1)
```

The denominator must be finite and strictly positive. Missing, malformed, non-finite, or non-separating anchors fail closed. Reports show raw reward for diagnosis, plus the empty/reference means, net reward, and normalized reward. Raw reward is not a buyer comparison metric and must not be compared across capability levels. Overall capability is the unweighted mean of the four level-specific normalized rewards.

The fixture's public-reference policy yields a mean of 1.000 at each level, so each denominator is positive. The fixed empty/reference anchor regression tests lock all four level values and the buyer-report tests lock fail-closed handling and normalized calculations.

Each `run_full_context_calibration()` result also exposes a `calibration_metrics` object keyed by the four levels. Every entry contains `empty_anchor_mean`, `reference_anchor_mean`, `net_reward`, and `normalized_reward`; raw model reward remains available in `model_scores`. This additive calibration JSON shape is versioned as `0.2.0` and uses the same fixture anchors included in that result.

## Limitations

These are small public calibration fixtures, not a private procurement panel. This report does not establish benchmark qualification, production-agent performance, uncertainty intervals, or commercial readiness. Use a same-build private stratified evaluation with repeated attempts for buyer decisions.
