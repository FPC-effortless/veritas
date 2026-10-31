from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, Field

from investigation_world.experience.models import (
    CanonicalModel,
    CapabilityGap,
    ExperienceDiagnostics,
    ExperienceReference,
    FailureFamily,
    FailureMechanism,
    MachineExperience,
)
from investigation_world.observatory.trajectory_diagnostics.engine import diagnose_failure
from investigation_world.observatory.trajectory_diagnostics.models import FailureAttribution
from investigation_world.trajectory import (
    StateDigest,
    StateDigestScope,
    VisibilityClass,
    canonical_hash,
)
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    AuthorizedVerifierRegistry,
    OperationalReplayEvidence,
    ReverificationStatus,
    reverify_trajectory,
)


class DiagnosticObservation(CanonicalModel):
    code: str
    value: float
    status: Literal["OBSERVED"] = "OBSERVED"
    mechanism_candidate: FailureMechanism = FailureMechanism.UNKNOWN
    mechanism_status: Literal["HYPOTHESIZED"] = "HYPOTHESIZED"
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    visibility: VisibilityClass = VisibilityClass.INTERNAL


class DiagnosticReport(CanonicalModel):
    experience_id: str
    source_digest: str
    origin: FailureAttribution
    diagnostics: ExperienceDiagnostics
    observations: tuple[DiagnosticObservation, ...]
    metrics: dict[str, float | None]
    unavailable: dict[str, str]
    capability_gaps: tuple[CapabilityGap, ...] = ()
    visibility: VisibilityClass = VisibilityClass.INTERNAL


class FailureFamilyCandidate(CanonicalModel):
    family: FailureFamily
    status: Literal["HYPOTHESIZED"] = "HYPOTHESIZED"
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    grouping_code: str
    visibility: VisibilityClass = VisibilityClass.INTERNAL


_GOLD_COMPONENTS = {
    "evidence_coverage": FailureMechanism.OBSERVATION,
    "hypothesis_structure": FailureMechanism.EVIDENCE_WEIGHTING,
    "canonical_target_fidelity": FailureMechanism.VERIFICATION,
    "calibration_integrity": FailureMechanism.EVIDENCE_WEIGHTING,
    "rights_temporal_integrity": FailureMechanism.TEMPORAL_REASONING,
}
_REASON_FIELDS = {
    "invariant_violations": FailureMechanism.UNKNOWN,
    "missing_required_actions": FailureMechanism.PROCESS,
    "forbidden_actions_taken": FailureMechanism.PERMISSION_AUTHORITY,
    "missing_evidence_ids": FailureMechanism.OBSERVATION,
    "process_violations": FailureMechanism.PROCESS,
}


def _canonical(value: MachineExperience) -> MachineExperience:
    result = MachineExperience.model_validate(value.model_dump(mode="python"))
    scores = result.trajectory.original_evaluation
    if not all(math.isfinite(x) for x in (scores.reward, *scores.component_scores.values())):
        raise ValueError("diagnostic scores must be finite")
    return result


_VISIBILITY = list(VisibilityClass)


def _source_visibility(value: Any) -> VisibilityClass:
    """Conservative derived classification, including private buckets and nested sources."""
    levels = [VisibilityClass.INTERNAL]
    if isinstance(value, BaseModel):
        levels.append(getattr(value, "visibility", VisibilityClass.PUBLIC))
        for name in type(value).model_fields:
            child = getattr(value, name)
            if name in {"private_payload", "private_metadata"} and child:
                levels.append(VisibilityClass.EVALUATOR_PRIVATE)
            else:
                levels.append(_source_visibility(child))
    elif isinstance(value, dict):
        levels.extend(_source_visibility(child) for child in value.values())
    elif isinstance(value, (list, tuple)):
        levels.extend(_source_visibility(child) for child in value)
    return max(levels, key=_VISIBILITY.index)


