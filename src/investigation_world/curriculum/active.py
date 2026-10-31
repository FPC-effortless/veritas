"""Measured TRAIN frontiers and conditional, held-out-validation stage decisions.

The controller checks supplied evidence, not whether a model actually executed.
Development validation may guide advancement; untouched final tests never do.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from itertools import islice
from typing import Literal, Self, cast

from pydantic import Field, model_validator

from investigation_world.capability_science import (
    AcquisitionCurve,
    EvaluationPoint,
    EvaluationPopulation,
    PrerequisiteGraph,
)
from investigation_world.capability_science.core import Digest, Text, validate_references
from investigation_world.experience import ExperienceReference
from investigation_world.experience.counterfactual import CounterfactualReceipt
from investigation_world.experience_foundry.admission import RecordedExperience
from investigation_world.experience_foundry.derivation import (
    LearningAssetCompilation,
    PrivateRecord,
    TransformPolicy,
    TransformRule,
    _contains_sealed,
    compile_learning_assets,
)
from investigation_world.experience_selection import (
    SelectionPolicy,
    SelectionReport,
    select_experiences,
)
from investigation_world.foundry.curriculum import TaskPerformance, frontier_priority
from investigation_world.trajectory import VisibilityClass, canonical_hash


class CurriculumPolicy(PrivateRecord):
    schema_version: Literal["veritas.active-curriculum-policy.v1"] = (
        "veritas.active-curriculum-policy.v1"
    )
    version: Literal["1"] = "1"
    mode: Literal["frontier", "random_control"] = "frontier"
    seed: int = Field(default=0, strict=True, ge=0, le=2**32 - 1)
    low: float = Field(default=0.10, ge=0, le=1)
    high: float = Field(default=0.70, ge=0, le=1)
    minimum_attempts: int = Field(default=3, strict=True, ge=1, le=256)
    max_items_per_stage: int = Field(default=8, strict=True, ge=1, le=256)
    minimum_validation_score: float = Field(default=0.8, ge=0, le=1)
    minimum_validation_delta: float = Field(default=0.05, ge=0, le=1)
    selection: SelectionPolicy = Field(default_factory=SelectionPolicy)
    prerequisite_basis: Literal["DECLARED_NONREFUTED_NOT_CAUSAL"] = "DECLARED_NONREFUTED_NOT_CAUSAL"

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.low >= self.high:
            raise ValueError("frontier success-rate band must be ordered")
        if self.selection.max_hard_negatives or self.selection.mode != "representative":
            raise ValueError("curriculum requires the same verified-success selection pool")
        return self


def _members(populations: Iterable[EvaluationPopulation]) -> tuple[set[str], set[str]]:
    refs = [member for panel in populations for member in panel.members]
    return {r.reference_id for r in refs}, {str(r.digest) for r in refs}


class FixedPanels(PrivateRecord):
    schema_version: Literal["veritas.curriculum-fixed-panels.v1"] = (
        "veritas.curriculum-fixed-panels.v1"
    )
    validation: tuple[EvaluationPopulation, ...] = Field(min_length=1, max_length=64)
    final_test: tuple[EvaluationPopulation, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def disjoint_panels(self) -> Self:
        for group in (self.validation, self.final_test):
            if any(p.split != "HELD_OUT" for p in group):
                raise ValueError("validation and final test must be HELD_OUT populations")
            if len({p.capability.record_id for p in group}) != len(group):
                raise ValueError("one fixed population per capability and panel role required")
        vi, vd = _members(self.validation)
        ti, td = _members(self.final_test)
        if vi & ti or vd & td:
            raise ValueError("validation/final-test overlap")
        return self


class FrontierObservation(PrivateRecord):
    schema_version: Literal["veritas.curriculum-frontier-observation.v1"] = (
        "veritas.curriculum-frontier-observation.v1"
    )
    points: tuple[EvaluationPoint, ...] = Field(default=(), max_length=256)
    execution_attestation: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def training_only(self) -> Self:
        if any(p.population.split != "TRAIN" for p in self.points):
            raise ValueError("frontier observations must use TRAIN, never held-out outcomes")
        if any(p.population.conditions.metric != "success_fraction" for p in self.points):
            raise ValueError("frontier ranking requires binary success_fraction observations")
        keys = [(p.population.record_id, p.sequence_index) for p in self.points]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate frontier observation sequence")
        populations: dict[str, str] = {}
        for point in self.points:
            spec = point.population.capability.record_id
            previous = populations.setdefault(spec, point.population.record_id)
            if previous != point.population.record_id:
                raise ValueError("frontier capability population or measurement semantics changed")
        # Repeated copies of an outcome reference are not independent attempts.
        ids, digests = set(), set()
        for point in self.points:
            for row in point.outcomes:
                for ref in row.evidence_references:
                    if ref.reference_id in ids or ref.digest in digests:
                        raise ValueError("reused frontier outcome evidence")
                    ids.add(ref.reference_id)
                    digests.add(ref.digest)
        return self


class CurriculumCandidate(PrivateRecord):
    slot_id: Text
    experience_id: Text
    input_digest: Digest
    capability_spec_id: Text
    task: ExperienceReference
    asset_ids: tuple[Text, ...] = Field(min_length=1)
    training_qualified: Literal[False] = False

    @model_validator(mode="after")
    def task_commitment(self) -> Self:
        validate_references((self.task,))
        return self


ChoiceReason = Literal[
    "measured_frontier",
    "fallback_no_observation",
    "fallback_unknown_outcomes",
    "fallback_sparse_observation",
    "fallback_above_band",
    "fallback_below_band",
    "stage_budget",
    "duplicate_task",
]
StageDecision = Literal["HOLD", "ADVANCE_RECORDED_CRITERION"]


class TaskChoice(PrivateRecord):
    candidate_id: Text
    task_id: Text
    selected: bool
    reason: ChoiceReason
    attempts: int = Field(ge=0)
    success_rate: float | None = Field(default=None, ge=0, le=1)
    frontier_priority: float | None = Field(default=None, ge=0)


class CurriculumStage(PrivateRecord):
    index: int = Field(ge=0)
    policy_id: Text
    capability_spec_id: Text
    prerequisites: tuple[Text, ...]
    validation_population_id: Text
    choices: tuple[TaskChoice, ...]
    training_members: tuple[ExperienceReference, ...]


def _schedule(
    graph: PrerequisiteGraph,
    panels: FixedPanels,
    observation: FrontierObservation,
    policy: CurriculumPolicy,
    candidates: tuple[CurriculumCandidate, ...],
) -> tuple[CurriculumStage, ...]:
    parents: dict[str, set[str]] = {s.record_id: set() for s in graph.specs}
    for claim in graph.claims:
        if claim.status != "REFUTED":
            parents[claim.dependent].add(claim.prerequisite)
    order: list[str] = []
    while len(order) < len(parents):
        ready = sorted(
            k for k, values in parents.items() if k not in order and values <= set(order)
        )
        if not ready:
            raise ValueError("prerequisite stage cycle")
        order.append(ready[0])
    measurements: dict[tuple[str, str, str], list[float | None]] = defaultdict(list)
    for point in observation.points:
        for row in point.outcomes:
            measurements[
                (point.population.capability.record_id, row.member_id, row.member_digest)
            ].append(row.value)
    stages = []
    for index, spec_id in enumerate(order):
        ranked = []
        for candidate in candidates:
            if candidate.capability_spec_id != spec_id:
                continue
            values = measurements.get(
                (spec_id, candidate.task.reference_id, str(candidate.task.digest)), []
            )
            rate = (
                None
                if not values or None in values
                else sum(v for v in values if v is not None) / len(values)
            )
            priority = None
            if not values:
                reason = "fallback_no_observation"
            elif rate is None:
                reason = "fallback_unknown_outcomes"
            elif len(values) < policy.minimum_attempts:
                reason = "fallback_sparse_observation"
            else:
                reason = (
                    "measured_frontier"
                    if policy.low <= rate <= policy.high
                    else "fallback_above_band"
                    if rate > policy.high
                    else "fallback_below_band"
                )
                priority = frontier_priority(
                    TaskPerformance(
                        candidate.task.reference_id, len(values), sum(v == 1 for v in values), rate
                    ),
                    low=policy.low,
                    high=policy.high,
                    exploration_attempts=policy.minimum_attempts,
                )
            # Matched control uses precisely the same pool, caps and stage order.
            tie = canonical_hash({"seed": policy.seed, "candidate": candidate.record_id})
            rank = 0.0 if policy.mode == "random_control" else -(priority or 0.0)
            ranked.append((rank, tie, candidate, reason, len(values), rate, priority))
        ranked.sort(key=lambda row: (row[0], row[1], row[2].record_id))
        choices: list[TaskChoice] = []
        members: list[ExperienceReference] = []
        seen_ids, seen_digests = set(), set()
        for _, _, candidate, reason, attempts, rate, priority in ranked:
            selected = len(members) < policy.max_items_per_stage
            if candidate.task.reference_id in seen_ids or candidate.task.digest in seen_digests:
                selected, reason = False, "duplicate_task"
            elif not selected:
                reason = "stage_budget"
            if selected:
                members.append(candidate.task)
                seen_ids.add(candidate.task.reference_id)
                seen_digests.add(candidate.task.digest)
            choices.append(
                TaskChoice(
                    candidate_id=candidate.record_id,
                    task_id=candidate.task.reference_id,
                    selected=selected,
                    reason=cast(ChoiceReason, reason),
                    attempts=attempts,
                    success_rate=rate,
                    frontier_priority=priority,
                )
            )
        panel = next(p for p in panels.validation if p.capability.record_id == spec_id)
        stages.append(
            CurriculumStage(
                index=index,
                policy_id=policy.record_id,
                capability_spec_id=spec_id,
                prerequisites=tuple(sorted(parents[spec_id])),
                validation_population_id=panel.record_id,
                choices=tuple(choices),
                training_members=tuple(members),
            )
        )
    return tuple(stages)


class CurriculumPlan(PrivateRecord):
    schema_version: Literal["veritas.active-curriculum-plan.v1"] = (
        "veritas.active-curriculum-plan.v1"
    )
    graph: PrerequisiteGraph
    panels: FixedPanels
    observation: FrontierObservation
    policy: CurriculumPolicy
    model_id: Text
    model_revision: Text
    selection_id: Text
    compilation_id: Text
    selection_report: SelectionReport | None = None
    compilation: LearningAssetCompilation | None = None
    candidates: tuple[CurriculumCandidate, ...] = Field(max_length=256)
    stages: tuple[CurriculumStage, ...]
    qualification: Literal["UNKNOWN"] = "UNKNOWN"
    stage_order_basis: Literal["PRECOMMITTED_DECLARED_GRAPH_AND_TRAIN_OBSERVATIONS"] = (
        "PRECOMMITTED_DECLARED_GRAPH_AND_TRAIN_OBSERVATIONS"
    )

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if any(
            v.lower() in {"unknown", "latest", "main", "head", "unspecified"}
            for v in (self.model_id, self.model_revision)
        ):
            raise ValueError("explicit pinned learner identity/checkpoint required")
        if (self.selection_report is None) != (self.compilation is None):
            raise ValueError("retain both source-provider reports together")
        if self.selection_report is not None and self.compilation is not None:
            if (self.selection_id, self.compilation_id) != (
                self.selection_report.record_id,
                self.compilation.record_id,
            ):
                raise ValueError("provider report identity mismatch")
            selected_slots = {
                d.slot_id for d in self.selection_report.decisions if d.reason == "selected"
            }
            assets = {a.record_id for a in self.compilation.assets}
            if any(
                c.slot_id not in selected_slots or not set(c.asset_ids) <= assets
                for c in self.candidates
            ):
                raise ValueError("candidate missing selected source/derivative lineage")
        known = {s.record_id for s in self.graph.specs}
        if len(known) > 64:
            raise ValueError("curriculum capability bound exceeded")
        for group in (self.panels.validation, self.panels.final_test):
            if {p.capability.record_id for p in group} != known:
                raise ValueError("fixed panels must cover each graph capability exactly")
        if any(c.capability_spec_id not in known for c in self.candidates):
            raise ValueError("candidate capability not in curriculum graph")
        if len({c.slot_id for c in self.candidates}) != len(self.candidates):
            raise ValueError("duplicate curriculum candidate slot")
        ids, digests = _members((*self.panels.validation, *self.panels.final_test))
        for candidate in self.candidates:
            if candidate.task.reference_id in ids or candidate.task.digest in digests:
                raise ValueError("training candidate/fixed-panel overlap")
        for point in self.observation.points:
            if (point.model_id, point.model_revision) != (self.model_id, self.model_revision):
                raise ValueError("frontier observation learner checkpoint mismatch")
            if point.population.capability.record_id not in known:
                raise ValueError("frontier capability not in graph")
            pi, pd = _members((point.population,))
            if pi & ids or pd & digests:
                raise ValueError("frontier observation/fixed-panel overlap")
        if self.stages != _schedule(
            self.graph, self.panels, self.observation, self.policy, self.candidates
        ):
            raise ValueError("curriculum stages do not match precommitted scheduling inputs")
        return self


def _make_plan(**kwargs) -> CurriculumPlan:
    """Internal engine seam; does not establish source or execution authenticity."""
    kwargs["candidates"] = tuple(sorted(kwargs["candidates"], key=lambda c: c.record_id))
    kwargs["stages"] = _schedule(
        *(kwargs[k] for k in ("graph", "panels", "observation", "policy", "candidates"))
    )
    return CurriculumPlan(**kwargs)


def _bounded(values: Iterable, limit: int) -> tuple:
    result = tuple(islice(values, limit + 1))
    if len(result) > limit:
        raise ValueError("curriculum input bound exceeded")
    return result


def build_curriculum(
    sources: Iterable[RecordedExperience],
    *,
    graph: PrerequisiteGraph,
    panels: FixedPanels,
    observation: FrontierObservation,
    model_id: str,
    model_revision: str,
    policy: CurriculumPolicy,
    gap_sources: Iterable[tuple[CounterfactualReceipt, RecordedExperience]] = (),
) -> CurriculumPlan:
    """Freshly select actual TRAIN sources and preserve #160 candidate lineage."""
    graph, panels, observation, policy = (
        graph.checked(),
        panels.checked(),
        observation.checked(),
        policy.checked(),
    )
    # Normalize set-like provider inputs before deriving content identities.
    graph = PrerequisiteGraph(
        specs=tuple(sorted(graph.specs, key=lambda s: s.record_id)),
        claims=tuple(sorted(graph.claims, key=lambda c: c.record_id)),
        visibility=graph.visibility,
    )
    panels = FixedPanels(
        validation=tuple(sorted(panels.validation, key=lambda p: p.record_id)),
        final_test=tuple(sorted(panels.final_test, key=lambda p: p.record_id)),
    )
    observation = FrontierObservation(
        points=tuple(sorted(observation.points, key=lambda p: p.record_id))
    )
    _make_plan(
        graph=graph,
        panels=panels,
        observation=observation,
        policy=policy,
        model_id=model_id,
        model_revision=model_revision,
        selection_id="preflight",
        compilation_id="preflight",
        candidates=(),
    )  # Reject held-out observations and unknown model/panel bindings before source access.
    raw, gaps = _bounded(sources, 256), _bounded(gap_sources, 64)
    for source in (*raw, *(source for _, source in gaps)):
        if _contains_sealed(
            [
                source.experience.model_dump(mode="json"),
                source.companion.model_dump(mode="json"),
                source.capability.model_dump(mode="json"),
            ]
        ):
            raise ValueError("SEALED_INPUT_REQUIRES_STRICTER_BOUNDARY")
    if any(_contains_sealed(receipt.model_dump(mode="json")) for receipt, _ in gaps):
        raise ValueError("SEALED_INPUT_REQUIRES_STRICTER_BOUNDARY")
    ids, digests = _members((*panels.validation, *panels.final_test))
    selection_data = policy.selection.model_dump(exclude={"record_id"})
    selection_data.update(
        heldout_task_ids=tuple(sorted(ids | set(policy.selection.heldout_task_ids))),
        heldout_source_digests=tuple(
            sorted(digests | set(policy.selection.heldout_source_digests))
        ),
    )
    selection = select_experiences(raw, gap_sources=gaps, policy=SelectionPolicy(**selection_data))
    chosen = {d.experience_id for d in selection.decisions if d.reason == "selected"}
    selected_sources = tuple(s for s in raw if s.experience.experience_id in chosen)
    compilation = compile_learning_assets(
        selected_sources,
        policy=TransformPolicy(rules=(TransformRule(kind="next_state"),)),
        frozen_panel_task_ids=tuple(sorted(ids)),
        frozen_panel_source_digests=tuple(sorted(digests)),
    )
    spec_by_digest = {s.contract_digest: s.record_id for s in graph.specs}
    source_by_id = {s.experience.experience_id: s for s in selected_sources}
    candidates = []
    for decision in selection.decisions:
        if decision.reason != "selected":
            continue
        assets = tuple(
            a.record_id
            for a in compilation.assets
            if a.lineage.source.reference_id == decision.experience_id
        )
        if not assets:
            continue  # Provider-rejected derivatives never become curriculum candidates.
        if decision.capability_digest not in spec_by_digest:
            raise ValueError("selected source capability is outside curriculum graph")
        source = source_by_id[decision.experience_id]
        candidates.append(
            CurriculumCandidate(
                slot_id=decision.slot_id,
                experience_id=decision.experience_id,
                input_digest=decision.input_digest,
                capability_spec_id=spec_by_digest[decision.capability_digest],
                task=ExperienceReference(
                    reference_id=source.companion.task_id,
                    reference_type="TRAIN_source_fixture",
                    digest=decision.source_fixture_digest,
                    visibility=VisibilityClass.EVALUATOR_PRIVATE,
                ),
                asset_ids=assets,
            )
        )
    return _make_plan(
        graph=graph,
        panels=panels,
        observation=observation,
        policy=policy,
        model_id=model_id,
        model_revision=model_revision,
        selection_id=selection.record_id,
        compilation_id=compilation.record_id,
        candidates=tuple(candidates),
        selection_report=selection,
        compilation=compilation,
    )


