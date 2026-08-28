from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.evidence import (
    EvidenceDependencyRef,
    EvidenceOutcome,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)

QUALITY_SCORECARD_VERSION = "veritas.environment-quality-scorecard.v1"


class QualityDimension(StrEnum):
    SEMANTIC_COMPLETENESS = "semantic_completeness"
    VERIFIER_PRECISION = "verifier_precision"
    VERIFIER_RECALL = "verifier_recall"
    REWARD_HACK_RESISTANCE = "reward_hack_resistance"
    RESET_DETERMINISM = "reset_determinism"
    PRIVATE_DATA_ISOLATION = "private_data_isolation"
    TASK_AMBIGUITY = "task_ambiguity"
    ARTIFACT_FIDELITY = "artifact_fidelity"
    STATE_FIDELITY = "state_fidelity"
    EXPERT_TASK_QA = "expert_task_qa"
    STRUCTURAL_DIVERSITY = "structural_diversity"
    FRONTIER_HEADROOM = "frontier_headroom"
    FAILURE_DIVERSITY = "failure_diversity"
    GENERALIZATION = "generalization"
    TRAINING_SIGNAL_DENSITY = "training_signal_density"
    RUNTIME_CONFORMANCE = "runtime_conformance"
    REPRODUCIBILITY = "reproducibility"
    PROVENANCE_COMPLETENESS = "provenance_completeness"


class QualityDimensionOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class QualityScorecardContext(BaseModel):
    """Content-bound subjects that evidence may attach to for one scorecard."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: EvidenceSubjectRef
    verifier: EvidenceSubjectRef
    portable_contract: EvidenceSubjectRef | None = None

    @model_validator(mode="after")
    def validate_subject_kinds(self) -> "QualityScorecardContext":
        if self.environment.kind != "environment":
            raise ValueError("scorecard environment subject must use kind=environment")
        if self.verifier.kind != "verifier":
            raise ValueError("scorecard verifier subject must use kind=verifier")
        if self.portable_contract and self.portable_contract.kind != "portable_contract":
            raise ValueError(
                "scorecard portable contract subject must use kind=portable_contract"
            )
        return self

    def subject_for_kind(self, kind: str) -> EvidenceSubjectRef | None:
        if kind == "environment":
            return self.environment
        if kind == "verifier":
            return self.verifier
        if kind == "portable_contract":
            return self.portable_contract
        raise ValueError(f"unsupported scorecard evidence subject kind: {kind}")


class QualityDimensionRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: QualityDimension
    subject_kind: str
    accepted_evidence_types: tuple[str, ...] = Field(min_length=1)
    minimum_records: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_rule(self) -> "QualityDimensionRule":
        if self.subject_kind not in {"environment", "verifier", "portable_contract"}:
            raise ValueError("quality dimension rule uses an unsupported subject kind")
        normalized = tuple(sorted(set(self.accepted_evidence_types)))
        if len(normalized) != len(self.accepted_evidence_types):
            raise ValueError("accepted evidence types must be unique")
        object.__setattr__(self, "accepted_evidence_types", normalized)
        return self


class QualityScorecardPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_version: str = QUALITY_SCORECARD_VERSION
    policy_id: str = ""
    rules: tuple[QualityDimensionRule, ...]

    @model_validator(mode="after")
    def validate_policy(self) -> "QualityScorecardPolicy":
        rules = tuple(sorted(self.rules, key=lambda item: item.dimension.value))
        dimensions = [item.dimension for item in rules]
        if set(dimensions) != set(QualityDimension):
            raise ValueError("quality scorecard policy must define every canonical dimension")
        if len(dimensions) != len(set(dimensions)):
            raise ValueError("quality scorecard dimensions must be unique")
        object.__setattr__(self, "rules", rules)
        payload = {
            "policy_version": self.policy_version,
            "rules": [item.model_dump(mode="json") for item in rules],
        }
        expected = f"QSCPOL-{_stable_hash(payload)[:24].upper()}"
        if self.policy_id and self.policy_id != expected:
            raise ValueError("quality scorecard policy ID does not match immutable rules")
        object.__setattr__(self, "policy_id", expected)
        return self


DEFAULT_QUALITY_SCORECARD_POLICY = QualityScorecardPolicy(
    rules=(
        QualityDimensionRule(
            dimension=QualityDimension.SEMANTIC_COMPLETENESS,
            subject_kind="environment",
            accepted_evidence_types=("qualification.semantic_completeness",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.VERIFIER_PRECISION,
            subject_kind="verifier",
            accepted_evidence_types=("qualification.verifier_precision",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.VERIFIER_RECALL,
            subject_kind="verifier",
            accepted_evidence_types=("qualification.verifier_recall",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.REWARD_HACK_RESISTANCE,
            subject_kind="verifier",
            accepted_evidence_types=("qualification.reward_hack_resistance",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.RESET_DETERMINISM,
            subject_kind="environment",
            accepted_evidence_types=("qualification.reset_determinism",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.PRIVATE_DATA_ISOLATION,
            subject_kind="environment",
            accepted_evidence_types=("qualification.private_data_isolation",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.TASK_AMBIGUITY,
            subject_kind="environment",
            accepted_evidence_types=("qualification.task_ambiguity",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.ARTIFACT_FIDELITY,
            subject_kind="environment",
            accepted_evidence_types=("qualification.artifact_fidelity",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.STATE_FIDELITY,
            subject_kind="environment",
            accepted_evidence_types=("qualification.state_fidelity",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.EXPERT_TASK_QA,
            subject_kind="environment",
            accepted_evidence_types=("qualification.task_qa",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.STRUCTURAL_DIVERSITY,
            subject_kind="environment",
            accepted_evidence_types=("qualification.structural_diversity",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.FRONTIER_HEADROOM,
            subject_kind="environment",
            accepted_evidence_types=("qualification.frontier_headroom",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.FAILURE_DIVERSITY,
            subject_kind="environment",
            accepted_evidence_types=("qualification.failure_diversity",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.GENERALIZATION,
            subject_kind="environment",
            accepted_evidence_types=("qualification.generalization",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.TRAINING_SIGNAL_DENSITY,
            subject_kind="environment",
            accepted_evidence_types=("qualification.training_signal_density",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.RUNTIME_CONFORMANCE,
            subject_kind="portable_contract",
            accepted_evidence_types=("conformance.adapter",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.REPRODUCIBILITY,
            subject_kind="environment",
            accepted_evidence_types=("qualification.reproducibility",),
        ),
        QualityDimensionRule(
            dimension=QualityDimension.PROVENANCE_COMPLETENESS,
            subject_kind="environment",
            accepted_evidence_types=("qualification.provenance_completeness",),
        ),
    )
)


class QualityDimensionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: QualityDimension
    outcome: QualityDimensionOutcome
    evidence: tuple[EvidenceDependencyRef, ...]
    accepted_evidence_types: tuple[str, ...]
    minimum_records: int
    observed_records: int
    detail: str = ""


class EnvironmentQualityScorecard(BaseModel):
    """Multidimensional evidence view; not a replacement for maturity qualification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scorecard_version: str = QUALITY_SCORECARD_VERSION
    scorecard_id: str = ""
    scorecard_content_sha256: str = ""
    policy_id: str
    policy_version: str
    context: QualityScorecardContext
    dimensions: tuple[QualityDimensionAssessment, ...]

    @model_validator(mode="after")
    def validate_scorecard(self) -> "EnvironmentQualityScorecard":
        if self.scorecard_version != QUALITY_SCORECARD_VERSION:
            raise ValueError("unsupported environment quality scorecard version")
        dimensions = tuple(sorted(self.dimensions, key=lambda item: item.dimension.value))
        if set(item.dimension for item in dimensions) != set(QualityDimension):
            raise ValueError("quality scorecard must contain every canonical dimension")
        if len(dimensions) != len({item.dimension for item in dimensions}):
            raise ValueError("quality scorecard dimensions must be unique")
        object.__setattr__(self, "dimensions", dimensions)
        payload = self.model_dump(
            mode="json", exclude={"scorecard_id", "scorecard_content_sha256"}
        )
        digest = _stable_hash(payload)
        identifier = f"QSCORE-{digest[:24].upper()}"
        if self.scorecard_content_sha256 and self.scorecard_content_sha256 != digest:
            raise ValueError("quality scorecard digest does not match immutable contents")
        if self.scorecard_id and self.scorecard_id != identifier:
            raise ValueError("quality scorecard ID does not match immutable contents")
        object.__setattr__(self, "scorecard_content_sha256", digest)
        object.__setattr__(self, "scorecard_id", identifier)
        return self

    @property
    def failed_dimensions(self) -> tuple[QualityDimension, ...]:
        return tuple(
            item.dimension
            for item in self.dimensions
            if item.outcome == QualityDimensionOutcome.FAIL
        )

    @property
    def unknown_dimensions(self) -> tuple[QualityDimension, ...]:
        return tuple(
            item.dimension
            for item in self.dimensions
            if item.outcome == QualityDimensionOutcome.UNKNOWN
        )

    @property
    def complete(self) -> bool:
        return not self.unknown_dimensions