def _reference(
    experience: MachineExperience, kind: str, payload: Any, **metadata: Any
) -> ExperienceReference:
    digest = canonical_hash({"experience_id": experience.experience_id, "evidence": payload})
    return ExperienceReference(
        reference_id=f"DIAGNOSTIC-EVIDENCE-{digest}",
        reference_type=kind,
        digest=digest,
        visibility=_source_visibility(experience),
        public_metadata={"experience_id": experience.experience_id, **metadata},
    )


def _metrics(experience: MachineExperience) -> dict[str, float | None]:
    """Recorded protocol quality/acquisition metrics, never truth or information utility."""
    events = [event for event in experience.trajectory.events if event.evidence_references]
    references = {ref.reference_id for event in events for ref in event.evidence_references}
    mentions = sum(len(event.evidence_references) for event in events)
    metrics: dict[str, float | None] = {
        "distinct_evidence_reference_count": float(len(references)),
        "evidence_cost_per_distinct_reference": None,
        "duplicate_evidence_reference_fraction": 1 - len(references) / mentions
        if mentions
        else None,
        "belief_revision_snapshot_coverage": None,
        "belief_revision_consistency": None,
        "belief_revision_temporal_support": None,
        "reported_contradiction_count_reduction": None,
    }
    if events and references and all(event.cost is not None for event in events):
        costs = [event.cost for event in events if event.cost is not None]
        if not all(math.isfinite(cost) for cost in costs):
            raise ValueError("diagnostic costs must be finite")
        metrics["evidence_cost_per_distinct_reference"] = sum(costs) / len(references)
    revisions = experience.belief_revisions
    if not revisions:
        return metrics
    checked = consistent = supported = 0
    contradiction_reduction = 0
    for revision in revisions:
        states = [
            (snapshot.step, hypothesis)
            for snapshot in experience.epistemic_snapshots
            for hypothesis in snapshot.hypotheses
            if hypothesis.hypothesis_id == revision.hypothesis_id
        ]
        before = [state for state in states if state[0] < revision.step]
        after = [state for state in states if state[0] == revision.step]
        last = max((step for step, _ in before), default=-1)
        prior = [hypothesis for step, hypothesis in before if step == last]
        if (
            len(prior) != 1
            or len(after) != 1
            or revision.prior_confidence is None
            or revision.revised_confidence is None
        ):
            continue
        checked += 1
        consistent += int(
            prior[0].confidence == revision.prior_confidence
            and after[0][1].confidence == revision.revised_confidence
        )
        available = {
            ref.reference_id
            for event in events
            if event.step <= revision.step
            for ref in event.evidence_references
        }
        supported += int(
            bool(revision.evidence_reference_ids)
            and set(revision.evidence_reference_ids).issubset(available)
        )
        contradiction_reduction += len(set(prior[0].contradictions)) - len(
            set(after[0][1].contradictions)
        )
    metrics["belief_revision_snapshot_coverage"] = checked / len(revisions)
    if checked == len(revisions):
        metrics["belief_revision_consistency"] = consistent / checked
        metrics["belief_revision_temporal_support"] = supported / checked
        metrics["reported_contradiction_count_reduction"] = float(contradiction_reduction)
    return metrics


