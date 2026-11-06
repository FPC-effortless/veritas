"""Bounded stateful research receipts, not a model runner or qualification provider.

The exact planned matrix and CAP populations are supplied independently. Imported
observations, lifecycle checks and hardware-specific resources remain declarations;
neither complete arithmetic nor consistent hashes authenticate model execution.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, model_validator

from investigation_world.capability_science import EvaluationPoint, EvaluationPopulation
from investigation_world.capability_science.core import ScienceRecord, Text, validate_references
from investigation_world.evidence.models import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)
from investigation_world.experience import ExperienceReference
from investigation_world.trajectory import VisibilityClass, canonical_hash

Provenance = Literal["EXTERNALLY_REPORTED", "CONSTRUCTED", "UNKNOWN"]
Family = Literal[
    "psn",
    "bounded_field",
    "usef_x",
    "atlas_cassa",
    "psn2",
    "dpsl",
    "nsf_nfd",
    "constructed",
]
RunStatus = Literal[
    "completed",
    "failed",
    "not_run",
    "unknown",
    "preflight_failed",
    "incomplete_budget",
    "source_blocked",
]


def _reject_sealed(value: Any) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        if value.get("visibility") in (VisibilityClass.SEALED, EvidenceVisibility.SEALED):
            raise ValueError("sealed evidence is not accepted by this research adapter")
        for child in value.values():
            _reject_sealed(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            _reject_sealed(child)


class PrivateRecord(ScienceRecord):
    model_config = ConfigDict(hide_input_in_errors=True)
    visibility: Literal[VisibilityClass.EVALUATOR_PRIVATE] = VisibilityClass.EVALUATOR_PRIVATE

    @model_validator(mode="before")
    @classmethod
    def no_sealed(cls, value: Any) -> Any:
        _reject_sealed(value)
        return value


class RunManifest(PrivateRecord):
    schema_version: Literal["veritas.stateful-manifest.v1"] = "veritas.stateful-manifest.v1"
    family: Family
    arm: Text
    condition: Text
    init_seed: int = Field(strict=True, ge=0, le=2**32 - 1)
    data_seed: int = Field(strict=True, ge=0, le=2**32 - 1)
    model_id: Text
    source_revision: Text
    source_provenance: Provenance
    protocol: ExperienceReference
    source: ExperienceReference
    configuration: ExperienceReference
    checkpoint: ExperienceReference
    stream: ExperienceReference
    adapter: ExperienceReference
    evaluator: ExperienceReference
    runtime: ExperienceReference
    exact_population: EvaluationPopulation | None = None
    criterion_population: EvaluationPopulation | None = None
    exact_unavailable_reason: Text | None = None
    criterion_unavailable_reason: Text | None = None

    @model_validator(mode="after")
    def bind_expectations(self) -> Self:
        validate_references(
            tuple(
                getattr(self, name)
                for name in (
                    "protocol",
                    "source",
                    "configuration",
                    "checkpoint",
                    "stream",
                    "adapter",
                    "evaluator",
                    "runtime",
                )
            )
        )
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_revision) and not (
            self.source_provenance == "CONSTRUCTED"
            and self.source_revision.startswith("constructed-")
        ):
            raise ValueError(
                "source revision requires a full commit or explicit constructed version"
            )
        if self.model_id.casefold() in {"unknown", "main", "latest", "head"}:
            raise ValueError("pinned model identity required")
        for panel, reason, metric in (
            (self.exact_population, self.exact_unavailable_reason, "success_fraction"),
            (self.criterion_population, self.criterion_unavailable_reason, "criterion_score"),
        ):
            if panel is None:
                if reason is None:
                    raise ValueError(
                        "absent metric requires an explicit applicability/unknown reason"
                    )
            elif reason is not None or panel.conditions.metric != metric:
                raise ValueError("planned metric semantics conflict")
            elif len(panel.members) > 4096:
                raise ValueError("research population exceeds bounded 4096 members")
        if self.exact_population is None and self.criterion_population is None:
            raise ValueError("at least one planned metric population required")
        if self.exact_population is not None and self.criterion_population is not None:
            a, b = self.exact_population, self.criterion_population
            if (
                a.members != b.members
                or a.capability != b.capability
                or a.split != b.split
                or a.conditions.model_dump(
                    exclude={"record_id", "metric", "metric_definition_digest"}
                )
                != b.conditions.model_dump(
                    exclude={"record_id", "metric", "metric_definition_digest"}
                )
            ):
                raise ValueError("exact and criterion populations must share cases and conditions")
        return self

    @property
    def cell(self) -> tuple[str, str, str, int, int]:
        return self.family, self.arm, self.condition, self.init_seed, self.data_seed

    @property
    def population(self) -> EvaluationPopulation:
        panel = self.exact_population or self.criterion_population
        assert panel is not None  # Validated above, not a qualification assumption.
        return panel


class StateComponent(PrivateRecord):
    component_id: Text
    owner_id: Text
    scope: Literal["transient", "adaptive", "shared", "optimizer", "rng"]
    owner_scope: Literal["per_stream", "shared"] = "per_stream"
    bytes: int | None = Field(default=None, strict=True, ge=0)
    reason: Text | None = None
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def observation(self) -> Self:
        validate_references(self.evidence_references)
        if (self.bytes is None) != (self.reason is not None):
            raise ValueError("unknown component size needs a reason, known size cannot have one")
        return self


class StateCheck(PrivateRecord):
    kind: Literal[
        "reset",
        "restart",
        "query_erasure",
        "retrained_removal",
        "frozen_plasticity",
        "stream_isolation",
        "snapshot_ownership",
        "predict_before_feedback",
    ]
    component_ids: tuple[Text, ...] = Field(default=(), max_length=64)
    status: Literal["OBSERVED", "UNKNOWN", "NOT_RUN"] = "UNKNOWN"
    provenance: Provenance = "UNKNOWN"
    passed: bool | None = Field(default=None, strict=True)
    detail: Text
    evidence_references: tuple[ExperienceReference, ...] = Field(default=(), max_length=64)

    @model_validator(mode="after")
    def observation(self) -> Self:
        if len(self.component_ids) != len(set(self.component_ids)):
            raise ValueError("duplicate state component scope")
        if self.kind != "predict_before_feedback" and not self.component_ids:
            raise ValueError("state intervention requires explicit component scope")
        if self.evidence_references:
            validate_references(self.evidence_references)
        if self.status == "OBSERVED":
            if self.provenance == "UNKNOWN" or not self.evidence_references:
                raise ValueError("observed state check requires provenance and evidence")
        elif self.passed is not None:
            raise ValueError("unobserved check cannot supply a fixture result")
        return self


class TimingContext(PrivateRecord):
    method: Text
    hardware: Text
    runtime: ExperienceReference
    import_path: Text
    imported_source: ExperienceReference
    import_evidence: ExperienceReference
    threads: int = Field(strict=True, ge=1)
    batch_size: int = Field(strict=True, ge=1)
    stream_steps: int = Field(strict=True, ge=1)
    warmups: int = Field(strict=True, ge=0)
    repetitions: int = Field(strict=True, ge=1)
    boundary: Text
    samples: ExperienceReference

    @model_validator(mode="after")
    def evidence(self) -> Self:
        validate_references(
            (
                self.runtime,
                self.imported_source,
                self.import_evidence,
                self.samples,
            )
        )
        return self


class ResourceMeasurement(PrivateRecord):
    metric: Literal[
        "latency_p50",
        "latency_p95",
        "state_bytes",
        "peak_memory_bytes",
        "parameters",
        "cpu_core_seconds",
        "flops",
        "energy_joules",
    ]
    unit: Literal["second", "byte", "count", "CPU-core-second", "FLOP", "joule"]
    scope: Text
    value: float | None = Field(default=None, strict=True, ge=0)
    reason: Text | None = None
    provenance: Provenance = "UNKNOWN"
    measurement: ExperienceReference
    timing: TimingContext | None = None

    @model_validator(mode="after")
    def observation(self) -> Self:
        validate_references((self.measurement,))
        latency = self.metric.startswith("latency_")
        expected = {
            "latency_p50": "second",
            "latency_p95": "second",
            "parameters": "count",
            "state_bytes": "byte",
            "peak_memory_bytes": "byte",
            "cpu_core_seconds": "CPU-core-second",
            "flops": "FLOP",
            "energy_joules": "joule",
        }[self.metric]
        if self.unit != expected:
            raise ValueError("resource unit does not match metric; conversions are not supported")
        if self.value is None:
            if self.reason is None:
                raise ValueError("unknown resource requires a reason")
        elif self.reason is not None or self.provenance == "UNKNOWN":
            raise ValueError("observed resource requires provenance and no unknown reason")
        elif latency and self.timing is None:
            raise ValueError("latency quantile requires complete measurement context")
        elif self.metric in {"state_bytes", "peak_memory_bytes", "parameters", "flops"} and (
            not self.value.is_integer()
        ):
            raise ValueError("byte and parameter counts must be integral")
        if not latency and self.timing is not None:
            raise ValueError("timing context does not measure memory or parameter counts")
        return self


class ImportedRun(PrivateRecord):
    schema_version: Literal["veritas.stateful-receipt.v1"] = "veritas.stateful-receipt.v1"
    manifest: RunManifest
    status: RunStatus
    reason: Text | None = None
    provenance: Provenance = "UNKNOWN"
    exact: EvaluationPoint | None = None
    criterion: EvaluationPoint | None = None
    native_acceptance: dict[str, StrictBool | None] | None = None
    policy_acceptance: dict[str, StrictBool | None] | None = None
    policy: ExperienceReference | None = None
    components: tuple[StateComponent, ...] = Field(default=(), max_length=64)
    checks: tuple[StateCheck, ...] = Field(default=(), max_length=128)
    resources: tuple[ResourceMeasurement, ...] = Field(default=(), max_length=128)
    evidence_references: tuple[ExperienceReference, ...] = Field(min_length=1, max_length=128)
    actual_import_verified: Literal["UNKNOWN"] = "UNKNOWN"
    execution_attestation: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def bind_observations(self) -> Self:
        validate_references(self.evidence_references)
        if self.status == "completed":
            if self.reason is not None or self.provenance == "UNKNOWN":
                raise ValueError(
                    "completed receipt needs declared provenance and no failure reason"
                )
        elif self.reason is None:
            raise ValueError("noncompleted receipt requires an explicit reason")
        for point, panel in (
            (self.exact, self.manifest.exact_population),
            (self.criterion, self.manifest.criterion_population),
        ):
            if point is None:
                if panel is not None and self.status == "completed":
                    raise ValueError("completed receipt must retain every planned metric")
            elif (
                panel is None
                or point.population != panel
                or (
                    point.model_id != self.manifest.model_id
                    or point.model_revision != self.manifest.checkpoint.digest
                )
            ):
                raise ValueError("observation does not bind planned population/model/checkpoint")
        members = {m.reference_id for m in self.manifest.population.members}
        for mask in (self.native_acceptance, self.policy_acceptance):
            if mask is not None and (
                set(mask) != members
                or any(type(value) is not bool and value is not None for value in mask.values())
            ):
                raise ValueError(
                    "acceptance mask must cover every planned member with bool/unknown"
                )
        if self.policy is not None:
            validate_references((self.policy,))
        if (self.policy_acceptance is None) != (self.policy is None):
            raise ValueError("policy mask and exact policy identity must be supplied together")
        component_ids = [component.component_id for component in self.components]
        if len(component_ids) != len(set(component_ids)) or any(
            set(check.component_ids) - set(component_ids) for check in self.checks
        ):
            raise ValueError("state checks require unique explicitly owned components")
        references: dict[str, str | None] = {}
        metrics = set()
        for resource in self.resources:
            identity, digest = resource.measurement.reference_id, resource.measurement.digest
            if identity in references and references[identity] != digest:
                raise ValueError("one resource artifact identity cannot name different content")
            references[identity] = digest
            key = (resource.metric, resource.scope, digest)
            if key in metrics:
                raise ValueError("duplicate resource metric/scope observations are not additive")
            metrics.add(key)
        if any(
            r.timing is not None and r.timing.runtime != self.manifest.runtime
            for r in self.resources
        ):
            raise ValueError("timing runtime differs from pinned run runtime")
        if any(
            r.timing is not None and r.timing.imported_source != self.manifest.source
            for r in self.resources
        ):
            raise ValueError("timed imported implementation differs from pinned run source")
        return self


class StatefulStudy(PrivateRecord):
    schema_version: Literal["veritas.stateful-study.v1"] = "veritas.stateful-study.v1"
    expected: tuple[RunManifest, ...] = Field(min_length=1, max_length=512)
    runs: tuple[ImportedRun, ...] = Field(default=(), max_length=512)

    @model_validator(mode="after")
    def exact_matrix(self) -> Self:
        cells = [manifest.cell for manifest in self.expected]
        ids = {manifest.record_id for manifest in self.expected}
        observed = [run.manifest.record_id for run in self.runs]
        if len(cells) != len(set(cells)):
            raise ValueError("duplicate expected family/arm/condition/seed cell")
        if len(observed) != len(set(observed)) or set(observed) - ids:
            raise ValueError(
                "observed run is duplicated or outside the independently expected matrix"
            )
        return self


class SelectionSummary(PrivateRecord):
    total: int
    accepted: int
    rejected: int
    unknown: int
    coverage: float | None
    accepted_exact: float | None
    accepted_exact_error: float | None
    accepted_criterion: float | None


class RunSummary(PrivateRecord):
    manifest_id: Text
    status: RunStatus | Literal["missing"]
    reason: str | None
    population_size: int
    exact_mean: float | None
    criterion_mean: float | None
    exact_unknown: int | None
    criterion_unknown: int | None
    native: SelectionSummary | None
    policy: SelectionSummary | None


def _selected(
    run: ImportedRun,
    mask: dict[str, bool | None] | None,
) -> SelectionSummary | None:
    if mask is None:
        return None
    accepted = {member for member, value in mask.items() if value is True}
    unknown = sum(value is None for value in mask.values())

    def score(point: EvaluationPoint | None) -> float | None:
        if unknown or not accepted or point is None:
            return None
        values = [row.value for row in point.outcomes if row.member_id in accepted]
        return (
            None
            if any(v is None for v in values)
            else sum(v for v in values if v is not None) / len(values)
        )

    exact = score(run.exact)
    return SelectionSummary(
        total=len(mask),
        accepted=len(accepted),
        rejected=len(mask) - len(accepted) - unknown,
        unknown=unknown,
        coverage=None if unknown else len(accepted) / len(mask),
        accepted_exact=exact,
        accepted_exact_error=None if exact is None else 1 - exact,
        accepted_criterion=score(run.criterion),
    )


def _rows(study: StatefulStudy) -> tuple[RunSummary, ...]:
    observed = {run.manifest.record_id: run for run in study.runs}

    def unknown(point: EvaluationPoint | None, panel: EvaluationPopulation | None) -> int | None:
        if panel is None:
            return None
        return (
            len(panel.members)
            if point is None
            else sum(row.value is None for row in point.outcomes)
        )

    return tuple(
        RunSummary(
            manifest_id=manifest.record_id,
            status=run.status if run else "missing",
            reason=run.reason if run else "expected run has no supplied receipt",
            population_size=len(manifest.population.members),
            exact_mean=run.exact.recorded_mean if run and run.exact else None,
            criterion_mean=run.criterion.recorded_mean if run and run.criterion else None,
            exact_unknown=unknown(run.exact if run else None, manifest.exact_population),
            criterion_unknown=unknown(
                run.criterion if run else None, manifest.criterion_population
            ),
            native=_selected(run, run.native_acceptance) if run else None,
            policy=_selected(run, run.policy_acceptance) if run else None,
        )
        for manifest in study.expected
        for run in (observed.get(manifest.record_id),)
    )


class StatefulReport(PrivateRecord):
    schema_version: Literal["veritas.stateful-report.v1"] = "veritas.stateful-report.v1"
    study: StatefulStudy
    rows: tuple[RunSummary, ...]
    expected_runs: int
    completed_runs: int
    missing_runs: int
    complete_matrix: bool = Field(
        description="All planned receipts completed; does not mean every case score is known."
    )
    execution_attestation: Literal["UNKNOWN"] = "UNKNOWN"
    actual_import_verified: Literal["UNKNOWN"] = "UNKNOWN"
    causal_qualification: Literal["UNKNOWN"] = "UNKNOWN"
    scientific_qualification: Literal["UNKNOWN"] = "UNKNOWN"
    frontier_qualification: Literal["UNKNOWN"] = "UNKNOWN"
    capability_gain: None = None
    maturity_promotion: Literal[False] = False

    @model_validator(mode="after")
    def recompute(self) -> Self:
        rows = _rows(self.study)
        completed = sum(row.status == "completed" for row in rows)
        missing = sum(row.status == "missing" for row in rows)
        if self.rows != rows or (
            self.expected_runs,
            self.completed_runs,
            self.missing_runs,
            self.complete_matrix,
        ) != (len(rows), completed, missing, completed == len(rows)):
            raise ValueError("report must equal recomputed complete-matrix observations")
        return self


def assess_stateful(study: StatefulStudy) -> StatefulReport:
    """Reparse all evidence; report each planned cell without pooled leaderboard claims."""
    study = study.checked()
    rows = _rows(study)
    completed = sum(row.status == "completed" for row in rows)
    return StatefulReport(
        study=study,
        rows=rows,
        expected_runs=len(rows),
        completed_runs=completed,
        missing_runs=sum(row.status == "missing" for row in rows),
        complete_matrix=completed == len(rows),
    )


def shared_stateful_evidence(
    report: StatefulReport,
    *,
    observed_at: datetime,
    producer: ExperienceReference,
) -> EvidenceRecord:
    """Emit only a private OBSERVED envelope; no qualification or execution claim."""
    checked = report.checked()
    validate_references((producer,))
    _reject_sealed(producer)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observation time requires a timezone")
    digest = canonical_hash(checked.model_dump(mode="json"))
    return EvidenceRecord(
        evidence_type="stateful.research.receipt",
        outcome=EvidenceOutcome.OBSERVED,
        visibility=EvidenceVisibility.OPERATOR_PRIVATE,
        claim="Descriptive supplied stateful receipts; no execution attestation or qualification.",
        subjects=(
            EvidenceSubjectRef(
                kind="stateful.report",
                subject_id=checked.record_id,
                content_sha256=digest,
            ),
        ),
        producer=EvidenceProducerRef(
            producer_id=producer.reference_id,
            producer_version=producer.digest or "",
            content_sha256=producer.digest or "",
        ),
        artifacts=(
            EvidenceArtifactRef(
                artifact_id=checked.record_id,
                role="descriptive_report",
                content_sha256=digest,
                media_type="application/json",
            ),
        ),
        observed_at=observed_at,
        provenance={"scope": "supplied_records_only", "execution_attestation": "UNKNOWN"},
    )
