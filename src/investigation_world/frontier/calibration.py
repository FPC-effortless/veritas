from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from .models import (
    FrontierCalibrationObservation,
    FrontierQualificationPolicy,
    FrontierUtilityGateResult,
    GateStatus,
    PairedCapabilityComparison,
)


def _interval(observation: FrontierCalibrationObservation) -> tuple[float, float] | None:
    if observation.successes is not None and observation.sample_size is not None:
        n = observation.sample_size
        p = observation.successes / n
        z = 1.959963984540054
        denom = 1 + z * z / n
        center = (p + z * z / (2 * n)) / denom
        margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
        return max(0.0, center - margin), min(1.0, center + margin)
    if observation.score_stddev is not None and observation.sample_size is not None:
        margin = 1.959963984540054 * observation.score_stddev / math.sqrt(observation.sample_size)
        return max(0.0, observation.score - margin), min(1.0, observation.score + margin)
    return None


def _paired_difference_interval(
    comparison: PairedCapabilityComparison,
) -> tuple[float, tuple[float, float]]:
    """Approximate 95% CI for paired accuracy difference from a 2x2 aggregate.

    Each paired case contributes +1 when only the strong system is correct, -1 when
    only the weak system is correct, and 0 when their correctness agrees. The sample
    variance of those paired differences is recoverable from the four buyer-safe
    aggregate cells; no private row IDs or labels are required.
    """

    n = (
        comparison.both_correct
        + comparison.weak_only_correct
        + comparison.strong_only_correct
        + comparison.both_wrong
    )
    diff = (comparison.strong_only_correct - comparison.weak_only_correct) / n
    if n == 1:
        return diff, (-1.0, 1.0)

    zero_count = comparison.both_correct + comparison.both_wrong
    ss = (
        comparison.strong_only_correct * (1.0 - diff) ** 2
        + comparison.weak_only_correct * (-1.0 - diff) ** 2
        + zero_count * (0.0 - diff) ** 2
    )
    sample_variance = ss / (n - 1)
    se = math.sqrt(sample_variance / n)
    margin = 1.959963984540054 * se
    return diff, (max(-1.0, diff - margin), min(1.0, diff + margin))


def non_saturation_gate(
    observations: list[FrontierCalibrationObservation], policy: FrontierQualificationPolicy
) -> FrontierUtilityGateResult:
    strong = [item for item in observations if item.tier in set(policy.strong_model_tiers)]
    required = {
        "strong_model_tiers": list(policy.strong_model_tiers),
        "floor": policy.non_saturation_floor,
        "ceiling": policy.non_saturation_ceiling,
        "intermediate_observation_required": True,
    }
    if not strong:
        return FrontierUtilityGateResult(
            name="non_saturation",
            status=GateStatus.UNKNOWN,
            observed={"strong_observation_count": 0},
            required=required,
            detail="No observations match the policy-declared strong/frontier tiers.",
        )
    scores = [item.score for item in strong]
    intermediate = [
        item
        for item in strong
        if policy.non_saturation_floor < item.score < policy.non_saturation_ceiling
    ]
    observed = {
        "strong_observation_count": len(strong),
        "minimum_score": min(scores),
        "maximum_score": max(scores),
        "mean_score": mean(scores),
        "intermediate_observation_count": len(intermediate),
        "observation_ids": [item.observation_id for item in strong],
    }
    if intermediate:
        return FrontierUtilityGateResult(
            name="non_saturation",
            status=GateStatus.PASS,
            observed={**observed, "classification": "useful_intermediate_difficulty"},
            required=required,
            detail="Strong-model evidence includes non-saturated intermediate performance.",
            evidence_ids=[item.observation_id for item in strong],
        )
    if all(score <= policy.non_saturation_floor for score in scores):
        classification = "strong_models_at_floor"
        detail = "All policy-declared strong-model results are at or below the floor threshold."
    elif all(score >= policy.non_saturation_ceiling for score in scores):
        classification = "strong_models_saturated"
        detail = (
            "All policy-declared strong-model results are at or above the saturation ceiling."
        )
    else:
        classification = "no_intermediate_strong_performance"
        detail = (
            "Strong-tier results occur only at/beyond the configured floor and ceiling; "
            "no strong/frontier observation occupies useful intermediate difficulty."
        )
    return FrontierUtilityGateResult(
        name="non_saturation",
        status=GateStatus.FAIL,
        observed={**observed, "classification": classification},
        required=required,
        detail=detail,
        evidence_ids=[item.observation_id for item in strong],
    )