def diagnose_experience(
    value: MachineExperience,
    *,
    registry: AuthorizedVerifierRegistry | None = None,
    reference: MachineExperience | None = None,
) -> DiagnosticReport:
    """Describe recorded symptoms; optionally execute existing authorized reverification.

    Mechanism candidates are hypotheses, never root-cause or capability assertions.
    No canonical input, readiness, original evaluation or trajectory is changed.
    """
    experience = _canonical(value)
    trajectory = experience.trajectory
    observations: list[DiagnosticObservation] = []
    recoveries: tuple[ExperienceReference, ...] = ()
    unavailable = {
        "first_causal_divergence": "Qualified policy / bound intervention evidence unavailable.",
        "recovery": "No bound executable recovery sequence evidence.",
        "causal_candidates": "Retained state deltas and score comparisons are not interventions.",
        "capability_gaps": "Symptoms do not establish capability or prerequisite claims.",
    }
    evaluation = trajectory.original_evaluation
    if (
        trajectory.verifier.verifier_id == "veritas.gold10.evidence-discipline"
        and trajectory.verifier.version == "0.3.0"
    ):
        components = evaluation.component_scores
        if set(components) != set(_GOLD_COMPONENTS) or any(
            not 0 <= x <= 1 for x in components.values()
        ):
            unavailable["gold10_components"] = (
                "Missing or invalid supported verifier component set."
            )
        else:
            for key, mechanism in _GOLD_COMPONENTS.items():
                if components[key] < 1:
                    observations.append(
                        DiagnosticObservation(
                            code=f"gold10.{key}",
                            value=components[key],
                            mechanism_candidate=mechanism,
                            evidence_references=(
                                _reference(
                                    experience,
                                    "recorded_verifier_component",
                                    evaluation,
                                    component=key,
                                    verifier=trajectory.verifier.model_dump(mode="json"),
                                    qualification=(
                                        "Recorded pilot symptom, not independent verification."
                                    ),
                                ),
                            ),
                        )
                    )
    if registry is not None:
        # Re-run rather than accepting caller-produced PASS/records as execution authority.
        fresh_input = trajectory.model_dump(mode="python")
        fresh_input["reverifications"] = ()
        from investigation_world.trajectory import TrajectoryV2

        outcome = reverify_trajectory(
            TrajectoryV2.model_validate(fresh_input),
            verifier=trajectory.verifier,
            registry=registry,
        )
        record = outcome.record
        if (
            outcome.status
            not in {ReverificationStatus.REVERIFIED, ReverificationStatus.ALREADY_RECORDED}
            or record is None
        ):
            unavailable["reverification"] = outcome.reason_code or outcome.status.value
        else:
            raw = record.private_metadata.get("verification_breakdown")
            if not isinstance(raw, dict) or any(
                not isinstance(raw.get(key), list) or any(not isinstance(x, str) for x in raw[key])
                for key in _REASON_FIELDS
            ):
                unavailable["verifier_reasons"] = "Explicit complete verifier reasons unavailable."
            else:
                recoveries = _native_recoveries(experience, raw, record.record_id)
                if recoveries:
                    unavailable.pop("recovery")
                for key, mechanism in _REASON_FIELDS.items():
                    if raw[key]:
                        ref = _reference(
                            experience,
                            "authorized_reverification_reason",
                            record,
                            record_id=record.record_id,
                            reason_field=key,
                        )
                        ref = ref.model_copy(
                            update={
                                "visibility": _source_visibility((experience, record)),
                                "private_metadata": {"reasons": raw[key]},
                            }
                        )
                        observations.append(
                            DiagnosticObservation(
                                code=f"verifier.{key}",
                                value=float(len(raw[key])),
                                mechanism_candidate=mechanism,
                                evidence_references=(ref,),
                                visibility=VisibilityClass.EVALUATOR_PRIVATE,
                            )
                        )
    return DiagnosticReport(
        experience_id=experience.experience_id,
        source_digest=canonical_hash(experience),
        visibility=_source_visibility((experience, reference)),
        origin=diagnose_failure(trajectory),
        diagnostics=ExperienceDiagnostics(
            failure_mechanisms=(FailureMechanism.UNKNOWN,),
            visibility=_source_visibility((experience, reference)),
            recovery_point_references=recoveries,
            successful_recovery_references=recoveries,
            first_divergence_reference=(
                reference_action_divergence(experience, reference)
                if reference is not None
                else None
            ),
        ),
        observations=tuple(
            sorted(
                (
                    item.model_copy(update={"visibility": _source_visibility((experience, item))})
                    for item in observations
                ),
                key=lambda x: x.code,
            )
        ),
        metrics=_metrics(experience),
        unavailable=unavailable,
    )


