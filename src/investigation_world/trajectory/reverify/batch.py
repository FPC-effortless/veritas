from __future__ import annotations

from collections.abc import Iterable

from investigation_world.trajectory.models import (
    ReverificationRecord,
    TrajectoryV2,
    VerifierIdentity,
)
from investigation_world.trajectory.reverify.engine import reverify_trajectory
from investigation_world.trajectory.reverify.models import (
    BatchReverificationEntry,
    BatchReverificationReport,
    BatchReverificationResult,
    ComparisonStatus,
    EvaluationSnapshot,
    EvaluationSource,
    ReverificationComparison,
    VerifierReasonAttribution,
)
from investigation_world.trajectory.reverify.operational import AuthorizedVerifierRegistry

_ATTRIBUTION_FIELDS = (
    "invariant_violations",
    "missing_required_actions",
    "forbidden_actions_taken",
    "missing_evidence_ids",
    "process_violations",
)


def _original_snapshot(trajectory: TrajectoryV2) -> EvaluationSnapshot:
    evaluation = trajectory.original_evaluation
    return EvaluationSnapshot(
        input_trajectory_id=trajectory.trajectory_id,
        source=EvaluationSource.ORIGINAL,
        verifier=evaluation.verifier,
        component_scores=evaluation.component_scores,
        reward=evaluation.reward,
    )


def _record_snapshot(record: ReverificationRecord) -> EvaluationSnapshot:
    return EvaluationSnapshot(
        input_trajectory_id=record.input_trajectory_id,
        source=EvaluationSource.REVERIFICATION,
        source_record_id=record.record_id,
        verifier=record.verifier,
        component_scores=record.component_scores,
        reward=record.reward,
    )


def _snapshot_for_verifier(
    trajectory: TrajectoryV2,
    verifier: VerifierIdentity,
    *,
    record_id: str | None,
    prefer_original: bool,
) -> tuple[EvaluationSnapshot | None, str | None]:
    if record_id is not None:
        matches = [item for item in trajectory.reverifications if item.record_id == record_id]
        if not matches:
            return None, "EVALUATION_RECORD_NOT_AVAILABLE"
        record = matches[0]
        if record.verifier != verifier:
            return None, "EVALUATION_RECORD_VERIFIER_MISMATCH"
        return _record_snapshot(record), None

    original_matches = trajectory.original_evaluation.verifier == verifier
    records = [item for item in trajectory.reverifications if item.verifier == verifier]
    if prefer_original and original_matches:
        return _original_snapshot(trajectory), None
    if len(records) > 1:
        return None, "EVALUATION_VERSION_AMBIGUOUS"
    if records:
        return _record_snapshot(records[0]), None
    if original_matches:
        return _original_snapshot(trajectory), None
    return None, "EVALUATION_NOT_AVAILABLE"


def _reason_attribution(record: ReverificationRecord | None) -> VerifierReasonAttribution | None:
    if record is None:
        return None
    raw = record.private_metadata.get("verification_breakdown")
    if not isinstance(raw, dict):
        return None
    extracted: dict[str, tuple[str, ...]] = {}
    for field in _ATTRIBUTION_FIELDS:
        value = raw.get(field)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            return None
        extracted[field] = tuple(value)
    evidence_provenance = tuple(
        item
        for item in record.provenance
        if item.source_kind == "trajectory.reverification_evidence"
    )
    return VerifierReasonAttribution(
        source_record_id=record.record_id,
        evidence_provenance=evidence_provenance,
        **extracted,
    )


