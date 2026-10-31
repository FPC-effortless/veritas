"""Content-bound, offline continual-learning records; no learner or execution attestor."""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Literal, Self

from pydantic import ConfigDict, Field, StrictInt, model_validator

from investigation_world.capability_science import (
    AcquisitionCurve,
    EvaluationPoint,
    EvaluationPopulation,
    RetentionLink,
)
from investigation_world.capability_science.core import Digest, Text, validate_references
from investigation_world.capability_science.measurements import _pinned_identity
from investigation_world.experience import ExperienceReference, ExperienceSequence
from investigation_world.experience_foundry.derivation import PrivateRecord as FoundryPrivateRecord
from investigation_world.experience_foundry.paired_evaluation import _training_membership
from investigation_world.experience_selection import SelectionReport
from investigation_world.foundry.models import capability_contract_digest_payload
from investigation_world.foundry.training_product import TrainingBundle, TrainingRunManifest
from investigation_world.qualification.maturity import GateOutcome
from investigation_world.training_qualification import TrainingReport
from investigation_world.trajectory import canonical_hash


class PrivateRecord(FoundryPrivateRecord):
    model_config = ConfigDict(hide_input_in_errors=True)


class ExternalLearner(PrivateRecord):
    backend_id: Text
    backend_revision: Text
    configuration_digest: Digest
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def pinned(self) -> Self:
        _pinned_identity(self.backend_id)
        _pinned_identity(self.backend_revision)
        validate_references(self.evidence_references)
        return self


class ScheduledStep(PrivateRecord):
    index: int = Field(ge=1, le=32, strict=True)
    new_experience_ids: tuple[Text, ...] = Field(min_length=1, max_length=256)
    replay_experience_ids: tuple[Text, ...] = Field(default=(), max_length=256)
    bundle: TrainingBundle
    training_population: EvaluationPopulation
    learner: ExternalLearner
    replay_selection: SelectionReport | None = None

    @model_validator(mode="after")
    def bind_lineage(self) -> Self:
        _training_membership(self.bundle)
        rows = self.bundle.metadata["verified_learning_lineage"]
        ids = (*self.new_experience_ids, *self.replay_experience_ids)
        if len(set(ids)) != len(ids) or set(ids) != {r["experience_id"] for r in rows}:
            raise ValueError("new/replay experiences must exactly cover the bound bundle")
        if self.training_population.split != "TRAIN" or {
            (r["source_id"], r["source_digest"]) for r in rows
        } != {(m.reference_id, m.digest) for m in self.training_population.members}:
            raise ValueError("training population must match every exact TRAIN bundle source")
        if canonical_hash(capability_contract_digest_payload(self.bundle.capability_contract)) != (
            self.training_population.capability.contract_digest
        ):
            raise ValueError("bundle and training population capability mismatch")
        if self.replay_experience_ids:
            if self.replay_selection is None:
                raise ValueError("replay requires exact selection provenance")
            selected = [d for d in self.replay_selection.decisions if d.reason == "selected"]
            if len(selected) != len(self.replay_experience_ids) or {
                d.experience_id for d in selected
            } != set(self.replay_experience_ids):
                raise ValueError("replay corpus differs from selected experience identities")
            sources = {r["experience_id"]: r.get("fixture_digest") for r in rows}
            if any(
                d.source_fixture_digest is None
                or d.source_fixture_digest != sources[d.experience_id]
                for d in selected
            ):
                raise ValueError("replay selected source digest differs from bundle lineage")
        elif self.replay_selection is not None:
            raise ValueError("selection report without replay corpus")
        return self


class PanelPlan(PrivateRecord):
    population: EvaluationPopulation
    role: Literal["target", "guardrail"] = "target"
    reference_step: int = Field(ge=0, le=32, strict=True)

    @model_validator(mode="after")
    def heldout(self) -> Self:
        if self.population.split != "HELD_OUT":
            raise ValueError("continual evaluation panels must be held out")
        if (self.role == "guardrail") != (self.reference_step == 0):
            raise ValueError("guardrails reference baseline; targets reference acquisition step")
        return self


