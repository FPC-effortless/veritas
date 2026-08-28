from __future__ import annotations

from collections import defaultdict
from itertools import combinations
from typing import Iterable, Sequence

from investigation_world.trajectory import (
    FailureCategory,
    ReverificationRecord,
    TrajectoryV2,
    canonical_hash,
    canonical_json,
)

from .models import (
    AttributionEvidence,
    CapabilityFailureProfile,
    ComparisonKind,
    ComparisonView,
    ControlledRunComparison,
    DiagnosticInput,
    FailureAttribution,
    FailureCategoryDistribution,
    TrajectoryDiagnosticInput,
    TrajectoryDiagnosticsReport,
    VerifierVersionComparison,
)

_PRIMARY_THRESHOLD = 0.80
_UNTAGGED_CAPABILITY = "__untagged__"
_BUDGET_REASONS = frozenset(
    {
        "budget_exhausted",
        "cost_budget_exhausted",
        "tool_call_budget_exhausted",
        "token_budget_exhausted",
        "time_limit",
        "time_limit_exceeded",
    }
)


def _trajectory(value: DiagnosticInput) -> TrajectoryV2:
    if isinstance(value, TrajectoryDiagnosticInput):
        return value.trajectory
    return value


def _taxonomy_zeros() -> dict[str, float]:
    return {category.value: 0.0 for category in FailureCategory}


def _taxonomy_int_zeros() -> dict[str, int]:
    return {category.value: 0 for category in FailureCategory}


def _signal(
    signal: str,
    probabilities: dict[FailureCategory, float],
    qualification: str,
    *,
    direct: bool = False,
) -> AttributionEvidence:
    encoded = {category.value: probability for category, probability in probabilities.items()}
    return AttributionEvidence(
        signal=signal,
        category_probabilities=encoded,
        qualification=qualification,
        direct=direct,
    )


def _average_signal_probabilities(evidence: Sequence[AttributionEvidence]) -> dict[str, float]:
    probabilities = _taxonomy_zeros()
    if not evidence:
        probabilities[FailureCategory.UNKNOWN.value] = 1.0
        return probabilities
    for item in evidence:
        for category, value in item.category_probabilities.items():
            probabilities[category] += value / len(evidence)
    total = sum(probabilities.values())
    if total <= 0.0:
        return {**_taxonomy_zeros(), FailureCategory.UNKNOWN.value: 1.0}
    return {key: value / total for key, value in probabilities.items()}