def compare_reverification_versions(
    trajectory: TrajectoryV2,
    *,
    baseline_verifier: VerifierIdentity,
    candidate_verifier: VerifierIdentity,
    baseline_record_id: str | None = None,
    candidate_record_id: str | None = None,
) -> ReverificationComparison:
    """Compare two exact verifier identities without inventing absent component scores."""
    trajectory = TrajectoryV2.model_validate(trajectory.model_dump(mode="python"))
    baseline, baseline_error = _snapshot_for_verifier(
        trajectory,
        baseline_verifier,
        record_id=baseline_record_id,
        prefer_original=baseline_record_id is None,
    )
    candidate, candidate_error = _snapshot_for_verifier(
        trajectory,
        candidate_verifier,
        record_id=candidate_record_id,
        prefer_original=False,
    )
    if baseline is None or candidate is None:
        ambiguous = baseline_error == "EVALUATION_VERSION_AMBIGUOUS" or (
            candidate_error == "EVALUATION_VERSION_AMBIGUOUS"
        )
        if baseline is None:
            reason = f"BASELINE_{baseline_error}"
        else:
            reason = f"CANDIDATE_{candidate_error}"
        return ReverificationComparison(
            input_trajectory_id=trajectory.trajectory_id,
            status=ComparisonStatus.UNKNOWN if ambiguous else ComparisonStatus.NOT_AVAILABLE,
            baseline_verifier=baseline_verifier,
            candidate_verifier=candidate_verifier,
            baseline=baseline,
            candidate=candidate,
            reason_code=reason,
        )

    component_names = sorted(
        set(baseline.component_scores) | set(candidate.component_scores)
    )
    known = {
        name: candidate.component_scores[name] - baseline.component_scores[name]
        for name in component_names
        if name in baseline.component_scores and name in candidate.component_scores
    }
    unknown = tuple(
        name
        for name in component_names
        if name not in baseline.component_scores or name not in candidate.component_scores
    )
    record = next(
        (
            item
            for item in trajectory.reverifications
            if item.record_id == candidate.source_record_id
        ),
        None,
    )
    return ReverificationComparison(
        input_trajectory_id=trajectory.trajectory_id,
        status=ComparisonStatus.COMPARED,
        baseline_verifier=baseline_verifier,
        candidate_verifier=candidate_verifier,
        baseline=baseline,
        candidate=candidate,
        reward_delta=candidate.reward - baseline.reward,
        component_deltas=known,
        unknown_components=unknown,
        attribution=_reason_attribution(record),
    )


def batch_reverify_trajectories(
    trajectories: Iterable[TrajectoryV2],
    *,
    verifier: VerifierIdentity,
    registry: AuthorizedVerifierRegistry,
    baseline_verifier: VerifierIdentity | None = None,
) -> BatchReverificationResult:
    """Reverify a deterministic batch using the same offline-only exact-binding engine."""
    canonical = tuple(
        TrajectoryV2.model_validate(item.model_dump(mode="python")) for item in trajectories
    )
    ids = [item.trajectory_id for item in canonical]
    if len(ids) != len(set(ids)):
        raise ValueError("batch contains duplicate trajectory identity")

    entries: list[BatchReverificationEntry] = []
    updated_trajectories: list[TrajectoryV2] = []
    for trajectory in sorted(canonical, key=lambda item: item.trajectory_id):
        outcome = reverify_trajectory(trajectory, verifier=verifier, registry=registry)
        updated = outcome.trajectory_with_reverification or trajectory
        effective_baseline = baseline_verifier or trajectory.verifier
        if outcome.record is None:
            baseline, baseline_error = _snapshot_for_verifier(
                updated,
                effective_baseline,
                record_id=None,
                prefer_original=baseline_verifier is None,
            )
            comparison = ReverificationComparison(
                input_trajectory_id=trajectory.trajectory_id,
                status=(
                    ComparisonStatus.UNKNOWN
                    if baseline_error == "EVALUATION_VERSION_AMBIGUOUS"
                    else ComparisonStatus.NOT_AVAILABLE
                ),
                baseline_verifier=effective_baseline,
                candidate_verifier=verifier,
                baseline=baseline,
                reason_code="CANDIDATE_REVERIFICATION_NOT_AVAILABLE",
            )
        else:
            comparison = compare_reverification_versions(
                updated,
                baseline_verifier=effective_baseline,
                candidate_verifier=verifier,
                candidate_record_id=outcome.record.record_id,
            )
        entries.append(
            BatchReverificationEntry(
                input_trajectory_id=trajectory.trajectory_id,
                trajectory_visibility=trajectory.visibility,
                original_verifier=trajectory.verifier,
                requested_verifier=verifier,
                status=outcome.status,
                reason_code=outcome.reason_code,
                record_id=(outcome.record.record_id if outcome.record is not None else None),
                comparison=comparison,
            )
        )
        updated_trajectories.append(updated)

    report = BatchReverificationReport(
        requested_verifier=verifier,
        baseline_mode="exact_verifier" if baseline_verifier is not None else "original",
        baseline_verifier=baseline_verifier,
        entries=tuple(entries),
    )
    return BatchReverificationResult(
        report=report,
        trajectories=tuple(updated_trajectories),
    )