class ContinualPlan(PrivateRecord):
    schema_version: Literal["veritas.continual-plan.v1"] = "veritas.continual-plan.v1"
    sequence: ExperienceSequence
    steps: tuple[ScheduledStep, ...] = Field(min_length=2, max_length=32)
    panels: tuple[PanelPlan, ...] = Field(min_length=2, max_length=16)
    model_id: Text
    baseline_revision: Text
    expected_seeds: tuple[StrictInt, ...] = Field(min_length=1, max_length=32)
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1)
    prospective_commitment_attestation: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def fixed_schedule(self) -> Self:
        validate_references(self.evidence_references)
        _pinned_identity(self.model_id)
        _pinned_identity(self.baseline_revision)
        if len(set(self.expected_seeds)) != len(self.expected_seeds) or any(
            not 0 <= seed < 2**32 for seed in self.expected_seeds
        ):
            raise ValueError("expected seeds must be unique bounded integers")
        if tuple(s.index for s in self.steps) != tuple(range(1, len(self.steps) + 1)):
            raise ValueError("scheduled steps must be contiguous and ordered")
        ordered = tuple(x for s in self.steps for x in s.new_experience_ids)
        if ordered != self.sequence.experience_ids or len(set(ordered)) != len(ordered):
            raise ValueError("ordered new experience schedule must equal exact ExperienceSequence")
        if set(ordered) & set(self.sequence.transfer_test_experience_ids):
            raise ValueError("sequence training/transfer experience overlap")
        capabilities = [p.population.capability.contract_digest for p in self.panels]
        if len(set(capabilities)) != len(capabilities) or {p.role for p in self.panels} != {
            "target",
            "guardrail",
        }:
            raise ValueError("fixed panels need unique capabilities, targets and guardrails")
        first: dict[str, int] = {}
        history: dict[str, str] = {}
        heldout_ids = {m.reference_id for p in self.panels for m in p.population.members}
        heldout_hashes = {m.digest for p in self.panels for m in p.population.members}
        for s in self.steps:
            capability = s.training_population.capability.contract_digest
            first.setdefault(capability, s.index)
            if not set(s.replay_experience_ids) <= set(history):
                raise ValueError("replay may contain only earlier committed experiences")
            for row in s.bundle.metadata["verified_learning_lineage"]:
                exp = row["experience_id"]
                fingerprint = canonical_hash(row)
                if exp in history and history[exp] != fingerprint:
                    raise ValueError("replay source lineage substitution")
                if (
                    {row["source_id"], row["task_id"], exp} & heldout_ids
                    or row["source_digest"] in heldout_hashes
                    or row.get("fixture_digest") in heldout_hashes
                    or exp in self.sequence.transfer_test_experience_ids
                ):
                    raise ValueError("training/replay and frozen evaluation panel overlap")
                history[exp] = fingerprint
            if s.replay_selection is not None and (
                not heldout_ids <= set(s.replay_selection.policy.heldout_task_ids)
                or not heldout_hashes <= set(s.replay_selection.policy.heldout_source_digests)
            ):
                raise ValueError("replay selection must exclude every frozen evaluation source")
        targets = {
            p.population.capability.contract_digest for p in self.panels if p.role == "target"
        }
        if set(first) != targets:
            raise ValueError("every trained capability requires exactly one fixed target panel")
        for p in self.panels:
            cap = p.population.capability.contract_digest
            if p.role == "target" and p.reference_step != first[cap]:
                raise ValueError("target reference must be its first scheduled acquisition step")
            if p.role == "guardrail" and cap in first:
                raise ValueError("guardrails must remain unrelated to trained capabilities")
        return self


class StepRun(PrivateRecord):
    manifest: TrainingRunManifest
    before_checkpoint: Text
    after_checkpoint: Text
    training_report: TrainingReport | None = None

    @model_validator(mode="after")
    def checkpoints(self) -> Self:
        _pinned_identity(self.before_checkpoint)
        _pinned_identity(self.after_checkpoint)
        if self.before_checkpoint == self.after_checkpoint:
            raise ValueError("external step requires distinct checkpoint declarations")
        return self

    @property
    def declaration_reference(self) -> ExperienceReference:
        # A content binding, never a claim that this run happened.
        return ExperienceReference(
            reference_id=self.manifest.run_id,
            reference_type="external-step-declaration",
            digest=canonical_hash(
                {
                    "manifest": self.manifest,
                    "before_checkpoint": self.before_checkpoint,
                    "after_checkpoint": self.after_checkpoint,
                }
            ),
            visibility=self.visibility,
        )