def diagnose_failure(value: DiagnosticInput) -> FailureAttribution:
    """Attribute one failure conservatively from canonical, structured trajectory evidence."""

    trajectory = _trajectory(value)
    declared = trajectory.failure
    if declared.category != FailureCategory.UNKNOWN:
        confidence = 1.0 if declared.confidence is None else declared.confidence
        probabilities = _taxonomy_zeros()
        probabilities[declared.category.value] = confidence
        probabilities[FailureCategory.UNKNOWN.value] = 1.0 - confidence
        primary = (
            declared.category
            if confidence >= _PRIMARY_THRESHOLD
            else FailureCategory.UNKNOWN
        )
        evidence = (
            _signal(
                "trajectory.failure.category",
                {
                    declared.category: confidence,
                    FailureCategory.UNKNOWN: 1.0 - confidence,
                },
                "Preserves the canonical failure classification and its stated confidence.",
                direct=True,
            ),
        )
        return FailureAttribution(
            trajectory_id=trajectory.trajectory_id,
            primary_category=primary,
            category_probabilities=probabilities,
            evidence=evidence,
            ambiguous=confidence < 1.0 or primary == FailureCategory.UNKNOWN,
            qualified=confidence < 1.0,
        )

    evidence: list[AttributionEvidence] = []
    if any(call.success is False for call in trajectory.provider_calls):
        evidence.append(
            _signal(
                "provider_call_unsuccessful",
                {
                    FailureCategory.INFRASTRUCTURE_PROVIDER_FAILURE: 0.65,
                    FailureCategory.UNKNOWN: 0.35,
                },
                (
                    "An unsuccessful provider call is consistent with provider/infrastructure "
                    "failure, but the record alone does not establish root cause."
                ),
            )
        )

    if any(call.success is False for call in trajectory.resource_calls):
        evidence.append(
            _signal(
                "resource_call_unsuccessful",
                {
                    FailureCategory.TOOL_ACTION_FAILURE: 0.375,
                    FailureCategory.ENVIRONMENT_RUNTIME_FAILURE: 0.375,
                    FailureCategory.UNKNOWN: 0.25,
                },
                (
                    "A failed resource call cannot uniquely distinguish tool behavior from "
                    "environment/runtime behavior."
                ),
            )
        )

    reason = trajectory.termination.reason.strip().casefold()
    if trajectory.termination.truncated is True and reason in _BUDGET_REASONS:
        evidence.append(
            _signal(
                "explicit_budget_or_limit_truncation",
                {
                    FailureCategory.BUDGET_TERMINATION_FAILURE: 0.70,
                    FailureCategory.UNKNOWN: 0.30,
                },
                (
                    "The structured truncation plus a recognized limit reason supports a "
                    "budget/termination diagnosis without proving the upstream cause."
                ),
            )
        )

    probabilities = _average_signal_probabilities(evidence)
    ranked = sorted(
        (
            (probability, FailureCategory(category))
            for category, probability in probabilities.items()
            if category != FailureCategory.UNKNOWN.value
        ),
        reverse=True,
        key=lambda item: item[0],
    )
    top_probability, top_category = ranked[0]
    primary = (
        top_category
        if top_probability >= _PRIMARY_THRESHOLD
        else FailureCategory.UNKNOWN
    )
    return FailureAttribution(
        trajectory_id=trajectory.trajectory_id,
        primary_category=primary,
        category_probabilities=probabilities,
        evidence=tuple(evidence),
        ambiguous=True,
        qualified=True,
    )


def _identity_payload(trajectory: TrajectoryV2) -> dict[str, object]:
    return {
        "world": trajectory.world.model_dump(mode="json"),
        "task": trajectory.task.model_dump(mode="json"),
        "model": trajectory.model.model_dump(mode="json"),
        "agent": trajectory.agent.model_dump(mode="json"),
        "harness": trajectory.harness.model_dump(mode="json"),
        "runtime": trajectory.runtime.model_dump(mode="json"),
        "verifier": trajectory.verifier.model_dump(mode="json"),
        "reset": trajectory.reset.model_dump(mode="json"),
        "initial_state": trajectory.initial_state.model_dump(mode="json"),
    }


def _control_key(trajectory: TrajectoryV2, *, exclude: str) -> str:
    payload = _identity_payload(trajectory)
    payload.pop(exclude)
    return canonical_hash(payload)


def _harness_label(trajectory: TrajectoryV2) -> str:
    harness_id = trajectory.harness.harness_id or "unspecified"
    version = trajectory.harness.version or "unspecified"
    return f"{harness_id}@{version}"


def _model_label(trajectory: TrajectoryV2) -> str:
    provider = trajectory.model.provider or "unspecified"
    model_id = trajectory.model.model_id or "unspecified"
    snapshot = trajectory.model.snapshot or "unspecified"
    return f"{provider}:{model_id}@{snapshot}"


