"""Frozen-population evidence records, not a trainer or an execution attestor.

Numerical changes describe the supplied records. They do not establish that the
named models ran, that a panel was committed prospectively, or that training
caused an improvement. Those distinctions survive serialization and projection.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from investigation_world.experience import ExperienceReference

from .core import CapabilitySpec, Digest, ScienceRecord, Text, validate_references

Provenance = Literal["UNKNOWN", "DECLARED", "CONSTRUCTED"]


def _pinned_identity(value: str) -> None:
    if value.lower() in {"unknown", "unspecified", "latest", "main", "head"}:
        raise ValueError("an explicit pinned identity/revision is required")


class EvaluationConditions(ScienceRecord):
    schema_version: Literal["veritas.capability-evaluation-conditions.v1"] = (
        "veritas.capability-evaluation-conditions.v1"
    )
    environment_id: Text
    environment_revision: Text
    verifier_id: Text
    verifier_revision: Text
    metric: Literal["success_fraction", "criterion_score"]
    metric_definition_digest: Digest
    distribution_id: Text
    structure_id: Text
    interface_id: Text
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_evidence(self) -> Self:
        validate_references(self.evidence_references)
        for value in (
            self.environment_id,
            self.environment_revision,
            self.verifier_id,
            self.verifier_revision,
            self.distribution_id,
            self.structure_id,
            self.interface_id,
        ):
            _pinned_identity(value)
        return self


class EvaluationPopulation(ScienceRecord):
    """Exact declared population, including failures and presently unscored members."""

    schema_version: Literal["veritas.capability-evaluation-population.v1"] = (
        "veritas.capability-evaluation-population.v1"
    )
    capability: CapabilitySpec
    conditions: EvaluationConditions
    split: Literal["TRAIN", "HELD_OUT"]
    members: tuple[ExperienceReference, ...] = Field(min_length=1)
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_members(self) -> Self:
        validate_references(self.members)
        validate_references(self.evidence_references)
        if len({r.reference_id for r in self.members}) != len(self.members) or (
            len({r.digest for r in self.members}) != len(self.members)
        ):
            raise ValueError("population requires unique member identities and source digests")
        return self


class CaseOutcome(ScienceRecord):
    schema_version: Literal["veritas.capability-case-outcome.v1"] = (
        "veritas.capability-case-outcome.v1"
    )
    member_id: Text
    member_digest: Digest
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_references: tuple[ExperienceReference, ...] = ()
    unavailable_reason: Text | None = None

    @model_validator(mode="after")
    def require_observation_or_reason(self) -> Self:
        if self.value is None:
            if self.unavailable_reason is None:
                raise ValueError("unknown outcome requires an unavailable reason")
        elif self.unavailable_reason is not None:
            raise ValueError("known outcome cannot also be unavailable")
        if self.value is not None or self.evidence_references:
            validate_references(self.evidence_references)
        return self


def _mean(outcomes: tuple[CaseOutcome, ...]) -> float | None:
    values = [row.value for row in outcomes]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None) / len(values)


class EvaluationPoint(ScienceRecord):
    schema_version: Literal["veritas.capability-evaluation-point.v1"] = (
        "veritas.capability-evaluation-point.v1"
    )
    population: EvaluationPopulation
    model_id: Text
    model_revision: Text
    sequence_index: int = Field(ge=0, strict=True)
    observed_at: AwareDatetime | None = None
    outcomes: tuple[CaseOutcome, ...] = Field(min_length=1)
    execution_provenance: Provenance = "UNKNOWN"
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_population(self) -> Self:
        validate_references(self.evidence_references)
        _pinned_identity(self.model_id)
        _pinned_identity(self.model_revision)
        ids = [row.member_id for row in self.outcomes]
        if len(ids) != len(set(ids)) or set(ids) != {
            member.reference_id for member in self.population.members
        }:
            raise ValueError("outcomes must cover the exact population once per member")
        source_digests = {ref.reference_id: ref.digest for ref in self.population.members}
        if any(row.member_digest != source_digests[row.member_id] for row in self.outcomes):
            raise ValueError("outcome source digest does not match its population member")
        if self.population.conditions.metric == "success_fraction" and any(
            row.value not in (None, 0.0, 1.0) for row in self.outcomes
        ):
            raise ValueError("success_fraction requires binary case outcomes")
        return self

    @property
    def recorded_mean(self) -> float | None:
        return _mean(self.checked().outcomes)


class TrainingIntervention(ScienceRecord):
    """Pinned external intervention declaration; no training is launched here."""

    schema_version: Literal["veritas.capability-training-intervention.v1"] = (
        "veritas.capability-training-intervention.v1"
    )
    before_point_id: Text
    after_point_id: Text
    training_population: EvaluationPopulation
    trainer_id: Text
    trainer_revision: Text
    training_bundle_digest: Digest
    training_configuration_digest: Digest
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    execution_provenance: Provenance = "UNKNOWN"
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_intervention(self) -> Self:
        validate_references(self.evidence_references)
        _pinned_identity(self.trainer_id)
        _pinned_identity(self.trainer_revision)
        if self.before_point_id == self.after_point_id:
            raise ValueError("intervention requires distinct before and after evaluation points")
        if self.training_population.split != "TRAIN":
            raise ValueError("intervention training population must use TRAIN")
        if (
            self.started_at is not None
            and self.finished_at is not None
            and (self.started_at > self.finished_at)
        ):
            raise ValueError("intervention chronology is reversed")
        return self


def _comparable(before: EvaluationPoint, after: EvaluationPoint) -> None:
    if before.population.record_id != after.population.record_id:
        raise ValueError("evaluation population, capability or measurement semantics changed")
    if before.model_id != after.model_id:
        raise ValueError("comparison requires the same model identity, not the same checkpoint")
    if before.sequence_index >= after.sequence_index:
        raise ValueError("evaluation sequence must be ordered")
    if (
        before.observed_at is not None
        and after.observed_at is not None
        and (before.observed_at >= after.observed_at)
    ):
        raise ValueError("evaluation chronology must be strictly ordered")


def _disjoint(source: EvaluationPopulation, target: EvaluationPopulation) -> None:
    if {ref.reference_id for ref in source.members} & {
        ref.reference_id for ref in target.members
    } or {ref.digest for ref in source.members} & {ref.digest for ref in target.members}:
        raise ValueError("training and held-out population overlap")


def _semantics(conditions: EvaluationConditions) -> tuple[str, ...]:
    return (
        conditions.verifier_id,
        conditions.verifier_revision,
        conditions.metric,
        conditions.metric_definition_digest,
    )


class AcquisitionCurve(ScienceRecord):
    schema_version: Literal["veritas.capability-acquisition-curve.v1"] = (
        "veritas.capability-acquisition-curve.v1"
    )
    points: tuple[EvaluationPoint, ...] = Field(min_length=2)
    interventions: tuple[TrainingIntervention, ...] = Field(min_length=1)
    model_execution_attestation: Literal["UNKNOWN"] = "UNKNOWN"
    chronology_attestation: Literal["UNKNOWN"] = "UNKNOWN"
    capability_gain: None = None

    @model_validator(mode="after")
    def validate_ordered_interventions(self) -> Self:
        if len(self.interventions) != len(self.points) - 1:
            raise ValueError("each consecutive evaluation pair requires exactly one intervention")
        for before, after, intervention in zip(
            self.points, self.points[1:], self.interventions, strict=False
        ):
            _comparable(before, after)
            if after.sequence_index != before.sequence_index + 1:
                raise ValueError("acquisition sequence cannot silently skip evaluations")
            if (intervention.before_point_id, intervention.after_point_id) != (
                before.record_id,
                after.record_id,
            ):
                raise ValueError("intervention evaluation-point binding mismatch")
            if before.population.split == "HELD_OUT":
                _disjoint(intervention.training_population, before.population)
            chronology = (
                before.observed_at,
                intervention.started_at,
                intervention.finished_at,
                after.observed_at,
            )
            # Known endpoints cannot contradict ordering just because another timestamp is absent.
            known = [(index, time) for index, time in enumerate(chronology) if time is not None]
            for (left_index, left), (right_index, right) in zip(known, known[1:], strict=False):
                simultaneous_training = (left_index, right_index) == (1, 2)
                if left > right or (left == right and not simultaneous_training):
                    raise ValueError("evaluation/intervention chronology is inconsistent")
        return self

    @property
    def recorded_metric_deltas(self) -> tuple[float | None, ...]:
        points = self.checked().points
        means = [_mean(point.outcomes) for point in points]
        return tuple(
            after - before if before is not None and after is not None else None
            for before, after in zip(means, means[1:], strict=False)
        )


class RetentionLink(ScienceRecord):
    schema_version: Literal["veritas.capability-retention-link.v1"] = (
        "veritas.capability-retention-link.v1"
    )
    acquired: EvaluationPoint
    later: EvaluationPoint
    intervention_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    capability_gain: None = None

    @model_validator(mode="after")
    def validate_retention(self) -> Self:
        validate_references(self.intervention_references)
        _comparable(self.acquired, self.later)
        return self

    @property
    def recorded_metric_delta(self) -> float | None:
        checked = self.checked()
        before, after = _mean(checked.acquired.outcomes), _mean(checked.later.outcomes)
        return after - before if before is not None and after is not None else None

    @property
    def recorded_relation(self) -> Literal["UNKNOWN", "REGRESSION", "RETAINED", "IMPROVED"]:
        delta = self.recorded_metric_delta
        if delta is None:
            return "UNKNOWN"
        return "REGRESSION" if delta < 0 else "IMPROVED" if delta > 0 else "RETAINED"


class CompositionTest(ScienceRecord):
    schema_version: Literal["veritas.capability-composition-test.v1"] = (
        "veritas.capability-composition-test.v1"
    )
    target: CapabilitySpec
    required_components: tuple[CapabilitySpec, ...] = Field(min_length=2)
    component_evaluations: tuple[EvaluationPoint, ...] = Field(min_length=2)
    composed_evaluation: EvaluationPoint
    criterion_digest: Digest
    minimum_score: float = Field(ge=0, le=1)
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    qualification: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def validate_composition(self) -> Self:
        validate_references(self.evidence_references)
        components = [spec.record_id for spec in self.required_components]
        observed = [point.population.capability.record_id for point in self.component_evaluations]
        if (
            len(components) != len(set(components))
            or len(observed) != len(set(observed))
            or (set(components) != set(observed))
        ):
            raise ValueError(
                "component evaluations must cover each declared component exactly once"
            )
        if self.target.record_id in components or (
            self.composed_evaluation.population.capability.record_id != self.target.record_id
        ):
            raise ValueError("composition requires separate evidence for its declared target")
        reference = self.composed_evaluation
        target_references = (
            *reference.evidence_references,
            *(ref for row in reference.outcomes for ref in row.evidence_references),
        )
        target_ids = {ref.reference_id for ref in target_references}
        target_digests = {ref.digest for ref in target_references}
        for point in self.component_evaluations:
            if (point.model_id, point.model_revision) != (
                reference.model_id,
                reference.model_revision,
            ):
                raise ValueError("composition evaluations require the same model checkpoint")
            if _semantics(point.population.conditions) != _semantics(
                reference.population.conditions
            ):
                raise ValueError("composition evaluations require the same measurement semantics")
            refs = (
                *point.evidence_references,
                *(ref for row in point.outcomes for ref in row.evidence_references),
            )
            if target_ids & {ref.reference_id for ref in refs} or (
                target_digests & {ref.digest for ref in refs}
            ):
                raise ValueError(
                    "composed outcome requires evidence distinct from component results"
                )
        return self

    @property
    def recorded_result(self) -> Literal["PASS", "FAIL", "UNKNOWN"]:
        checked = self.checked()
        means = [
            _mean(point.outcomes)
            for point in (*checked.component_evaluations, checked.composed_evaluation)
        ]
        if any(value is not None and value < checked.minimum_score for value in means):
            return "FAIL"
        return "UNKNOWN" if any(value is None for value in means) else "PASS"


class TransferEvidence(ScienceRecord):
    """Classify a declared transfer protocol, not its external scientific validity."""

    schema_version: Literal["veritas.capability-transfer-evidence.v1"] = (
        "veritas.capability-transfer-evidence.v1"
    )
    source: EvaluationPoint
    target: AcquisitionCurve
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    classification_basis: Literal["DECLARED_SOURCE_TARGET_CONDITIONS"] = (
        "DECLARED_SOURCE_TARGET_CONDITIONS"
    )
    capability_gain: None = None
    qualification: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def validate_heldout_transfer(self) -> Self:
        validate_references(self.evidence_references)
        source, target = self.source.population, self.target.points[0].population
        if source.split != "TRAIN" or target.split != "HELD_OUT":
            raise ValueError("transfer requires source TRAIN and independently held-out target")
        if source.capability.record_id != target.capability.record_id:
            raise ValueError("transfer capability identity differs between source and target")
        if any(
            step.training_population.record_id != source.record_id
            for step in self.target.interventions
        ):
            raise ValueError("transfer source does not bind every intervention training population")
        _disjoint(source, target)
        if _semantics(source.conditions) != _semantics(target.conditions):
            raise ValueError("transfer requires comparable source and target measurement semantics")
        return self

    @property
    def classifications(self) -> tuple[str, ...]:
        checked = self.checked()
        source = checked.source.population.conditions
        target = checked.target.points[0].population.conditions
        result = []
        if (
            source.structure_id != target.structure_id
            or (source.distribution_id != target.distribution_id)
            or (source.environment_id, source.environment_revision)
            != (target.environment_id, target.environment_revision)
        ):
            result.append("STRUCTURAL_OOD")
        if source.interface_id != target.interface_id:
            result.append("INTERFACE_TOOL")
        if checked.source.model_id != checked.target.points[0].model_id:
            result.append("CROSS_MODEL")
        return tuple(result) if result else ("IID",)

    @property
    def recorded_metric_delta(self) -> float | None:
        points = self.checked().target.points
        before, after = _mean(points[0].outcomes), _mean(points[-1].outcomes)
        return after - before if before is not None and after is not None else None