class Replicate(PrivateRecord):
    seed: int = Field(ge=0, lt=2**32, strict=True)
    runs: tuple[StepRun, ...] = Field(min_length=2, max_length=32)
    curves: tuple[AcquisitionCurve, ...] = Field(min_length=2, max_length=16)
    forward_controls: tuple[EvaluationPoint, ...] = Field(default=(), max_length=16)


def _point_refs(point: EvaluationPoint) -> tuple[ExperienceReference, ...]:
    # Panel/paired-report context may legitimately be shared (#162 adapter).
    # Only scored case observations establish independent measured outcomes;
    # repeated unavailable-result markers remain explicit UNKNOWN, not evidence.
    return tuple(r for o in point.outcomes if o.value is not None for r in o.evidence_references)


def _check_training_report(
    run: StepRun, seed: int, step: ScheduledStep, curves: dict[str, AcquisitionCurve]
) -> tuple[EvaluationPoint, ...]:
    report = run.training_report
    if report is None:
        return ()
    evidence = report.evidence
    if (
        evidence.bundle != step.bundle
        or evidence.expected_seeds != (seed,)
        or len(evidence.replicates) != 1
        or evidence.replicates[0].manifest != run.manifest
        or evidence.configuration_digest != step.learner.configuration_digest
        or evidence.capability != step.training_population.capability
    ):
        raise ValueError(
            "training report must bind this exact step, bundle, manifest and replicate"
        )
    rep = evidence.replicates[0]
    extra: list[EvaluationPoint] = []
    if rep.train is not None:
        train = rep.train
        expected = next(iter(curves.values())).interventions[step.index - 1]
        if (
            train.points[0].population != step.training_population
            or tuple(p.model_id for p in train.points) != (run.manifest.base_model,) * 2
            or tuple(p.model_revision for p in train.points)
            != (run.before_checkpoint, run.after_checkpoint)
            or tuple(p.sequence_index for p in train.points) != (step.index - 1, step.index)
            or train.interventions[0].model_dump(
                exclude={"record_id", "before_point_id", "after_point_id"}
            )
            != expected.model_dump(exclude={"record_id", "before_point_id", "after_point_id"})
        ):
            raise ValueError("training report train panel differs from exact step/checkpoints")
        extra.extend(train.points)
    if rep.learnability is not None:
        extra.append(rep.learnability)
    for curve in (rep.heldout, *rep.guardrails, *rep.transfer):
        if curve is None:
            continue
        match = curves.get(curve.points[0].population.record_id)
        i = step.index - 1
        if (
            match is None
            or curve.points != match.points[i : i + 2]
            or (curve.interventions != match.interventions[i : i + 1])
        ):
            raise ValueError("training report evaluation differs from committed continual matrix")
    return tuple(extra)