def validate_curriculum(
    plan: CurriculumPlan, sources: Iterable[RecordedExperience], **expected
) -> CurriculumPlan:
    """Recompute against actual retained sources and externally pinned expected inputs."""
    checked = plan.checked()
    fresh = build_curriculum(sources, **expected)
    if checked != fresh:
        raise ValueError("curriculum differs from freshly validated expected inputs")
    return fresh


class StageEvent(PrivateRecord):
    sequence: int = Field(ge=0)
    previous_event_id: Text | None
    stage_id: Text
    acquisition: AcquisitionCurve | None
    prerequisite_evaluations: tuple[EvaluationPoint, ...]
    decision: StageDecision
    reason: Text
    execution_attestation: Literal["UNKNOWN"] = "UNKNOWN"
    qualification: Literal["UNKNOWN"] = "UNKNOWN"


class CurriculumHistory(PrivateRecord):
    schema_version: Literal["veritas.curriculum-stage-history.v1"] = (
        "veritas.curriculum-stage-history.v1"
    )
    plan_id: Text
    events: tuple[StageEvent, ...] = Field(default=(), max_length=1024)


class StageReadiness(PrivateRecord):
    plan_id: Text
    history_id: Text
    stage_id: Text | None
    status: Literal["READY_CONDITIONAL", "BLOCKED", "COMPLETE_RECORDED_CRITERIA"]
    reason: Text
    candidate_ids: tuple[Text, ...] = ()
    prerequisite_point_ids: tuple[Text, ...] = ()
    qualification: Literal["UNKNOWN"] = "UNKNOWN"