def _paired_capability_candidates(
    observations: list[FrontierCalibrationObservation],
    comparisons: list[PairedCapabilityComparison],
    policy: FrontierQualificationPolicy,
) -> list[
    tuple[
        float,
        tuple[float, float],
        FrontierCalibrationObservation,
        FrontierCalibrationObservation,
        PairedCapabilityComparison,
    ]
]:
    by_id = {item.observation_id: item for item in observations}
    order = {tier: index for index, tier in enumerate(policy.tier_order)}
    strong_tiers = set(policy.strong_model_tiers)
    candidates = []
    for comparison in comparisons:
        low = by_id.get(comparison.weak_observation_id)
        high = by_id.get(comparison.strong_observation_id)
        if low is None or high is None:
            continue
        if low.tier not in order or high.tier not in order:
            continue
        if high.tier not in strong_tiers or low.tier in strong_tiers:
            continue
        if order[low.tier] >= order[high.tier]:
            continue
        if low.metric_name != high.metric_name:
            continue
        context_pairs = (
            (low.benchmark_name, high.benchmark_name),
            (low.benchmark_version, high.benchmark_version),
            (low.candidate_id, high.candidate_id),
            (low.panel_id, high.panel_id),
            (comparison.benchmark_name, high.benchmark_name),
            (comparison.benchmark_version, high.benchmark_version),
            (comparison.candidate_id, high.candidate_id),
            (comparison.panel_id, high.panel_id),
        )
        if any(
            left is not None and right is not None and left != right
            for left, right in context_pairs
        ):
            continue
        sample_size = (
            comparison.both_correct
            + comparison.weak_only_correct
            + comparison.strong_only_correct
            + comparison.both_wrong
        )
        if low.sample_size is not None and low.sample_size != sample_size:
            continue
        if high.sample_size is not None and high.sample_size != sample_size:
            continue
        effect, interval = _paired_difference_interval(comparison)
        candidates.append((effect, interval, low, high, comparison))
    return candidates