class ContinualEvidence(PrivateRecord):
    schema_version: Literal["veritas.continual-evidence.v1"] = "veritas.continual-evidence.v1"
    plan: ContinualPlan
    replicates: tuple[Replicate, ...] = Field(default=(), max_length=32)
    provenance: Literal["UNKNOWN", "DECLARED", "CONSTRUCTED"] = "UNKNOWN"
    execution_attestation_provider: Literal["UNAVAILABLE"] = "UNAVAILABLE"

    @model_validator(mode="after")
    def matrix(self) -> Self:
        p = self.plan
        seeds = [r.seed for r in self.replicates]
        if len(set(seeds)) != len(seeds) or not set(seeds) <= set(p.expected_seeds):
            raise ValueError("duplicate or unexpected replicate seed")
        seen_ids: set[str] = set()
        seen_hashes: set[str | None] = set()
        run_ids: set[str] = set()
        intervention_ids: set[str] = set()
        intervention_hashes: set[str | None] = set()
        for rep in self.replicates:
            by_panel = {c.points[0].population.record_id: c for c in rep.curves}
            if len(by_panel) != len(rep.curves) or set(by_panel) != {
                panel.population.record_id for panel in p.panels
            }:
                raise ValueError("replicate must cover every fixed capability panel exactly once")
            if len(rep.runs) != len(p.steps):
                raise ValueError("replicate must include every scheduled external run")
            checkpoints: tuple[str, ...] | None = None
            signatures: tuple[str, ...] | None = None
            times: list[tuple] = []
            chronology: dict[int, list[datetime]] = {}
            for curve in rep.curves:
                if tuple(x.sequence_index for x in curve.points) != tuple(range(len(p.steps) + 1)):
                    raise ValueError("evaluation matrix cannot omit or substitute steps")
                revisions = tuple(x.model_revision for x in curve.points)
                if any(x.model_id != p.model_id for x in curve.points) or (
                    revisions[0] != p.baseline_revision
                    or len(set(revisions)) != len(revisions)
                    or (checkpoints is not None and revisions != checkpoints)
                ):
                    raise ValueError("exact baseline/model/checkpoint matrix binding mismatch")
                checkpoints = revisions
                current = []
                for i, (step, intervention) in enumerate(
                    zip(p.steps, curve.interventions, strict=True)
                ):
                    if (
                        intervention.training_population != step.training_population
                        or intervention.training_bundle_digest != canonical_hash(step.bundle)
                        or intervention.training_configuration_digest
                        != step.learner.configuration_digest
                        or intervention.trainer_id != step.learner.backend_id
                        or intervention.trainer_revision != step.learner.backend_revision
                    ):
                        raise ValueError(
                            "intervention differs from exact scheduled learner or data"
                        )
                    for phase, timestamp in (
                        (3 * i + 1, intervention.started_at),
                        (3 * i + 2, intervention.finished_at),
                    ):
                        if timestamp is not None:
                            chronology.setdefault(phase, []).append(timestamp)
                    current.append(
                        canonical_hash(
                            intervention.model_dump(
                                exclude={"record_id", "before_point_id", "after_point_id"}
                            )
                        )
                    )
                    if len(times) <= i:
                        times.append((intervention.started_at, intervention.finished_at))
                if signatures is not None and tuple(current) != signatures:
                    raise ValueError(
                        "capability panels must share exact external intervention evidence"
                    )
                signatures = tuple(current)
                for point in curve.points:
                    if point.observed_at is not None:
                        chronology.setdefault(3 * point.sequence_index, []).append(
                            point.observed_at
                        )
                    refs = _point_refs(point)
                    ids, hashes = {r.reference_id for r in refs}, {r.digest for r in refs}
                    if (
                        len(ids) != len(refs)
                        or len(hashes) != len(refs)
                        or (ids & seen_ids or hashes & seen_hashes)
                    ):
                        raise ValueError(
                            "reused evaluation evidence across outcomes, steps or replicates"
                        )
                    seen_ids |= ids
                    seen_hashes |= hashes
            for step, run, intervention in zip(
                p.steps, rep.runs, rep.curves[0].interventions, strict=True
            ):
                manifest = run.manifest
                if not manifest.run_id.strip() or manifest.run_id in run_ids:
                    raise ValueError("external run identities must be nonblank and unique")
                run_ids.add(manifest.run_id)
                if (
                    manifest.seed != rep.seed
                    or manifest.bundle_id != step.bundle.bundle_id
                    or manifest.trainer != step.bundle.recipe.trainer
                    or manifest.base_model != p.model_id
                    or manifest.trainer_version != step.learner.backend_revision
                    or canonical_hash(manifest.parameters) != step.learner.configuration_digest
                ):
                    raise ValueError(
                        "external run manifest differs from scheduled learner/seed/bundle"
                    )
                if (
                    checkpoints is None
                    or (run.before_checkpoint, run.after_checkpoint)
                    != (checkpoints[step.index - 1], checkpoints[step.index])
                    or run.declaration_reference not in intervention.evidence_references
                ):
                    raise ValueError(
                        "external run declaration is not bound to intervention/checkpoints"
                    )
                refs = intervention.evidence_references
                ids, hashes = {r.reference_id for r in refs}, {r.digest for r in refs}
                if ids & intervention_ids or hashes & intervention_hashes:
                    raise ValueError(
                        "reused intervention execution evidence across steps or replicates"
                    )
                intervention_ids |= ids
                intervention_hashes |= hashes
                for extra in _check_training_report(run, rep.seed, step, by_panel):
                    refs = _point_refs(extra)
                    ids, hashes = {r.reference_id for r in refs}, {r.digest for r in refs}
                    if (
                        len(ids) != len(refs)
                        or len(hashes) != len(refs)
                        or ids & seen_ids
                        or hashes & seen_hashes
                    ):
                        raise ValueError(
                            "training report reuses matrix/control evaluation evidence"
                        )
                    seen_ids |= ids
                    seen_hashes |= hashes
                    train = (
                        run.training_report.evidence.replicates[0].train
                        if run.training_report is not None
                        else None
                    )
                    if (
                        train is not None
                        and extra in train.points
                        and extra.observed_at is not None
                    ):
                        chronology.setdefault(3 * extra.sequence_index, []).append(
                            extra.observed_at
                        )
            controls: set[str] = set()
            for control in rep.forward_controls:
                panel_id = control.population.record_id
                panel = next((x for x in p.panels if x.population.record_id == panel_id), None)
                if (
                    panel is None
                    or panel.role != "target"
                    or panel.reference_step <= 1
                    or panel_id in controls
                ):
                    raise ValueError("forward control must bind one future target panel")
                controls.add(panel_id)
                if (control.model_id, control.model_revision, control.sequence_index) != (
                    p.model_id,
                    p.baseline_revision,
                    0,
                ):
                    raise ValueError(
                        "forward control must be the exact prelearning baseline checkpoint"
                    )
                if control.observed_at is not None:
                    chronology.setdefault(0, []).append(control.observed_at)
                first_start = times[0][0]
                if (
                    control.observed_at is not None
                    and first_start is not None
                    and (control.observed_at >= first_start)
                ):
                    raise ValueError("forward control was observed after learning began")
                refs = _point_refs(control)
                ids, hashes = {r.reference_id for r in refs}, {r.digest for r in refs}
                if (
                    len(ids) != len(refs)
                    or len(hashes) != len(refs)
                    or ids & seen_ids
                    or hashes & seen_hashes
                ):
                    raise ValueError("forward control requires distinct evaluation evidence")
                seen_ids |= ids
                seen_hashes |= hashes
            phases = sorted(chronology)
            for left, right in zip(phases, phases[1:], strict=False):
                latest, earliest = max(chronology[left]), min(chronology[right])
                simultaneous_training = left % 3 == 1 and right == left + 1
                if latest > earliest or (latest == earliest and not simultaneous_training):
                    raise ValueError("combined step/panel chronology contradicts the schedule")
        if seen_ids & intervention_ids or seen_hashes & intervention_hashes:
            raise ValueError(
                "evaluation evidence cannot substitute for external intervention evidence"
            )
        return self