def _native_recoveries(
    experience: MachineExperience,
    breakdown: dict[str, Any],
    record_id: str,
) -> tuple[ExperienceReference, ...]:
    """Called only after fresh authorized receipt binding and retained-artifact verification."""
    trajectory = experience.trajectory
    if (
        trajectory.termination.terminated is not True
        or trajectory.termination.truncated is not False
        or breakdown.get("outcome") != 1
        or any(breakdown[key] for key in _REASON_FIELDS)
        or not isinstance(breakdown.get("target_assertions_total"), int)
        or breakdown["target_assertions_total"] <= 0
        or breakdown.get("target_assertions_met") != breakdown["target_assertions_total"]
    ):
        return ()
    evidence = OperationalReplayEvidence.model_validate(
        trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    )
    receipt = evidence.native_submission
    if receipt is None or not evidence.portable_contract.private.semantic_state.invariants:
        return ()
    if [event.step for event in trajectory.events] != list(range(len(trajectory.events))):
        return ()
    results = []
    actions = evidence.action_events
    for index, blocked in enumerate(actions):
        if not blocked.blocked or blocked.effect_applied:
            continue
        for retry in actions[index + 1 :]:
            if (
                retry.action_name != blocked.action_name
                or retry.parameters != blocked.parameters
                or retry.blocked
                or not retry.effect_applied
            ):
                continue
            start, end = blocked.sequence - 1, retry.sequence - 1
            ref = _reference(
                experience,
                "observed_native_blocked_to_successful_retry",
                {
                    "receipt_digest": receipt.receipt_digest,
                    "record_id": record_id,
                    "events": trajectory.events[start : end + 1],
                },
                status="OBSERVED",
                causal_status="UNKNOWN",
                start_step=start,
                end_step=end,
                record_id=record_id,
                receipt_id=receipt.receipt_id,
                qualification=(
                    "Recorded retry and valid terminal outcome; not causal proof, "
                    "general recoverability or independent execution attestation."
                ),
            )
            results.append(ref)
            break
    return tuple(results)


def reference_action_divergence(
    value: MachineExperience,
    reference: MachineExperience,
) -> ExperienceReference | None:
    """First *descriptive* action difference under a shared recorded state/control context.

    This neither qualifies the reference policy nor calls a valid alternative a failure.
    Missing runtime identity or pre-action state evidence is unsupported, not a match.
    """
    left, right = _canonical(value), _canonical(reference)
    a, b = left.trajectory, right.trajectory
    if not (
        a.runtime.runtime_id
        and a.runtime.version
        and a.verifier.verifier_id
        and a.verifier.version
        and a.initial_state.digest
        and a.world.environment_id
        and a.world.environment_version
        and a.world.world_id
        and a.world.world_version
    ):
        return None
    if any(
        getattr(a, field) != getattr(b, field)
        for field in ("world", "task", "runtime", "verifier", "reset", "initial_state")
    ):
        return None
    actions_a = [event for event in a.events if event.payload.get("method") == "act"]
    actions_b = [event for event in b.events if event.payload.get("method") == "act"]
    if not actions_a or not actions_b:
        return None
    for trajectory, actions in ((a, actions_a), (b, actions_b)):
        previous = trajectory.initial_state
        for event in actions:
            if event.state_before != previous or event.state_after is None:
                return None
            previous = event.state_after
    for first, second in zip(actions_a, actions_b, strict=False):
        if first.step != second.step or first.state_before is None or second.state_before is None:
            return None
        if first.state_before != second.state_before:
            return None

        def action(event: Any) -> tuple[Any, Any] | None:
            args, kwargs = event.payload.get("args"), event.payload.get("kwargs")
            if not isinstance(args, list) or len(args) != 1 or not isinstance(args[0], str):
                return None
            if not isinstance(kwargs, dict):
                return None
            return args, kwargs

        l_action, r_action = action(first), action(second)
        if l_action is None or r_action is None:
            return None
        if l_action != r_action:
            return _reference(
                left,
                "observed_reference_action_difference",
                {"left": first, "right": second, "reference": right.experience_id},
                reference_experience_id=right.experience_id,
                step=first.step,
                status="OBSERVED",
                causal_status="UNKNOWN",
                failure_claim=False,
                qualification="Descriptive reference difference; not policy error or causality.",
            ).model_copy(update={"visibility": _source_visibility((left, right))})
    return None