def _comparison_view(
    values: Iterable[DiagnosticInput],
    *,
    kind: ComparisonKind,
) -> ComparisonView:
    trajectories = sorted(
        (_trajectory(value) for value in values),
        key=lambda item: item.trajectory_id,
    )
    exclude = (
        "harness"
        if kind == ComparisonKind.SAME_MODEL_DIFFERENT_HARNESS
        else "model"
    )
    groups: dict[str, list[TrajectoryV2]] = defaultdict(list)
    for trajectory in trajectories:
        groups[_control_key(trajectory, exclude=exclude)].append(trajectory)

    rows: list[ControlledRunComparison] = []
    for control_key, group in sorted(groups.items()):
        for left, right in combinations(group, 2):
            if kind == ComparisonKind.SAME_MODEL_DIFFERENT_HARNESS:
                left_variant = _harness_label(left)
                right_variant = _harness_label(right)
                qualification = (
                    "Controlled association with harness identity/version; the comparison does "
                    "not by itself establish harness causality."
                )
            else:
                left_variant = _model_label(left)
                right_variant = _model_label(right)
                qualification = (
                    "Controlled association with model identity/snapshot; the comparison does "
                    "not by itself establish model causality."
                )
            if left_variant == right_variant:
                continue
            payload = {
                "kind": kind.value,
                "control_key": control_key,
                "left": left.trajectory_id,
                "right": right.trajectory_id,
            }
            rows.append(
                ControlledRunComparison(
                    comparison_id=f"DIAG-CMP-{canonical_hash(payload)[:24].upper()}",
                    kind=kind,
                    control_key=control_key,
                    left_trajectory_id=left.trajectory_id,
                    right_trajectory_id=right.trajectory_id,
                    left_variant=left_variant,
                    right_variant=right_variant,
                    left_reward=left.original_evaluation.reward,
                    right_reward=right.original_evaluation.reward,
                    reward_delta=(
                        right.original_evaluation.reward - left.original_evaluation.reward
                    ),
                    left_failure=left.failure.category,
                    right_failure=right.failure.category,
                    qualification=qualification,
                )
            )
    return ComparisonView(kind=kind, rows=tuple(rows))


def compare_same_model_different_harness(
    values: Iterable[DiagnosticInput],
) -> ComparisonView:
    return _comparison_view(
        values,
        kind=ComparisonKind.SAME_MODEL_DIFFERENT_HARNESS,
    )


def compare_same_harness_different_model(
    values: Iterable[DiagnosticInput],
) -> ComparisonView:
    return _comparison_view(
        values,
        kind=ComparisonKind.SAME_HARNESS_DIFFERENT_MODEL,
    )


def compare_same_trajectory_verifier_versions(
    trajectory: TrajectoryV2,
    records: Iterable[ReverificationRecord] = (),
) -> tuple[VerifierVersionComparison, ...]:
    combined: dict[str, ReverificationRecord] = {
        record.record_id: record for record in trajectory.reverifications
    }
    for record in records:
        if record.input_trajectory_id != trajectory.trajectory_id:
            raise ValueError("reverification record references a different trajectory")
        combined.setdefault(record.record_id, record)

    evaluations: list[dict[str, object]] = [
        {
            "id": "original",
            "source": "original",
            "verifier_id": trajectory.original_evaluation.verifier.verifier_id,
            "version": trajectory.original_evaluation.verifier.version,
            "reward": trajectory.original_evaluation.reward,
            "components": trajectory.original_evaluation.component_scores,
        }
    ]
    for record in sorted(combined.values(), key=lambda item: item.record_id):
        evaluations.append(
            {
                "id": record.record_id,
                "source": "reverification",
                "verifier_id": record.verifier.verifier_id,
                "version": record.verifier.version,
                "reward": record.reward,
                "components": record.component_scores,
            }
        )

    rows: list[VerifierVersionComparison] = []
    for left, right in combinations(evaluations, 2):
        verifier_id = left["verifier_id"]
        if not verifier_id or verifier_id != right["verifier_id"]:
            continue
        left_version = str(left["version"] or "unspecified")
        right_version = str(right["version"] or "unspecified")
        if left_version == right_version:
            continue
        left_components = dict(left["components"])
        right_components = dict(right["components"])
        common_components = sorted(set(left_components) & set(right_components))
        component_deltas = {
            name: float(right_components[name]) - float(left_components[name])
            for name in common_components
        }
        payload = {
            "trajectory_id": trajectory.trajectory_id,
            "left": left["id"],
            "right": right["id"],
        }
        rows.append(
            VerifierVersionComparison(
                comparison_id=f"DIAG-VERIFY-{canonical_hash(payload)[:24].upper()}",
                trajectory_id=trajectory.trajectory_id,
                verifier_id=str(verifier_id),
                baseline_version=left_version,
                candidate_version=right_version,
                baseline_source=str(left["source"]),
                candidate_source=str(right["source"]),
                baseline_reward=float(left["reward"]),
                candidate_reward=float(right["reward"]),
                reward_delta=float(right["reward"]) - float(left["reward"]),
                component_deltas=component_deltas,
                qualification=(
                    "Score sensitivity under a verifier-version change. This does not establish "
                    "verifier failure or invalidate either evaluation."
                ),
            )
        )
    return tuple(rows)