def capability_separation_gate(
    observations: list[FrontierCalibrationObservation],
    policy: FrontierQualificationPolicy,
    paired_comparisons: list[PairedCapabilityComparison] | None = None,
) -> FrontierUtilityGateResult:
    order = {tier: index for index, tier in enumerate(policy.tier_order)}
    strong = [item for item in observations if item.tier in set(policy.strong_model_tiers)]
    strong_tiers = set(policy.strong_model_tiers)
    weaker = [
        item for item in observations if item.tier in order and item.tier not in strong_tiers
    ]
    required = {
        "tier_order": list(policy.tier_order),
        "strong_model_tiers": list(policy.strong_model_tiers),
        "minimum_effect": policy.capability_separation_min_effect,
        "minimum_confidence_gap": policy.capability_separation_min_confidence_gap,
        "uncertainty_required_for_pass": True,
        "paired_evidence_preferred_for_shared_panels": True,
    }
    if not strong or not weaker:
        return FrontierUtilityGateResult(
            name="capability_separation",
            status=GateStatus.UNKNOWN,
            observed={"strong_count": len(strong), "weaker_count": len(weaker)},
            required=required,
            detail="Both weaker-tier and policy-declared strong-tier observations are required.",
        )

    paired = _paired_capability_candidates(
        observations, paired_comparisons or [], policy
    )
    if paired:
        effect, ci95, low, high, comparison = max(paired, key=lambda item: item[0])
        observed = {
            "method": "paired-difference-normal-v1",
            "paired_comparison_id": comparison.comparison_id,
            "weak_observation_id": low.observation_id,
            "strong_observation_id": high.observation_id,
            "weak_tier": low.tier,
            "strong_tier": high.tier,
            "weak_score": low.score,
            "strong_score": high.score,
            "effect_size_score_gap": effect,
            "paired_difference_ci95": list(ci95),
            "paired_case_count": (
                comparison.both_correct
                + comparison.weak_only_correct
                + comparison.strong_only_correct
                + comparison.both_wrong
            ),
            "both_correct": comparison.both_correct,
            "weak_only_correct": comparison.weak_only_correct,
            "strong_only_correct": comparison.strong_only_correct,
            "both_wrong": comparison.both_wrong,
        }
        if (
            effect >= policy.capability_separation_min_effect
            and ci95[0] >= policy.capability_separation_min_confidence_gap
        ):
            status = GateStatus.PASS
            detail = (
                "Paired weak/strong outcomes separate by the required effect "
                "with uncertainty support."
            )
        elif effect <= 0 or ci95[1] <= 0:
            status = GateStatus.FAIL
            detail = "The stronger tier does not outperform the weaker tier in paired outcomes."
        elif (
            effect < policy.capability_separation_min_effect
            or ci95[0] < policy.capability_separation_min_confidence_gap
        ):
            status = GateStatus.FAIL
            detail = (
                "Measured paired separation is below the configured effect or "
                "confidence threshold."
            )
        else:
            status = GateStatus.UNKNOWN
            detail = "Paired uncertainty is inconclusive for the configured threshold."
        return FrontierUtilityGateResult(
            name="capability_separation",
            status=status,
            observed=observed,
            required=required,
            detail=detail,
            evidence_ids=[
                low.observation_id,
                high.observation_id,
                comparison.comparison_id,
            ],
        )

    candidates: list[
        tuple[float, FrontierCalibrationObservation, FrontierCalibrationObservation]
    ] = []
    for low in weaker:
        for high in strong:
            if low.metric_name != high.metric_name:
                continue
            context_pairs = (
                (low.benchmark_name, high.benchmark_name),
                (low.benchmark_version, high.benchmark_version),
                (low.candidate_id, high.candidate_id),
                (low.panel_id, high.panel_id),
            )
            if any(
                left is not None and right is not None and left != right
                for left, right in context_pairs
            ):
                continue
            if order.get(low.tier, -1) >= order.get(high.tier, len(order)):
                continue
            candidates.append((high.score - low.score, low, high))
    if not candidates:
        return FrontierUtilityGateResult(
            name="capability_separation",
            status=GateStatus.UNKNOWN,
            observed={"comparable_pairs": 0},
            required=required,
            detail="No comparable weak/strong metric pairs exist under the declared tier ordering.",
        )
    effect, low, high = max(candidates, key=lambda item: item[0])
    low_ci, high_ci = _interval(low), _interval(high)
    observed: dict[str, Any] = {
        "method": "independent-interval-gap-v1",
        "weak_observation_id": low.observation_id,
        "strong_observation_id": high.observation_id,
        "weak_tier": low.tier,
        "strong_tier": high.tier,
        "weak_score": low.score,
        "strong_score": high.score,
        "effect_size_score_gap": effect,
    }
    if low_ci is None or high_ci is None:
        return FrontierUtilityGateResult(
            name="capability_separation",
            status=GateStatus.UNKNOWN,
            observed={**observed, "uncertainty_available": False},
            required=required,
            detail=(
                "Point estimates separate, but uncertainty is unavailable; "
                "the gate does not pass on point estimates alone."
            ),
            evidence_ids=[low.observation_id, high.observation_id],
        )
    confidence_gap = high_ci[0] - low_ci[1]
    observed.update(
        {
            "uncertainty_available": True,
            "weak_ci95": list(low_ci),
            "strong_ci95": list(high_ci),
            "confidence_adjusted_gap": confidence_gap,
        }
    )
    if (
        effect >= policy.capability_separation_min_effect
        and confidence_gap >= policy.capability_separation_min_confidence_gap
    ):
        status = GateStatus.PASS
        detail = "Weak/strong tiers separate by the required effect with uncertainty support."
    elif high_ci[1] <= low_ci[0] or effect <= 0:
        status = GateStatus.FAIL
        detail = "The stronger tier does not outperform the weaker tier under uncertainty."
    elif high_ci[0] - low_ci[1] < policy.capability_separation_min_confidence_gap:
        status = GateStatus.FAIL
        detail = "Observed separation is not large enough after uncertainty adjustment."
    else:
        status = GateStatus.UNKNOWN
        detail = "Available uncertainty is inconclusive for the configured separation threshold."
    return FrontierUtilityGateResult(
        name="capability_separation",
        status=status,
        observed=observed,
        required=required,
        detail=detail,
        evidence_ids=[low.observation_id, high.observation_id],
    )