class ContinualPolicy(PrivateRecord):
    minimum_replicates: int = Field(default=2, ge=2, le=32, strict=True)
    maximum_forgetting: float = Field(default=0.25, ge=0, le=1)
    catastrophic_forgetting_threshold: float = Field(default=0.5, gt=0, le=1)
    maximum_guardrail_regression: float = Field(default=0, ge=0, le=1)
    maximum_replicate_range: float = Field(default=0.25, ge=0, le=2)


class ContinualMeasurement(PrivateRecord):
    seed: int
    panel_id: str
    step: int
    reference_step: int
    role: Literal["target", "guardrail"]
    expected_cases: int
    known_cases: int
    recorded_score: float | None
    recorded_retention: float | None
    recorded_backward_transfer: float | None
    recorded_forgetting: float | None
    recorded_forward_transfer: float | None
    retention_link: RetentionLink | None = None
    catastrophic_forgetting: GateOutcome
    guardrail_status: GateOutcome


class ContinualGate(PrivateRecord):
    name: str
    outcome: GateOutcome
    reason: str


def _reduce(values: list[GateOutcome]) -> GateOutcome:
    return (
        GateOutcome.FAIL
        if GateOutcome.FAIL in values
        else GateOutcome.UNKNOWN
        if not values or GateOutcome.UNKNOWN in values
        else GateOutcome.PASS
    )


def _within(value: float | None, maximum: float) -> GateOutcome:
    return (
        GateOutcome.UNKNOWN
        if value is None
        else GateOutcome.PASS
        if value <= maximum
        else GateOutcome.FAIL
    )