def _history_points(events: tuple[StageEvent, ...]) -> tuple[EvaluationPoint, ...]:
    return tuple(
        point
        for event in events
        for point in (
            *(event.acquisition.points if event.acquisition else ()),
            *event.prerequisite_evaluations,
        )
    )


def _validate_extension(
    points: tuple[EvaluationPoint, ...],
    events: tuple[StageEvent, ...],
) -> None:
    for point in points:
        if _contains_sealed(point.model_dump(mode="json")):
            raise ValueError("SEALED_INPUT_REQUIRES_STRICTER_BOUNDARY")
        for prior in _history_points(events):
            if prior.population.record_id != point.population.record_id:
                continue
            if point.sequence_index < prior.sequence_index:
                raise ValueError("stage evaluation sequence moved backwards")
            if point.sequence_index == prior.sequence_index and point.record_id != prior.record_id:
                raise ValueError("stage evaluation sequence rewrote earlier evidence")
            if point.sequence_index > prior.sequence_index and (
                point.observed_at is not None
                and prior.observed_at is not None
                and point.observed_at <= prior.observed_at
            ):
                raise ValueError("stage evaluation chronology moved backwards")


def stage_readiness(
    plan: CurriculumPlan,
    history: CurriculumHistory,
    *,
    prerequisite_evaluations: Iterable[EvaluationPoint] = (),
) -> StageReadiness:
    """Release only the current stage's task references under recorded prerequisites.

    This is a conditional snapshot, not trainer execution or external state storage.
    A caller must retain the plan/history and not ignore a newer observation.
    """
    plan, history = plan.checked(), validate_history(history, plan)
    completed = sum(e.decision == "ADVANCE_RECORDED_CRITERION" for e in history.events)
    supplied = tuple(p.checked() for p in _bounded(prerequisite_evaluations, 64))
    _validate_extension(supplied, history.events)
    if completed == len(plan.stages):
        if supplied:
            raise ValueError("completed curriculum accepts no further prerequisite evidence")
        return StageReadiness(
            plan_id=plan.record_id,
            history_id=history.record_id,
            stage_id=None,
            status="COMPLETE_RECORDED_CRITERIA",
            reason="all_recorded_stage_criteria_met",
        )
    stage = plan.stages[completed]
    current_revision = next(
        (
            e.acquisition.points[-1].model_revision
            for e in reversed(history.events)
            if e.acquisition is not None
        ),
        plan.model_revision,
    )
    observations: dict[str, EvaluationPoint] = {}
    for event in history.events:
        prior = (
            (*event.acquisition.points, *event.prerequisite_evaluations)
            if event.acquisition
            else ()
        )
        for point in prior:
            capability = point.population.capability.record_id
            if capability in stage.prerequisites and point.model_revision == current_revision:
                observations[capability] = point
    seen: set[str] = set()
    for point in supplied:
        capability = point.population.capability.record_id
        expected = next(
            (p for p in plan.panels.validation if p.capability.record_id == capability), None
        )
        if (
            capability not in stage.prerequisites
            or capability in seen
            or (expected is None or point.population.record_id != expected.record_id)
            or (point.model_id, point.model_revision) != (plan.model_id, current_revision)
        ):
            raise ValueError("unexpected prerequisite validation population/checkpoint")
        seen.add(capability)
        observations[capability] = point
    reason = "recorded_prerequisites_met"
    if not stage.training_members:
        reason = "no_selected_training_candidates"
    elif set(stage.prerequisites) - observations.keys():
        reason = "prerequisite_evidence_missing"
    elif any(p.recorded_mean is None for p in observations.values()):
        reason = "prerequisite_outcomes_unknown"
    elif any(
        cast(float, p.recorded_mean) < plan.policy.minimum_validation_score
        for p in observations.values()
    ):
        reason = "prerequisite_criterion_failed"
    ready = reason == "recorded_prerequisites_met"
    return StageReadiness(
        plan_id=plan.record_id,
        history_id=history.record_id,
        stage_id=stage.record_id,
        status="READY_CONDITIONAL" if ready else "BLOCKED",
        reason=reason,
        candidate_ids=tuple(c.candidate_id for c in stage.choices if c.selected) if ready else (),
        prerequisite_point_ids=tuple(sorted(p.record_id for p in observations.values())),
    )