def failure_category_distribution(
    attributions: Iterable[FailureAttribution],
) -> FailureCategoryDistribution:
    values = tuple(attributions)
    expected_counts = _taxonomy_zeros()
    primary_counts = _taxonomy_int_zeros()
    ambiguous_count = 0
    for attribution in values:
        for category, probability in attribution.category_probabilities.items():
            expected_counts[category] += probability
        primary_counts[attribution.primary_category.value] += 1
        ambiguous_count += int(attribution.ambiguous)
    count = len(values)
    expected_rates = {
        category: (value / count if count else 0.0)
        for category, value in expected_counts.items()
    }
    return FailureCategoryDistribution(
        trajectory_count=count,
        expected_counts=expected_counts,
        expected_rates=expected_rates,
        primary_counts=primary_counts,
        ambiguous_count=ambiguous_count,
    )


def capability_conditioned_failure_profiles(
    values: Iterable[DiagnosticInput],
) -> tuple[CapabilityFailureProfile, ...]:
    grouped: dict[str, list[FailureAttribution]] = defaultdict(list)
    for value in values:
        trajectory = _trajectory(value)
        attribution = diagnose_failure(value)
        tags = trajectory.capability_tags or (_UNTAGGED_CAPABILITY,)
        for tag in tags:
            grouped[tag].append(attribution)
    return tuple(
        CapabilityFailureProfile(
            capability_tag=tag,
            distribution=failure_category_distribution(grouped[tag]),
        )
        for tag in sorted(grouped)
    )


def build_trajectory_diagnostics(
    values: Iterable[DiagnosticInput],
    *,
    reverifications: Iterable[ReverificationRecord] = (),
) -> TrajectoryDiagnosticsReport:
    inputs = tuple(values)
    trajectories = tuple(_trajectory(value) for value in inputs)
    trajectory_ids = [trajectory.trajectory_id for trajectory in trajectories]
    if len(trajectory_ids) != len(set(trajectory_ids)):
        raise ValueError("trajectory diagnostics require unique trajectory ids")

    by_id = {trajectory.trajectory_id: trajectory for trajectory in trajectories}
    external_records: dict[str, list[ReverificationRecord]] = defaultdict(list)
    consumed_record_ids: set[str] = set()
    for record in reverifications:
        if record.input_trajectory_id not in by_id:
            raise ValueError("reverification record has no matching diagnostic trajectory")
        external_records[record.input_trajectory_id].append(record)
        consumed_record_ids.add(record.record_id)

    attributions = tuple(diagnose_failure(value) for value in inputs)
    verifier_rows = tuple(
        row
        for trajectory in trajectories
        for row in compare_same_trajectory_verifier_versions(
            trajectory,
            external_records.get(trajectory.trajectory_id, ()),
        )
    )
    return TrajectoryDiagnosticsReport(
        attributions=attributions,
        same_model_different_harness=compare_same_model_different_harness(inputs),
        same_harness_different_model=compare_same_harness_different_model(inputs),
        verifier_version_comparisons=verifier_rows,
        failure_distribution=failure_category_distribution(attributions),
        capability_failure_profiles=capability_conditioned_failure_profiles(inputs),
        consumed_reverification_record_ids=tuple(sorted(consumed_record_ids)),
    )


__all__ = [
    "build_trajectory_diagnostics",
    "capability_conditioned_failure_profiles",
    "compare_same_harness_different_model",
    "compare_same_model_different_harness",
    "compare_same_trajectory_verifier_versions",
    "diagnose_failure",
    "failure_category_distribution",
]