def harness_sensitivity_gate(
    observations: list[FrontierCalibrationObservation], policy: FrontierQualificationPolicy
) -> FrontierUtilityGateResult:
    groups: dict[
        tuple[str, str | None, str], list[FrontierCalibrationObservation]
    ] = defaultdict(list)
    for item in observations:
        groups[(item.model_identity, item.model_snapshot, item.metric_name)].append(item)

    comparable_pairs: list[
        tuple[float, FrontierCalibrationObservation, FrontierCalibrationObservation]
    ] = []
    for items in groups.values():
        for i, left in enumerate(items):
            for right in items[i + 1 :]:
                if left.harness_identity == right.harness_identity:
                    continue
                paired = (
                    left.comparison_group_id is not None
                    and left.comparison_group_id == right.comparison_group_id
                ) or (left.seed is not None and left.seed == right.seed)
                if paired:
                    comparable_pairs.append((abs(left.score - right.score), left, right))
    required = {
        "minimum_effect": policy.harness_sensitivity_min_effect,
        "paired_or_same_seed": True,
    }
    if not comparable_pairs:
        return FrontierUtilityGateResult(
            name="harness_sensitivity",
            status=GateStatus.UNKNOWN,
            observed={"comparable_harness_pairs": 0},
            required=required,
            detail=(
                "No paired/comparable multi-harness observations exist for "
                "the same model snapshot."
            ),
        )
    effect, left, right = max(comparable_pairs, key=lambda item: item[0])
    status = GateStatus.PASS if effect >= policy.harness_sensitivity_min_effect else GateStatus.FAIL
    return FrontierUtilityGateResult(
        name="harness_sensitivity",
        status=status,
        observed={
            "maximum_harness_effect": effect,
            "left_harness": left.harness_identity,
            "right_harness": right.harness_identity,
            "left_score": left.score,
            "right_score": right.score,
        },
        required=required,
        detail=(
            "Veritas surfaces a meaningful harness-dependent difference."
            if status is GateStatus.PASS
            else (
                "Comparable harnesses were measured, but the observed difference "
                "is below policy threshold."
            )
        ),
        evidence_ids=[left.observation_id, right.observation_id],
    )


def failure_mode_breadth_gate(
    observations: list[FrontierCalibrationObservation], policy: FrontierQualificationPolicy
) -> FrontierUtilityGateResult:
    counts: Counter[str] = Counter()
    for item in observations:
        counts.update(item.failure_mode_counts)
    total = sum(counts.values())
    required = {
        "minimum_failure_categories": policy.minimum_failure_categories,
        "maximum_failure_category_share": policy.maximum_failure_category_share,
        "parser_labels": list(policy.parser_failure_labels),
        "infrastructure_labels": list(policy.infrastructure_failure_labels),
    }
    if total == 0:
        return FrontierUtilityGateResult(
            name="failure_mode_breadth",
            status=GateStatus.UNKNOWN,
            observed={"measured_failures": 0},
            required=required,
            detail="No categorized failure evidence was supplied.",
        )
    dominant, dominant_count = counts.most_common(1)[0]
    dominant_share = dominant_count / total
    parser_share = sum(counts[label] for label in policy.parser_failure_labels) / total
    infra_share = sum(counts[label] for label in policy.infrastructure_failure_labels) / total
    degenerate = (
        max(dominant_share, parser_share, infra_share)
        > policy.maximum_failure_category_share
    )
    status = (
        GateStatus.PASS
        if len(counts) >= policy.minimum_failure_categories and not degenerate
        else GateStatus.FAIL
    )
    return FrontierUtilityGateResult(
        name="failure_mode_breadth",
        status=status,
        observed={
            "failure_categories": dict(sorted(counts.items())),
            "category_count": len(counts),
            "total_failures": total,
            "dominant_category": dominant,
            "dominant_share": dominant_share,
            "parser_share": parser_share,
            "infrastructure_share": infra_share,
        },
        required=required,
        detail=(
            "Failures span multiple non-degenerate categories."
            if status is GateStatus.PASS
            else "Failure evidence is too concentrated or spans too few meaningful categories."
        ),
        evidence_ids=[item.observation_id for item in observations if item.failure_mode_counts],
    )


def calibration_gates(
    observations: list[FrontierCalibrationObservation],
    policy: FrontierQualificationPolicy,
    paired_comparisons: list[PairedCapabilityComparison] | None = None,
) -> list[FrontierUtilityGateResult]:
    return [
        non_saturation_gate(observations, policy),
        capability_separation_gate(observations, policy, paired_comparisons),
        harness_sensitivity_gate(observations, policy),
        failure_mode_breadth_gate(observations, policy),
    ]
