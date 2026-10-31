"""Private, content-bound descriptive resource arithmetic; never a training attestor."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from itertools import islice
from statistics import mean, stdev
from typing import Literal, Self, get_args

from pydantic import ConfigDict, Field, model_validator

from investigation_world.capability_science import RetentionLink
from investigation_world.capability_science.core import (
    ScienceRecord,
    Text,
    validate_references,
)
from investigation_world.experience import ExperienceReference
from investigation_world.experience.counterfactual import CounterfactualReceipt
from investigation_world.experience_foundry.admission import RecordedExperience, authorized_registry
from investigation_world.experience_foundry.bundle_bridge import compile_verified_bundle
from investigation_world.experience_foundry.derivation import (
    LearningAssetCompilation,
    TransformPolicy,
    validate_compilation,
)
from investigation_world.experience_foundry.external_receipt import ReceiptValidation
from investigation_world.experience_selection import (
    SelectionPolicy,
    SelectionReport,
    validate_selection,
)
from investigation_world.training_qualification import TrainingReport
from investigation_world.trajectory import VisibilityClass, canonical_hash

Stage = Literal["generation", "selection", "derivation", "training", "evaluation"]
Metric = Literal[
    "training_tokens",
    "gpu_hours",
    "equivalent_compute",
    "teacher_calls",
    "teacher_tokens",
    "teacher_cost",
    "human_review_examples",
    "human_hours",
    "monetary_cost",
    "wall_seconds",
]
STAGES: tuple[Stage, ...] = get_args(Stage)
_FIXED_UNITS = {
    "training_tokens": "token",
    "gpu_hours": "GPU-hour",
    "teacher_calls": "call",
    "teacher_tokens": "token",
    "human_review_examples": "example",
    "human_hours": "hour",
    "wall_seconds": "second",
}


class PrivateRecord(ScienceRecord):
    model_config = ConfigDict(hide_input_in_errors=True)
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE


class RunReceipt(PrivateRecord):
    seed: int = Field(strict=True, ge=0, le=2**32 - 1)
    receipt: ReceiptValidation

    @model_validator(mode="after")
    def validate_receipt_digest_shapes(self) -> Self:
        for field in ("manifest_digest", "bundle_digest", "input_digest", "checkpoint_digest"):
            if re.fullmatch(r"[0-9a-f]{64}", getattr(self.receipt, field)) is None:
                raise ValueError("receipt requires full content digests")
        for amount in (self.receipt.elapsed_s, self.receipt.cost):
            if amount is not None and (not math.isfinite(amount) or amount < 0):
                raise ValueError("receipt resource must be finite and nonnegative")
        memory = self.receipt.peak_memory_bytes
        if memory is not None and (type(memory) is not int or memory < 0):
            raise ValueError("receipt memory must be a nonnegative integer")
        return self


class EfficiencyStudy(PrivateRecord):
    schema_version: Literal["veritas.efficiency-study.v1"] = "veritas.efficiency-study.v1"
    experiment_id: Text
    training: TrainingReport
    selection: SelectionReport | None = None
    derivation: LearningAssetCompilation | None = None
    receipts: tuple[RunReceipt, ...] = Field(default=(), max_length=32)
    retention: tuple[RetentionLink, ...] = Field(default=(), max_length=256)
    # Classifications are explicit declarations on already bound populations, not proof.
    panel_designations: dict[str, Literal["iid", "adversarial"]] = Field(default_factory=dict)
    remaining_gap_references: tuple[ExperienceReference, ...] = Field(default=(), max_length=256)
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1, max_length=256)
    limitations: tuple[Text, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def bind_providers(self) -> Self:
        validate_references(self.evidence_references)
        if self.remaining_gap_references:
            validate_references(self.remaining_gap_references)
        evidence = self.training.evidence
        allowed = {
            p.population_id: "iid" if p.role == "heldout" else "adversarial"
            for p in self.training.panels
            if p.role in {"heldout", "transfer"}
        }
        if any(allowed.get(key) != value for key, value in self.panel_designations.items()):
            raise ValueError("panel designation requires the exact heldout/transfer population")
        curves = [
            curve
            for rep in evidence.replicates
            for curve in (rep.train, rep.heldout, *rep.transfer, *rep.guardrails)
            if curve is not None
        ]
        pairs = {(c.points[0].record_id, c.points[1].record_id) for c in curves}
        if any((r.acquired.record_id, r.later.record_id) not in pairs for r in self.retention):
            raise ValueError("retention must bind an exact before/after pair from this study")
        if len({r.record_id for r in self.retention}) != len(self.retention):
            raise ValueError("duplicate retention evidence")
        replicas = {r.seed: r for r in evidence.replicates}
        if len({r.seed for r in self.receipts}) != len(self.receipts):
            raise ValueError("duplicate receipt seed")
        for binding in self.receipts:
            rep = replicas.get(binding.seed)
            receipt = binding.receipt
            curve = rep.heldout if rep else None
            if (
                rep is None
                or curve is None
                or evidence.bundle is None
                or receipt.run_id != rep.manifest.run_id
                or receipt.expected_manifest != rep.manifest
                or receipt.manifest_digest != canonical_hash(rep.manifest)
                or receipt.bundle_digest != canonical_hash(evidence.bundle)
                or receipt.base_model_revision != curve.points[0].model_revision
                or receipt.checkpoint_digest != curve.points[1].model_revision
            ):
                raise ValueError("receipt does not bind exact manifest/bundle/checkpoint")
        if self.selection is not None:
            selected = {
                d.experience_id: d for d in self.selection.decisions if d.reason == "selected"
            }
            if evidence.bundle is not None:
                for row in evidence.bundle.metadata["verified_learning_lineage"]:
                    decision = selected.get(row["experience_id"])
                    if (
                        decision is None
                        or decision.role != "verified_success_candidate"
                        or decision.source_fixture_digest != row.get("fixture_digest")
                        or decision.capability_digest != evidence.capability.contract_digest
                    ):
                        raise ValueError("training lineage is not an exact selected success source")
            if self.derivation is not None and any(
                source.reference_id not in selected for source in self.derivation.sources
            ):
                raise ValueError("derivation source is not in the selected pool")
        return self


class ResourcePlan(PrivateRecord):
    """Explicit denominator scope, including measurement-unit definition (no conversions)."""

    schema_version: Literal["veritas.resource-plan.v1"] = "veritas.resource-plan.v1"
    metric: Metric
    unit: Text
    unit_definition: ExperienceReference
    stages: tuple[Stage, ...] = Field(min_length=1, max_length=5)
    seed: int | None = Field(default=None, strict=True, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def check_unit(self) -> Self:
        validate_references((self.unit_definition,))
        expected = _FIXED_UNITS.get(self.metric)
        if expected is not None and self.unit != expected:
            raise ValueError("resource unit does not match the metric")
        if self.metric in {"teacher_cost", "monetary_cost"} and not re.fullmatch(
            r"[A-Z]{3}", self.unit
        ):
            raise ValueError("monetary unit requires an explicit three-letter currency code")
        if self.metric == "equivalent_compute" and self.unit not in {"FLOP", "CPU-core-hour"}:
            raise ValueError("equivalent compute unit must be FLOP or CPU-core-hour")
        if self.metric == "training_tokens" and self.stages != ("training",):
            raise ValueError("training_tokens require exactly the training stage")
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("duplicate resource stage")
        if self.seed is not None and set(self.stages) - {"training", "evaluation"}:
            raise ValueError("shared generation/selection/derivation cannot be charged per seed")
        return self


class ResourceObservation(PrivateRecord):
    schema_version: Literal["veritas.resource-observation.v1"] = "veritas.resource-observation.v1"
    study_id: Text
    plan_id: Text
    measurement: ExperienceReference
    component_ids: tuple[Text, ...] = Field(min_length=1, max_length=2048)
    value: float | None = Field(default=None, strict=True, ge=0)
    provenance: Literal["EXTERNALLY_REPORTED", "CONSTRUCTED", "UNKNOWN"] = "UNKNOWN"
    unavailable_reason: Text | None = None

    @model_validator(mode="after")
    def observed_or_unknown(self) -> Self:
        validate_references((self.measurement,))
        if len(set(self.component_ids)) != len(self.component_ids):
            raise ValueError("duplicate observation component")
        if self.value is None:
            if self.unavailable_reason is None:
                raise ValueError("unknown resource requires an unavailable reason")
        elif self.unavailable_reason is not None or self.provenance == "UNKNOWN":
            raise ValueError("known resource requires declared provenance and no unknown reason")
        return self


def _components(
    study: EfficiencyStudy, plan: ResourcePlan
) -> tuple[tuple[str, ...], tuple[Stage, ...]]:
    values: list[str] = []
    unavailable: set[Stage] = set()
    evidence = study.training.evidence
    if plan.seed is not None and plan.seed not in evidence.expected_seeds:
        raise ValueError("resource seed is not an expected replicate")
    seeds = evidence.expected_seeds if plan.seed is None else (plan.seed,)
    reps = {r.seed: r for r in evidence.replicates}

    def add(stage: Stage, identity: str) -> None:
        values.append(stage + ":" + canonical_hash(identity))

    for stage in plan.stages:
        if stage in {"generation", "selection"}:
            if study.selection is None:
                unavailable.add(stage)
            else:
                # The commitment includes EVERY candidate/rejection and all gap-source work.
                add(stage, study.selection.record_id)
        elif stage == "derivation":
            if study.derivation is None:
                unavailable.add(stage)
            else:
                add(stage, study.derivation.record_id)
        else:
            for seed in seeds:
                rep = reps.get(seed)
                if rep is None:
                    unavailable.add(stage)
                    continue
                if stage == "training":
                    add(stage, canonical_hash(rep.manifest))
                else:
                    curves = (rep.train, rep.heldout, *rep.transfer, *rep.guardrails)
                    for curve in curves:
                        if curve is not None:
                            for point in curve.points:
                                add(stage, point.record_id)
                    if rep.learnability is not None:
                        add(stage, rep.learnability.record_id)
                    if rep.exploits is not None:
                        add(stage, rep.exploits.record_id)
                    if rep.train is None or rep.heldout is None or rep.exploits is None:
                        unavailable.add(stage)
    return tuple(sorted(set(values))), tuple(s for s in STAGES if s in unavailable)


def resource_components(study: EfficiencyStudy, plan: ResourcePlan) -> tuple[str, ...]:
    """Exact available scope commitments; missing stage identities cannot be filled by a guess."""
    return _components(study.checked(), plan.checked())[0]


class ResourceDenominator(PrivateRecord):
    plan_id: Text
    metric: Text
    unit: Text
    unit_definition: ExperienceReference
    stages: tuple[Stage, ...]
    seed: int | None
    expected_components: tuple[str, ...]
    known_components: tuple[str, ...]
    unavailable_stages: tuple[Stage, ...]
    excluded_stages: tuple[Stage, ...]
    measurement_references: tuple[ExperienceReference, ...]
    provenances: tuple[str, ...]
    duplicate_observations: int
    known_subtotal: float | None
    value: float | None
    coverage: Literal["COMPLETE_DECLARED_SCOPE", "INCOMPLETE"]
    recorded_metric_delta: float | None
    ratio: float | None
    reason: str | None
    aggregation: Literal[
        "mean_recorded_delta_per_total_resource", "seed_recorded_delta_per_resource"
    ]
    verified_efficiency: None = None


class AccountingCounts(PrivateRecord):
    raw_candidates: int | None
    selected_experiences: int | None
    rejected_experiences: int | None
    selected_not_in_training: int | None
    derived_candidates: int | None
    derivation_rejections: int | None
    training_examples: int | None
    training_tokens: None = None
    native_runtime_budget_cost: float | None
    known_native_runtime_budget_subtotal: float | None
    native_unit: Literal["native_runtime_budget_units_not_compute_or_money"] = (
        "native_runtime_budget_units_not_compute_or_money"
    )
    native_scope: Literal["entire_candidate_and_gap_execution_union_not_pipeline_compute"] = (
        "entire_candidate_and_gap_execution_union_not_pipeline_compute"
    )
    full_pipeline_accounting_complete: Literal[False] = False


class ReplicateUncertainty(PrivateRecord):
    expected_seeds: tuple[int, ...]
    observed_seeds: tuple[int, ...]
    missing_seeds: tuple[int, ...]
    unknown_seeds: tuple[int, ...]
    deltas: dict[int, float | None]
    complete: bool
    mean: float | None
    known_minimum: float | None
    known_maximum: float | None
    known_sample_standard_deviation: float | None
    confidence_interval: None = None
    interpretation: Literal["descriptive_recorded_seed_variability_not_inference"] = (
        "descriptive_recorded_seed_variability_not_inference"
    )


def _uncertainty(study: EfficiencyStudy) -> ReplicateUncertainty:
    expected = study.training.evidence.expected_seeds
    observed = tuple(sorted(r.seed for r in study.training.evidence.replicates))
    rows = {p.seed: p.delta for p in study.training.panels if p.role == "heldout"}
    deltas = {s: rows.get(s) for s in expected}
    known = [v for v in deltas.values() if v is not None]
    complete = len(known) == len(expected)
    return ReplicateUncertainty(
        expected_seeds=expected,
        observed_seeds=observed,
        missing_seeds=tuple(s for s in expected if s not in observed),
        unknown_seeds=tuple(s for s in expected if deltas[s] is None),
        deltas=deltas,
        complete=complete,
        mean=mean(known) if complete else None,
        known_minimum=min(known) if known else None,
        known_maximum=max(known) if known else None,
        known_sample_standard_deviation=stdev(known) if len(known) >= 2 else None,
    )


def _denominator(
    study: EfficiencyStudy,
    plan: ResourcePlan,
    observations: tuple[ResourceObservation, ...],
    uncertainty: ReplicateUncertainty,
) -> ResourceDenominator:
    expected, unavailable = _components(study, plan)
    unique: dict[str, ResourceObservation] = {}
    duplicate = 0
    covered: set[str] = set()
    known: set[str] = set()
    numbers: list[float] = []
    for row in observations:
        if row.plan_id != plan.record_id:
            continue
        key = row.measurement.digest
        assert key is not None  # validated full reference
        if key in unique:
            prior = unique[key]
            # Alias labels cannot create another charge for identical measurement bytes.
            if (
                prior.value != row.value
                or set(prior.component_ids) != set(row.component_ids)
                or prior.provenance != row.provenance
                or prior.unavailable_reason != row.unavailable_reason
            ):
                raise ValueError("conflicting shared measurement")
            duplicate += 1
            continue
        if set(row.component_ids) - set(expected):
            raise ValueError("resource observation includes an unexpected component")
        if covered & set(row.component_ids):
            raise ValueError("resource component overlap would double charge")
        unique[key] = row
        covered.update(row.component_ids)
        if row.value is not None:
            known.update(row.component_ids)
            numbers.append(row.value)
    complete = not unavailable and known == set(expected) and bool(expected)
    subtotal = sum(numbers) if numbers else None
    total = subtotal if complete else None
    delta = uncertainty.mean if plan.seed is None else uncertainty.deltas.get(plan.seed)
    reason = (
        "incomplete_resource_coverage"
        if total is None
        else "zero_denominator"
        if total == 0
        else "incomplete_metric_or_replicates"
        if delta is None
        else None
    )
    return ResourceDenominator(
        plan_id=plan.record_id,
        metric=plan.metric,
        unit=plan.unit,
        unit_definition=plan.unit_definition,
        stages=plan.stages,
        seed=plan.seed,
        expected_components=expected,
        known_components=tuple(sorted(known)),
        unavailable_stages=unavailable,
        excluded_stages=tuple(s for s in STAGES if s not in plan.stages),
        measurement_references=tuple(unique[k].measurement for k in sorted(unique)),
        provenances=tuple(sorted({r.provenance for r in unique.values()})),
        duplicate_observations=duplicate,
        known_subtotal=subtotal,
        value=total,
        coverage="COMPLETE_DECLARED_SCOPE" if complete else "INCOMPLETE",
        recorded_metric_delta=delta,
        ratio=delta / total if reason is None and delta is not None and total is not None else None,
        reason=reason,
        aggregation="mean_recorded_delta_per_total_resource"
        if plan.seed is None
        else "seed_recorded_delta_per_resource",
    )


def _derived_denominators(
    study: EfficiencyStudy,
    counts: AccountingCounts,
    uncertainty: ReplicateUncertainty,
) -> tuple[ResourceDenominator, ...]:
    bundle = study.training.evidence.bundle
    selection = study.selection
    specs: tuple[
        tuple[str, str, int | float | None, int | float | None, Stage, str | None, str], ...
    ] = (
        (
            "training_examples",
            "example",
            counts.training_examples,
            counts.training_examples,
            "training",
            canonical_hash(bundle) if bundle else None,
            "DERIVED_RECORD_COUNT",
        ),
        (
            "raw_candidates",
            "candidate-slot",
            counts.raw_candidates,
            counts.raw_candidates,
            "generation",
            selection.record_id if selection else None,
            "DERIVED_RECORD_COUNT",
        ),
        (
            "selected_experiences",
            "selected-slot",
            counts.selected_experiences,
            counts.selected_experiences,
            "selection",
            selection.record_id if selection else None,
            "DERIVED_RECORD_COUNT",
        ),
        (
            "native_runtime_budget",
            counts.native_unit,
            counts.native_runtime_budget_cost,
            counts.known_native_runtime_budget_subtotal,
            "generation",
            selection.record_id if selection else None,
            "FRESH_PROVIDER_NATIVE_BUDGET",
        ),
    )
    rows = []
    for metric, unit, value, subtotal, stage, identity, provenance in specs:
        reason = (
            "incomplete_resource_coverage"
            if value is None
            else "zero_denominator"
            if value == 0
            else "incomplete_metric_or_replicates"
            if uncertainty.mean is None
            else None
        )
        definition = ExperienceReference(
            reference_id="veritas.learning-efficiency.units.v1:" + metric,
            reference_type="unit_definition",
            digest=canonical_hash({"metric": metric, "unit": unit}),
            visibility=VisibilityClass.EVALUATOR_PRIVATE,
        )
        references = (
            (
                ExperienceReference(
                    reference_id=identity,
                    reference_type="provider_record",
                    digest=canonical_hash(bundle if metric == "training_examples" else selection),
                    visibility=VisibilityClass.EVALUATOR_PRIVATE,
                ),
            )
            if identity
            else ()
        )
        rows.append(
            ResourceDenominator(
                plan_id="derived:" + canonical_hash({"study": study.record_id, "metric": metric}),
                metric=metric,
                unit=unit,
                unit_definition=definition,
                stages=(stage,),
                seed=None,
                expected_components=(identity,) if identity else (),
                known_components=(identity,) if identity and value is not None else (),
                unavailable_stages=(stage,) if value is None else (),
                excluded_stages=tuple(s for s in STAGES if s != stage),
                measurement_references=references,
                provenances=(provenance,) if identity else (),
                duplicate_observations=0,
                known_subtotal=subtotal,
                value=value,
                coverage="INCOMPLETE" if value is None else "COMPLETE_DECLARED_SCOPE",
                recorded_metric_delta=uncertainty.mean,
                ratio=uncertainty.mean / value
                if reason is None and uncertainty.mean is not None and value is not None
                else None,
                reason=reason,
                aggregation="mean_recorded_delta_per_total_resource",
            )
        )
    return tuple(rows)


def _computed(
    study: EfficiencyStudy,
    plans: tuple[ResourcePlan, ...],
    observations: tuple[ResourceObservation, ...],
) -> tuple[tuple[ResourceDenominator, ...], AccountingCounts, ReplicateUncertainty, dict, dict]:
    if len({p.record_id for p in plans}) != len(plans):
        raise ValueError("duplicate resource plan")
    ids = {p.record_id for p in plans}
    if any(o.study_id != study.record_id for o in observations):
        raise ValueError("resource observation study binding mismatch")
    if any(o.plan_id not in ids for o in observations):
        raise ValueError("resource observation plan binding mismatch")
    by_plan = {p.record_id: p for p in plans}
    charges: dict[tuple, tuple] = {}
    labels: dict[tuple, str | None] = {}
    for observation in observations:
        plan = by_plan[observation.plan_id]
        basis = (plan.metric, plan.unit, plan.unit_definition.digest)
        key = (*basis, observation.measurement.digest)
        material = (
            observation.value,
            tuple(sorted(observation.component_ids)),
            observation.provenance,
            observation.unavailable_reason,
        )
        if key in charges and charges[key] != material:
            raise ValueError("shared measurement has conflicting scope or amount")
        charges[key] = material
        label = (*basis, observation.measurement.reference_id)
        if label in labels and labels[label] != observation.measurement.digest:
            raise ValueError("measurement identity rebound to different bytes")
        labels[label] = observation.measurement.digest
        if plan.metric in {
            "training_tokens",
            "teacher_tokens",
            "teacher_calls",
            "human_review_examples",
        }:
            if observation.value is not None and not observation.value.is_integer():
                raise ValueError("count resources require integer observations")
    uncertainty = _uncertainty(study)
    denominators = tuple(_denominator(study, p, observations, uncertainty) for p in plans)
    selection, derivation, bundle = (
        study.selection,
        study.derivation,
        study.training.evidence.bundle,
    )
    training_ids = (
        {r["experience_id"] for r in bundle.metadata["verified_learning_lineage"]}
        if bundle
        else set()
    )
    selected_ids = (
        {d.experience_id for d in selection.decisions if d.reason == "selected"}
        if selection
        else set()
    )
    counts = AccountingCounts(
        raw_candidates=selection.resources.pool_entries if selection else None,
        selected_experiences=selection.selected_count if selection else None,
        rejected_experiences=selection.rejected_count if selection else None,
        selected_not_in_training=len(selected_ids - training_ids) if selection and bundle else None,
        derived_candidates=len(derivation.assets) if derivation else None,
        derivation_rejections=len(derivation.rejections) if derivation else None,
        training_examples=len(bundle.train_examples) + len(bundle.preference_examples)
        if bundle
        else None,
        native_runtime_budget_cost=selection.resources.known_union_recorded_cost
        if selection and selection.resources.recorded_candidate_cost is not None
        else None,
        known_native_runtime_budget_subtotal=selection.resources.known_union_recorded_cost
        if selection
        else None,
    )
    denominators += _derived_denominators(study, counts, uncertainty)
    roles = {p.role for p in study.training.panels}
    coverage = {
        "heldout": "RECORDED" if "heldout" in roles else "UNKNOWN",
        "iid": "DECLARED" if "iid" in study.panel_designations.values() else "UNKNOWN",
        "ood": "DECLARED_STRUCTURAL_SHIFT"
        if any("STRUCTURAL_OOD" in p.transfer_classifications for p in study.training.panels)
        else "WITHIN_FAMILY_ONLY"
        if "transfer" in roles
        else "UNKNOWN",
        "adversarial": "DECLARED"
        if "adversarial" in study.panel_designations.values()
        else "UNKNOWN",
        "retention": "RECORDED" if study.retention else "UNKNOWN",
        "regression": "RECORDED" if "guardrail" in roles else "UNKNOWN",
    }
    availability = {
        metric: "COMPLETE_DECLARED_SCOPE"
        if any(d.metric == metric and d.value is not None for d in denominators)
        else "PARTIAL"
        if any(d.metric == metric and d.known_subtotal is not None for d in denominators)
        else "UNKNOWN"
        for metric in get_args(Metric)
    }
    return denominators, counts, uncertainty, coverage, availability


class LearningEfficiencyReport(PrivateRecord):
    schema_version: Literal["veritas.learning-efficiency-report.v1"] = (
        "veritas.learning-efficiency-report.v1"
    )
    study: EfficiencyStudy
    plans: tuple[ResourcePlan, ...] = Field(max_length=128)
    observations: tuple[ResourceObservation, ...] = Field(max_length=2048)
    denominators: tuple[ResourceDenominator, ...]
    counts: AccountingCounts
    uncertainty: ReplicateUncertainty
    evaluation_coverage: dict[str, str]
    resource_availability: dict[str, str]
    verified_capability_efficiency: Literal["UNKNOWN"] = "UNKNOWN"
    capability_gain: None = None
    resource_authentication: Literal["external_declarations_or_constructed_not_attested"] = (
        "external_declarations_or_constructed_not_attested"
    )
    limitation: Literal["execution_chronology_memorization_unavailable_no_efficiency_claim"] = (
        "execution_chronology_memorization_unavailable_no_efficiency_claim"
    )

    @model_validator(mode="after")
    def recompute(self) -> Self:
        if (
            self.denominators,
            self.counts,
            self.uncertainty,
            self.evaluation_coverage,
            self.resource_availability,
        ) != _computed(self.study, self.plans, self.observations):
            raise ValueError("efficiency report must match recomputed evidence arithmetic")
        return self


def _bounded(values: Iterable, limit: int) -> tuple:
    result = tuple(islice(values, limit + 1))
    if len(result) > limit:
        raise ValueError("efficiency input bound exceeded")
    return result


def _fresh_sources(
    study: EfficiencyStudy,
    *,
    selection_sources: Iterable[RecordedExperience] | None,
    gap_sources: Iterable[tuple[CounterfactualReceipt, RecordedExperience]],
    expected_selection_policy: SelectionPolicy | None,
    derivation_sources: Iterable[RecordedExperience] | None,
    derivation_receipts: Iterable[CounterfactualReceipt],
    expected_transform_policy: TransformPolicy | None,
) -> None:
    gaps = _bounded(gap_sources, 64)
    receipts = _bounded(derivation_receipts, 64)
    selected_inputs: set[str] = set()

    def source_key(source: RecordedExperience) -> str:
        return canonical_hash(
            {
                "experience": source.experience.model_dump(mode="json"),
                "companion": source.companion.model_dump(mode="json"),
                "capability": source.capability.model_dump(mode="json"),
            }
        )

    if study.selection is not None:
        if selection_sources is None or expected_selection_policy is None:
            raise ValueError("selection requires actual sources and externally expected policy")
        candidates = _bounded(selection_sources, 256)
        validate_selection(
            study.selection, candidates, gap_sources=gaps, policy=expected_selection_policy
        )
        selected_inputs = {
            d.input_digest for d in study.selection.decisions if d.reason == "selected"
        }
        selected = {
            s.experience.experience_id: s for s in candidates if source_key(s) in selected_inputs
        }
        bundle = study.training.evidence.bundle
        if bundle is not None:
            training_sources = [
                selected[row["experience_id"]]
                for row in bundle.metadata["verified_learning_lineage"]
            ]
            fresh_bundle = compile_verified_bundle(
                training_sources,
                bundle.recipe,
                registry=authorized_registry(),
                frozen_panel_task_ids=expected_selection_policy.heldout_task_ids,
                frozen_panel_source_digests=expected_selection_policy.heldout_source_digests,
            ).bundle
            if fresh_bundle != bundle:
                raise ValueError("training bundle differs from freshly admitted selected sources")
    elif selection_sources is not None or gaps:
        raise ValueError("selection sources require a selection report")
    if study.derivation is not None:
        if derivation_sources is None or expected_transform_policy is None:
            raise ValueError("derivation requires actual sources and externally expected policy")
        sources = _bounded(derivation_sources, 256)
        if study.selection is not None and any(
            source_key(s) not in selected_inputs for s in sources
        ):
            raise ValueError("derivation inputs differ from freshly selected material")
        validate_compilation(
            study.derivation,
            sources=sources,
            receipts=receipts,
            policy=expected_transform_policy,
            saturation_evidence=study.derivation.saturation_evidence,
            frozen_panel_task_ids=study.derivation.frozen_panel_task_ids,
            frozen_panel_source_digests=study.derivation.frozen_panel_source_digests,
        )
    elif derivation_sources is not None or receipts:
        raise ValueError("derivation sources require a compilation report")


def assess_efficiency(
    study: EfficiencyStudy,
    *,
    plans: Iterable[ResourcePlan] = (),
    observations: Iterable[ResourceObservation] = (),
    selection_sources: Iterable[RecordedExperience] | None = None,
    gap_sources: Iterable[tuple[CounterfactualReceipt, RecordedExperience]] = (),
    expected_selection_policy: SelectionPolicy | None = None,
    derivation_sources: Iterable[RecordedExperience] | None = None,
    derivation_receipts: Iterable[CounterfactualReceipt] = (),
    expected_transform_policy: TransformPolicy | None = None,
) -> LearningEfficiencyReport:
    study = study.checked()
    checked_plans = tuple(p.checked() for p in _bounded(plans, 128))
    checked_observations = tuple(o.checked() for o in _bounded(observations, 2048))
    _fresh_sources(
        study,
        selection_sources=selection_sources,
        gap_sources=gap_sources,
        expected_selection_policy=expected_selection_policy,
        derivation_sources=derivation_sources,
        derivation_receipts=derivation_receipts,
        expected_transform_policy=expected_transform_policy,
    )
    denominators, counts, uncertainty, coverage, availability = _computed(
        study,
        checked_plans,
        checked_observations,
    )
    return LearningEfficiencyReport(
        study=study,
        plans=checked_plans,
        observations=checked_observations,
        denominators=denominators,
        counts=counts,
        uncertainty=uncertainty,
        evaluation_coverage=coverage,
        resource_availability=availability,
    )


def validate_efficiency(
    report: LearningEfficiencyReport,
    *,
    study: EfficiencyStudy,
    plans: Iterable[ResourcePlan],
    observations: Iterable[ResourceObservation],
    **source_inputs,
) -> LearningEfficiencyReport:
    """Recompute against independently retained expected inputs, not a self-rehashed envelope."""
    checked = report.checked()
    expected = assess_efficiency(study, plans=plans, observations=observations, **source_inputs)
    if checked != expected:
        raise ValueError("report does not match expected study/resource/provider evidence")
    return expected