def _measure(
    e: ContinualEvidence, policy: ContinualPolicy
) -> tuple[tuple[ContinualMeasurement, ...], tuple[ContinualGate, ...]]:
    rows: list[ContinualMeasurement] = []
    for rep in e.replicates:
        curves = {c.points[0].population.record_id: c for c in rep.curves}
        controls = {c.population.record_id: c for c in rep.forward_controls}
        for panel in e.plan.panels:
            curve = curves[panel.population.record_id]
            reference = curve.points[panel.reference_step]
            for i, point in enumerate(curve.points):
                score = point.recorded_mean
                link = None
                backward = None
                forgetting = None
                retention = None
                if i >= panel.reference_step:
                    retention = score
                    if i == panel.reference_step:
                        backward = 0.0 if score is not None else None
                    else:
                        link = RetentionLink(
                            acquired=reference,
                            later=point,
                            intervention_references=tuple(
                                r
                                for s in curve.interventions[panel.reference_step : i]
                                for r in s.evidence_references
                            ),
                        )
                        backward = link.recorded_metric_delta
                    forgetting = max(0.0, -backward) if backward is not None else None
                forward = None
                if panel.role == "target" and i == panel.reference_step - 1 and i > 0:
                    control = controls.get(panel.population.record_id)
                    start = curve.interventions[0].started_at
                    # Known ordering is necessary, not an attestation of prospective execution.
                    if (
                        control is not None
                        and control.observed_at is not None
                        and start is not None
                        and (
                            control.observed_at < start
                            and point.observed_at is not None
                            and point.observed_at > start
                            and control.recorded_mean is not None
                            and score is not None
                        )
                    ):
                        forward = score - control.recorded_mean
                rows.append(
                    ContinualMeasurement(
                        seed=rep.seed,
                        panel_id=panel.record_id,
                        step=i,
                        reference_step=panel.reference_step,
                        role=panel.role,
                        expected_cases=len(point.outcomes),
                        known_cases=sum(o.value is not None for o in point.outcomes),
                        recorded_score=score,
                        recorded_retention=retention,
                        recorded_backward_transfer=backward,
                        recorded_forgetting=forgetting,
                        recorded_forward_transfer=forward,
                        retention_link=link,
                        catastrophic_forgetting=_within(
                            forgetting, policy.catastrophic_forgetting_threshold
                        ),
                        guardrail_status=_within(forgetting, policy.maximum_guardrail_regression)
                        if panel.role == "guardrail"
                        else GateOutcome.UNKNOWN,
                    )
                )
    full = len(e.replicates) == len(e.plan.expected_seeds)
    checks: dict[str, GateOutcome] = {
        "complete_replicates": GateOutcome.PASS
        if full and len(e.replicates) >= policy.minimum_replicates
        else GateOutcome.UNKNOWN,
        "complete_outcomes": _reduce(
            [
                GateOutcome.PASS if r.known_cases == r.expected_cases else GateOutcome.UNKNOWN
                for r in rows
            ]
        ),
        "retention": _reduce(
            [
                _within(r.recorded_forgetting, policy.maximum_forgetting)
                for r in rows
                if r.role == "target" and r.step > r.reference_step
            ]
        ),
        "catastrophic_forgetting": _reduce(
            [
                r.catastrophic_forgetting
                for r in rows
                if r.role == "target" and r.step > r.reference_step
            ]
        ),
        "guardrails": _reduce(
            [r.guardrail_status for r in rows if r.role == "guardrail" and r.step > 0]
        ),
        "forward_controls": _reduce(
            [
                GateOutcome.PASS if r.recorded_forward_transfer is not None else GateOutcome.UNKNOWN
                for r in rows
                if r.role == "target" and r.reference_step > 1 and r.step == r.reference_step - 1
            ]
        ),
        "training_qualification": _reduce(
            [
                run.training_report.status if run.training_report else GateOutcome.UNKNOWN
                for rep in e.replicates
                for run in rep.runs
            ]
        ),
        "execution_and_chronology": GateOutcome.UNKNOWN,
    }
    spreads: list[GateOutcome] = []
    for panel in e.plan.panels:
        for i in range(len(e.plan.steps) + 1):
            values = [
                r.recorded_score for r in rows if r.panel_id == panel.record_id and r.step == i
            ]
            known = [v for v in values if v is not None]
            spreads.append(
                _within(max(known) - min(known), policy.maximum_replicate_range)
                if full and len(known) == len(e.plan.expected_seeds) >= policy.minimum_replicates
                else GateOutcome.UNKNOWN
            )
    checks["replicate_stability"] = _reduce(spreads)
    if not full:
        # Missing planned replicates never turn observed-subset checks into full PASS.
        checks = {name: _reduce([value, GateOutcome.UNKNOWN]) for name, value in checks.items()}
    return tuple(rows), tuple(
        ContinualGate(
            name=name,
            outcome=value,
            reason=(
                "independent_execution_and_prospective_chronology_provider_unavailable"
                if name == "execution_and_chronology"
                else "policy_applied_to_all_declared_steps_panels_and_replicates"
            ),
        )
        for name, value in checks.items()
    )