def failure_family_candidates(
    values: Iterable[MachineExperience],
) -> tuple[FailureFamilyCandidate, ...]:
    """Group repeated recorded symptoms, without promoting them to capability gaps."""
    sources: dict[str, DiagnosticReport] = {}
    for value in values:
        report = diagnose_experience(value)
        old = sources.get(report.experience_id)
        if old is not None and old != report:
            raise ValueError("conflicting diagnostics for the same source experience")
        sources[report.experience_id] = report
    groups: dict[str, list[tuple[str, DiagnosticObservation]]] = defaultdict(list)
    for source_id, report in sorted(sources.items()):
        for observation in report.observations:
            groups[observation.mechanism_candidate.value].append((source_id, observation))
    result = []
    for code, members in sorted(groups.items()):
        if len({source for source, _ in members}) < 2:
            continue
        result.append(
            FailureFamilyCandidate(
                family=FailureFamily(
                    member_experience_ids=tuple(source for source, _ in members),
                    affected_capability="unknown",
                    visibility=_source_visibility([sources[source] for source, _ in members]),
                    severity=max(1 - obs.value for _, obs in members),
                    mechanisms=tuple(obs.mechanism_candidate for _, obs in members),
                ),
                evidence_references=tuple(
                    ref for _, obs in members for ref in obs.evidence_references
                ),
                grouping_code=f"hypothesized_mechanism:{code}",
                visibility=_source_visibility([sources[source] for source, _ in members]),
            )
        )
    return tuple(result)


def _restricted(value: Any) -> bool:
    if isinstance(value, StateDigest) and value.scope is StateDigestScope.SEMANTIC:
        return True
    if isinstance(value, BaseModel):
        visibility = getattr(value, "visibility", VisibilityClass.PUBLIC)
        if visibility not in {VisibilityClass.PUBLIC, VisibilityClass.BUYER_SAFE}:
            return True
        return any(
            (
                bool(getattr(value, name))
                if name in {"private_payload", "private_metadata"}
                else _restricted(getattr(value, name))
            )
            for name in type(value).model_fields
        )
    if isinstance(value, dict):
        return any(
            (bool(child) if key in {"private_payload", "private_metadata"} else _restricted(child))
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_restricted(child) for child in value)
    return False


def buyer_safe_diagnostics(value: MachineExperience) -> dict[str, Any]:
    """Conservative allowlist: withhold all derived identities for mixed/private sources.

    ponytail: no field-level declassification; add it only with independently bound public evidence.
    """
    experience = _canonical(value)
    relevant = (
        experience.trajectory,
        experience.epistemic_snapshots,
        experience.belief_revisions,
        experience.private_metadata,
    )
    if (
        experience.visibility not in {VisibilityClass.PUBLIC, VisibilityClass.BUYER_SAFE}
        or experience.private_metadata
        or _restricted(relevant)
    ):
        return {"status": "UNKNOWN", "reason": "source_not_fully_buyer_safe"}
    report = diagnose_experience(experience)
    return {
        "status": "OBSERVED",
        "projection_id": canonical_hash(
            {
                "observations": [(x.code, x.value) for x in report.observations],
                "metrics": report.metrics,
            }
        ),
        "observations": [
            {
                "code": x.code,
                "value": x.value,
                "status": x.status,
                "mechanism_candidate": x.mechanism_candidate.value,
                "mechanism_status": x.mechanism_status,
            }
            for x in report.observations
        ],
        "metrics": report.metrics,
        "unavailable": report.unavailable,
    }