def _record_matches_subject(record: EvidenceRecord, subject: EvidenceSubjectRef) -> bool:
    return any(item == subject for item in record.subjects)


def _dimension_outcome(records: tuple[EvidenceRecord, ...]) -> QualityDimensionOutcome:
    if any(record.outcome == EvidenceOutcome.FAIL for record in records):
        return QualityDimensionOutcome.FAIL
    if any(
        record.outcome in {EvidenceOutcome.UNKNOWN, EvidenceOutcome.OBSERVED}
        for record in records
    ):
        return QualityDimensionOutcome.UNKNOWN
    return QualityDimensionOutcome.PASS


def build_environment_quality_scorecard(
    *,
    context: QualityScorecardContext,
    evidence: Iterable[EvidenceRecord],
    policy: QualityScorecardPolicy = DEFAULT_QUALITY_SCORECARD_POLICY,
    public_only: bool = False,
) -> EnvironmentQualityScorecard:
    """Build a scorecard without averaging dimensions into a scalar quality score."""

    records = tuple(evidence)
    assessments: list[QualityDimensionAssessment] = []
    for rule in policy.rules:
        subject = context.subject_for_kind(rule.subject_kind)
        if subject is None:
            assessments.append(
                QualityDimensionAssessment(
                    dimension=rule.dimension,
                    outcome=QualityDimensionOutcome.UNKNOWN,
                    evidence=(),
                    accepted_evidence_types=rule.accepted_evidence_types,
                    minimum_records=rule.minimum_records,
                    observed_records=0,
                    detail=f"required {rule.subject_kind} identity is unavailable",
                )
            )
            continue
        matching = tuple(
            record
            for record in records
            if record.evidence_type in rule.accepted_evidence_types
            and _record_matches_subject(record, subject)
            and (not public_only or record.visibility == EvidenceVisibility.PUBLIC)
        )
        if len(matching) < rule.minimum_records:
            outcome = QualityDimensionOutcome.UNKNOWN
            detail = "required evidence is missing or not visible in this projection"
        else:
            outcome = _dimension_outcome(matching)
            detail = ""
        dependencies = tuple(
            record.dependency_ref(relation=f"quality_dimension:{rule.dimension.value}")
            for record in sorted(matching, key=lambda item: item.evidence_id)
        )
        assessments.append(
            QualityDimensionAssessment(
                dimension=rule.dimension,
                outcome=outcome,
                evidence=dependencies,
                accepted_evidence_types=rule.accepted_evidence_types,
                minimum_records=rule.minimum_records,
                observed_records=len(matching),
                detail=detail,
            )
        )
    return EnvironmentQualityScorecard(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        context=context,
        dimensions=tuple(assessments),
    )