def _event(
    plan: CurriculumPlan,
    events: tuple[StageEvent, ...],
    acquisition: AcquisitionCurve | None,
    prerequisite_evaluations: tuple[EvaluationPoint, ...],
) -> StageEvent:
    completed = sum(e.decision == "ADVANCE_RECORDED_CRITERION" for e in events)
    if completed >= len(plan.stages):
        raise ValueError("all precommitted curriculum stages already completed")
    stage = plan.stages[completed]
    current_revision = next(
        (
            e.acquisition.points[-1].model_revision
            for e in reversed(events)
            if e.acquisition is not None
        ),
        plan.model_revision,
    )
    decision: StageDecision = "HOLD"
    reason = "missing_acquisition_evidence"
    if acquisition is not None:
        acquisition = acquisition.checked()
        if _contains_sealed(acquisition.model_dump(mode="json")):
            raise ValueError("SEALED_INPUT_REQUIRES_STRICTER_BOUNDARY")
        before, after = acquisition.points[0], acquisition.points[-1]
        if len(acquisition.points) != 2:
            raise ValueError("one bound intervention per stage attempt required")
        if before.population.record_id != stage.validation_population_id:
            raise ValueError("stage requires its fixed development-validation population")
        if before.model_id != plan.model_id or before.model_revision != current_revision:
            raise ValueError("stage acquisition learner checkpoint mismatch")
        training = acquisition.interventions[0].training_population
        if training.capability.record_id != stage.capability_spec_id or (
            {(r.reference_id, r.digest) for r in training.members}
            != {(r.reference_id, r.digest) for r in stage.training_members}
        ):
            raise ValueError("intervention training population differs from selected stage")
        ids, digests = _members((*plan.panels.validation, *plan.panels.final_test))
        ti, td = _members((training,))
        if ti & ids or td & digests:
            raise ValueError("intervention/fixed-panel overlap")
        _validate_extension((*acquisition.points, *prerequisite_evaluations), events)
        observed = {p.population.capability.record_id: p for p in prerequisite_evaluations}
        if len(observed) != len(prerequisite_evaluations) or set(observed) - set(
            stage.prerequisites
        ):
            raise ValueError("unexpected or duplicate prerequisite evaluation")
        for spec_id, point in observed.items():
            expected = next(p for p in plan.panels.validation if p.capability.record_id == spec_id)
            if point.population.record_id != expected.record_id or (
                point.model_id,
                point.model_revision,
            ) != (after.model_id, after.model_revision):
                raise ValueError("prerequisite validation population/checkpoint mismatch")
        if not stage.training_members:
            reason = "no_selected_training_candidates"
        elif set(stage.prerequisites) - set(observed):
            reason = "prerequisite_evidence_missing"
        elif any(p.recorded_mean is None for p in observed.values()):
            reason = "prerequisite_outcomes_unknown"
        elif any(
            cast(float, p.recorded_mean) < plan.policy.minimum_validation_score
            for p in observed.values()
        ):
            reason = "prerequisite_criterion_failed"
        elif before.recorded_mean is None or after.recorded_mean is None:
            reason = "validation_outcomes_unknown"
        elif after.recorded_mean < plan.policy.minimum_validation_score:
            reason = "validation_criterion_failed"
        elif after.recorded_mean - before.recorded_mean < plan.policy.minimum_validation_delta:
            reason = "validation_delta_insufficient"
        else:
            decision, reason = "ADVANCE_RECORDED_CRITERION", "heldout_validation_criterion_met"
    elif prerequisite_evaluations:
        raise ValueError("prerequisite evaluations require a bound stage acquisition")
    return StageEvent(
        sequence=len(events),
        previous_event_id=events[-1].record_id if events else None,
        stage_id=stage.record_id,
        acquisition=acquisition,
        prerequisite_evaluations=prerequisite_evaluations,
        decision=decision,
        reason=reason,
    )


def validate_history(history: CurriculumHistory, plan: CurriculumPlan) -> CurriculumHistory:
    plan, history = plan.checked(), history.checked()
    if history.plan_id != plan.record_id:
        raise ValueError("history belongs to a different precommitted plan")
    prefix: tuple[StageEvent, ...] = ()
    for recorded in history.events:
        expected = _event(plan, prefix, recorded.acquisition, recorded.prerequisite_evaluations)
        if expected != recorded:
            raise ValueError("stage history was reordered, rewritten or forged")
        prefix = (*prefix, recorded)
    return history


def advance_stage(
    plan: CurriculumPlan,
    history: CurriculumHistory,
    *,
    acquisition: AcquisitionCurve | None = None,
    prerequisite_evaluations: Iterable[EvaluationPoint] = (),
) -> CurriculumHistory:
    plan = plan.checked()
    history = validate_history(history, plan)
    points = tuple(
        sorted(
            (p.checked() for p in _bounded(prerequisite_evaluations, 64)), key=lambda p: p.record_id
        )
    )
    event = _event(plan, history.events, acquisition, points)
    return CurriculumHistory(plan_id=plan.record_id, events=(*history.events, event))