class ContinualReport(PrivateRecord):
    schema_version: Literal["veritas.continual-report.v1"] = "veritas.continual-report.v1"
    evidence: ContinualEvidence
    policy: ContinualPolicy
    measurements: tuple[ContinualMeasurement, ...]
    gates: tuple[ContinualGate, ...]
    status: GateOutcome
    mean_final_recorded_backward_transfer: float | None
    demonstrated_continual_learning: Literal["UNKNOWN"] = "UNKNOWN"
    capability_gain: None = None
    e7_promotion: Literal[False] = False

    @model_validator(mode="after")
    def recompute(self) -> Self:
        rows, gates = _measure(self.evidence, self.policy)
        if (
            self.measurements != rows
            or self.gates != gates
            or self.status != _reduce([g.outcome for g in gates])
            or (self.mean_final_recorded_backward_transfer != _final_mean(self.evidence, rows))
        ):
            raise ValueError("continual report differs from recomputed complete evidence")
        return self


def _final_mean(e: ContinualEvidence, rows: tuple[ContinualMeasurement, ...]) -> float | None:
    values = [
        r.recorded_backward_transfer
        for r in rows
        if r.role == "target" and r.step == len(e.plan.steps) and r.step > r.reference_step
    ]
    if (
        len(e.replicates) != len(e.plan.expected_seeds)
        or not values
        or any(v is None for v in values)
    ):
        return None
    return mean(v for v in values if v is not None)


def assess_continual_learning(
    evidence: ContinualEvidence, *, policy: ContinualPolicy | None = None
) -> ContinualReport:
    evidence = evidence.checked()
    policy = (policy or ContinualPolicy()).checked()
    rows, gates = _measure(evidence, policy)
    return ContinualReport(
        evidence=evidence,
        policy=policy,
        measurements=rows,
        gates=gates,
        status=_reduce([g.outcome for g in gates]),
        mean_final_recorded_backward_transfer=_final_mean(evidence, rows),
    )


class ExperimentRevision(PrivateRecord):
    index: int = Field(ge=0, strict=True)
    previous_record_id: Text | None = None
    report: ContinualReport


class ExperimentHistory(PrivateRecord):
    """Immutable snapshots, not a database or proof of prospectively recorded history."""

    schema_version: Literal["veritas.continual-history.v1"] = "veritas.continual-history.v1"
    plan: ContinualPlan
    revisions: tuple[ExperimentRevision, ...] = ()

    @model_validator(mode="after")
    def chain(self) -> Self:
        previous = None
        for i, entry in enumerate(self.revisions):
            if (
                entry.index != i
                or entry.previous_record_id != previous
                or entry.report.evidence.plan != self.plan
            ):
                raise ValueError("experiment history has a broken, reordered or substituted chain")
            previous = entry.record_id
        return self

    def append(
        self, report: ContinualReport, *, expected_previous_commitment: str
    ) -> ExperimentHistory:
        current = self.checked()
        if current.record_id != expected_previous_commitment:
            raise ValueError(
                "stored previous history commitment mismatch; possible history rewrite"
            )
        revision = ExperimentRevision(
            index=len(current.revisions),
            report=report,
            previous_record_id=current.revisions[-1].record_id if current.revisions else None,
        )
        return ExperimentHistory(plan=current.plan, revisions=(*current.revisions, revision))
